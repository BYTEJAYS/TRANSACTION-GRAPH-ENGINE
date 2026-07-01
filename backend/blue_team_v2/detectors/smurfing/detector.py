"""
Smurfing / Structuring detector.

Flags deliberate fragmentation of a large sum into many similar, often
threshold-avoiding, transfers.  Two signatures:
  * repeated near-identical amounts across the cluster
  * many transfers clustered just below a reporting threshold
"""
from __future__ import annotations

from collections import Counter

from ...types import Evidence

NAME = "smurfing"
# Common AML reporting threshold (₹50,000 for PAN/CTR-style rules in IN context)
STRUCTURING_THRESHOLD = 50_000
NEAR = 0.92  # within 8% below the threshold


def detect(tg, metrics, meta) -> list[Evidence]:
    edges = [(u, v, d["amount"]) for u, v, d in tg.G.edges(data=True)]
    if len(edges) < 3:
        return []
    evidence: list[Evidence] = []

    # ── repeated identical amounts ──
    amt_counter = Counter(round(a, 2) for _, _, a in edges if a > 1000)
    for amt, cnt in amt_counter.items():
        if cnt >= 3:
            nodes = sorted({n for u, v, a in edges if abs(a - amt) < 0.01 for n in (u, v)})
            evidence.append(Evidence(
                pattern=NAME,
                title=f"{cnt}× identical transfers of ₹{amt:,.0f}",
                description=(
                    f"{cnt} transfers of the exact same amount (₹{amt:,.0f}) across the "
                    f"cluster indicate scripted structuring rather than organic activity."
                ),
                nodes=nodes[:14],
                severity=min(0.9, 0.62 + 0.04 * cnt),
                confidence=0.84,
                data={"amount": amt, "count": cnt},
            ))

    # ── just-below-threshold clustering ──
    near = [(u, v, a) for u, v, a in edges
            if STRUCTURING_THRESHOLD * NEAR <= a < STRUCTURING_THRESHOLD]
    if len(near) >= 3:
        nodes = sorted({n for u, v, a in near for n in (u, v)})
        evidence.append(Evidence(
            pattern=NAME,
            title=f"{len(near)} transfers just below ₹{STRUCTURING_THRESHOLD:,.0f}",
            description=(
                f"{len(near)} transfers fall in the {int(NEAR*100)}–100% band just under "
                f"the ₹{STRUCTURING_THRESHOLD:,.0f} reporting threshold — textbook structuring "
                f"to stay below mandatory reporting."
            ),
            nodes=nodes[:14],
            severity=min(0.93, 0.66 + 0.03 * len(near)),
            confidence=0.87,
            data={"threshold": STRUCTURING_THRESHOLD, "count": len(near)},
        ))
    return evidence
