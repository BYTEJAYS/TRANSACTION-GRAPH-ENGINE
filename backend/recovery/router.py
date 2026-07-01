"""Recovery Probability Engine API — under /api/recovery (rides the /api proxy,
reuses platform auth)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth.router import require_auth
from .store import store
from .ub_client import UB_MODEL, build_prompt, heuristic_answer, llm_answer

router = APIRouter(tags=["Recovery"])


class AnalyzeRequest(BaseModel):
    case_id: str
    force: bool = False


class AskRequest(BaseModel):
    case_id: str
    question: Optional[str] = None


@router.post("/api/recovery/analyze")
async def analyze(body: AnalyzeRequest, ctx: dict = Depends(require_auth)):
    res = store.analyze(body.case_id, force=body.force)
    if not res:
        raise HTTPException(404, f"Case '{body.case_id}' not found")
    return res


@router.get("/api/recovery/dashboard")
async def dashboard(ctx: dict = Depends(require_auth)):
    return store.dashboard()


@router.get("/api/recovery/case/{case_id}")
async def for_case(case_id: str, ctx: dict = Depends(require_auth)):
    res = store.analyze(case_id)
    if not res:
        raise HTTPException(404, f"Case '{case_id}' not found")
    return res


@router.get("/api/recovery/actions")
async def actions(case_id: str = Query(...), ctx: dict = Depends(require_auth)):
    acts = store.actions(case_id)
    if acts is None:
        raise HTTPException(404, f"Case '{case_id}' not found")
    return {"case_id": case_id, "actions": acts}


@router.get("/api/recovery/simulation")
async def simulation(
    case_id: str = Query(...),
    scenario: str = Query("freeze", pattern="^(freeze|no_action|delay)$"),
    account: Optional[str] = Query(None),
    delay_hours: float = Query(24.0, ge=0, le=720),
    ctx: dict = Depends(require_auth),
):
    res = store.simulate(case_id, scenario, account, delay_hours)
    if not res:
        raise HTTPException(404, f"Case '{case_id}' not found")
    return res


@router.post("/api/recovery/explain")
async def explain(body: AskRequest, ctx: dict = Depends(require_auth)):
    """Plain-banking recovery answer from the live UB model, falling back to the
    deterministic heuristic when Ollama is unreachable."""
    res = store.analyze(body.case_id)
    if not res:
        raise HTTPException(404, f"Case '{body.case_id}' not found")
    text = await llm_answer(build_prompt(res, body.question))
    if text:
        return {"case_id": body.case_id, "answer": text, "source": "ub", "model": UB_MODEL}
    return {"case_id": body.case_id, "answer": heuristic_answer(res, body.question),
            "source": "heuristic", "model": None}
