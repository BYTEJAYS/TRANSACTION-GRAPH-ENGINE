"""
Weekend-activity detector.

Material flow concentrated on Saturdays/Sundays — when monitoring teams are thin
and inter-bank settlement is delayed — is a known timing tactic for moving funds
before they can be reviewed. Supporting signal (low confidence).
"""
from __future__ import annotations

from ...types import Evidence
from .._common import weekend_fraction

NAME = "weekend_activity"
MIN_TXNS = 4
MIN_WEEKEND_FRACTION = 0.7
MIN_VOLUME = 1_00_000


def detect(tg, metrics, meta) -> list[Evidence]:
    evidence: list[Evidence] = []
    for node in tg.nodes:
        ts = tg.timestamps(node)
        if len(ts) < MIN_TXNS:
            continue
        frac = weekend_fraction(ts)
        if frac < MIN_WEEKEND_FRACTION:
            continue
        volume = tg.in_volume(node) + tg.out_volume(node)
        if volume < MIN_VOLUME:
            continue
        sev = min(0.65, 0.28 + 0.4 * frac)
        evidence.append(Evidence(
            pattern=NAME,
            title=f"Weekend-concentrated activity ({frac:.0%})",
            description=(
                f"{frac:.0%} of {node}'s {len(ts)} transactions (₹{volume:,.0f}) fall on weekends, "
                f"when oversight is reduced and settlement is delayed. Concentrating movement in "
                f"low-monitoring windows is a deliberate timing tactic."
            ),
            nodes=[node],
            severity=sev,
            confidence=0.55,
            data={"node": node, "weekend_fraction": round(frac, 3), "txns": len(ts),
                  "volume": round(volume, 2)},
        ))
    return evidence
