"""
Optional, self-contained FastAPI router for Blue Team V2.

This is ADDITIVE. Including it adds new endpoints under /api/v2/* and never
touches or overrides any existing TGIE route. Wiring is one line in main.py
(see docs/INTEGRATION.md) and is entirely optional — V2 works without it.

    from blue_team_v2.api import router as blue_team_v2_router
    app.include_router(blue_team_v2_router)

Endpoints:
    GET  /api/v2/health
    POST /api/v2/analyze            — V2 analysis of components
    POST /api/v2/shadow             — run V1 + V2 on the same graph, compare
    POST /api/v2/validation-panel   — developer comparison panel
    GET  /api/v2/engine             — which engine the router currently selects
"""
from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter
    from pydantic import BaseModel
except Exception:  # pragma: no cover - FastAPI not present in pure-lib use
    APIRouter = None  # type: ignore

if APIRouter is not None:
    from .adapter import analyze_all_components
    from .engine import __version__
    from .router import active_engine
    from .shadow import run_shadow
    from .validation_panel import panel_for_results, panel_for_shadow

    router = APIRouter(prefix="/api/v2", tags=["Blue Team V2"])

    class ComponentsBody(BaseModel):
        components: list[dict[str, Any]]

    @router.get("/health")
    async def health() -> dict:
        return {"status": "ok", "engine": "blue_team_v2", "version": __version__}

    @router.get("/engine")
    async def which_engine() -> dict:
        return {"active_engine": active_engine(),
                "note": "set ACTIVE_BLUE_TEAM=v2 to route production traffic to V2"}

    @router.post("/analyze")
    async def analyze(body: ComponentsBody) -> dict:
        results = await analyze_all_components(body.components)
        panel = panel_for_results("blue_team_v2", results)
        return {"engine": "blue_team_v2", "version": __version__,
                "results": results, "validation_panel": panel}

    @router.post("/shadow")
    async def shadow(body: ComponentsBody) -> dict:
        result = await run_shadow(body.components)
        result["validation_panel"] = panel_for_shadow(result)
        return result

    @router.post("/validation-panel")
    async def validation_panel(body: ComponentsBody) -> dict:
        results = await analyze_all_components(body.components)
        return panel_for_results("blue_team_v2", results)
else:  # pragma: no cover
    router = None
