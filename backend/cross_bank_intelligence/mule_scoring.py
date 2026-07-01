"""
Mule scoring — combine the cross-bank signals for ONE account into a 0–100 risk,
with human-readable reasons. Deliberately bounded so cross-bank risk *contributes*
to the Blue Team score but never *dominates* it (see risk_engine integration: it is
a single capped factor).
"""
from __future__ import annotations

from typing import Dict, List

from .external_signals import ExternalSignal
from .schemas import AccountIntel, band_for


def score_account(account: str,
                  linked_accounts: List[str],
                  linked_banks: int,
                  shared_devices: int,
                  shared_phones: int,
                  external: ExternalSignal,
                  velocity_reasons: List[str]) -> AccountIntel:
    reasons: List[str] = []
    score = 0.0

    # 1. Known cross-bank history (the strongest signal — "seen suspicious elsewhere")
    if external.get("known"):
        rr = int(external.get("registry_risk", 0))
        score = max(score, rr)
        reasons.append(
            f"Fingerprint known across {len(external.get('banks_seen', []))} bank(s)"
            + (f", {external['known_fraud_cases']} prior fraud case(s)"
               if external.get("known_fraud_cases") else ""))

    # 2. Breadth: one entity spanning many banks / accounts
    if linked_banks >= 2:
        score += min(30, (linked_banks - 1) * 12)
        reasons.append(f"Entity linked across {linked_banks} banks")
    if len(linked_accounts) >= 3:
        score += min(18, (len(linked_accounts) - 2) * 4)
        reasons.append(f"{len(linked_accounts)} accounts resolve to one entity")

    # 3. Shared device / phone across accounts (mule-farm tell)
    if shared_devices:
        score += min(16, shared_devices * 8)
        reasons.append(f"Shares {shared_devices} device(s) with other account(s)")
    if shared_phones:
        score += min(12, shared_phones * 6)
        reasons.append(f"Shares {shared_phones} phone number(s) with other account(s)")

    # 4. Velocity behaviour
    if "dormant_activation" in velocity_reasons:
        score += 18
        reasons.append("Dormant account activated then forwarded rapidly")
    if "rapid_passthrough" in velocity_reasons:
        score += 12
        reasons.append("Rapid cross-bank pass-through of received funds")

    s = int(max(0, min(100, round(score))))
    return AccountIntel(
        account=account,
        cross_bank_risk=s,
        banks_seen=sorted(external.get("banks_seen", [])),
        linked_banks=linked_banks,
        linked_accounts=len(linked_accounts),
        shared_devices=shared_devices,
        shared_phones=shared_phones,
        known_suspicious=bool(external.get("known")),
        reasons=reasons,
    )


def component_risk(account_intel: Dict[str, AccountIntel], pattern_boost: int) -> int:
    """Aggregate per-account risk into a component cross-bank risk. The component is as
    risky as its riskiest mule (max), nudged up by corroborating cross-bank patterns,
    then clamped. (Max, not sum, so a big benign cluster never inflates risk.)"""
    if not account_intel:
        return 0
    top = max(a["cross_bank_risk"] for a in account_intel.values())
    return int(max(0, min(100, top + pattern_boost)))
