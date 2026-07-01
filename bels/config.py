"""Central configuration for BELS. Environment-overridable for deployment."""
from __future__ import annotations

import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
# Default data root sits beside this package so the module is self-contained.
_PKG_DIR = Path(__file__).resolve().parent
_TGIE_ROOT = _PKG_DIR.parent

DATA_DIR = Path(os.getenv("BELS_DATA_DIR", _PKG_DIR / "data"))
# Per the core principle, raw files live OUTSIDE the chain in a dedicated store.
EVIDENCE_STORAGE_DIR = Path(os.getenv("BELS_EVIDENCE_DIR", _TGIE_ROOT / "evidence_storage"))
LEDGER_FILE = DATA_DIR / "ledger.jsonl"
CASES_FILE = DATA_DIR / "cases.json"
AUDIT_LOG_FILE = DATA_DIR / "operational_audit.log.jsonl"
CERTS_DIR = DATA_DIR / "certificates"
REPORTS_DIR = DATA_DIR / "reports"
KEYS_DIR = DATA_DIR / "keys"

# ── Blockchain provider selection ──────────────────────────────────────────────
# "internal"  → bundled hash-linked PoW ledger (default, no external deps)
# "ethereum"  → Ethereum/Polygon-compatible adapter (requires web3 + RPC config)
BLOCKCHAIN_PROVIDER = os.getenv("BELS_PROVIDER", "internal")

# Internal-ledger proof-of-work difficulty (number of leading hex zeros).
# Kept low so demos confirm instantly; raise for stronger anchoring.
POW_DIFFICULTY = int(os.getenv("BELS_POW_DIFFICULTY", "3"))
CHAIN_ID = os.getenv("BELS_CHAIN_ID", "tgie-bels-devnet-1")

# Ethereum-family settings (only read when BLOCKCHAIN_PROVIDER == "ethereum").
ETH_RPC_URL = os.getenv("BELS_ETH_RPC_URL", "")
ETH_CONTRACT_ADDRESS = os.getenv("BELS_ETH_CONTRACT", "")
ETH_PRIVATE_KEY = os.getenv("BELS_ETH_PRIVATE_KEY", "")

# ── Security ───────────────────────────────────────────────────────────────────
# HMAC fallback secret (used only if `cryptography` / ed25519 is unavailable).
SIGNING_SECRET = os.getenv("BELS_SIGNING_SECRET", "tgie-bels-dev-signing-secret-change-me")

# ── Service ────────────────────────────────────────────────────────────────────
API_PREFIX = "/bels"
HOST = os.getenv("BELS_HOST", "0.0.0.0")
PORT = int(os.getenv("BELS_PORT", "8200"))
MAX_UPLOAD_MB = int(os.getenv("BELS_MAX_UPLOAD_MB", "50"))

ALLOWED_ORIGINS = os.getenv("BELS_ALLOWED_ORIGINS", "*").split(",")


def ensure_dirs() -> None:
    """Create all runtime directories. Safe to call repeatedly."""
    for d in (DATA_DIR, EVIDENCE_STORAGE_DIR, CERTS_DIR, REPORTS_DIR, KEYS_DIR):
        d.mkdir(parents=True, exist_ok=True)
