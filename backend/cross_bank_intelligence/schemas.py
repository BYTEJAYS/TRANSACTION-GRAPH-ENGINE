"""
Cross-Bank Intelligence — data shapes.

The module is a pure ENRICHMENT layer: it reads a read-only component snapshot (the
exact dict the rest of TGIE already produces) plus the per-session entity_context,
and returns intelligence ONLY. It never mutates the graph, creates nodes/edges, or
touches layout. These TypedDicts document the contract of what it returns.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

# Simulated bank universe (demo). An account's bank comes from the input
# (from_bank/to_bank) or the entity_context; if absent it defaults to UNION_BANK.
KNOWN_BANKS: tuple[str, ...] = (
    "UNION_BANK", "SBI", "HDFC", "ICICI", "AXIS",
    "KOTAK", "BOB", "PNB", "CANARA", "IDFC",
)
DEFAULT_BANK = "UNION_BANK"

# The cross-bank behaviours the engine can name (stable identifiers).
CROSS_BANK_PATTERNS: tuple[str, ...] = (
    "same_device_multi_bank",
    "same_phone_multiple_accounts",
    "multi_bank_layering",
    "multi_bank_fanout",
    "multi_bank_fanin",
    "dormant_activation",
    "cross_bank_circular",
    "same_merchant_across_banks",
    "same_device_different_names",
    "known_suspicious_entity",
)


class AccountFingerprint(TypedDict, total=False):
    account: str
    bank: str
    devices: List[str]
    phones: List[str]
    pans: List[str]
    emails: List[str]
    upi_handles: List[str]
    names: List[str]
    merchants: List[str]


class RegistryEntry(TypedDict, total=False):
    """A known cross-bank fingerprint (phone / device / pan / account)."""
    fingerprint: str
    kind: str                 # device | phone | pan | account | email | upi
    banks_seen: List[str]
    accounts_seen: int
    known_fraud_cases: int
    risk_score: int           # 0–100


class AccountIntel(TypedDict, total=False):
    account: str
    cross_bank_risk: int      # 0–100
    banks_seen: List[str]
    linked_banks: int
    linked_accounts: int
    shared_devices: int
    shared_phones: int
    known_suspicious: bool
    reasons: List[str]


class CrossBankReport(TypedDict, total=False):
    available: bool
    cross_bank_risk: int                 # 0–100 component-level
    band: str                            # Low / Elevated / High / Critical
    linked_banks: int
    linked_accounts: int
    shared_devices: int
    shared_phone_numbers: int
    known_suspicious_entities: int
    banks_involved: List[str]
    cross_bank_patterns: List[str]
    accounts: Dict[str, AccountIntel]    # per-account intelligence (metadata only)
    explanation: Optional[str]


def empty_report() -> CrossBankReport:
    return {
        "available": False, "cross_bank_risk": 0, "band": "Low",
        "linked_banks": 0, "linked_accounts": 0, "shared_devices": 0,
        "shared_phone_numbers": 0, "known_suspicious_entities": 0,
        "banks_involved": [], "cross_bank_patterns": [], "accounts": {},
        "explanation": None,
    }


def band_for(score: int) -> str:
    if score >= 85:
        return "Critical"
    if score >= 70:
        return "High"
    if score >= 45:
        return "Elevated"
    return "Low"
