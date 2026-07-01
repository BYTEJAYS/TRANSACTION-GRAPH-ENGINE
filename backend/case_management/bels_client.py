"""
BELS blockchain client — thin HTTP wrapper around the live BELS evidence ledger
service (standalone on :8200, router mounted with no prefix → /evidence/...).

Used to anchor a case's evidence bundle hash on-chain and verify it later. Every
call is best-effort: on any failure (service down, timeout, bad response) it
returns None so the caller can fall back to a self-contained internal anchor and
never 500s. The user chose LIVE BELS; the fallback only guards availability.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

BELS_URL = os.getenv("BELS_URL", "http://127.0.0.1:8200").rstrip("/")
_TIMEOUT = float(os.getenv("BELS_TIMEOUT", "4.0"))


def healthy() -> bool:
    try:
        r = httpx.get(f"{BELS_URL}/health", timeout=_TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


def register(file_hash: str, case_id: str, filename: str, evidence_type: str,
             owner: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[dict]:
    """Anchor an already-computed SHA-256 on the BELS chain. Returns the evidence
    record (with anchor_tx_id / block_index / block_hash) or None."""
    try:
        r = httpx.post(
            f"{BELS_URL}/evidence/register",
            json={
                "file_hash": file_hash,
                "case_id": case_id,
                "filename": filename,
                "evidence_type": evidence_type,
                "owner": owner,
                "role": "investigator",
                "metadata": metadata or {},
            },
            timeout=_TIMEOUT,
        )
        if r.status_code in (200, 201):
            return r.json()
    except Exception:
        pass
    return None


def verify_hash(evidence_id: str, file_hash: str, actor: str = "system") -> Optional[dict]:
    """Re-verify an anchored hash. Returns the verify result (outcome VERIFIED/…)."""
    try:
        r = httpx.post(
            f"{BELS_URL}/evidence/verify-hash",
            json={"evidence_id": evidence_id, "file_hash": file_hash,
                  "actor": actor, "role": "auditor"},
            timeout=_TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def certificate(evidence_id: str) -> Optional[dict]:
    try:
        r = httpx.get(f"{BELS_URL}/evidence/{evidence_id}/certificate", timeout=_TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None
