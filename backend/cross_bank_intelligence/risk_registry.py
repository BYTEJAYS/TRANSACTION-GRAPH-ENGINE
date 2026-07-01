"""
Cross-Bank Risk Registry — the "has this entity behaved suspiciously elsewhere?"
memory. In production this is fed by Kafka streams from many banks; for the demo it
is an in-memory, deterministically-seeded registry of known cross-bank fingerprints
plus a live accumulation seam (`register_sighting`) so an entity that recurs across
sessions builds history.

Thread-safe. A default singleton is provided, but callers may pass their own
instance (tests do, to avoid global-state leakage — see learning.py/xp_config).
"""
from __future__ import annotations

import threading
from typing import Dict, List, Optional

from .schemas import RegistryEntry


def _norm(fp: str) -> str:
    return str(fp).strip().upper()


# Deterministically-seeded known-suspicious fingerprints (the "intel from other
# banks"). Each represents an identity already linked to fraud across institutions.
_SEED: list[RegistryEntry] = [
    {"fingerprint": "DEV_MULE_RING_1", "kind": "device",
     "banks_seen": ["SBI", "HDFC", "ICICI", "AXIS"], "accounts_seen": 11,
     "known_fraud_cases": 3, "risk_score": 88},
    {"fingerprint": "PHONE_9800000001", "kind": "phone",
     "banks_seen": ["UNION_BANK", "SBI", "HDFC", "KOTAK", "BOB"], "accounts_seen": 14,
     "known_fraud_cases": 3, "risk_score": 91},
    {"fingerprint": "PAN_AAAPM0001M", "kind": "pan",
     "banks_seen": ["HDFC", "ICICI"], "accounts_seen": 5,
     "known_fraud_cases": 1, "risk_score": 67},
    {"fingerprint": "DEV_SHARED_KYC_9", "kind": "device",
     "banks_seen": ["ICICI", "AXIS", "PNB"], "accounts_seen": 9,
     "known_fraud_cases": 2, "risk_score": 84},
    {"fingerprint": "PHONE_9800000042", "kind": "phone",
     "banks_seen": ["AXIS", "CANARA"], "accounts_seen": 6,
     "known_fraud_cases": 1, "risk_score": 58},
    {"fingerprint": "UPI_MULE@OKAXIS", "kind": "upi",
     "banks_seen": ["AXIS", "SBI", "IDFC"], "accounts_seen": 7,
     "known_fraud_cases": 2, "risk_score": 79},
]


class CrossBankRiskRegistry:
    def __init__(self, seed: Optional[list[RegistryEntry]] = None):
        self._lock = threading.RLock()
        self._by_fp: Dict[str, RegistryEntry] = {}
        for e in (seed if seed is not None else _SEED):
            self._by_fp[_norm(e["fingerprint"])] = dict(e)  # copy

    def lookup(self, fingerprint: Optional[str]) -> Optional[RegistryEntry]:
        if not fingerprint:
            return None
        with self._lock:
            return self._by_fp.get(_norm(fingerprint))

    def is_known(self, fingerprint: Optional[str]) -> bool:
        return self.lookup(fingerprint) is not None

    def banks_for(self, fingerprint: Optional[str]) -> List[str]:
        e = self.lookup(fingerprint)
        return list(e.get("banks_seen", [])) if e else []

    def register_sighting(self, fingerprint: str, kind: str, bank: str,
                          fraud: bool = False) -> RegistryEntry:
        """Accumulate a live observation of a fingerprint at a bank (the Kafka seam).
        Never lowers an existing risk; grows banks_seen / accounts_seen / cases."""
        fp = _norm(fingerprint)
        with self._lock:
            e = self._by_fp.get(fp)
            if e is None:
                e = {"fingerprint": fp, "kind": kind, "banks_seen": [],
                     "accounts_seen": 0, "known_fraud_cases": 0, "risk_score": 0}
                self._by_fp[fp] = e
            if bank and bank not in e["banks_seen"]:
                e["banks_seen"].append(bank)
            e["accounts_seen"] = int(e.get("accounts_seen", 0)) + 1
            if fraud:
                e["known_fraud_cases"] = int(e.get("known_fraud_cases", 0)) + 1
            # risk grows with breadth of banks + known cases, capped.
            derived = min(100, len(e["banks_seen"]) * 12 + e["known_fraud_cases"] * 18)
            e["risk_score"] = max(int(e.get("risk_score", 0)), derived)
            return dict(e)

    def all_entries(self) -> List[RegistryEntry]:
        with self._lock:
            return [dict(e) for e in self._by_fp.values()]


# Process-default singleton (the live demo registry).
_DEFAULT: Optional[CrossBankRiskRegistry] = None
_DEFAULT_LOCK = threading.Lock()


def get_registry() -> CrossBankRiskRegistry:
    global _DEFAULT
    if _DEFAULT is None:
        with _DEFAULT_LOCK:
            if _DEFAULT is None:
                _DEFAULT = CrossBankRiskRegistry()
    return _DEFAULT
