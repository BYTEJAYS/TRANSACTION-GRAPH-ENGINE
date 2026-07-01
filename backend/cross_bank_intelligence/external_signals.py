"""
External (cross-bank) signals — what other institutions already know about an
account's fingerprints. Backed by the CrossBankRiskRegistry (Kafka-fed in
production, seeded in the demo). Pure aggregation; no mutation.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .fingerprints import all_fingerprints
from .risk_registry import CrossBankRiskRegistry
from .schemas import AccountFingerprint


class ExternalSignal(dict):
    """{banks_seen, accounts_seen, known_fraud_cases, registry_risk, known, hits[]}"""


def external_signal_for(fp: AccountFingerprint,
                        registry: CrossBankRiskRegistry) -> ExternalSignal:
    banks_seen: set[str] = set()
    accounts_seen = 0
    known_fraud = 0
    registry_risk = 0
    hits: List[str] = []
    # own declared bank counts toward banks-seen breadth
    if fp.get("bank"):
        banks_seen.add(fp["bank"])
    for kind, value in all_fingerprints(fp):
        e = registry.lookup(value)
        if not e:
            continue
        hits.append(value)
        banks_seen.update(e.get("banks_seen", []))
        accounts_seen = max(accounts_seen, int(e.get("accounts_seen", 0)))
        known_fraud += int(e.get("known_fraud_cases", 0))
        registry_risk = max(registry_risk, int(e.get("risk_score", 0)))
    return ExternalSignal(
        banks_seen=sorted(banks_seen),
        accounts_seen=accounts_seen,
        known_fraud_cases=known_fraud,
        registry_risk=registry_risk,
        known=bool(hits),
        hits=hits,
    )


def external_signals(fingerprints: Dict[str, AccountFingerprint],
                     registry: CrossBankRiskRegistry) -> Dict[str, ExternalSignal]:
    return {acct: external_signal_for(fp, registry) for acct, fp in fingerprints.items()}
