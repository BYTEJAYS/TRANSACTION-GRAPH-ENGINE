"""
RL Red Team — PPO over the attack action space (specification + scaffold).

The evolutionary engine searches genomes holistically; an RL agent instead makes
*sequential* edits and receives credit per step, which suits long multi-stage
infiltrations where the right move depends on the Blue Team's current reaction.
It shares the exact same agents (action primitives) and oracle (environment) as
the evolutionary engine, so the two are directly comparable and can seed each
other (curriculum L9).

This module fixes the MDP precisely and IMPLEMENTS the trainer (2026-06-24). The
engine is deliberately torch-free (deployment removed PyTorch), so PPO is realised
in pure NumPy (``ppo.py``) over the ``AttackEnv`` environment (``env.py``) — faithful
to PPO and to the codebase's NumPy discipline. ``PPORedTeam`` (below) wires them.

MDP
---
State  s_t (per the directive):
    - graph features of the current attack: per-component [n_nodes, n_edges,
      density, degree mean/var, max chain depth, cycle count, value moved]
    - Blue Team feedback: worst verdict (1-hot), max_cluster_risk, detection
      score, # flagged nodes, residual detector multi-hot (11 dims)
    - embedding statistics: distribution of per-node risk scores (mean/p90/max)
    - budget: steps remaining, current distortion, objective shortfall
Action a_t:
    (agent ∈ AGENT_NAMES, intensity ∈ {0.25,0.5,0.75,1.0})  — discretised, or a
    parameterised-action head (discrete agent + continuous intensity).
Reward r_t:
    Δ(-detection_score)·W_evade + Δstealth·W_stealth - Δdistortion·W_dist
    - step_cost ; terminal bonus if evaded & objective_ok ; hard penalty if the
    objective breaks (episode ends infeasible).
Transition:
    s_{t+1} = oracle.detect(apply(agent, intensity)) ; episode ends on evasion,
    objective break, or step budget.

Trainer (BUILT): PPO (clip 0.2, GAE λ=0.95, γ=0.99) with a shared two-layer tanh
MLP trunk and actor-critic heads, entropy bonus, Adam — all NumPy with hand-derived
backprop (``ppo.py``). Vectorised over the archetype set (one env per archetype,
one shared policy). The greedy policy is always re-scored on the REAL engine. An
optional distilled ``VerdictSurrogate`` (graph_gan/) can stand in as a fast reward
model so rollouts skip the real engine; true evasion is still re-checked on it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ...common.attack_graph import AttackGraph
from ...common.oracle import BlueTeamOracle
from ..graph_generator import make_base_attacks
from .env import AttackEnv, INTENSITIES
from .ppo import PPO, PPOConfig

AGENT_INTENSITIES = INTENSITIES


@dataclass
class PPOResult:
    """Greedy (deterministic) evaluation of the trained policy on one archetype."""
    archetype: str
    evaded: bool
    detection_score: float
    verdict: str
    distortion: float
    num_components: int
    steps: int
    genome: list = field(default_factory=list)   # the move sequence the policy played


class PPORedTeam:
    """PPO over the attack action space, trained against the real Blue Team.

    The MDP is exactly the one specified in this module's docstring; the
    environment is :class:`AttackEnv` (the real :class:`BlueTeamOracle` plus the
    registered agents as sequential edits) and the trainer is the pure-NumPy
    :class:`PPO`. One vectorised env per archetype shares a single policy, so the
    agent learns a transferable evasion policy rather than one recipe per graph.
    """

    def __init__(self, target: str = "v2", arsenal: list[str] | None = None,
                 oracle: BlueTeamOracle | None = None,
                 base_seed: int = 42, max_steps: int = 12,
                 surrogate=None, ppo: PPOConfig | None = None,
                 archetypes: list[str] | None = None):
        self.target = target
        self.arsenal = arsenal
        self.oracle = oracle or BlueTeamOracle(target=target)
        self.bases: list[AttackGraph] = make_base_attacks(seed=base_seed, archetypes=archetypes)
        self.max_steps = max_steps
        self.surrogate = surrogate
        self.cfg = ppo or PPOConfig()
        self.envs = [AttackEnv(self.oracle, b, max_steps=max_steps, seed=i + 1,
                               arsenal=arsenal, surrogate=surrogate)
                     for i, b in enumerate(self.bases)]
        self.ppo = PPO(self.envs, self.cfg)

    # ── training ──────────────────────────────────────────────────────────────────
    def train(self, updates: int = 60, verbose: bool = False) -> list[dict]:
        for u in range(updates):
            stats = self.ppo.update()
            if verbose:
                print(f"  update {u:03d}  train_asr={stats['train_asr']:.2f}  "
                      f"return={stats['mean_return']:+.3f}  ent={stats['entropy']:.3f}  "
                      f"vloss={stats['value_loss']:.3f}  eps={stats['episodes']}")
        return self.ppo.history

    # ── greedy evaluation against the REAL engine ─────────────────────────────────
    def evaluate(self) -> list[PPOResult]:
        from ..base import Move
        results: list[PPOResult] = []
        for env in self.envs:
            # greedy rollout uses a truth oracle (never the surrogate) for scoring
            truth_env = AttackEnv(self.oracle, env.base, max_steps=self.max_steps,
                                  seed=env._seed, arsenal=self.arsenal, surrogate=None)
            state = truth_env.reset()
            played: list[Move] = []
            info: dict = {}
            for _ in range(self.max_steps):
                a = self.ppo.greedy_action(state)
                name, inten = truth_env.decode(a)
                played.append(Move(name, inten))
                res = truth_env.step(a)
                state, info = res.state, res.info
                if res.done:
                    break
            results.append(PPOResult(
                archetype=env.base.archetype,
                evaded=bool(info.get("evaded")),
                detection_score=float(info.get("detection_score", 1.0)),
                verdict=str(info.get("verdict", "FRAUD")),
                distortion=float(info.get("distortion", 1.0)),
                num_components=int(info.get("num_components", 1)),
                steps=len(played), genome=played))
        return results

    def asr(self) -> float:
        res = self.evaluate()
        return sum(1 for r in res if r.evaded) / max(1, len(res))

    # ── on-policy attack graphs (for GAN surrogate re-distillation) ───────────────
    def rollout_graphs(self, per_env: int = 6, sample: bool = True) -> list[AttackGraph]:
        """Realised AttackGraphs the current policy produces — the on-policy
        distribution a re-distilled surrogate must learn to judge correctly."""
        graphs: list[AttackGraph] = []
        for env in self.envs:
            for _ in range(per_env):
                state = env.reset()
                for _ in range(self.max_steps):
                    a = (self.ppo.sample_action(state) if sample
                         else self.ppo.greedy_action(state))
                    res = env.step(a)
                    state = res.state
                    if res.done:
                        break
                graphs.append(env.ag.clone())
        return graphs
