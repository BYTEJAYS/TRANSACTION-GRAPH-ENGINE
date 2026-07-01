"""
Nested layering detector.

A primary forwarding chain whose interior also spawns a secondary deep chain —
i.e. layering within layering. The signature of an operator who, mid-way through
moving funds, peels off another multi-hop laundering branch.
"""
from __future__ import annotations

from ...types import Evidence

NAME = "nested_layering"
MIN_PRIMARY = 4
MIN_BRANCH = 3


def _forward_depth(tg, start, on_chain: set[str], max_depth=8) -> list[str]:
    """Greedy longest forward path from `start` avoiding the primary chain nodes."""
    path, cur, seen = [start], start, {start}
    for _ in range(max_depth):
        succ = [s for s in tg.G.successors(cur) if s not in seen and s not in on_chain]
        if not succ:
            break
        cur = max(succ, key=lambda s: tg.out_volume(s))
        path.append(cur)
        seen.add(cur)
    return path


def detect(tg, metrics, meta) -> list[Evidence]:
    chain = meta.get("chain") or tg.longest_chain()
    if len(chain) < MIN_PRIMARY:
        return []
    on_chain = set(chain)
    for node in chain[1:-1]:
        # an interior node that forks off the main chain into another deep branch
        branch = _forward_depth(tg, node, on_chain - {node})
        if len(branch) >= MIN_BRANCH + 1:  # node + >=MIN_BRANCH hops
            m = metrics.get(node)
            relay = m and m.pass_through_ratio >= 0.4
            sev = min(0.95, 0.62 + 0.03 * len(chain) + 0.04 * len(branch) + (0.05 if relay else 0))
            return [Evidence(
                pattern=NAME,
                title=f"Nested layering ({len(chain)}-hop primary + {len(branch)}-hop branch)",
                description=(
                    f"A primary {len(chain)}-hop forwarding chain has an interior relay {node} "
                    f"that itself spawns a secondary {len(branch)}-hop laundering branch — "
                    f"layering nested inside layering, used to multiply the obfuscation depth. "
                    f"Primary: {' → '.join(chain[:6])}{' → …' if len(chain) > 6 else ''}."
                ),
                nodes=list(dict.fromkeys([*chain, *branch])),
                severity=sev,
                confidence=0.8,
                data={"primary_chain": chain, "branch_from": node, "branch": branch,
                      "primary_depth": len(chain), "branch_depth": len(branch)},
            )]
    return []
