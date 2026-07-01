"""
TGIE auth + account-intelligence API.

Routes (all under the existing /api proxy so no Vite config change is needed):

  POST /api/auth/login            issue access + refresh JWT
  POST /api/auth/logout           close session
  GET  /api/auth/me               current investigator from token
  POST /api/auth/refresh          mint a fresh access token
  GET  /api/accounts/search       resolve / fuzzy-search accounts
  GET  /api/accounts/{number}     full account investigation record
  GET  /api/investigator/profile  profile panel payload (+ session + activity)
  GET  /api/investigator/activity audit log for the current investigator
"""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel

from .accounts_db import registry
from .security import (
    ACCESS_TTL,
    REFRESH_TTL,
    decode_token,
    encode_token,
    verify_password,
)
from .store import AVATARS, ROLE_RANK, ROLES, store

router = APIRouter(tags=["Auth"])


# ── models ───────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    investigator_id: str
    password: str
    remember_device: bool = False


class RegisterRequest(BaseModel):
    investigator_id: str
    password: str
    name: str
    employee_id: str
    department: str
    role: str = "Investigator"
    branch: str
    email: str
    avatar: Optional[str] = None


class AvatarRequest(BaseModel):
    avatar: str


# ── token dependency ─────────────────────────────────────────────────────────
def _bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def require_auth(authorization: Optional[str] = Header(None)) -> dict:
    token = _bearer(authorization)
    payload = decode_token(token) if token else None
    if not payload or payload.get("typ") != "access":
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = store.get(payload.get("sub", ""))
    if not user:
        raise HTTPException(status_code=401, detail="Investigator not found")
    # ensure the session wasn't logged out
    if payload.get("jti") and not store.session(payload["jti"]):
        raise HTTPException(status_code=401, detail="Session expired")
    return {"payload": payload, "user": user}


def require_role(minimum: str):
    def _dep(ctx: dict = Depends(require_auth)) -> dict:
        if ROLE_RANK.get(ctx["user"]["role"], 0) < ROLE_RANK.get(minimum, 0):
            raise HTTPException(status_code=403, detail="Insufficient clearance")
        return ctx
    return _dep


def _client_ip(req: Request) -> str:
    return (req.client.host if req.client else "") or req.headers.get("x-forwarded-for", "")


# ── auth endpoints ───────────────────────────────────────────────────────────
@router.post("/api/auth/login")
async def login(body: LoginRequest, request: Request):
    inv_id = (body.investigator_id or "").strip()
    ip = _client_ip(request)
    agent = request.headers.get("user-agent", "unknown")

    locked = store.lock_status(inv_id)
    if locked:
        store.audit("login", inv_id, False, "account locked", ip)
        raise HTTPException(
            status_code=423,
            detail=f"Account locked due to failed attempts. Try again in {locked // 60 + 1} min.",
        )

    user = store.get(inv_id)
    if not user or not verify_password(body.password, user["password_hash"]):
        left = store.register_failure(inv_id) if user else 0
        store.audit("login", inv_id, False, "bad credentials", ip)
        detail = "Invalid Investigator ID or password."
        if user and left > 0:
            detail += f" {left} attempt(s) remaining before lockout."
        raise HTTPException(status_code=401, detail=detail)

    store.reset_failures(inv_id)
    real_id = user["investigator_id"]
    jti = store.open_session(real_id, ip, agent)
    store.audit("login", real_id, True, "authenticated", ip)

    access = encode_token(
        {"sub": real_id, "role": user["role"], "jti": jti, "typ": "access"}, ACCESS_TTL
    )
    refresh_ttl = REFRESH_TTL * (4 if body.remember_device else 1)
    refresh = encode_token(
        {"sub": real_id, "jti": jti, "typ": "refresh"}, refresh_ttl
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": ACCESS_TTL,
        "investigator": store.public_profile(real_id),
    }


@router.get("/api/auth/roles")
async def roles():
    """Selectable roles for the create-profile form."""
    return {"roles": ROLES}


@router.post("/api/auth/register", status_code=201)
async def register(body: RegisterRequest, request: Request):
    """Self-service investigator profile creation, then auto sign-in."""
    try:
        user = store.create_user(body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    ip = _client_ip(request)
    agent = request.headers.get("user-agent", "unknown")
    real_id = user["investigator_id"]
    store.audit("register", real_id, True, f"profile created ({user['role']})", ip)

    jti = store.open_session(real_id, ip, agent)
    access = encode_token(
        {"sub": real_id, "role": user["role"], "jti": jti, "typ": "access"}, ACCESS_TTL
    )
    refresh = encode_token({"sub": real_id, "jti": jti, "typ": "refresh"}, REFRESH_TTL)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": ACCESS_TTL,
        "investigator": store.public_profile(real_id),
    }


@router.post("/api/auth/logout")
async def logout(ctx: dict = Depends(require_auth), request: Request = None):
    jti = ctx["payload"].get("jti")
    store.close_session(jti)
    store.audit("logout", ctx["user"]["investigator_id"], True, "session closed",
                _client_ip(request) if request else "")
    return {"status": "logged_out"}


@router.get("/api/auth/me")
async def me(ctx: dict = Depends(require_auth)):
    return {"investigator": store.public_profile(ctx["user"]["investigator_id"])}


@router.post("/api/auth/refresh")
async def refresh(authorization: Optional[str] = Header(None)):
    token = _bearer(authorization)
    payload = decode_token(token) if token else None
    if not payload or payload.get("typ") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    jti = payload.get("jti")
    if not store.session(jti):
        raise HTTPException(status_code=401, detail="Session expired")
    user = store.get(payload.get("sub", ""))
    if not user:
        raise HTTPException(status_code=401, detail="Investigator not found")
    access = encode_token(
        {"sub": user["investigator_id"], "role": user["role"], "jti": jti, "typ": "access"},
        ACCESS_TTL,
    )
    return {"access_token": access, "token_type": "bearer", "expires_in": ACCESS_TTL}


# ── account intelligence ─────────────────────────────────────────────────────
@router.get("/api/accounts/search")
async def search_accounts(
    q: str = Query(..., min_length=1, description="Account / customer / txn / case / evidence id, or name"),
    ctx: dict = Depends(require_auth),
):
    results = registry.search(q, limit=12)
    resolved = registry.resolve(q)
    store.audit("account_search", ctx["user"]["investigator_id"], True, f"q={q}")
    return {
        "query": q,
        "resolved_account": resolved,
        "count": len(results),
        "results": results,
    }


@router.get("/api/accounts/{account_number}")
async def account_detail(account_number: str, ctx: dict = Depends(require_auth)):
    resolved = registry.resolve(account_number)
    rec = registry.get(resolved) if resolved else None
    if not rec:
        raise HTTPException(status_code=404, detail=f"Account '{account_number}' not found")
    store.audit("account_view", ctx["user"]["investigator_id"], True, resolved)
    # attach lightweight linked-account cards
    linked_cards = [
        registry.summary(registry.get(a)) for a in rec["linked_accounts"] if registry.get(a)
    ]
    return {**rec, "linked_account_cards": linked_cards}


# ── investigator profile ─────────────────────────────────────────────────────
@router.get("/api/investigator/profile")
async def investigator_profile(ctx: dict = Depends(require_auth)):
    uid = ctx["user"]["investigator_id"]
    profile = store.public_profile(uid)
    sess = store.session(ctx["payload"].get("jti"))
    return {
        "profile": profile,
        "session": {
            "started_at": sess["started_at"] if sess else None,
            "ip": sess["ip"] if sess else None,
            "expires_at": ctx["payload"].get("exp"),
            "now": int(time.time()),
        },
        "recent_activity": store.audit_log(uid, limit=15),
    }


@router.get("/api/investigator/activity")
async def investigator_activity(
    limit: int = Query(50, le=200), ctx: dict = Depends(require_auth)
):
    return {"activity": store.audit_log(ctx["user"]["investigator_id"], limit=limit)}


@router.get("/api/investigator/avatars")
async def list_avatars():
    """Selectable avatar character keys."""
    return {"avatars": AVATARS}


@router.post("/api/investigator/avatar")
async def set_avatar(body: AvatarRequest, ctx: dict = Depends(require_auth)):
    uid = ctx["user"]["investigator_id"]
    if not store.set_avatar(uid, body.avatar):
        raise HTTPException(status_code=400, detail="Invalid avatar selection.")
    store.audit("avatar_change", uid, True, body.avatar)
    return {"investigator": store.public_profile(uid)}
