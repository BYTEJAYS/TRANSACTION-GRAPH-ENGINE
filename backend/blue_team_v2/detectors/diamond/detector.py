"""
Diamond layering detector.

A diamond is a split-then-merge motif: one account fans funds out across several
parallel relay paths that re-converge on a single collector — 1 → k → 1. It is a
deliberate obfuscation shape (harder to trace than a straight chain). Sequential
diamonds (a merge that is itself the next split) are reported as double/triple
diamonds via the `diamonds_in_sequence` count.
"""
from __future__ import annotations

from ...types import Evidence

NAME = "diamond"
MIN_BRANCHES = 2
MIN_VALUE = 1_00_000


def _reachable_within(tg, start, max_hops=2):
    """Nodes reachable from `start` within max_hops (excluding start)."""
    seen, frontier = set(), {start}
    for _ in range(max_hops):
        nxt = set()
        for u in frontier:
            nxt |= set(tg.G.successors(u))
        nxt -= seen | {start}
        seen |= nxt
        frontier = nxt
    return seen


def detect(tg, metrics, meta) -> list[Evidence]:
    evidence: list[Evidence] = []
    for split in tg.nodes:
        succ = list(tg.G.successors(split))
        if len(succ) < MIN_BRANCHES:
            continue
        # find merge nodes reachable from >= 2 distinct branches
        branch_reach: dict[str, set[str]] = {s: _reachable_within(tg, s, 2) | {s} for s in succ}
        merge_votes: dict[str, set[str]] = {}
        for s, reach in branch_reach.items():
            for m in reach:
                if m in (split, s):
                    continue
                merge_votes.setdefault(m, set()).add(s)
        merges = {m: branches for m, branches in merge_votes.items() if len(branches) >= MIN_BRANCHES}
        if not merges:
            continue
        merge_node = max(merges, key=lambda m: len(merges[m]))
        branches = merges[merge_node]
        flow = tg.out_volume(split)
        if flow < MIN_VALUE:
            continue
        k = len(branches)
        # detect a downstream second diamond (merge node itself splits again)
        seq = 1 + sum(1 for n in [merge_node] if tg.G.out_degree(n) >= MIN_BRANCHES)
        sev = min(0.97, 0.66 + 0.05 * (k - MIN_BRANCHES) + 0.06 * (seq - 1))
        label = {1: "Diamond", 2: "Double-diamond"}.get(seq, f"{seq}× diamond")
        evidence.append(Evidence(
            pattern=NAME,
            title=f"{label} layering ({k} parallel paths)",
            description=(
                f"Account {split} split ₹{flow:,.0f} across {k} parallel relay paths that "
                f"re-converge on {merge_node} — a split→merge 'diamond' used to fragment and "
                f"re-aggregate funds so the flow is hard to follow. "
                + ("Chained diamonds detected (compounded obfuscation)." if seq > 1 else "")
            ),
            nodes=[split, *sorted(branches), merge_node],
            severity=sev,
            confidence=0.84,
            data={"split": split, "merge": merge_node, "branches": sorted(branches),
                  "branch_count": k, "diamonds_in_sequence": seq, "split_volume": round(flow, 2)},
        ))
    return evidence
