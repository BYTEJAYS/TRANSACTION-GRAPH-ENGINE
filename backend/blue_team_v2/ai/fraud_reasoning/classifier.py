"""
Fraud Reasoning — maps the evidence + cluster structure to primary / secondary
fraud classifications, the way an investigator would label a case.
"""
from __future__ import annotations

from ...types import Evidence

# pattern → (classification label, weight toward being primary)
_PATTERN_CLASS = {
    "circular_flow":      ("Money Laundering — Circular Layering", 1.0),
    "layering":           ("Money Laundering — Layering", 0.95),
    "smurfing":           ("Structuring / Smurfing", 0.85),
    "mule_accounts":      ("Mule Network Operation", 0.9),
    "fan_out":            ("Rapid Fund Distribution", 0.8),
    "fan_in":             ("Fund Collection / Aggregation", 0.8),
    "bridge_accounts":    ("Bridged Laundering Pipeline", 0.75),
    "velocity":           ("Rapid Movement / Burst Dispersal", 0.7),
    "cashout":            ("Cash-Out Operation", 0.85),
    "dormant_accounts":   ("Account Takeover / Mule Onboarding", 0.65),
    "synthetic_networks": ("Synthetic Identity Ring", 0.95),
    "hybrid_network":     ("Organised Laundering Network", 1.05),
}


def classify(evidence: list[Evidence]) -> tuple[str, str | None]:
    """Return (primary_classification, secondary_classification|None)."""
    if not evidence:
        return "Legitimate Activity", None

    # rank patterns by (weight * max severity observed for that pattern)
    best: dict[str, float] = {}
    for ev in evidence:
        label, weight = _PATTERN_CLASS.get(ev.pattern, (ev.pattern.title(), 0.5))
        score = weight * ev.severity
        if score > best.get(label, 0.0):
            best[label] = score

    ranked = sorted(best.items(), key=lambda x: x[1], reverse=True)
    primary = ranked[0][0]
    secondary = ranked[1][0] if len(ranked) > 1 else None
    return primary, secondary
