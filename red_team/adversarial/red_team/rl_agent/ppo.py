"""
Pure-NumPy PPO — actor-critic over the AttackEnv.

The adversarial engine is deliberately torch-free (the deployment removed
PyTorch); rather than reintroduce it for one trainer, this is a small,
self-contained PPO with a two-layer tanh MLP trunk and actor/critic heads, hand-
derived backprop, and an Adam optimiser. It is faithful to PPO (clipped surrogate,
GAE(λ), entropy bonus, value loss) and to the codebase's pure-NumPy discipline.

Everything is seeded (NumPy Generator) so a run reproduces — the same contract the
GA earned with blake2b genome seeds.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


# ── numerics ────────────────────────────────────────────────────────────────────
def _log_softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=-1, keepdims=True)
    return z - np.log(np.exp(z).sum(axis=-1, keepdims=True))


def _softmax(z: np.ndarray) -> np.ndarray:
    e = np.exp(z - z.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


@dataclass
class PPOConfig:
    hidden: int = 64
    lr: float = 3e-4
    clip: float = 0.2
    gamma: float = 0.99
    gae_lambda: float = 0.95
    entropy_coef: float = 0.01
    vf_coef: float = 0.5
    epochs: int = 4
    minibatch: int = 64
    rollout_steps: int = 256       # transitions collected per env per update
    max_grad_norm: float = 1.0
    seed: int = 0


class MLPActorCritic:
    """Shared tanh trunk → (policy logits, state value). NumPy params + Adam."""

    def __init__(self, in_dim: int, n_actions: int, hidden: int, rng: np.random.Generator):
        def glorot(a, b):
            return rng.standard_normal((a, b)) * np.sqrt(2.0 / (a + b))
        self.p = {
            "W1": glorot(in_dim, hidden), "b1": np.zeros(hidden),
            "W2": glorot(hidden, hidden), "b2": np.zeros(hidden),
            "Wp": glorot(hidden, n_actions) * 0.1, "bp": np.zeros(n_actions),
            "Wv": glorot(hidden, 1) * 0.1, "bv": np.zeros(1),
        }
        # Adam state
        self._m = {k: np.zeros_like(v) for k, v in self.p.items()}
        self._v = {k: np.zeros_like(v) for k, v in self.p.items()}
        self._t = 0

    # forward, returns (logits, value, cache)
    def forward(self, x: np.ndarray):
        z1 = x @ self.p["W1"] + self.p["b1"]; h1 = np.tanh(z1)
        z2 = h1 @ self.p["W2"] + self.p["b2"]; h2 = np.tanh(z2)
        logits = h2 @ self.p["Wp"] + self.p["bp"]
        value = (h2 @ self.p["Wv"] + self.p["bv"])[:, 0]
        return logits, value, (x, h1, h2)

    def backward(self, cache, dlogits: np.ndarray, dvalue: np.ndarray) -> dict:
        x, h1, h2 = cache
        g = {}
        g["Wp"] = h2.T @ dlogits; g["bp"] = dlogits.sum(0)
        dv = dvalue[:, None]
        g["Wv"] = h2.T @ dv; g["bv"] = dv.sum(0)
        dh2 = dlogits @ self.p["Wp"].T + dv @ self.p["Wv"].T
        dz2 = dh2 * (1.0 - h2 ** 2)
        g["W2"] = h1.T @ dz2; g["b2"] = dz2.sum(0)
        dh1 = dz2 @ self.p["W2"].T
        dz1 = dh1 * (1.0 - h1 ** 2)
        g["W1"] = x.T @ dz1; g["b1"] = dz1.sum(0)
        return g

    def adam_step(self, grads: dict, lr: float, max_norm: float,
                  b1: float = 0.9, b2: float = 0.999, eps: float = 1e-8) -> None:
        # global grad-norm clip
        total = np.sqrt(sum(float((g ** 2).sum()) for g in grads.values())) + 1e-12
        scale = min(1.0, max_norm / total)
        self._t += 1
        for k, g in grads.items():
            g = g * scale
            self._m[k] = b1 * self._m[k] + (1 - b1) * g
            self._v[k] = b2 * self._v[k] + (1 - b2) * (g * g)
            mhat = self._m[k] / (1 - b1 ** self._t)
            vhat = self._v[k] / (1 - b2 ** self._t)
            self.p[k] -= lr * mhat / (np.sqrt(vhat) + eps)


@dataclass
class Rollout:
    states: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    logps: list = field(default_factory=list)
    rewards: list = field(default_factory=list)
    values: list = field(default_factory=list)
    dones: list = field(default_factory=list)


class PPO:
    """PPO trainer driving a set of AttackEnv instances (one trajectory each)."""

    def __init__(self, envs: list, cfg: PPOConfig | None = None):
        self.envs = envs
        self.cfg = cfg or PPOConfig()
        self.rng = np.random.default_rng(self.cfg.seed)
        in_dim = envs[0].state_dim
        n_actions = envs[0].n_actions
        self.net = MLPActorCritic(in_dim, n_actions, self.cfg.hidden, self.rng)
        self._cur = [e.reset() for e in envs]
        self.history: list[dict] = []

    # ── act ──────────────────────────────────────────────────────────────────────
    def _policy(self, states: np.ndarray):
        logits, value, _ = self.net.forward(states)
        logp = _log_softmax(logits)
        probs = np.exp(logp)
        # sample one action per row
        acts = np.array([self.rng.choice(len(p), p=p) for p in probs])
        chosen_logp = logp[np.arange(len(acts)), acts]
        return acts, chosen_logp, value

    def greedy_action(self, state: np.ndarray) -> int:
        logits, _, _ = self.net.forward(state[None, :])
        return int(logits[0].argmax())

    def sample_action(self, state: np.ndarray) -> int:
        logits, _, _ = self.net.forward(state[None, :])
        p = np.exp(_log_softmax(logits))[0]
        return int(self.rng.choice(len(p), p=p))

    # ── collect one rollout across all envs ──────────────────────────────────────
    def collect(self) -> tuple[list[Rollout], list, dict]:
        rolls = [Rollout() for _ in self.envs]
        ep_returns: list[float] = []
        ep_evaded = 0
        ep_count = 0
        run_ret = [0.0] * len(self.envs)
        for _ in range(self.cfg.rollout_steps):
            states = np.stack(self._cur)
            acts, logps, vals = self._policy(states)
            for i, env in enumerate(self.envs):
                res = env.step(int(acts[i]))
                r = rolls[i]
                r.states.append(self._cur[i]); r.actions.append(int(acts[i]))
                r.logps.append(float(logps[i])); r.rewards.append(res.reward)
                r.values.append(float(vals[i])); r.dones.append(res.done)
                run_ret[i] += res.reward
                if res.done:
                    ep_returns.append(run_ret[i]); run_ret[i] = 0.0
                    ep_count += 1
                    ep_evaded += 1 if res.info.get("evaded") else 0
                    self._cur[i] = env.reset()
                else:
                    self._cur[i] = res.state
        # bootstrap value for the unfinished tail
        last_vals = self.net.forward(np.stack(self._cur))[1]
        stats = {"episodes": ep_count,
                 "evaded": ep_evaded,
                 "train_asr": (ep_evaded / ep_count) if ep_count else 0.0,
                 "mean_return": float(np.mean(ep_returns)) if ep_returns else 0.0}
        return rolls, list(last_vals), stats

    # ── GAE per trajectory ───────────────────────────────────────────────────────
    def _gae(self, r: Rollout, last_v: float):
        c = self.cfg
        rew = np.asarray(r.rewards); val = np.asarray(r.values)
        done = np.asarray(r.dones, dtype=np.float64)
        adv = np.zeros_like(rew); gae = 0.0
        for t in reversed(range(len(rew))):
            next_v = last_v if t == len(rew) - 1 else val[t + 1]
            next_nonterm = 1.0 - done[t]
            delta = rew[t] + c.gamma * next_v * next_nonterm - val[t]
            gae = delta + c.gamma * c.gae_lambda * next_nonterm * gae
            adv[t] = gae
        ret = adv + val
        return adv, ret

    # ── one PPO update ────────────────────────────────────────────────────────────
    def update(self) -> dict:
        rolls, last_vals, stats = self.collect()
        S, A, LP, ADV, RET = [], [], [], [], []
        for r, lv in zip(rolls, last_vals):
            if not r.rewards:
                continue
            adv, ret = self._gae(r, lv)
            S.append(np.asarray(r.states)); A.append(np.asarray(r.actions))
            LP.append(np.asarray(r.logps)); ADV.append(adv); RET.append(ret)
        S = np.concatenate(S); A = np.concatenate(A)
        LP = np.concatenate(LP); ADV = np.concatenate(ADV); RET = np.concatenate(RET)
        ADV = (ADV - ADV.mean()) / (ADV.std() + 1e-8)

        cfg = self.cfg
        n = len(S)
        idx = np.arange(n)
        ploss = vloss = ent = 0.0
        for _ in range(cfg.epochs):
            self.rng.shuffle(idx)
            for start in range(0, n, cfg.minibatch):
                mb = idx[start:start + cfg.minibatch]
                ploss, vloss, ent = self._step(S[mb], A[mb], LP[mb], ADV[mb], RET[mb])
        stats.update(policy_loss=ploss, value_loss=vloss, entropy=ent)
        self.history.append(stats)
        return stats

    def _step(self, s, a, old_lp, adv, ret) -> tuple[float, float, float]:
        cfg = self.cfg
        B = len(s)
        logits, value, cache = self.net.forward(s)
        logp_all = _log_softmax(logits)
        p = np.exp(logp_all)
        rows = np.arange(B)
        logp = logp_all[rows, a]
        ratio = np.exp(logp - old_lp)
        clipped = np.clip(ratio, 1 - cfg.clip, 1 + cfg.clip)
        obj = np.minimum(ratio * adv, clipped * adv)
        # gradient mask: derivative = ratio*adv on the active (unclamped) branch
        active = (ratio * adv <= clipped * adv) | ((ratio >= 1 - cfg.clip) & (ratio <= 1 + cfg.clip))
        d_obj_d_logp = np.where(active, ratio * adv, 0.0)
        d_policy_d_logp = -(1.0 / B) * d_obj_d_logp           # minimise -obj

        # dlogits from policy: d_logp/d_logits = onehot(a) - p
        dlogits = (-p) * d_policy_d_logp[:, None]
        dlogits[rows, a] += d_policy_d_logp

        # entropy bonus: H_b = -sum p logp ; dH/dlogits_k = -p_k (logp_k + H_b)
        H = -(p * logp_all).sum(axis=1)
        dent = -p * (logp_all + H[:, None])                    # dH/dlogits
        dlogits += cfg.entropy_coef * (1.0 / B) * (-dent)      # loss = -ent_coef*H

        # value loss = vf_coef * mean (value-ret)^2
        dvalue = cfg.vf_coef * (2.0 / B) * (value - ret)

        grads = self.net.backward(cache, dlogits, dvalue)
        self.net.adam_step(grads, cfg.lr, cfg.max_grad_norm)

        policy_loss = float(-obj.mean())
        value_loss = float(((value - ret) ** 2).mean())
        entropy = float(H.mean())
        return policy_loss, value_loss, entropy
