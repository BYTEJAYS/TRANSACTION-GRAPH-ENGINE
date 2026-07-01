"""
Cryptographic primitives for TGIE auth — standard library only.

  * PBKDF2-HMAC-SHA256 password hashing (salted, constant-time verify)
  * Compact JWT (HS256) encode / decode with expiry validation

No third-party packages so this drops into the existing venv unchanged.
The signing secret is read from TGIE_AUTH_SECRET; a stable per-host fallback
keeps tokens valid across reloads in local/demo use.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Dict, Optional


# ── Signing secret ───────────────────────────────────────────────────────────
def _load_secret() -> bytes:
    env = os.getenv("TGIE_AUTH_SECRET", "").strip()
    if env:
        return env.encode("utf-8")
    # Deterministic local fallback so a dev restart doesn't invalidate sessions.
    # Override TGIE_AUTH_SECRET in any real deployment.
    return hashlib.sha256(b"tgie-investigator-local-dev-secret-v1").digest()


_SECRET = _load_secret()
_ALG = "HS256"

# Token lifetimes (seconds)
ACCESS_TTL = int(os.getenv("TGIE_ACCESS_TTL", str(60 * 60)))          # 1 hour
REFRESH_TTL = int(os.getenv("TGIE_REFRESH_TTL", str(60 * 60 * 12)))   # 12 hours


# ── base64url helpers ────────────────────────────────────────────────────────
def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


# ── Password hashing (PBKDF2) ────────────────────────────────────────────────
_PBKDF2_ITERATIONS = 240_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters_s, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters_s)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# ── JWT (HS256) ──────────────────────────────────────────────────────────────
def _sign(signing_input: bytes) -> str:
    sig = hmac.new(_SECRET, signing_input, hashlib.sha256).digest()
    return _b64e(sig)


def encode_token(claims: Dict[str, Any], ttl: int) -> str:
    now = int(time.time())
    header = {"alg": _ALG, "typ": "JWT"}
    payload = {**claims, "iat": now, "exp": now + ttl}
    seg_h = _b64e(json.dumps(header, separators=(",", ":")).encode())
    seg_p = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{seg_h}.{seg_p}".encode("ascii")
    return f"{seg_h}.{seg_p}.{_sign(signing_input)}"


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Return the payload if the signature is valid and not expired, else None."""
    try:
        seg_h, seg_p, seg_s = token.split(".")
        signing_input = f"{seg_h}.{seg_p}".encode("ascii")
        if not hmac.compare_digest(_sign(signing_input), seg_s):
            return None
        payload = json.loads(_b64d(seg_p))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None
