"""
Graph GAN — generator (Red) vs discriminator (Blue) (specification + scaffold).

The directive's framing: the Red Team is the generator producing attack graphs;
the Blue Team is the discriminator detecting them; train until equilibrium.

A subtlety this scaffold records so it is not lost: the primary Blue Team (V2) is
non-differentiable (rule/gate based), so a *classic* GAN gradient cannot flow
from discriminator to generator. Two viable formulations:

  1. Surrogate-discriminator GAN: train a differentiable GNN surrogate to imitate
     V2's verdict (distillation), backprop attack-graph generation through the
     surrogate, periodically re-distill against the real V2. (Recommended.)
  2. Score-function / RL-as-GAN: treat V2's detection score as a black-box reward
     and optimise the generator with policy gradients (this collapses into the
     PPO Red Team — see rl_agent/spec.py).

Generator (planned): a graph generative model emitting (nodes, edges, amounts,
timestamps) for one operation, constrained to satisfy the AttackObjective; latent
z → operation. Discriminator: the surrogate of V2 (formulation 1) or V2 itself as
a reward oracle (formulation 2). Equilibrium tracked via ASR plateau + surrogate
fidelity to V2.

BUILT (2026-06-24): both halves of the recommended formulation now exist —

  • Discriminator: ``VerdictSurrogate`` (surrogate.py) — a differentiable NumPy proxy
    distilled from V2's verdicts; measured fidelity to the real engine.
  • Generator: the PPO Red Team (rl_agent/) — policy-gradient generation against the
    real V2 (formulation 2), optionally accelerated by the surrogate reward model
    (``AttackEnv(surrogate=...)``) with true evasion always re-checked on the real V2.

The classic single-tensor GAN generator (formulation 1, emitting whole graphs and
backpropagating through the surrogate) is intentionally not built: the action-space
generator (PPO) reuses the validated agents/objective machinery and produces
realisable laundering operations, where a free-form node/edge generator would need a
separate feasibility projection. The surrogate is the reusable piece that lets either
generator train fast.
"""
from __future__ import annotations

from .surrogate import VerdictSurrogate, surrogate_features  # noqa: F401


class GraphGAN:
    """Generator(Red)-vs-discriminator(Blue) — realised as PPO + VerdictSurrogate.

    Kept as a thin convenience entrypoint; the working pieces are
    :class:`VerdictSurrogate` (the distilled differentiable discriminator) and the
    PPO Red Team (the generator). See the module docstring for why this is the
    recommended surrogate-distillation formulation rather than a free-form graph GAN.
    """

    def __init__(self, target: str = "v2", formulation: str = "surrogate"):
        self.target = target
        self.formulation = formulation

    def fit_discriminator(self, oracle, **kw) -> VerdictSurrogate:
        """Distil the differentiable surrogate discriminator from the real engine."""
        return VerdictSurrogate.distill(oracle, **kw)

    def train(self, oracle=None, rounds: int = 4, updates_per_round: int = 15,
              per_env: int = 6, arsenal=None, max_steps: int = 10,
              verbose: bool = False, **ppo):
        """GAN loop: generator (PPO) vs discriminator (surrogate), re-distilled
        on-policy each round.

        A STATIC surrogate is Goodhart-exploitable — PPO learns to fool the proxy in
        the region where it disagrees with the real engine, so true ASR stays ~0 even
        as surrogate-ASR saturates. Each round we re-distil the surrogate on the
        generator's CURRENT attacks (labelled by the real V2), shrinking that gap, so
        the policy is pushed toward attacks that fool the real engine, not just the proxy.

        Returns (policy, surrogate, history) where history[r] carries the round's true
        ASR (greedy, real V2) and the surrogate's on-policy fidelity before re-distilling.
        """
        from ..rl_agent import PPORedTeam
        from ..rl_agent.ppo import PPOConfig
        if oracle is None:
            from ...common.oracle import BlueTeamOracle
            oracle = BlueTeamOracle(target=self.target)

        surrogate = self.fit_discriminator(oracle)
        rt = PPORedTeam(target=self.target, oracle=oracle, arsenal=arsenal,
                        max_steps=max_steps, surrogate=surrogate, ppo=PPOConfig(**ppo))
        accum: list = []
        history: list[dict] = []
        for r in range(rounds):
            rt.train(updates=updates_per_round)
            graphs = rt.rollout_graphs(per_env=per_env)
            gap = surrogate.onpolicy_gap(oracle, graphs)   # fidelity BEFORE re-distilling
            true_asr = rt.asr()                            # greedy, scored on the real V2
            history.append({"round": r, "true_asr": true_asr,
                            "onpolicy_mae": gap["mae"], "onpolicy_acc": gap["acc"]})
            if verbose:
                print(f"  GAN round {r}: true_asr(realV2)={true_asr:.2f}  "
                      f"surrogate on-policy MAE={gap['mae']:.3f} acc={gap['acc']:.2f}", flush=True)
            accum.extend(graphs)
            surrogate.refit(oracle, extra_graphs=accum)    # re-teach the proxy the exploits
        return rt, surrogate, history
