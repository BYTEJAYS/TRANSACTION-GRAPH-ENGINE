"""
Uniform-amount (templated transfer) detector.

Automated laundering scripts move identical or near-identical amounts across many
edges — organic human payments almost never do. A single amount value repeated
across many distinct transfers is a strong automation/templating signature.
"""
from __future__ import annotations

from collections import Counter

from ...types import Evidence

NAME = "uniform_amount"
MIN_REPEATS = 4
MIN_AMOUNT = 20_000
ROUNDING = 100   # bucket to nearest ₹100 so "near-identical" counts


def detect(tg, metrics, meta) -> list[Evidence]:
    buckets: Counter = Counter()
    members: dict[int, list[tuple[str, str]]] = {}
    for u, v, d in tg.G.edges(data=True):
        per = d["amount"] / max(1, d.get("count", 1))
        if per < MIN_AMOUNT:
            continue
        key = round(per / ROUNDING) * ROUNDING
        buckets[key] += d.get("count", 1)
        members.setdefault(key, []).append((u, v))

    evidence: list[Evidence] = []
    for amount, n in buckets.items():
        if n < MIN_REPEATS:
            continue
        edges = members[amount]
        nodes = list(dict.fromkeys([x for e in edges for x in e]))
        sev = min(0.9, 0.5 + 0.06 * (n - MIN_REPEATS))
        evidence.append(Evidence(
            pattern=NAME,
            title=f"Templated transfers (₹{amount:,.0f} × {n})",
            description=(
                f"The exact amount ≈₹{amount:,.0f} recurs across {n} separate transfers spanning "
                f"{len(nodes)} accounts. Repetition of an identical value at this frequency "
                f"indicates scripted/automated movement rather than organic payments — a "
                f"hallmark of mechanised laundering."
            ),
            nodes=nodes[:25],
            severity=sev,
            confidence=0.72,
            data={"amount": amount, "repeat_count": n, "distinct_edges": len(edges)},
        ))
    return evidence
