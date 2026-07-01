"""
Investigator directory + session / lockout / audit state.

No pre-filled accounts: the directory starts empty and investigators create their
own profile (self-service registration → see auth/router.py /api/auth/register).
Registered profiles are persisted to a JSON file so they survive backend restarts.
Passwords are stored only as PBKDF2 hashes — plaintext is never written.
Session / lockout / audit state stays in memory (transient by design).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from collections import deque
from typing import Deque, Dict, List, Optional

from .security import hash_password

# ── Role hierarchy (low → high privilege) ────────────────────────────────────
# Original platform roles + the enterprise collaboration roles (Investigation
# Manager, Read-Only Auditor). ROLE_RANK is declared EXPLICITLY (not positional)
# so adding a role never shifts an existing role's privilege — require_role() is
# the only consumer and it compares ranks. The collaboration capability layer
# (case_management/collab.py) maps each role onto a permission tier.
ROLES = [
    "Read-Only Auditor",
    "Investigator",
    "Senior Investigator",
    "Supervisor",
    "Investigation Manager",
    "Administrator",
]
ROLE_RANK = {
    "Read-Only Auditor": 0,
    "Investigator": 1,
    "Senior Investigator": 2,
    "Supervisor": 3,
    "Investigation Manager": 3,
    "Administrator": 4,
}

# ── Avatar characters ────────────────────────────────────────────────────────
# Investigators get an animal avatar (auto-assigned at registration, changeable
# later). Backend stores the key; the frontend maps it to a character glyph.
AVATARS = [
    "fox", "wolf", "cat", "dog", "owl", "tiger",
    "lion", "bear", "panda", "raccoon", "eagle", "leopard",
]


def _default_avatar(investigator_id: str) -> str:
    h = int(hashlib.sha256((investigator_id or "").encode()).hexdigest(), 16)
    return AVATARS[h % len(AVATARS)]

# Account lockout policy
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60  # 15 minutes

# Where registered investigators are persisted (override with TGIE_AUTH_STORE).
_DATA_FILE = os.getenv(
    "TGIE_AUTH_STORE",
    os.path.join(os.path.dirname(__file__), "_data", "investigators.json"),
)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_]{2,31}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _initials(name: str) -> str:
    parts = [w for w in name.split() if w]
    return ("".join(w[0] for w in parts[:2]) or "?").upper()


class InvestigatorStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._users: Dict[str, dict] = {}
        self._failed: Dict[str, int] = {}
        self._locked_until: Dict[str, float] = {}
        self._sessions: Dict[str, dict] = {}        # jti -> session meta
        self._last_login: Dict[str, float] = {}
        self._audit: Deque[dict] = deque(maxlen=2000)
        self._load()

    # ── persistence ─────────────────────────────────────────────────────────
    def _load(self) -> None:
        try:
            with open(_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._users = data
        except FileNotFoundError:
            self._users = {}
        except Exception:
            self._users = {}

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(_DATA_FILE), exist_ok=True)
            tmp = f"{_DATA_FILE}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._users, f, indent=2)
            os.replace(tmp, _DATA_FILE)
        except Exception:
            pass  # persistence is best-effort; never block auth on disk errors

    # ── registration ────────────────────────────────────────────────────────
    def count(self) -> int:
        return len(self._users)

    def create_user(self, data: dict) -> dict:
        """Validate + persist a new investigator. Raises ValueError on bad input."""
        inv_id = (data.get("investigator_id") or "").strip()
        name = (data.get("name") or "").strip()
        password = data.get("password") or ""
        employee_id = (data.get("employee_id") or "").strip()
        department = (data.get("department") or "").strip()
        role = (data.get("role") or "Investigator").strip()
        branch = (data.get("branch") or "").strip()
        email = (data.get("email") or "").strip()

        if not _ID_RE.match(inv_id):
            raise ValueError("Investigator ID must be 3–32 chars: letters, digits, hyphen or underscore.")
        if len(name) < 2:
            raise ValueError("Please enter your full name.")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters.")
        if not employee_id:
            raise ValueError("Employee ID is required.")
        if not department:
            raise ValueError("Department is required.")
        if role not in ROLES:
            raise ValueError("Invalid role selected.")
        if not branch:
            raise ValueError("Branch is required.")
        if not _EMAIL_RE.match(email):
            raise ValueError("Please enter a valid email address.")

        with self._lock:
            if inv_id.upper() in self._users:
                raise ValueError("An investigator with this ID already exists.")
            if any(u.get("employee_id", "").lower() == employee_id.lower() for u in self._users.values()):
                raise ValueError("This Employee ID is already registered.")

            avatar = data.get("avatar")
            if avatar not in AVATARS:
                avatar = _default_avatar(inv_id)

            record = {
                "investigator_id": inv_id,
                "name": name,
                "employee_id": employee_id,
                "department": department,
                "role": role,
                "branch": branch,
                "email": email,
                "password_hash": hash_password(password),
                "avatar_initials": _initials(name),
                "avatar": avatar,
                "created_at": time.time(),
            }
            self._users[inv_id.upper()] = record
            self._save()
        return record

    # ── lookup ──────────────────────────────────────────────────────────────
    def get(self, investigator_id: str) -> Optional[dict]:
        return self._users.get((investigator_id or "").upper())

    def public_profile(self, investigator_id: str) -> Optional[dict]:
        u = self.get(investigator_id)
        if not u:
            return None
        last = self._last_login.get(u["investigator_id"])
        return {
            "investigator_id": u["investigator_id"],
            "name": u["name"],
            "employee_id": u["employee_id"],
            "department": u["department"],
            "role": u["role"],
            "branch": u["branch"],
            "email": u["email"],
            "avatar_initials": u["avatar_initials"],
            "avatar": u.get("avatar") or _default_avatar(u["investigator_id"]),
            "last_login": last,
        }

    def set_avatar(self, investigator_id: str, avatar: str) -> bool:
        """Persist a user-chosen avatar. Returns False on invalid input."""
        if avatar not in AVATARS:
            return False
        with self._lock:
            u = self.get(investigator_id)
            if not u:
                return False
            u["avatar"] = avatar
            self._save()
        return True

    # ── lockout ─────────────────────────────────────────────────────────────
    def lock_status(self, investigator_id: str) -> Optional[int]:
        """Seconds remaining if locked, else None."""
        uid = (investigator_id or "").upper()
        until = self._locked_until.get(uid)
        if until and until > time.time():
            return int(until - time.time())
        if until:
            self._locked_until.pop(uid, None)
            self._failed.pop(uid, None)
        return None

    def register_failure(self, investigator_id: str) -> int:
        """Increment failure counter, lock if threshold reached. Returns attempts left."""
        uid = (investigator_id or "").upper()
        with self._lock:
            self._failed[uid] = self._failed.get(uid, 0) + 1
            if self._failed[uid] >= MAX_FAILED_ATTEMPTS:
                self._locked_until[uid] = time.time() + LOCKOUT_SECONDS
            return max(0, MAX_FAILED_ATTEMPTS - self._failed[uid])

    def reset_failures(self, investigator_id: str) -> None:
        uid = (investigator_id or "").upper()
        self._failed.pop(uid, None)
        self._locked_until.pop(uid, None)

    # ── sessions ────────────────────────────────────────────────────────────
    def open_session(self, investigator_id: str, ip: str, agent: str) -> str:
        jti = uuid.uuid4().hex
        now = time.time()
        self._last_login[investigator_id] = now
        self._sessions[jti] = {
            "jti": jti,
            "investigator_id": investigator_id,
            "started_at": now,
            "ip": ip,
            "agent": agent,
        }
        return jti

    def session(self, jti: str) -> Optional[dict]:
        return self._sessions.get(jti)

    def close_session(self, jti: str) -> None:
        self._sessions.pop(jti, None)

    def last_login(self, investigator_id: str) -> Optional[float]:
        return self._last_login.get(investigator_id)

    # ── audit log ───────────────────────────────────────────────────────────
    def audit(self, action: str, investigator_id: str, ok: bool, detail: str = "", ip: str = "") -> None:
        self._audit.appendleft({
            "ts": time.time(),
            "action": action,
            "investigator_id": investigator_id,
            "result": "success" if ok else "failure",
            "detail": detail,
            "ip": ip,
        })

    def audit_log(self, investigator_id: Optional[str] = None, limit: int = 50) -> List[dict]:
        items = list(self._audit)
        if investigator_id:
            items = [a for a in items if a["investigator_id"] == investigator_id]
        return items[:limit]


# Module-level singleton
store = InvestigatorStore()
