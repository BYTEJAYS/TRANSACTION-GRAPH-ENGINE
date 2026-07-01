"""
Central configuration for the adversarial ecosystem.

Keeps every tunable in one place (fitness weights, evolution hyper-params,
target-engine selection) and puts the TGiE ``backend/`` directory on sys.path so
the coupled Blue Team engine can be imported from anywhere in this package.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ── make the Blue Team importable ─────────────────────────────────────────────
# adversarial/ lives at <repo>/adversarial; the engine lives at <repo>/backend.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

REPO_ROOT = _REPO_ROOT
BACKEND_DIR = _BACKEND
DATA_DIR = _REPO_ROOT / "adversarial" / "_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── target selection (decision D2: V2 primary, V1 secondary) ──────────────────
TARGET_ENGINE = os.getenv("ADV_TARGET_ENGINE", "v2").strip().lower()


# ── fitness weights ───────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FitnessWeights:
    evasion: float = 0.55       # reward for lowering the Blue Team detection score
    stealth: float = 0.25       # reward for low cluster risk (margin below thresholds)
    distortion: float = 0.15    # penalty for deviating from the base fraud graph
    complexity: float = 0.05    # penalty for long, elaborate attack genomes
    infeasible_penalty: float = 1.0  # fitness floor when the laundering objective breaks


# ── evolutionary hyper-parameters ─────────────────────────────────────────────
@dataclass
class EvolutionConfig:
    population_size: int = 40
    generations: int = 25
    elite_fraction: float = 0.15
    tournament_k: int = 3
    crossover_rate: float = 0.6
    mutation_rate: float = 0.5      # P(mutate) per offspring
    max_genome_len: int = 8
    min_genome_len: int = 1
    seed: int = 1234
    # validity: evaluate each genome as an expectation over agent randomness.
    # >1 realization makes fitness reproducible and success robust rather than a
    # single lucky draw; success_quorum is the fraction of realizations that must
    # evade (1.0 = must evade in EVERY realization → a reliable attack).
    eval_samples: int = 3
    success_quorum: float = 1.0
    # optional arsenal restriction: when set, the GA only ever uses these agents
    # (for controlled experiments that isolate one capability). None → all agents.
    allowed_agents: tuple[str, ...] | None = None
    weights: FitnessWeights = field(default_factory=FitnessWeights)


# ── quality-diversity (MAP-Elites) ────────────────────────────────────────────
@dataclass
class QDConfig:
    """MAP-Elites over the attack space.

    Behaviour descriptors are the *diversity axes* (fragmentation × distortion);
    quality is pure evasion+stealth, so distortion is illuminated rather than
    penalised. This keeps the best attack of every kind instead of collapsing to
    the single highest-fitness recipe (the cross_component_split mode collapse the
    scalar GA exhibits).
    """
    evaluations: int = 3000          # total genome evaluations (the search budget)
    init_batch: int = 60             # random + seeded genomes before the main loop
    frag_bins: int = 5               # fragmentation (num_components) niches
    distortion_bins: int = 6         # distortion niches over [0,1]
    curiosity: float = 0.5           # P(select parent from a high-curiosity cell)
    # quality weights (no distortion/complexity penalty — those are descriptors)
    evasion: float = 0.7
    stealth: float = 0.3
    seed: int = 1234
    eval_samples: int = 3
    success_quorum: float = 1.0


# ── objective tolerance ───────────────────────────────────────────────────────
OBJECTIVE_TOLERANCE = 0.15   # laundering objective may lose ≤15% of target value
