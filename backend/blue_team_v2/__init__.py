"""
Blue Team V2 — next-generation experimental fraud-intelligence engine for TGIE.

This package is an INDEPENDENT, opt-in intelligence layer. It never imports,
modifies, or depends on the production `blue_team` package. It is wired into
TGIE only through the engine router (`router.py`) and stays dormant unless
explicitly selected via ACTIVE_BLUE_TEAM=v2 or shadow mode.

Public API (drop-in compatible with blue_team.adapter):
    analyze_all_components(components, blue_team_url="", api_key="") -> list[dict]
    analyze_component(component, blue_team_url="", api_key="")      -> dict

Richer programmatic access:
    BlueTeamV2Engine().analyze_component(component) -> ClusterAnalysis

Red Team coupling (the official adversarial interface — Red imports this, never
the engine internals; see red_team_interface.py):
    RedTeamTarget().judge_component / judge_operation / ensemble_scores / score_transactions
"""
from .adapter import (
    analyze_all_components,
    analyze_all_components_sync,
    analyze_component,
    analyze_component_sync,
)
from .engine import BlueTeamV2Engine, __version__
from .red_team_interface import (
    ComponentVerdict,
    OperationVerdict,
    RedTeamTarget,
    ensemble_scores,
    judge_component,
    judge_operation,
    score_transactions,
)

__all__ = [
    "analyze_all_components",
    "analyze_component",
    "analyze_all_components_sync",
    "analyze_component_sync",
    "BlueTeamV2Engine",
    "__version__",
    # Red Team coupling interface
    "RedTeamTarget",
    "ComponentVerdict",
    "OperationVerdict",
    "judge_component",
    "judge_operation",
    "ensemble_scores",
    "score_transactions",
]
