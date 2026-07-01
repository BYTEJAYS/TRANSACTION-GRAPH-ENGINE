"""
Round-tripping detector.

Funds leave an account and a near-equal amount returns to it within a short
loop (≤4 hops), often via an intermediary or merchant — value goes out and
comes back, manufacturing turnover or disguising the source. Distinct from a
generic cycle: the round-trip *value balance* is ~1.0 and the loop is short and
time-ordered (out before back).
"""
from __future__ import annotations

from ...types import Evidence

NAME = "round_tripping"
MIN_VALUE = 50_000
MAX_LOOP = 4
BALANCE_TOL = 0.15   # |out-back|/out must be within this to count as a round trip


def detect(tg, metrics, meta) -> list[Evidence]:
    evidence: list[Evidence] = []
    seen: set[frozenset] = set()
    for cyc in tg.cycles():
        if not (2 <= len(cyc) <= MAX_LOOP):
            continue
        key = frozenset(cyc)
        if key in seen:
            continue
        # walk the loop edges (rotation-independent)
        hops: list[tuple[str, str, float, object]] = []
        ok = True
        for i in range(len(cyc)):
            a, b = cyc[i], cyc[(i + 1) % len(cyc)]
            if not tg.G.has_edge(a, b):
                ok = False
                break
            d = tg.G[a][b]
            hops.append((a, b, d["amount"], min(d["timestamps"]) if d["timestamps"] else None))
        if not ok:
            continue
        amts = [h[2] for h in hops]
        if min(amts) < MIN_VALUE:
            continue
        # value conservation around the loop — out ≈ back
        balance = (max(amts) - min(amts)) / max(amts)
        if balance > BALANCE_TOL:
            continue
        # time ordering: some rotation of the hops is non-decreasing in time
        times = [h[3] for h in hops]
        if all(t is not None for t in times):
            k = times.index(min(times))
            rot = times[k:] + times[:k]
            if not all(rot[i] <= rot[i + 1] for i in range(len(rot) - 1)):
                continue
        seen.add(key)
        origin = cyc[0]
        out_amt, back_amt = max(amts), min(amts)
        sev = min(0.96, 0.74 + (BALANCE_TOL - balance) + 0.03 * (MAX_LOOP - len(cyc)))
        evidence.append(Evidence(
            pattern=NAME,
            title=f"Round-tripping via {len(cyc)}-account loop",
            description=(
                f"₹{out_amt:,.0f} left {origin} and ₹{back_amt:,.0f} ({1-balance:.0%} of it) "
                f"returned through a {len(cyc)}-account loop {' → '.join(cyc)} → {origin}. "
                f"Near-balanced out-and-back flow is round-tripping — used to inflate turnover "
                f"or launder funds back as 'clean' income."
            ),
            nodes=list(cyc),
            severity=sev,
            confidence=0.88,
            data={"origin": origin, "loop": list(cyc), "out_amount": round(out_amt, 2),
                  "returned_amount": round(back_amt, 2), "balance_gap": round(balance, 3)},
        ))
    return evidence
