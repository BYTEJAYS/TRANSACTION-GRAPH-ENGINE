"""
Collaboration layer for the Case Management system.

Pure, stdlib-only helpers shared by the case store + router that turn the
single-user case object into a multi-investigator one:

  • role → capability mapping (RBAC) — recognises BOTH the platform's original
    role names (Investigator / Senior Investigator / Supervisor / Administrator)
    AND the enterprise role names from the collaboration spec (Investigation
    Manager / Read-Only Auditor), so permissions are correct regardless of which
    role an investigator registered under.
  • the default investigation checklist seeded onto every case.
  • participant roles, id + @mention helpers, and ensure_collab_fields() which
    backfills the collaboration containers on any case dict (idempotent).

No new dependencies; mirrors the auth/case module style.
"""

from __future__ import annotations

import re
import time
import uuid
from typing import List, Optional

# ── Role → capability tier ────────────────────────────────────────────────────
ADMIN, MANAGER, INVESTIGATOR, AUDITOR = "admin", "manager", "investigator", "auditor"

_ROLE_TIER = {
    "administrator": ADMIN,
    "admin": ADMIN,
    "investigation manager": MANAGER,
    "supervisor": MANAGER,
    "manager": MANAGER,
    "senior investigator": INVESTIGATOR,
    "investigator": INVESTIGATOR,
    "analyst": INVESTIGATOR,
    "read-only auditor": AUDITOR,
    "read only auditor": AUDITOR,
    "auditor": AUDITOR,
}


def normalize_role(role: Optional[str]) -> str:
    """Map any known role string onto one of the four enterprise tiers."""
    return _ROLE_TIER.get((role or "").strip().lower(), INVESTIGATOR)


# Capabilities (granular so the router can gate each action precisely)
CAP_VIEW = "view"
CAP_CLAIM = "claim"
CAP_COMMENT = "comment"
CAP_EVIDENCE = "evidence"
CAP_TASK = "task"
CAP_HANDOVER = "handover"          # transfer a case you are on
CAP_ASSIGN_OTHERS = "assign_others"
CAP_REASSIGN = "reassign"
CAP_APPROVE = "approve"            # approve / close on manager review
CAP_VIEW_ALL = "view_all"
CAP_OPS = "ops"                    # workload + operational dashboards
CAP_MANAGE_USERS = "manage_users"

_CAPS = {
    ADMIN: {
        CAP_VIEW, CAP_CLAIM, CAP_COMMENT, CAP_EVIDENCE, CAP_TASK, CAP_HANDOVER,
        CAP_ASSIGN_OTHERS, CAP_REASSIGN, CAP_APPROVE, CAP_VIEW_ALL, CAP_OPS, CAP_MANAGE_USERS,
    },
    MANAGER: {
        CAP_VIEW, CAP_CLAIM, CAP_COMMENT, CAP_EVIDENCE, CAP_TASK, CAP_HANDOVER,
        CAP_ASSIGN_OTHERS, CAP_REASSIGN, CAP_APPROVE, CAP_VIEW_ALL, CAP_OPS,
    },
    INVESTIGATOR: {
        CAP_VIEW, CAP_CLAIM, CAP_COMMENT, CAP_EVIDENCE, CAP_TASK, CAP_HANDOVER,
    },
    AUDITOR: {
        CAP_VIEW,   # read-only: view completed investigations, verify blockchain, download
    },
}


def can(role: Optional[str], capability: str) -> bool:
    return capability in _CAPS.get(normalize_role(role), set())


def capabilities_for(role: Optional[str]) -> List[str]:
    """The full capability list for a role — handy for the frontend to hide/show controls."""
    return sorted(_CAPS.get(normalize_role(role), set()))


# ── Default investigation checklist (seeded on every case) ─────────────────────
DEFAULT_CHECKLIST = [
    "Review transaction graph",
    "Validate Fraud DNA pattern",
    "Verify recovery probability",
    "Collect customer complaint / KYC",
    "Contact originating branch",
    "Recommend account freeze",
    "Upload supporting evidence",
    "Anchor evidence to blockchain",
    "Manager review",
    "Close investigation",
]

# ── Participant roles on a case ────────────────────────────────────────────────
PARTICIPANT_ROLES = [
    "Primary Investigator", "Supporting Investigator",
    "Digital Forensics Analyst", "Recovery Specialist", "Observer",
]

# How long an editing lock is honoured before it is considered stale (seconds).
LOCK_TTL_SECONDS = 120
# Open-case count at/above which an investigator is flagged "overloaded".
OVERLOAD_THRESHOLD = 5


# ── helpers ───────────────────────────────────────────────────────────────────
def gen_id(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:10]


_MENTION_RE = re.compile(r"@([A-Za-z0-9][A-Za-z0-9\-_]{2,31})")


def parse_mentions(text: str) -> List[str]:
    """Extract @investigator-id mentions from comment text (uppercased ids)."""
    return sorted({m.upper() for m in _MENTION_RE.findall(text or "")})


def _now() -> float:
    return time.time()


def make_participant(investigator_id: str, name: str, role_on_case: str = "Supporting Investigator",
                     is_primary: bool = False, added_by: str = "system") -> dict:
    return {
        "investigator_id": investigator_id,
        "name": name or investigator_id,
        "role_on_case": role_on_case if role_on_case in PARTICIPANT_ROLES else "Supporting Investigator",
        "is_primary": is_primary,
        "added_by": added_by,
        "added_at": _now(),
    }


def ensure_collab_fields(case: dict) -> bool:
    """Backfill collaboration containers on a case dict. Idempotent — safe to call
    on every load / mutation. Returns True if the case was modified (so the caller
    can decide whether to persist)."""
    changed = False

    if "participants" not in case:
        participants = []
        # an already-assigned case gets its assignee seeded as the primary participant
        if case.get("assigned_to"):
            participants.append({
                "investigator_id": case["assigned_to"],
                "name": case.get("assigned_name") or case["assigned_to"],
                "role_on_case": "Primary Investigator",
                "is_primary": True,
                "added_by": "system",
                "added_at": case.get("updated_at") or _now(),
            })
        case["participants"] = participants
        changed = True

    if "comments" not in case:
        case["comments"] = []
        changed = True

    if "tasks" not in case:
        created = case.get("created_at") or _now()
        case["tasks"] = [
            {
                "id": gen_id("TSK-"), "label": label, "done": False,
                "assignee": None, "assignee_name": None,
                "done_by": None, "done_at": None,
                "created_by": "system", "created_at": created,
            }
            for label in DEFAULT_CHECKLIST
        ]
        changed = True

    if "locks" not in case:
        case["locks"] = {}      # resource -> {holder_id, holder_name, ts}
        changed = True

    return changed
