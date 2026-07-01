"""
Engine Router — selects which Blue Team engine analyses a graph, without any
existing caller having to know which one ran.

                         ┌──  (default / any value)  ──►  blue_team_v2.adapter  (PRODUCTION)
   TGIE ── route_*() ────┤
                         └──  ACTIVE_BLUE_TEAM=v1     ──►  blue_team.adapter     (retired, rollback only)

Selection precedence (highest first):
  1. explicit `engine=` argument
  2. ACTIVE_BLUE_TEAM environment variable  ("v1" | "v2")
  3. default → "v2"  (V2 is the production engine as of 2026-06-27)

V1 is retired: it is NEVER used in normal operation and is reachable only by an
explicit ACTIVE_BLUE_TEAM=v1 rollback. The router preserves V1's async signature
exactly, so it stands in for `blue_team.adapter.analyze_all_components` at the
import site with zero changes to callers.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

V1 = "v1"
V2 = "v2"
# Blue Team V2 is the PRODUCTION engine as of 2026-06-27 (benchmarked decisively
# better — far fewer false positives, faster, richer output). V1 is retired and
# kept only as an explicit rollback escape hatch via ACTIVE_BLUE_TEAM=v1.
DEFAULT_ENGINE = V2


def active_engine(engine: str | None = None) -> str:
    choice = (engine or os.getenv("ACTIVE_BLUE_TEAM") or DEFAULT_ENGINE).strip().lower()
    # V2 is the default for ANY unrecognised value — only an explicit, valid V1
    # selector reaches the retired engine, so a typo never silently downgrades.
    return V1 if choice in ("v1", "1", "blue_team") else V2


async def route_all_components(
    components: list[dict],
    blue_team_url: str = "",
    api_key: str = "",
    engine: str | None = None,
) -> list[dict]:
    """Drop-in replacement for blue_team.adapter.analyze_all_components."""
    which = active_engine(engine)
    if which == V2:
        from blue_team_v2.adapter import analyze_all_components as v2
        log.info("EngineRouter → Blue Team V2 (%d components)", len(components or []))
        return await v2(components, blue_team_url, api_key)
    # V1 — untouched production engine
    from blue_team.adapter import analyze_all_components as v1
    log.info("EngineRouter → Blue Team V1 (%d components)", len(components or []))
    return await v1(components, blue_team_url, api_key)


async def route_component(
    component: dict,
    blue_team_url: str = "",
    api_key: str = "",
    engine: str | None = None,
) -> dict:
    which = active_engine(engine)
    if which == V2:
        from blue_team_v2.adapter import analyze_component as v2
        return await v2(component, blue_team_url, api_key)
    from blue_team.adapter import analyze_component as v1
    return await v1(component, blue_team_url, api_key)
