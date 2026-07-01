"""
Conversation + session memory (Phase 3).

Lightweight, in-process session store: multi-turn history per session id, with a
rolling window so long technical discussions stay within the model context. Optional
JSON persistence so a session survives a process restart.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

SESSION_DIR = Path(__file__).resolve().parents[1] / "data" / "sessions"


@dataclass
class Message:
    role: str            # 'user' | 'assistant'
    content: str
    mode: str = "chat"
    ts: float = field(default_factory=time.time)


@dataclass
class Session:
    session_id: str
    mode: str = "chat"
    messages: List[Message] = field(default_factory=list)
    created: float = field(default_factory=time.time)

    def add(self, role: str, content: str, mode: Optional[str] = None) -> None:
        self.messages.append(Message(role, content, mode or self.mode))

    def history(self, max_turns: int = 8) -> List[Dict[str, str]]:
        """Last N messages as chat-format dicts (system prompt added by the brain)."""
        recent = self.messages[-max_turns * 2:]
        return [{"role": m.role, "content": m.content} for m in recent]

    def to_dict(self) -> Dict:
        return {"session_id": self.session_id, "mode": self.mode, "created": self.created,
                "messages": [vars(m) for m in self.messages]}


class ConversationManager:
    def __init__(self, persist: bool = True, session_dir: Path = SESSION_DIR):
        self._sessions: Dict[str, Session] = {}
        self.persist = persist
        self.session_dir = session_dir
        if persist:
            self.session_dir.mkdir(parents=True, exist_ok=True)

    def get(self, session_id: str, mode: str = "chat") -> Session:
        if session_id not in self._sessions:
            loaded = self._load(session_id)
            self._sessions[session_id] = loaded or Session(session_id, mode)
        s = self._sessions[session_id]
        if mode:
            s.mode = mode
        return s

    def record(self, session_id: str, user: str, assistant: str, mode: str = "chat") -> None:
        s = self.get(session_id, mode)
        s.add("user", user, mode)
        s.add("assistant", assistant, mode)
        if self.persist:
            self._save(s)

    def reset(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        if self.persist:
            p = self.session_dir / f"{session_id}.json"
            if p.exists():
                p.unlink()

    def info(self, session_id: str) -> Dict:
        s = self._sessions.get(session_id)
        if not s:
            return {"session_id": session_id, "exists": False}
        return {"session_id": session_id, "exists": True, "mode": s.mode,
                "turns": len(s.messages) // 2, "messages": len(s.messages)}

    # ── persistence ─────────────────────────────────────────────────────────
    def _save(self, s: Session) -> None:
        (self.session_dir / f"{s.session_id}.json").write_text(json.dumps(s.to_dict(), indent=2))

    def _load(self, session_id: str) -> Optional[Session]:
        p = self.session_dir / f"{session_id}.json"
        if not p.exists():
            return None
        try:
            d = json.loads(p.read_text())
            s = Session(d["session_id"], d.get("mode", "chat"), created=d.get("created", time.time()))
            s.messages = [Message(**m) for m in d.get("messages", [])]
            return s
        except Exception:
            return None
