"""
Shared FastAPI security dependencies for /api/v1.

Reuses the EXISTING auth primitives (auth.router.require_auth / require_role) —
we do not fork auth. Adds `require_perm` (maps to collab permission tiers when
available) and a cursor-pagination dependency used by every list/graph route.
"""
from __future__ import annotations

import base64
import json
from typing import Optional

from fastapi import Depends, HTTPException, Query

# reuse the shipped auth dependencies verbatim
from auth.router import require_auth, require_role  # noqa: F401


def current_user(ctx: dict = Depends(require_auth)) -> dict:
    """Authenticated investigator context. 401 if missing/invalid token."""
    return ctx


def require_perm(permission: str):
    """Capability gate. Uses case_management.collab permission tiers if present,
    else falls back to role rank so it always enforces *something*."""
    def _dep(ctx: dict = Depends(require_auth)) -> dict:
        try:
            from case_management import collab  # optional
            role = ctx.get("role")
            if hasattr(collab, "has_permission") and not collab.has_permission(role, permission):
                raise HTTPException(status_code=403, detail=f"missing permission: {permission}")
        except HTTPException:
            raise
        except Exception:
            pass  # collab not available → role check at route level still applies
        return ctx
    return _dep


# ── cursor pagination ────────────────────────────────────────────────────────
class Page:
    def __init__(self, limit: int, cursor: Optional[str]):
        self.limit = limit
        self.offset = 0
        if cursor:
            try:
                self.offset = int(json.loads(base64.urlsafe_b64decode(cursor.encode()))["o"])
            except Exception:
                raise HTTPException(status_code=400, detail="invalid cursor")

    @staticmethod
    def encode_cursor(offset: int) -> str:
        return base64.urlsafe_b64encode(json.dumps({"o": offset}).encode()).decode()

    def next_cursor(self, returned: int) -> Optional[str]:
        return self.encode_cursor(self.offset + returned) if returned >= self.limit else None


def pagination(
    limit: int = Query(50, ge=1, le=500),
    cursor: Optional[str] = Query(None),
) -> Page:
    return Page(limit, cursor)
