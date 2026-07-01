"""
Cash-Out / Suspicious-Cashout-Path detector.

Identifies the terminal nodes where laundered value exits the banking graph —
cash accounts, ATMs, merchants, or value sinks that absorb funds from several
upstream mules without forwarding.
"""
from __future__ import annotations

from ...types import Evidence

NAME = "cashout"
CASH_TYPES = {"cash", "atm", "merchant", "cashout", "exchange"}


def detect(tg, metrics, meta) -> list[Evidence]:
    evidence: list[Evidence] = []
    for node, m in metrics.items():
        acct_type = str(tg.G.nodes[node].get("account_type", "normal")).lower()
        is_sink = m.fan_out_count == 0 and m.incoming_volume > 0
        is_cash = acct_type in CASH_TYPES
        # cashout = value-absorbing endpoint fed by ≥2 upstream sources
        if (is_sink or is_cash) and m.fan_in_count >= 2 and m.incoming_volume >= 100_000:
            # trace upstream paths to an origin for the "cashout path"
            sources = list(tg.G.predecessors(node))
            severity = min(0.95, 0.6 + 0.06 * m.fan_in_count + (0.1 if is_cash else 0))
            evidence.append(Evidence(
                pattern=NAME,
                title=f"Cash-out point: {node}",
                description=(
                    f"Account {node}"
                    + (f" (type={acct_type})" if is_cash else "")
                    + f" absorbed ₹{m.incoming_volume:,.0f} from {m.fan_in_count} upstream "
                    f"accounts and forwarded none of it — the terminal cash-out of the "
                    f"laundering pipeline."
                ),
                nodes=[node] + sources[:8],
                severity=severity,
                confidence=0.83,
                data={"cashout": node, "sources": len(sources),
                      "absorbed": round(m.incoming_volume, 2), "is_cash_account": is_cash},
            ))
    return evidence
