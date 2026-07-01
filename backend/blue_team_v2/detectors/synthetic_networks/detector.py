"""
Synthetic-Ring detector.

Synthetic fraud rings are fabricated account networks that look engineered:
unusually uniform structure, dense interconnection among low-history accounts,
and topological regularity no organic banking network exhibits.
"""
from __future__ import annotations

import statistics

from ...types import Evidence

NAME = "synthetic_networks"


def detect(tg, metrics, meta) -> list[Evidence]:
    n = tg.num_nodes()
    if n < 5:
        return []

    degrees = [tg.G.in_degree(x) + tg.G.out_degree(x) for x in tg.nodes]
    if not degrees or max(degrees) == 0:
        return []

    mean_deg = statistics.mean(degrees)
    stdev_deg = statistics.pstdev(degrees) if len(degrees) > 1 else 0.0
    # density of the directed graph
    density = tg.num_edges() / (n * (n - 1)) if n > 1 else 0.0
    # uniformity: low degree variance relative to mean → engineered regularity
    cv = stdev_deg / mean_deg if mean_deg > 0 else 1.0
    uniformity = max(0.0, 1.0 - cv)

    # fraction of accounts with no prior history (fresh, fabricated)
    fresh = sum(1 for x in tg.nodes
                if tg.G.nodes[x].get("txn_count_meta", 0) <= 1
                and tg.G.nodes[x].get("prior_risk", 0.0) == 0.0)
    fresh_ratio = fresh / n

    synthetic_score = 0.0
    reasons: list[str] = []
    if density >= 0.25:
        synthetic_score += 0.3
        reasons.append(f"high interconnection density ({density:.0%})")
    if uniformity >= 0.7 and n >= 6:
        synthetic_score += 0.35
        reasons.append(f"topological regularity (degree uniformity {uniformity:.0%})")
    if fresh_ratio >= 0.6:
        synthetic_score += 0.3
        reasons.append(f"{fresh_ratio:.0%} of accounts have no transaction history")

    if synthetic_score < 0.45:
        return []

    return [Evidence(
        pattern=NAME,
        title=f"Synthetic fraud ring ({n} accounts)",
        description=(
            f"This {n}-account cluster shows engineered characteristics — "
            + ", ".join(reasons) + ". Such regularity does not occur in organic "
            f"banking and indicates a fabricated synthetic-identity ring."
        ),
        nodes=tg.nodes[:20],
        severity=min(0.95, 0.6 + synthetic_score * 0.35),
        confidence=min(0.9, 0.6 + synthetic_score * 0.3),
        data={"density": round(density, 3), "degree_uniformity": round(uniformity, 3),
              "fresh_ratio": round(fresh_ratio, 3), "nodes": n},
    )]
