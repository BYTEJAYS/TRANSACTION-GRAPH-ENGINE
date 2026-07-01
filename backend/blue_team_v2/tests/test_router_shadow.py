"""Router + shadow-mode tests — engine selection and side-by-side comparison."""
from __future__ import annotations

import asyncio
import os

from blue_team_v2.router import active_engine, route_all_components
from blue_team_v2.shadow import run_shadow
from blue_team_v2.simulation.generators import Simulator
from blue_team_v2.validation_panel import panel_for_shadow


def test_router_defaults_to_v2():
    os.environ.pop("ACTIVE_BLUE_TEAM", None)
    assert active_engine() == "v2", "V2 is the production engine as of 2026-06-27"


def test_router_v1_reachable_only_by_explicit_rollback():
    os.environ.pop("ACTIVE_BLUE_TEAM", None)
    assert active_engine("v1") == "v1"          # explicit rollback still works
    assert active_engine("nonsense") == "v2"    # any unrecognised value → V2, never V1


def test_router_env_selects_v2():
    os.environ["ACTIVE_BLUE_TEAM"] = "v2"
    try:
        assert active_engine() == "v2"
    finally:
        os.environ.pop("ACTIVE_BLUE_TEAM", None)


def test_router_explicit_arg_wins():
    assert active_engine("v2") == "v2"
    assert active_engine("v1") == "v1"


def test_router_v2_returns_v1_schema():
    comp, _ = Simulator().fan_out()
    results = asyncio.run(route_all_components([comp], engine="v2"))
    r = results[0]
    for key in ("graph_id", "verdict", "risk_score", "flagged_nodes", "nodes"):
        assert key in r


def test_shadow_runs_both_engines():
    sim = Simulator()
    components = [c for c, _ in sim.mixed_dataset(n_fraud=2, n_normal=2)]
    result = asyncio.run(run_shadow(components))
    assert "v1" in result and "v2" in result
    assert "comparison" in result and len(result["comparison"]) == len(components)
    assert "agreement" in result
    # validation panel renders for both engines
    panel = panel_for_shadow(result)
    assert panel["mode"] == "shadow"
    assert "v1" in panel and "v2" in panel
