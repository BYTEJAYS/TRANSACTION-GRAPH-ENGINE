from __future__ import annotations
"""
V2 Blue Team target — couples CRUCIBLE to the REAL TGIE Blue Team V2 engine.

This is the production counterpart to `blue_clone.MockBlueTeam`: instead of the
deterministic sandbox clone of the old union-bank Blue Team, genomes are scored
by the live `blue_team_v2` engine that TGIE actually deploys. Attacks that evade
this target therefore transfer to the real system.

Coupling direction (one-way): CRUCIBLE (Red) imports `blue_team_v2` (Blue).
Blue never imports Red — V2 ships a stable `red_team_interface` precisely so the
attacker has ONE import surface and the production engine stays decoupled. We go
through that interface (`RedTeamTarget.score_transactions`) and nothing else.

Drop-in contract: `V2BlueTeam` exposes the exact `MockBlueTeam` surface the rest
of CRUCIBLE depends on — `score(genome) -> [4 floats]` and
`score_action(scores) -> str` — so it slots into fitness, the mutation engine,
the API, attack_loop and the bypass verifier with no caller changes.

Activation: `get_blue_team()` (in blue_clone.py) returns this when
`CRUCIBLE_BLUE_TEAM=v2`. Default stays sandbox so the bypass DNAs / tests keep
scoring against the frozen clone.

Key divergence vs MockBlueTeam (see agent_docs/sandbox_vs_production_divergences.md
D-06): V2 scores purely on graph STRUCTURE + amounts from
`genome.to_transaction_list()`. It does NOT consume `account_fixtures` (KYC age,
occupation, VPA age, festival history). Fixtures are accepted and ignored for
drop-in compatibility, so context-dependent bypasses (festival adjuster, JAN_DHAN,
gig-worker velocity, payee-VPA age) have no effect against this target.
"""
import logging
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from red_team.core.genome import FraudGenome

logger = logging.getLogger(__name__)

# Score → action thresholds. Identical to MockBlueTeam so downstream behaviour
# (fitness mean-score gate, attack_loop action labels) is engine-independent.
_THRESHOLD_LOG = 0.40
_THRESHOLD_REVIEW = 0.62
_THRESHOLD_HIGH_RISK = 0.80

# Empty/edge-less attack → same near-zero ensemble the clone returns, so callers
# behave identically on degenerate genomes.
_EMPTY_SCORE = [0.05, 0.05, 0.04, 0.06]


def _resolve_backend_path() -> str | None:
    """Locate the TGIE backend dir that holds `blue_team_v2`.

    Honours `CRUCIBLE_V2_BACKEND` if set; otherwise walks up from this file
    looking for a `backend/blue_team_v2` package.
    """
    override = os.getenv("CRUCIBLE_V2_BACKEND")
    if override:
        return os.path.abspath(override)
    here = os.path.dirname(os.path.abspath(__file__))
    node = here
    for _ in range(8):  # crucible/red_team/sandbox → TGIE is a few levels up
        candidate = os.path.join(node, "backend")
        if os.path.isdir(os.path.join(candidate, "blue_team_v2")):
            return os.path.abspath(candidate)
        parent = os.path.dirname(node)
        if parent == node:
            break
        node = parent
    return None


def _load_v2_interface():
    """Import the V2 red-team interface, adding the backend dir to sys.path once."""
    backend = _resolve_backend_path()
    if backend is None:
        raise RuntimeError(
            "blue_team_v2 not found. Set CRUCIBLE_V2_BACKEND to the TGIE 'backend' "
            "directory (the one containing the blue_team_v2 package)."
        )
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from blue_team_v2.red_team_interface import RedTeamTarget  # noqa: E402
    return RedTeamTarget


class V2BlueTeam:
    """Real Blue Team V2, wrapped in the MockBlueTeam scoring contract.

    `account_fixtures` is accepted for signature parity with MockBlueTeam but is
    NOT used — V2 scores graph structure + amounts only (see module docstring /
    divergence D-06).
    """

    def __init__(self, account_fixtures: dict | None = None) -> None:
        self._fixtures = account_fixtures or {}  # accepted, intentionally unused
        RedTeamTarget = _load_v2_interface()
        self._target = RedTeamTarget()
        self.version = getattr(self._target, "version", "unknown")
        logger.info("CRUCIBLE coupled to Blue Team V2 (engine version %s)", self.version)

    def score(self, genome: "FraudGenome") -> list[float]:
        """[champion, challenger_1, challenger_2, challenger_3] in [0, 1]."""
        transactions = genome.to_transaction_list()
        if not transactions:
            return list(_EMPTY_SCORE)
        return self._target.score_transactions(
            transactions, graph_id=f"rt_{genome.genome_id[:8]}"
        )

    def score_action(self, scores: list[float]) -> str:
        c = scores[0] if scores else 0.0
        if c >= _THRESHOLD_HIGH_RISK:
            return "HIGH_RISK"
        if c >= _THRESHOLD_REVIEW:
            return "REVIEW"
        if c >= _THRESHOLD_LOG:
            return "LOG"
        return "PASS"

    def detailed_score(self, genome: "FraudGenome") -> dict:
        """Scoring breakdown, parallel to MockBlueTeam.detailed_score()."""
        scores = self.score(genome)
        return {
            "champion_score": scores[0] if scores else 0.0,
            "all_scores": scores,
            "action": self.score_action(scores),
            "engine": "blue_team_v2",
            "engine_version": self.version,
            "uses_account_fixtures": False,
        }
