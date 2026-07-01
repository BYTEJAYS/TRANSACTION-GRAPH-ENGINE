from __future__ import annotations
"""
Evolution Engine API — investigator-facing routes.

Mounted onto the Red Team FastAPI app. Follows the project response wrapper
({data, error, meta}), rejects unknown fields, and uses semantic status codes.

The ONLY route that can cause Blue-relevant "learning" is the approve endpoint,
and it merely appends to the hardening backlog — it never modifies Blue Team V2.
"""
import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from red_team.evolution import library
from red_team.evolution.difficulty import LEVELS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/evolution", tags=["evolution"])

_engine = None
_runner = None


def _get_engine():
    """Lazy singleton — building it imports Blue Team V2 (heavy)."""
    global _engine
    if _engine is None:
        from red_team.evolution.engine import EvolutionEngine
        _engine = EvolutionEngine()
    return _engine


def _get_runner():
    """Shared background runner over the same engine the API serves."""
    global _runner
    if _runner is None:
        from red_team.evolution.runner import BackgroundCampaignRunner
        _runner = BackgroundCampaignRunner(_get_engine())
    return _runner


def _ok(data: Any, meta: dict | None = None, status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content={"data": data, "error": None,
                                                     "meta": meta or {}})


def _err(code: str, message: str, status: int, field: str | None = None) -> HTTPException:
    detail = {"code": code, "message": message}
    if field:
        detail["field"] = field
    return HTTPException(status_code=status, detail=detail)


# ── request models (reject unknown fields) ────────────────────────────────────
class AttackRequest(BaseModel, extra="forbid"):
    family: str | None = Field(default=None, description="specific attack family")
    category: str | None = Field(default=None, description="weakness category to target")
    difficulty: str = Field(default="medium")


class CampaignRequest(BaseModel, extra="forbid"):
    n_attacks: int = Field(default=10, ge=1, le=100)
    difficulty: str = Field(default="medium")


class AutoStartRequest(BaseModel, extra="forbid"):
    difficulty: str = Field(default="medium")
    interval_seconds: float = Field(default=2.0, ge=0.1, le=3600)
    rotate_difficulty: bool = Field(default=False)


class LLMConfigRequest(BaseModel, extra="forbid"):
    enabled: bool


class DecisionRequest(BaseModel, extra="forbid"):
    investigator_id: str = Field(min_length=1, max_length=128)
    notes: str | None = Field(default=None, max_length=2000)


def _validate_difficulty(level: str) -> None:
    if level.strip().lower() not in LEVELS:
        raise _err("INVALID_DIFFICULTY", f"difficulty must be one of {LEVELS}", 422, "difficulty")


# ── attack / campaign ─────────────────────────────────────────────────────────
@router.post("/attacks")
def create_attack(req: AttackRequest) -> JSONResponse:
    _validate_difficulty(req.difficulty)
    if req.family and req.family not in library.FAMILIES:
        raise _err("UNKNOWN_FAMILY", f"unknown family {req.family!r}", 422, "family")
    if req.category and req.category not in library.CATEGORIES:
        raise _err("UNKNOWN_CATEGORY", f"unknown category {req.category!r}", 422, "category")
    run = _get_engine().run_attack(family=req.family, category=req.category,
                                   difficulty=req.difficulty)
    return _ok(run.to_dict(), status=201)


@router.post("/campaigns")
def run_campaign(req: CampaignRequest) -> JSONResponse:
    _validate_difficulty(req.difficulty)
    state = _get_engine().run_campaign(req.n_attacks, req.difficulty)
    return _ok(state, meta={"n_attacks": req.n_attacks}, status=201)


# ── continuous background campaign ────────────────────────────────────────────
@router.post("/campaigns/auto/start")
def auto_start(req: AutoStartRequest) -> JSONResponse:
    _validate_difficulty(req.difficulty)
    st = _get_runner().start(req.difficulty, req.interval_seconds, req.rotate_difficulty)
    return _ok(st.__dict__)


@router.post("/campaigns/auto/stop")
def auto_stop() -> JSONResponse:
    if _runner is None:
        return _ok({"running": False, "note": "runner was never started"})
    return _ok(_get_runner().stop().__dict__)


@router.get("/campaigns/auto/status")
def auto_status() -> JSONResponse:
    if _runner is None:
        return _ok({"running": False})
    return _ok(_get_runner().status().__dict__)


@router.get("/attacks/{attack_id}")
def get_attack(attack_id: str) -> JSONResponse:
    run = _get_engine().runs.get(attack_id)
    if run is None:
        raise _err("ATTACK_NOT_FOUND", "no such attack", 404)
    return _ok(run.to_dict())


# ── intelligence views ────────────────────────────────────────────────────────
@router.get("/dashboard")
def dashboard() -> JSONResponse:
    return _ok(_get_engine().dashboard_state())


@router.get("/weakness")
def weakness() -> JSONResponse:
    return _ok(_get_engine().weakness.report())


@router.get("/metrics")
def metrics() -> JSONResponse:
    eng = _get_engine()
    return _ok(eng.metrics.snapshot(eng.weakness.report()))


# ── Ollama adversarial strategist ─────────────────────────────────────────────
@router.get("/llm/status")
def llm_status() -> JSONResponse:
    eng = _get_engine()
    return _ok({**eng.llm.status(), "use_llm": eng.use_llm,
                "strategy_memory": eng.memory.stats()})


@router.post("/llm/config")
def llm_config(req: LLMConfigRequest) -> JSONResponse:
    eng = _get_engine()
    state = eng.set_llm(req.enabled)
    if req.enabled and not state["available"]:
        return _ok({**state, "note": "Ollama unavailable — run `ollama serve` and pull "
                    f"{eng.llm.model}. Strategist stays off; heuristic mutation is used."})
    return _ok(state)


@router.get("/learning_curve")
def learning_curve() -> JSONResponse:
    return _ok(_get_engine().metrics.learning_curve())


@router.get("/library")
def get_library() -> JSONResponse:
    fams = [{"name": f.name, "category": f.category, "description": f.description}
            for f in library.FAMILIES.values()]
    return _ok({"families": fams, "categories": library.CATEGORIES,
                "difficulty_levels": LEVELS}, meta={"count": len(fams)})


# ── investigator gate ─────────────────────────────────────────────────────────
@router.get("/alerts")
def list_alerts(status: str | None = Query(default=None,
               pattern="^(pending|approved|rejected)$")) -> JSONResponse:
    alerts = _get_engine().gate.list_alerts(status=status)
    return _ok([a.to_dict() for a in alerts], meta={"count": len(alerts), "filter": status})


@router.post("/alerts/{alert_id}/approve")
def approve_alert(alert_id: str, req: DecisionRequest) -> JSONResponse:
    """Investigator approves a missed attack → hardening backlog. Blue NOT modified."""
    entry = _get_engine().gate.approve(alert_id, req.investigator_id, req.notes)
    if entry is None:
        raise _err("ALERT_NOT_PENDING", "alert not found or already decided", 409)
    return _ok({"approved": True, "backlog_entry": entry,
                "note": "Recorded for Blue Team hardening review. Blue Team V2 was NOT auto-trained."})


@router.post("/alerts/{alert_id}/reject")
def reject_alert(alert_id: str, req: DecisionRequest) -> JSONResponse:
    alert = _get_engine().gate.reject(alert_id, req.investigator_id, req.notes)
    if alert is None:
        raise _err("ALERT_NOT_PENDING", "alert not found or already decided", 409)
    return _ok({"rejected": True, "alert_id": alert_id})


@router.get("/backlog")
def hardening_backlog() -> JSONResponse:
    backlog = _get_engine().gate.hardening_backlog()
    return _ok(backlog, meta={"count": len(backlog),
                              "note": "Investigator-approved patterns awaiting Blue Team hardening."})


# ── dashboard UI ──────────────────────────────────────────────────────────────
@router.get("/ui", response_class=HTMLResponse)
def dashboard_ui() -> HTMLResponse:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
    try:
        with open(path, encoding="utf-8") as fh:
            return HTMLResponse(fh.read())
    except OSError:
        raise _err("UI_UNAVAILABLE", "dashboard asset missing", 500)


def mount(app) -> None:
    """Attach the evolution router to an existing FastAPI app."""
    app.include_router(router)
