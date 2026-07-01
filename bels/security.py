"""
Security primitives for BELS: hashing, digital signatures, RBAC and an operational
audit log.

Signatures use Ed25519 when `cryptography` is installed (preferred, asymmetric, the
same scheme a production bank deployment would use). If the library is unavailable we
fall back to an HMAC-SHA256 keyed signature so the system still runs end-to-end.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from . import config

# ── Hashing ────────────────────────────────────────────────────────────────────
def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_of_obj(obj: Any) -> str:
    """Deterministic SHA-256 of a JSON-serialisable object (sorted keys)."""
    return sha256_hex(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode())


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Digital signatures ──────────────────────────────────────────────────────────
try:  # Preferred: real asymmetric signatures.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives import serialization

    _HAVE_ED25519 = True
except Exception:  # pragma: no cover - depends on environment
    _HAVE_ED25519 = False


class Signer:
    """
    Signs/verifies anchor payloads. The signature is embedded in each on-chain record
    so any party can later verify who attested to the evidence.
    """

    def __init__(self) -> None:
        self.scheme = "ed25519" if _HAVE_ED25519 else "hmac-sha256"
        config.ensure_dirs()
        if _HAVE_ED25519:
            self._load_or_create_ed25519()
        else:
            self._secret = config.SIGNING_SECRET.encode()
            self.public_key_id = sha256_hex(self._secret)[:16]

    # -- Ed25519 ---------------------------------------------------------------
    def _load_or_create_ed25519(self) -> None:
        key_path = config.KEYS_DIR / "bels_ed25519.pem"
        if key_path.exists():
            self._priv = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        else:
            self._priv = Ed25519PrivateKey.generate()
            key_path.write_bytes(
                self._priv.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
            try:
                os.chmod(key_path, 0o600)
            except OSError:
                pass
        pub = self._priv.public_key()
        self._pub_bytes = pub.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.public_key_id = sha256_hex(self._pub_bytes)[:16]

    def public_key_pem(self) -> str:
        if _HAVE_ED25519:
            pub = self._priv.public_key()
            return pub.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode()
        return f"hmac-keyid:{self.public_key_id}"

    def sign(self, message: str) -> str:
        if _HAVE_ED25519:
            return self._priv.sign(message.encode()).hex()
        return hmac.new(self._secret, message.encode(), hashlib.sha256).hexdigest()

    def verify(self, message: str, signature: str) -> bool:
        try:
            if _HAVE_ED25519:
                self._priv.public_key().verify(bytes.fromhex(signature), message.encode())
                return True
            expected = hmac.new(self._secret, message.encode(), hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, signature)
        except Exception:
            return False


# Process-wide signer.
signer = Signer()


# ── Role-based access control ───────────────────────────────────────────────────
# Coarse capability model; a real deployment maps these to the bank's IAM.
ROLE_PERMISSIONS: Dict[str, set] = {
    "admin":        {"upload", "register", "verify", "read", "export", "transfer", "archive", "report", "demo"},
    "investigator": {"upload", "register", "verify", "read", "export", "report"},
    "auditor":      {"verify", "read", "export", "report"},
    "compliance":   {"verify", "read", "export", "report", "archive"},
    "viewer":       {"read"},
}


def can(role: str, action: str) -> bool:
    return action in ROLE_PERMISSIONS.get((role or "").lower(), set())


class AccessDenied(Exception):
    pass


def require(role: str, action: str) -> None:
    if not can(role, action):
        raise AccessDenied(f"Role '{role}' is not permitted to '{action}'.")


# ── Operational audit log (separate from the blockchain custody trail) ───────────
class AuditLogger:
    """Append-only JSONL log of every privileged API action, for SOC/compliance."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        config.ensure_dirs()

    def record(self, action: str, actor: str, role: str, target: Optional[str] = None, **extra: Any) -> None:
        entry = {
            "ts": utc_now_iso(),
            "action": action,
            "actor": actor,
            "role": role,
            "target": target,
            **extra,
        }
        line = json.dumps(entry, sort_keys=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def tail(self, n: int = 200) -> list:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(x) for x in lines[-n:]]


audit_log = AuditLogger(config.AUDIT_LOG_FILE)
