"""
VerdictSurrogate — a differentiable NumPy proxy for the (non-differentiable) V2.

The GraphGAN framing (red_team/graph_gan/spec.py) wants the Blue Team as a
*discriminator* the generator can backprop through. V2 is rule/gate based, so no
gradient flows from it. The recommended formulation is surrogate-distillation:
train a differentiable model to imitate V2's verdict from pure graph features,
then use that fast model where V2's gradient (or just its speed) is needed.

This is that surrogate. It is:
  • a distilled regressor V2_score ≈ f(graph_features) — a stand-alone differentiable
    proxy of the engine, with measured fidelity;
  • an optional FAST reward model for the PPO Red Team (env ``surrogate=``): rollouts
    score against the proxy (cheap) while true evasion is always re-checked against the
    real engine, so the proxy accelerates search without falsifying any win.

Features are pure structure + the node attributes V2 actually reads (account_type,
risk_score, detected_patterns — the B8 trust surface) and the amount bands its gates
key on, so the proxy can in principle learn the gate logic.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import numpy as np

from ...common.attack_graph import AttackGraph
from ..base import apply_genome, random_genome
from ..graph_generator import make_base_attacks, make_benign_corpus

# amount gates V2 keys on (white-box report): structuring/mule band, fan/velocity, hop
_STRUCT_LO, _STRUCT_HI = 46_000.0, 50_000.0
_FAN_GATE = 150_000.0
_HOP_BAND = 25_000.0


def surrogate_features(ag: AttackGraph) -> np.ndarray:
    """Fixed-length structural + attribute feature vector (no oracle call)."""
    comps = ag.components
    n_comp = len(comps)
    n_nodes = 0
    n_edges = 0
    densities: list[float] = []
    max_out = max_in = 0
    total_value = 0.0
    amounts: list[float] = []
    struct = fan = hop = 0
    nonnormal = risky = patterned = 0
    risk_sum = 0.0
    seen_nodes: set[str] = set()

    for c in comps:
        edges = c.get("edges", [])
        outdeg: dict[str, int] = {}
        indeg: dict[str, int] = {}
        ids = set(c.get("node_ids") or [])
        for e in edges:
            s, t = str(e.get("source", "")), str(e.get("target", ""))
            ids.add(s); ids.add(t)
            outdeg[s] = outdeg.get(s, 0) + 1
            indeg[t] = indeg.get(t, 0) + 1
            amt = float(e.get("amount", 0) or 0)
            total_value += amt; amounts.append(amt)
            if _STRUCT_LO <= amt < _STRUCT_HI:
                struct += 1
            if amt >= _FAN_GATE:
                fan += 1
            if amt < _HOP_BAND:
                hop += 1
        cn = max(1, len(ids))
        densities.append(len(edges) / (cn * (cn - 1)) if cn > 1 else 0.0)
        max_out = max([max_out] + list(outdeg.values()))
        max_in = max([max_in] + list(indeg.values()))
        n_nodes += len(ids); n_edges += len(edges)
        for nd in c.get("nodes", []):
            nid = nd.get("id")
            if nid in seen_nodes:
                continue
            seen_nodes.add(nid)
            if nd.get("account_type", "normal") != "normal":
                nonnormal += 1
            rs = float(nd.get("risk_score", 0) or 0)
            risk_sum += rs
            if rs > 0:
                risky += 1
            if nd.get("detected_patterns"):
                patterned += 1

    n_nodes = max(1, n_nodes)
    n_edges_safe = max(1, n_edges)
    nn = max(1, len(seen_nodes))
    circuit_rank = max(0, n_edges - n_nodes + n_comp)   # cycle density proxy
    mean_amt = (sum(amounts) / len(amounts)) if amounts else 0.0
    max_amt = max(amounts) if amounts else 0.0

    return np.asarray([
        min(1.0, n_comp / 10.0),
        min(1.0, n_nodes / 100.0),
        min(1.0, n_edges / 200.0),
        sum(densities) / len(densities) if densities else 0.0,
        max(densities) if densities else 0.0,
        min(1.0, max_out / 20.0),
        min(1.0, max_in / 20.0),
        min(1.0, math.log1p(total_value) / 16.0),
        min(1.0, math.log1p(mean_amt) / 14.0),
        min(1.0, math.log1p(max_amt) / 16.0),
        min(1.0, n_comp / n_nodes),
        min(1.0, circuit_rank / n_edges_safe),
        struct / n_edges_safe,
        fan / n_edges_safe,
        hop / n_edges_safe,
        nonnormal / nn,
        min(1.0, risk_sum / nn),
        risky / nn,
        patterned / nn,
    ], dtype=np.float64)


# ── tiny differentiable MLP regressor (sigmoid output, MSE) ───────────────────────
class _Regressor:
    def __init__(self, in_dim: int, hidden: int, rng: np.random.Generator):
        def glorot(a, b):
            return rng.standard_normal((a, b)) * np.sqrt(2.0 / (a + b))
        self.p = {"W1": glorot(in_dim, hidden), "b1": np.zeros(hidden),
                  "W2": glorot(hidden, hidden), "b2": np.zeros(hidden),
                  "W3": glorot(hidden, 1) * 0.1, "b3": np.zeros(1)}
        self._m = {k: np.zeros_like(v) for k, v in self.p.items()}
        self._v = {k: np.zeros_like(v) for k, v in self.p.items()}
        self._t = 0

    def forward(self, x):
        z1 = x @ self.p["W1"] + self.p["b1"]; h1 = np.tanh(z1)
        z2 = h1 @ self.p["W2"] + self.p["b2"]; h2 = np.tanh(z2)
        y = 1.0 / (1.0 + np.exp(-(h2 @ self.p["W3"] + self.p["b3"])[:, 0]))
        return y, (x, h1, h2)

    def step(self, x, target, lr=3e-3):
        y, (x_, h1, h2) = self.forward(x)
        B = len(x)
        dy = (2.0 / B) * (y - target)               # dMSE/dy
        dpre = dy * y * (1 - y)                       # through sigmoid
        g = {}
        g["W3"] = h2.T @ dpre[:, None]; g["b3"] = dpre.sum()[None]
        dh2 = dpre[:, None] @ self.p["W3"].T
        dz2 = dh2 * (1 - h2 ** 2)
        g["W2"] = h1.T @ dz2; g["b2"] = dz2.sum(0)
        dh1 = dz2 @ self.p["W2"].T
        dz1 = dh1 * (1 - h1 ** 2)
        g["W1"] = x_.T @ dz1; g["b1"] = dz1.sum(0)
        # Adam
        self._t += 1
        for k, gk in g.items():
            self._m[k] = 0.9 * self._m[k] + 0.1 * gk
            self._v[k] = 0.999 * self._v[k] + 0.001 * (gk * gk)
            mhat = self._m[k] / (1 - 0.9 ** self._t)
            vhat = self._v[k] / (1 - 0.999 ** self._t)
            self.p[k] -= lr * mhat / (np.sqrt(vhat) + 1e-8)
        return float(((y - target) ** 2).mean())


@dataclass
class VerdictSurrogate:
    """A trained differentiable proxy of V2's detection score."""
    net: _Regressor
    mean: np.ndarray
    std: np.ndarray
    fidelity: dict = field(default_factory=dict)

    def detection_score(self, ag: AttackGraph) -> float:
        x = (surrogate_features(ag) - self.mean) / self.std
        return float(self.net.forward(x[None, :])[0][0])

    def onpolicy_gap(self, oracle, graphs: list) -> dict:
        """How well THIS surrogate judges a generator's current attacks: MAE and
        flag-agreement on graphs the policy actually produces (the exploited region)."""
        if not graphs:
            return {"mae": 0.0, "acc": 1.0, "n": 0}
        pred = np.asarray([self.detection_score(g) for g in graphs])
        true = np.asarray([oracle.detect(g).detection_score for g in graphs])
        return {"mae": float(np.abs(pred - true).mean()),
                "acc": float(((pred > 0.5) == (true > 0.5)).mean()), "n": len(graphs)}

    def refit(self, oracle, extra_graphs: list, **kw) -> "VerdictSurrogate":
        """Re-distil including on-policy attacks — re-teach the proxy the generator's
        exploits (closes the GraphGAN surrogate gap)."""
        fresh = VerdictSurrogate.distill(oracle, extra_graphs=extra_graphs, **kw)
        self.net, self.mean, self.std, self.fidelity = (
            fresh.net, fresh.mean, fresh.std, fresh.fidelity)
        return self

    # ── distillation ─────────────────────────────────────────────────────────────
    @classmethod
    def distill(cls, oracle, n_per_base: int = 40, epochs: int = 60,
                hidden: int = 32, seed: int = 0, verbose: bool = False,
                extra_graphs: list | None = None) -> "VerdictSurrogate":
        """Build a (graph → V2 detection_score) dataset and fit the proxy.

        Samples cover the spectrum V2 sees: confirmed-FRAUD archetypes, many random
        genome mutations of them (varied evasions/distortions), and the realistic
        benign corpus — each labelled by the REAL engine, then imitated. ``extra_graphs``
        adds ON-POLICY attacks from a generator (the GraphGAN re-distillation loop) so
        the proxy re-learns exactly the region a policy has been exploiting.
        """
        rng = random.Random(seed)
        bases = make_base_attacks(seed=42)
        graphs: list[AttackGraph] = []
        # fraud + mutated fraud across the difficulty spectrum
        for base in bases:
            graphs.append(base.clone())
            for _ in range(n_per_base):
                g = apply_genome(base, random_genome(rng, 1, 6), random.Random(rng.random()))
                graphs.append(g)
        # benign components (wrap each as a trivial single-component operation)
        from ..graph_generator import build_objective
        for comp in make_benign_corpus(seed=seed, n=len(bases) * 8):
            obj = build_objective(comp)
            graphs.append(AttackGraph(components=[comp], objective=obj, archetype="benign"))
        if extra_graphs:
            graphs.extend(extra_graphs)

        X = np.stack([surrogate_features(g) for g in graphs])
        y = np.asarray([oracle.detect(g).detection_score for g in graphs])

        mean = X.mean(0)
        std = X.std(0) + 1e-6
        Xn = (X - mean) / std

        gen = np.random.default_rng(seed)
        net = _Regressor(X.shape[1], hidden, gen)
        n = len(Xn)
        idx = np.arange(n)
        for ep in range(epochs):
            gen.shuffle(idx)
            loss = 0.0
            for s in range(0, n, 64):
                mb = idx[s:s + 64]
                loss = net.step(Xn[mb], y[mb])
            if verbose and (ep % 10 == 0 or ep == epochs - 1):
                print(f"    surrogate epoch {ep:02d}  mse={loss:.4f}")

        pred = net.forward(Xn)[0]
        mae = float(np.abs(pred - y).mean())
        # flag-agreement: both call it flagged (>0.5 ≈ SUSPICIOUS+) or not
        acc = float(((pred > 0.5) == (y > 0.5)).mean())
        return cls(net=net, mean=mean, std=std,
                   fidelity={"mae": mae, "acc": acc, "n": n})
