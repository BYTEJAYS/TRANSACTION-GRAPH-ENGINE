"""Fraud DNA Engine API — under /api/dna (rides the /api proxy, reuses auth)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth.router import require_auth
from case_management.store import store as case_store
from . import engine as E
from .store import store
from .ub_client import UB_MODEL, build_prompt, llm_explain

router = APIRouter(tags=["Fraud DNA"])


class GenerateRequest(BaseModel):
    case_id: str


class CompareRequest(BaseModel):
    case_a: str
    case_b: str


@router.post("/api/dna/generate")
async def generate(body: GenerateRequest, ctx: dict = Depends(require_auth)):
    prof = store.profile(body.case_id)
    if not prof:
        raise HTTPException(404, f"Case '{body.case_id}' not found")
    return prof


@router.get("/api/dna/trends")
async def trends(ctx: dict = Depends(require_auth)):
    return store.trends()


@router.get("/api/dna/high-risk")
async def high_risk(limit: int = Query(10, le=50), ctx: dict = Depends(require_auth)):
    return {"high_risk": store.high_risk(limit)}


@router.post("/api/dna/compare")
async def compare(body: CompareRequest, ctx: dict = Depends(require_auth)):
    res = store.compare(body.case_a, body.case_b)
    if not res:
        raise HTTPException(404, "One or both cases not found")
    return res


@router.get("/api/dna/similar/{case_id}")
async def similar(case_id: str, k: int = Query(5, le=20), ctx: dict = Depends(require_auth)):
    case_exists = store.profile(case_id)
    if not case_exists:
        raise HTTPException(404, f"Case '{case_id}' not found")
    return store.similar(case_id, k)


@router.get("/api/dna/explain/{case_id}")
async def explain(case_id: str, ctx: dict = Depends(require_auth)):
    """Natural-language DNA explanation from the live UB (Ollama) model, with
    graceful fallback to the deterministic heuristic explanation."""
    case = case_store.get(case_id)
    if not case:
        raise HTTPException(404, f"Case '{case_id}' not found")
    sim = store.similar(case_id)
    genes = E.build_genes(case)
    text = await llm_explain(build_prompt(case, genes, sim))
    if text:
        return {"case_id": case_id, "explanation": text, "source": "ub", "model": UB_MODEL}
    return {"case_id": case_id, "explanation": sim["explanation"], "source": "heuristic", "model": None}


@router.get("/api/dna/case/{case_id}")
async def dna_for_case(case_id: str, ctx: dict = Depends(require_auth)):
    prof = store.profile(case_id)
    if not prof:
        raise HTTPException(404, f"Case '{case_id}' not found")
    return prof


@router.get("/api/dna/{dna_id}")
async def get_dna(dna_id: str, ctx: dict = Depends(require_auth)):
    matches = store.find_by_dna(dna_id)
    if not matches:
        raise HTTPException(404, f"DNA '{dna_id}' not found")
    return {"dna_id": dna_id, "profiles": matches, "count": len(matches)}
