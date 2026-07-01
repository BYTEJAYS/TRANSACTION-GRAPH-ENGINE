"""
UBBrain — the orchestrator (Phases 3, 6-10).

Ties modes + conversation memory + the knowledge engine + Ollama into a single
"ask UB anything about TGIE" interface. Every answer is:
    retrieve relevant TGIE knowledge → build a grounded prompt (persona + summaries
    + retrieved chunks + recent history) → generate with the local model → return
    answer + the source files it drew from.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from . import modes
from .conversation import ConversationManager

try:
    from ..ollama_service import OllamaClient
    from ..knowledge_engine import KnowledgeEngine
    from ..knowledge_engine.summarizer import DATA_DIR
except ImportError:  # running as top-level package
    from ub.ollama_service import OllamaClient            # type: ignore
    from ub.knowledge_engine import KnowledgeEngine        # type: ignore
    from ub.knowledge_engine.summarizer import DATA_DIR    # type: ignore


def _greeting_word(hour: int) -> str:
    """Time-of-day greeting from the local clock. Night counts as 'Good Evening'."""
    if 5 <= hour < 12:
        return "Good Morning"
    if 12 <= hour < 17:
        return "Good Afternoon"
    return "Good Evening"


def _runtime_context(now: Optional[datetime] = None) -> str:
    """A live context block injected into EVERY prompt so the assistant can greet by
    the actual local time (the model has no clock of its own) and stay in the Union
    Bank demonstration frame. Computed fresh on every turn."""
    now = now or datetime.now()
    return (
        "RUNTIME CONTEXT (live system state — use this, never guess the time):\n"
        f"- Current local date & time: {now.strftime('%A, %d %B %Y, %I:%M %p')}\n"
        f"- Time-appropriate greeting to use: {_greeting_word(now.hour)}\n"
        "- Setting: a live Union Bank TGIE demonstration. Greet and address visitors "
        "accordingly; remember any name or title the visitor gives."
    )


def _load_summaries(data_dir: Path = DATA_DIR) -> str:
    """Compact project/architecture summaries injected into every prompt for grounding."""
    parts = []
    for name in ("project_summary.json", "architecture_summary.json"):
        p = data_dir / name
        if p.exists():
            try:
                parts.append(f"=== {name} ===\n{json.dumps(json.loads(p.read_text()), indent=1)}")
            except Exception:
                pass
    return "\n\n".join(parts)[:4000]


_QA_STOP = {
    "the", "a", "an", "is", "are", "do", "does", "did", "of", "to", "and", "in", "for",
    "how", "what", "why", "it", "this", "that", "you", "your", "our", "we", "with",
    "explain", "tell", "about", "can", "should", "would", "there", "have", "has", "was",
}


def _load_curated_qa(data_dir: Path = DATA_DIR) -> List[Dict[str, str]]:
    """The judge_questions.json bank — vetted Q&A used to GROUND cross-questioning so
    UB answers known questions from authoritative facts, not just code retrieval."""
    p = data_dir / "judge_questions.json"
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text())
        out: List[Dict[str, str]] = []
        for cat in d.get("categories", {}).values():
            for qa in cat:
                if isinstance(qa, dict) and qa.get("q") and qa.get("a"):
                    out.append({"q": qa["q"], "a": qa["a"]})
        return out
    except Exception:
        return []


def _qa_tokens(s: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in _QA_STOP and len(t) > 2}


def _relevant_qa(query: str, qa_list: List[Dict[str, str]], top: int = 3,
                 min_overlap: int = 2) -> List[Dict[str, str]]:
    """Token-overlap match (stdlib, fast) — the curated Q&A closest to the question."""
    q = _qa_tokens(query)
    if not q:
        return []
    scored = [(len(q & _qa_tokens(qa["q"])), qa) for qa in qa_list]
    scored = [s for s in scored if s[0] >= min_overlap]
    scored.sort(key=lambda x: -x[0])
    return [qa for _, qa in scored[:top]]


class UBBrain:
    def __init__(self, client: Optional[OllamaClient] = None,
                 engine: Optional[KnowledgeEngine] = None,
                 conversations: Optional[ConversationManager] = None,
                 auto_refresh: bool = False):
        self.client = client or OllamaClient()
        self.engine = engine or KnowledgeEngine(self.client)
        self.conv = conversations or ConversationManager()
        self.auto_refresh = auto_refresh
        self._summaries_cache: Optional[str] = None
        self._curated_qa: List[Dict[str, str]] = _load_curated_qa()

    # ── prompt assembly ─────────────────────────────────────────────────────
    def _summaries(self) -> str:
        if self._summaries_cache is None:
            self._summaries_cache = _load_summaries()
        return self._summaries_cache

    def _route(self, mode: str, message: str) -> str:
        """Pick the effective persona. `chat` auto-falls to `conversation` on small talk."""
        if mode == "chat" and modes.is_smalltalk(message):
            return "conversation"
        return mode if mode in modes.MODES else "chat"

    def _build_messages(self, mode: str, user_msg: str, *,
                        session_id: Optional[str], retrieval_query: Optional[str] = None
                        ) -> (List[Dict[str, str]], List[Dict], str, int):
        eff_mode = self._route(mode, user_msg)
        p = modes.params(eff_mode)
        system = modes.system_prompt(eff_mode)
        sources: List[Dict] = []
        grounding: List[str] = []
        qa_n = 0

        # Retrieval only when the mode wants it (conversation uses k=0 → pure social turn).
        if p["k"] > 0:
            query = retrieval_query or user_msg
            context = self.engine.context_block(query, k=p["k"]) if self.engine.store.ready() else ""
            sources = self.engine.sources(query, k=p["k"]) if self.engine.store.ready() else []
            if self._summaries():
                grounding.append("PROJECT SUMMARIES:\n" + self._summaries())
            # Authoritative vetted answers for any known cross-question — these
            # are the ground truth and OUTRANK raw code retrieval on the facts,
            # so UB doesn't drift on questions we've already answered carefully.
            qa_hits = _relevant_qa(query, self._curated_qa)
            qa_n = len(qa_hits)
            if qa_hits:
                block = "\n\n".join(f"Q: {qa['q']}\nA: {qa['a']}" for qa in qa_hits)
                grounding.append(
                    "VERIFIED PROJECT ANSWERS (authoritative — prefer these for the facts "
                    "over raw code if they conflict):\n" + block)
            if context:
                grounding.append("RETRIEVED TGIE KNOWLEDGE (cite these paths):\n" + context)
            else:
                grounding.append("(Knowledge index not built yet — answer from summaries and say "
                                 "the index should be built with `python -m ub index`.)")

        # Runtime context (current local time → correct greeting) is injected into
        # EVERY mode, including the no-retrieval conversation/greeting turn.
        sys_content = system + "\n\n" + _runtime_context()
        if grounding:
            sys_content += "\n\n" + "\n\n".join(grounding)
        messages: List[Dict[str, str]] = [{"role": "system", "content": sys_content}]
        if session_id:
            messages.extend(self.conv.get(session_id, mode).history())
        messages.append({"role": "user", "content": user_msg})
        return messages, sources, eff_mode, qa_n

    # ── public API ──────────────────────────────────────────────────────────
    def ask(self, message: str, *, mode: str = "chat", session_id: Optional[str] = None,
            retrieval_query: Optional[str] = None) -> Dict:
        if self.auto_refresh:
            self.engine.refresh_if_stale()
        messages, sources, eff_mode, qa_n = self._build_messages(mode, message, session_id=session_id,
                                                                retrieval_query=retrieval_query)
        temp = modes.params(eff_mode)["temperature"]
        answer = self.client.chat(messages, options={"temperature": temp})
        if session_id:
            self.conv.record(session_id, message, answer, eff_mode)
        return {"mode": eff_mode, "requested_mode": mode, "answer": answer, "sources": sources,
                "verified_answers": qa_n, "model": self.client.model, "session_id": session_id}

    def ask_stream(self, message: str, *, mode: str = "chat",
                   session_id: Optional[str] = None) -> Iterable[str]:
        messages, _, eff_mode, _ = self._build_messages(mode, message, session_id=session_id)
        temp = modes.params(eff_mode)["temperature"]
        buf = []
        for tok in self.client.chat_stream(messages, options={"temperature": temp}):
            buf.append(tok)
            yield tok
        if session_id:
            self.conv.record(session_id, message, "".join(buf), eff_mode)

    def demo(self, *, session_id: Optional[str] = None) -> List[Dict]:
        """Phase 9: auto-present TGIE across the scripted outline."""
        out = []
        for step in modes.DEMO_OUTLINE:
            res = self.ask(step, mode="demo", session_id=session_id, retrieval_query=step)
            out.append({"section": step, "content": res["answer"], "sources": res["sources"]})
        return out

    # convenience wrappers (Phase 12 endpoints map onto these)
    def founder(self, message: str, **kw) -> Dict:      return self.ask(message, mode="founder", **kw)
    def developer(self, message: str, **kw) -> Dict:    return self.ask(message, mode="developer", **kw)
    def presentation(self, message: str, **kw) -> Dict: return self.ask(message, mode="presentation", **kw)
    def judge(self, message: str, **kw) -> Dict:        return self.ask(message, mode="judge", **kw)

    def context_report(self) -> Dict:
        return {"knowledge": self.engine.stats(), "ollama": self.client.health(),
                "modes": list(modes.MODES.keys())}
