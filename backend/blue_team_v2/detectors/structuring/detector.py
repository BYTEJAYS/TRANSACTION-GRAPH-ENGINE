"""
Threshold-structuring detector.

Deliberately keeping individual transfers just below a regulatory reporting
threshold to avoid triggering a report. Signature: a cluster of transfers whose
amounts sit in the [0.80·T, T) band — too many, too close to the line, to be
coincidence. Complements `smurfing` (which keys on many small deposits): this
keys specifically on proximity to the reporting threshold.
"""
from __future__ import annotations

from collections import defaultdict

from ...types import Evidence
from .._common import report_threshold, NEAR_BAND

NAME = "structuring"
MIN_NEAR_TXNS = 3


def detect(tg, metrics, meta) -> list[Evidence]:
    T = report_threshold()
    lo, hi = NEAR_BAND * T, T
    # group near-threshold transfers by sender
    by_sender: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for u, v, d in tg.G.edges(data=True):
        amt = d["amount"]
        # an edge may aggregate several transfers; use per-transfer average
        per = amt / max(1, d.get("count", 1))
        if lo <= per < hi:
            by_sender[u].append((v, per))

    evidence: list[Evidence] = []
    for sender, txns in by_sender.items():
        if len(txns) < MIN_NEAR_TXNS:
            continue
        total = sum(a for _, a in txns)
        avg = total / len(txns)
        proximity = avg / T  # closer to 1.0 = more deliberate
        sev = min(0.95, 0.6 + 0.05 * (len(txns) - MIN_NEAR_TXNS) + 0.25 * (proximity - NEAR_BAND) / (1 - NEAR_BAND))
        recipients = [v for v, _ in txns][:10]
        evidence.append(Evidence(
            pattern=NAME,
            title=f"Threshold structuring ({len(txns)} transfers just under ₹{T:,.0f})",
            description=(
                f"Account {sender} made {len(txns)} transfers averaging ₹{avg:,.0f} — all sitting "
                f"in the {NEAR_BAND:.0%}–100% band just below the ₹{T:,.0f} reporting threshold. "
                f"Consistently transacting just under the line is structuring: splitting value to "
                f"stay beneath mandatory reporting."
            ),
            nodes=[sender, *recipients],
            severity=sev,
            confidence=0.82,
            data={"sender": sender, "near_threshold_txns": len(txns), "avg_amount": round(avg, 2),
                  "threshold": T, "proximity": round(proximity, 3)},
        ))
    return evidence
