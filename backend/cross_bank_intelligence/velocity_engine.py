"""
Cross-bank velocity / temporal signals — fast pass-through and dormant activation,
which are the behavioural tells of a cross-bank mule. Best-effort: uses timestamps
when present, falls back to a structural approximation otherwise. Pure reader.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from .schemas import AccountFingerprint


def _ts(v: Any) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def detect_velocity_signals(component: Dict[str, Any],
                            fingerprints: Dict[str, AccountFingerprint]) -> Dict[str, List[str]]:
    """account → list of velocity reasons (e.g. 'dormant_activation', 'rapid_passthrough').
    A pass-through that forwards most of an inflow onward — quickly, and to a DIFFERENT
    bank — is the cross-bank mule signature."""
    edges = [e for e in (component.get("edges") or []) if isinstance(e, dict)]
    incoming: Dict[str, list] = {}
    outgoing: Dict[str, list] = {}
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s is None or t is None:
            continue
        outgoing.setdefault(str(s), []).append(e)
        incoming.setdefault(str(t), []).append(e)

    bank_of = {a: fp.get("bank") for a, fp in fingerprints.items()}
    reasons: Dict[str, List[str]] = {}

    for acct in fingerprints:
        ins, outs = incoming.get(acct, []), outgoing.get(acct, [])
        if not ins or not outs:
            continue
        in_amt = sum(float(e.get("amount", 0) or 0) for e in ins)
        out_amt = sum(float(e.get("amount", 0) or 0) for e in outs)
        if in_amt <= 0:
            continue
        forwarded = out_amt / in_amt
        # cross-bank pass-through: forwards onward to a bank different from the inflow bank
        in_banks = {bank_of.get(str(e.get("source"))) for e in ins}
        out_banks = {bank_of.get(str(e.get("target"))) for e in outs}
        crosses_bank = bool(out_banks - in_banks - {bank_of.get(acct)})

        if forwarded >= 0.8 and crosses_bank:
            reasons.setdefault(acct, []).append("rapid_passthrough")

        # dormant activation: a single large inflow then near-total onward forward
        # within a short window (when timestamps are available).
        last_in = max((_ts(e.get("timestamp")) for e in ins if _ts(e.get("timestamp")) is not None), default=None)
        first_out = min((_ts(e.get("timestamp")) for e in outs if _ts(e.get("timestamp")) is not None), default=None)
        if last_in is not None and first_out is not None and first_out >= last_in:
            if (first_out - last_in) <= 600 and forwarded >= 0.8:  # ≤10 min
                reasons.setdefault(acct, []).append("dormant_activation")

    return reasons
