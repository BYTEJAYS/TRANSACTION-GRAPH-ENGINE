"""
AttackEnv — the sequential-edit MDP the PPO Red Team acts in.

The evolutionary engine searches whole genomes at once; this environment instead
exposes the SAME action primitives (the registered agents) as *sequential* edits,
so an RL policy can choose the next move conditioned on the Blue Team's current
reaction. One step = apply one agent at a chosen intensity, re-realise connected
components, re-judge with the real BlueTeamOracle, and emit a shaped reward.

State / action / reward follow ``rl_agent/spec.py`` exactly. The state is a
fixed-length float vector (so a plain MLP policy can consume it); the action is a
discrete (agent, intensity) pair; reward credits per-step detection drop, stealth
gain and low distortion, with a terminal bonus for a feasible evasion and a hard
penalty if the laundering objective breaks.

Determinism: every episode derives its per-step apply-rng from a fixed seed, so a
fixed policy yields identical trajectories — the same reproducibility contract the
GA earned with blake2b genome seeds.
"""
from __future__ import annotations

import math
import random
import zlib
from dataclasses import dataclass

import numpy as np

from ...common.attack_graph import AttackGraph, distortion
from ...common.oracle import BlueTeamOracle
from ..base import AGENT_NAMES, AGENTS

# Discretised intensities the policy may pick (mirrors spec.AGENT_INTENSITIES).
INTENSITIES: tuple[float, ...] = (0.25, 0.5, 0.75, 1.0)

# Fixed evidence-hashing width: V2 emits ~11 detector patterns; we hash pattern
# names into a fixed multi-hot so the state width is stable even if the detector
# vocabulary drifts (feature hashing, robust to unknown patterns).
EVIDENCE_BUCKETS = 11

_VERDICTS = ("CLEAN", "LOGGED", "SUSPICIOUS", "FRAUD")


@dataclass
class StepResult:
    state: np.ndarray
    reward: float
    done: bool
    info: dict


@dataclass
class _SurrogateDetection:
    """Cheap stand-in for OperationDetection when a fast surrogate scores rollouts.

    Exposes exactly the attributes ``_featurize``/``step`` read, derived from the
    surrogate's scalar detection score — so a surrogate rollout never touches the
    real engine. Per-component detail (node_risk/evidence) is unavailable from the
    proxy and is simply absent (empty), which the featuriser already handles.
    """
    detection_score: float
    per_component: tuple = ()
    evidence_patterns: tuple = ()

    @property
    def worst_verdict(self) -> str:
        s = self.detection_score
        return ("CLEAN" if s < 0.25 else "LOGGED" if s < 0.5
                else "SUSPICIOUS" if s < 0.75 else "FRAUD")

    @property
    def max_cluster_risk(self) -> float:
        return self.detection_score

    @property
    def total_flagged_nodes(self) -> int:
        return 0

    @property
    def evaded(self) -> bool:
        return self.detection_score < 0.5


def _component_features(comp: dict) -> tuple[int, int, float, float, float, float]:
    """(n_nodes, n_edges, density, mean_deg, max_deg, value_moved) for one component."""
    edges = comp.get("edges", [])
    ids = set(comp.get("node_ids") or [])
    deg: dict[str, int] = {}
    value = 0.0
    for e in edges:
        s, t = str(e.get("source", "")), str(e.get("target", ""))
        ids.add(s); ids.add(t)
        deg[s] = deg.get(s, 0) + 1
        deg[t] = deg.get(t, 0) + 1
        value += float(e.get("amount", 0) or 0)
    n = max(1, len(ids))
    m = len(edges)
    density = m / (n * (n - 1)) if n > 1 else 0.0
    degs = list(deg.values()) or [0]
    return len(ids), m, density, sum(degs) / n, float(max(degs)), value


class AttackEnv:
    """A laundering operation the policy mutates one move at a time vs the real Blue Team."""

    def __init__(self, oracle: BlueTeamOracle, base: AttackGraph,
                 max_steps: int = 12, seed: int = 0,
                 arsenal: list[str] | None = None,
                 step_cost: float = 0.01, terminal_bonus: float = 1.0,
                 infeasible_penalty: float = 1.0,
                 w_evade: float = 0.55, w_stealth: float = 0.25, w_dist: float = 0.15,
                 surrogate=None) -> None:
        self.oracle = oracle
        self.base = base
        self.max_steps = max_steps
        self.names = list(arsenal) if arsenal else list(AGENT_NAMES)
        self.n_intensities = len(INTENSITIES)
        self.n_actions = len(self.names) * self.n_intensities
        self.step_cost = step_cost
        self.terminal_bonus = terminal_bonus
        self.infeasible_penalty = infeasible_penalty
        self.w_evade, self.w_stealth, self.w_dist = w_evade, w_stealth, w_dist
        # optional differentiable surrogate of V2 (GraphGAN discriminator): when set,
        # rollout rewards are scored against the FAST surrogate instead of the real
        # engine, and only periodically re-checked against truth (surrogate-accelerated PPO).
        self.surrogate = surrogate
        self._rng = random.Random(seed)
        self._seed = seed
        self.episode = 0
        self.state_dim = self._featurize(self.base, self._judge(self.base), 0).shape[0]

    # ── action coding ──────────────────────────────────────────────────────────
    def decode(self, a: int) -> tuple[str, float]:
        return self.names[a // self.n_intensities], INTENSITIES[a % self.n_intensities]

    # ── Blue Team judgement (real engine, or fast surrogate proxy) ───────────────
    def _judge(self, ag: AttackGraph):
        """Real OperationDetection, or a cheap surrogate stand-in — no real-engine
        call on the surrogate path, which is the whole point of the proxy."""
        if self.surrogate is not None:
            return _SurrogateDetection(float(self.surrogate.detection_score(ag)))
        return self.oracle.detect(ag)

    # ── featurisation (fixed-length state, per the MDP spec) ─────────────────────
    def _featurize(self, ag: AttackGraph, det: OperationDetection, step: int) -> np.ndarray:
        comps = ag.components
        feats = [_component_features(c) for c in comps] or [(0, 0, 0.0, 0.0, 0.0, 0.0)]
        n_nodes = sum(f[0] for f in feats)
        n_edges = sum(f[1] for f in feats)
        mean_density = sum(f[2] for f in feats) / len(feats)
        mean_deg = sum(f[3] for f in feats) / len(feats)
        max_deg = max(f[4] for f in feats)
        value = sum(f[5] for f in feats)
        n_comp = len(comps)

        # graph block
        g = [
            min(1.0, n_comp / 10.0),
            min(1.0, n_nodes / 100.0),
            min(1.0, n_edges / 200.0),
            mean_density,
            min(1.0, mean_deg / 10.0),
            min(1.0, max_deg / 20.0),
            min(1.0, math.log1p(value) / 16.0),     # log-scaled value moved
            min(1.0, n_comp / max(1, n_nodes)),      # fragmentation
        ]

        # blue feedback block
        worst = det.worst_verdict
        vhot = [1.0 if worst == v else 0.0 for v in _VERDICTS]
        ev = [0.0] * EVIDENCE_BUCKETS
        for pat in det.evidence_patterns:
            # stable (process-independent) bucketing — the builtin hash is salted
            # per process (PYTHONHASHSEED), which would make the state irreproducible
            ev[zlib.crc32(str(pat).encode()) % EVIDENCE_BUCKETS] = 1.0
        blue = vhot + [
            det.max_cluster_risk,
            det.detection_score,
            min(1.0, det.total_flagged_nodes / 20.0),
        ] + ev

        # per-node risk distribution
        risks: list[float] = []
        for d in det.per_component:
            risks.extend(d.node_risk.values())
        if risks:
            arr = np.asarray(risks, dtype=np.float64)
            risk_block = [float(arr.mean()), float(np.percentile(arr, 90)), float(arr.max())]
        else:
            risk_block = [0.0, 0.0, 0.0]

        # budget block
        budget = [
            (self.max_steps - step) / self.max_steps,
            distortion(self.base, ag),
            ag.objective.shortfall(ag.components),
        ]

        return np.asarray(g + blue + risk_block + budget, dtype=np.float64)

    # ── episode protocol ─────────────────────────────────────────────────────────
    def reset(self) -> np.ndarray:
        self.episode += 1
        # deterministic per-episode apply-rng (reproducible trajectories per policy)
        self._rng = random.Random(self._seed * 1_000_003 + self.episode)
        self.ag = self.base.clone()
        self.step_idx = 0
        self._det = self._judge(self.ag)
        self._prev_det_score = self._det.detection_score
        self._prev_stealth = max(0.0, 1.0 - self._det.max_cluster_risk)
        self._prev_dist = 0.0
        return self._featurize(self.ag, self._det, self.step_idx)

    def step(self, action: int) -> StepResult:
        name, intensity = self.decode(action)
        fn = AGENTS.get(name)
        if fn is not None:
            try:
                fn(self.ag, self._rng, intensity)
            except Exception:
                pass  # an agent must never crash the episode (mirrors apply_genome)
        # realise any severed/added connectivity into true components
        from ..graph_generator import resplit_components
        self.ag = resplit_components(self.ag)
        self.step_idx += 1

        obj_ok = self.ag.objective_satisfied()
        if not obj_ok:
            # the laundering goal broke → infeasible, episode ends with a hard penalty
            state = self._featurize(self.ag, self._judge(self.ag), self.step_idx)
            return StepResult(state, -self.infeasible_penalty, True,
                              {"reason": "infeasible", "evaded": False, "obj_ok": False})

        det = self._judge(self.ag)
        det_score = det.detection_score
        stealth = max(0.0, 1.0 - det.max_cluster_risk)
        dist = distortion(self.base, self.ag)

        # shaped per-step reward = improvement in evasion + stealth - added distortion
        reward = (self.w_evade * (self._prev_det_score - det_score)
                  + self.w_stealth * (stealth - self._prev_stealth)
                  - self.w_dist * (dist - self._prev_dist)
                  - self.step_cost)
        self._prev_det_score, self._prev_stealth, self._prev_dist = det_score, stealth, dist
        self._det = det

        # Real path: the engine's own OperationDetection.evaded. Surrogate path:
        # the proxy's predicted not-flagged (score below the SUSPICIOUS band). Either
        # way the greedy evaluation (spec.evaluate) re-checks on the REAL engine, so no
        # surrogate-fooled attack is ever reported as a true win.
        evaded = det.evaded
        done = evaded or self.step_idx >= self.max_steps
        if evaded:
            reward += self.terminal_bonus
        info = {"reason": "evaded" if evaded else ("budget" if done else "step"),
                "evaded": bool(evaded), "obj_ok": True,
                "detection_score": det_score, "verdict": det.worst_verdict,
                "distortion": dist, "num_components": self.ag.num_components()}
        return StepResult(self._featurize(self.ag, det, self.step_idx), reward, done, info)
