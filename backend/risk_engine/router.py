"""Risk Engine API — explainable scoring + admin-tunable config under /api/risk."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.router import require_auth
from .config import config
from .engine import assess, classify_score

router = APIRouter(tags=["Risk"])


class ConfigPatch(BaseModel):
    thresholds: Optional[Dict[str, int]] = None
    weights: Optional[Dict[str, int]] = None
    investigation_threshold: Optional[int] = None
    velocity_window_seconds: Optional[int] = None
    velocity_txn_target: Optional[int] = None
    suppress_false_positives: Optional[bool] = None


class AssessRequest(BaseModel):
    component: Dict[str, Any]      # {node_ids, nodes, edges}


@router.get("/api/risk/config")
async def get_config(ctx: dict = Depends(require_auth)):
    return config.get()


@router.put("/api/risk/config")
async def update_config(body: ConfigPatch, ctx: dict = Depends(require_auth)):
    # Only managers/admins should retune bank policy; investigators can read.
    role = (ctx["user"].get("role") or "").lower()
    if role not in ("manager", "admin", "senior investigator", "administrator"):
        raise HTTPException(403, "Only managers/administrators can change risk policy.")
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    return config.update(patch)


@router.post("/api/risk/config/reset")
async def reset_config(ctx: dict = Depends(require_auth)):
    role = (ctx["user"].get("role") or "").lower()
    if role not in ("manager", "admin", "senior investigator", "administrator"):
        raise HTTPException(403, "Only managers/administrators can change risk policy.")
    return config.reset()


@router.post("/api/risk/assess")
async def assess_component(body: AssessRequest, ctx: dict = Depends(require_auth)):
    """Preview the risk score + explanation for a graph component (no case created)."""
    return assess(body.component)


@router.get("/api/risk/classify")
async def classify(score: int, ctx: dict = Depends(require_auth)):
    return classify_score(score)
