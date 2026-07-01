"""
Night-activity detector.

Accounts whose material activity is concentrated in the small hours (00:00–05:00)
deviate from normal customer behaviour and correlate with automated mule
operation and account-takeover cash-out runs. A supporting (not standalone)
signal — low confidence, contributes to the cumulative score.
"""
from __future__ import annotations

from ...types import Evidence
from .._common import night_fraction, NIGHT_START, NIGHT_END

NAME = "night_activity"
MIN_TXNS = 4
MIN_NIGHT_FRACTION = 0.6
MIN_VOLUME = 1_00_000


def detect(tg, metrics, meta) -> list[Evidence]:
    evidence: list[Evidence] = []
    for node in tg.nodes:
        ts = tg.timestamps(node)
        if len(ts) < MIN_TXNS:
            continue
        frac = night_fraction(ts)
        if frac < MIN_NIGHT_FRACTION:
            continue
        volume = tg.in_volume(node) + tg.out_volume(node)
        if volume < MIN_VOLUME:
            continue
        sev = min(0.7, 0.3 + 0.4 * frac)
        evidence.append(Evidence(
            pattern=NAME,
            title=f"Night-concentrated activity ({frac:.0%} between {NIGHT_START:02d}:00–{NIGHT_END:02d}:00)",
            description=(
                f"{frac:.0%} of {node}'s {len(ts)} transactions (₹{volume:,.0f}) occur in the "
                f"{NIGHT_START:02d}:00–{NIGHT_END:02d}:00 window. Heavy off-hours activity is atypical "
                f"of genuine customers and is associated with automated mule scripts and "
                f"account-takeover cash-out."
            ),
            nodes=[node],
            severity=sev,
            confidence=0.6,
            data={"node": node, "night_fraction": round(frac, 3), "txns": len(ts),
                  "volume": round(volume, 2)},
        ))
    return evidence
