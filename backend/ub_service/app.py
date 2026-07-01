"""
FastAPI surface for UB (Phase 12).

`ub_router` can be mounted onto the TGIE core backend:
    from ub_service import ub_router
    app.include_router(ub_router)
or run standalone:
    python -m ub_service        (uvicorn on :8000, all routes under /ub)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

# Make the top-level `ub` package importable (TGIE/ub) regardless of CWD.
_TGIE_ROOT = Path(__file__).resolve().parents[2]
if str(_TGIE_ROOT) not in sys.path:
    sys.path.insert(0, str(_TGIE_ROOT))

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ub.ai_core import UBBrain, modes          # type: ignore
from ub.ollama_service import OllamaError        # type: ignore

ub_router = APIRouter(prefix="/ub", tags=["UB — Universal Brain"])

# Lazy singleton so importing the router never blocks on Ollama.
_brain: Optional[UBBrain] = None


def get_brain() -> UBBrain:
    global _brain
    if _brain is None:
        # Auto-refresh keeps UB's knowledge in step with the codebase: when set, every
        # turn cheaply checks an mtime/size signature and re-indexes only if the project
        # changed. Default OFF so a demo question never blocks on a re-index; enable with
        # UB_AUTO_REFRESH=1 during development, or call POST /ub/reindex manually.
        import os
        auto = os.getenv("UB_AUTO_REFRESH", "0").strip().lower() in ("1", "true", "yes")
        _brain = UBBrain(auto_refresh=auto)
    return _brain


# ── request/response models ──────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str = Field(..., description="User question about TGIE")
    mode: str = Field("chat", description="chat|founder|developer|presentation|demo|judge")
    session_id: Optional[str] = Field(None, description="Conversation id for multi-turn memory")


class ModeRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class SwitchModelRequest(BaseModel):
    model: str


class Source(BaseModel):
    path: str
    component: str
    lines: str
    score: float


class ChatResponse(BaseModel):
    mode: str
    answer: str
    sources: List[Source] = []
    model: str
    session_id: Optional[str] = None


def _answer(message: str, mode: str, session_id: Optional[str]) -> dict:
    try:
        return get_brain().ask(message, mode=mode, session_id=session_id)
    except OllamaError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"UB error: {e}")


def _grounding_footer(res: dict) -> str:
    """Judge-mode transparency line: confidence + what the answer is grounded on.
    Confidence is heuristic — highest when a vetted curated answer grounded the
    response, then by best retrieval score, lowest when nothing was retrieved."""
    srcs = res.get("sources") or []
    verified = int(res.get("verified_answers", 0) or 0)
    top = max((s.get("score", 0.0) for s in srcs), default=0.0)
    if verified > 0:
        conf = "High — grounded on vetted project answers"
    elif top >= 0.6:
        conf = "Medium — grounded on retrieved source"
    elif srcs:
        conf = "Low — weak retrieval; verify against source"
    else:
        conf = "Low — answered without retrieval"
    paths = ", ".join(dict.fromkeys(s.get("path", "?") for s in srcs[:3])) or "project summaries"
    vtxt = f" · {verified} verified answer{'s' if verified != 1 else ''} used" if verified else ""
    return f"\n\n— Confidence: {conf}{vtxt} · sources: {paths}"


# ── chat + modes ──────────────────────────────────────────────────────────────
@ub_router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    mode = req.mode if req.mode in modes.MODES else "chat"
    return _answer(req.message, mode, req.session_id)


@ub_router.post("/chat/stream")
def chat_stream(req: ChatRequest):
    mode = req.mode if req.mode in modes.MODES else "chat"
    def gen():
        try:
            for tok in get_brain().ask_stream(req.message, mode=mode, session_id=req.session_id):
                yield tok
        except OllamaError as e:
            yield f"\n[UB unavailable: {e}]"
    return StreamingResponse(gen(), media_type="text/plain")


@ub_router.post("/founder", response_model=ChatResponse)
def founder(req: ModeRequest):
    return _answer(req.message, "founder", req.session_id)


@ub_router.post("/developer", response_model=ChatResponse)
def developer(req: ModeRequest):
    return _answer(req.message, "developer", req.session_id)


@ub_router.post("/presentation", response_model=ChatResponse)
def presentation(req: ModeRequest):
    return _answer(req.message, "presentation", req.session_id)


@ub_router.post("/judge", response_model=ChatResponse)
def judge(req: ModeRequest):
    res = _answer(req.message, "judge", req.session_id)
    # Judge mode appends a transparency footer (confidence + grounding sources).
    res["answer"] = res.get("answer", "").rstrip() + _grounding_footer(res)
    return res


@ub_router.post("/demo")
def demo(req: Optional[ModeRequest] = None):
    sid = req.session_id if req else None
    try:
        return {"demo": get_brain().demo(session_id=sid)}
    except OllamaError as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── introspection / control ─────────────────────────────────────────────────
@ub_router.get("/health")
def health():
    return get_brain().client.health()


@ub_router.get("/model")
def model():
    h = get_brain().client.health()
    return {"active_model": h.get("model"), "embed_model": h.get("embed_model"),
            "available_models": h.get("models", [])}


@ub_router.post("/model")
def switch_model(req: SwitchModelRequest):
    return {"active_model": get_brain().client.switch_model(req.model)}


@ub_router.get("/context")
def context():
    return get_brain().context_report()


@ub_router.get("/modes")
def list_modes():
    return {"modes": list(modes.MODES.keys()), "demo_outline": modes.DEMO_OUTLINE}


@ub_router.get("/sources")
def sources(q: str, k: int = 6):
    try:
        return {"query": q, "sources": get_brain().engine.sources(q, k=k)}
    except OllamaError as e:
        raise HTTPException(status_code=503, detail=str(e))


@ub_router.post("/reindex")
def reindex():
    """Force a knowledge re-index (Phase 11). Runs synchronously — may take a minute."""
    from ub.knowledge_engine.summarizer import generate_all  # type: ignore
    generate_all()
    meta = get_brain().engine.build(verbose=False)
    get_brain()._summaries_cache = None
    return {"status": "reindexed", "chunk_count": meta["chunk_count"],
            "file_count": meta["file_count"]}


# ── standalone app ──────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(title="UB — TGIE Universal Brain", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"])
    app.include_router(ub_router)

    @app.get("/")
    def root():
        return {"service": "UB — Universal Brain", "docs": "/docs", "routes": "/ub/*"}
    return app


app = create_app()
