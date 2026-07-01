"""
Dormant-Account-Reactivation detector.

Accounts that sit idle then suddenly spring into high-value activity are a
classic sign of a compromised/sold account being pressed into mule service.
"""
from __future__ import annotations

from ...types import Evidence

NAME = "dormant_accounts"


def detect(tg, metrics, meta) -> list[Evidence]:
    evidence: list[Evidence] = []
    for node, m in metrics.items():
        if m.dormancy_reactivation >= 0.45 and (m.incoming_volume + m.outgoing_volume) >= 50_000:
            evidence.append(Evidence(
                pattern=NAME,
                title=f"Dormant reactivation: {node}",
                description=(
                    f"Account {node} was quiet for a prolonged period, then abruptly "
                    f"resumed with ₹{m.incoming_volume + m.outgoing_volume:,.0f} of activity "
                    f"(reactivation index {m.dormancy_reactivation:.2f}). Sudden wake-ups of "
                    f"dormant accounts frequently indicate account takeover or mule onboarding."
                ),
                nodes=[node],
                severity=min(0.8, 0.45 + 0.45 * m.dormancy_reactivation),
                confidence=0.7,
                data={"reactivation_index": m.dormancy_reactivation},
            ))
    return evidence
