"""
Layout quality validation + repair.

`compute_layout` produces coordinates but never checked whether the result is
actually readable — a pathological graph could return overlapping nodes or a
high-crossing layer order and nothing would catch it server-side. This module
measures the qualities an investigator cares about (edge crossings, node
overlap, chain straightness) and, when a layout is poor, repairs node overlap
before the coordinates are returned.

Pure functions over `coords: {node_id: (x, y)}` + `edge_pairs: [(u, v), …]`.
Deterministic (sorted iteration, fixed iteration counts). Bounded for large
graphs (crossing counting samples edges past a cap).
"""
from __future__ import annotations

import math
from typing import Any

Coords = dict[str, tuple[float, float]]
EdgePairs = list[tuple[str, str]]
# A ring is (member-ids, centre, radius) — see graph_engine.layout.ring_geometry.
Rings = list[tuple[set[str], tuple[float, float], float]]

# An edge counts as cutting through a ring when its closest approach to the ring
# centre is inside this fraction of the radius (a true interior stab, not a chord
# that merely grazes the boundary between two adjacent ring nodes).
_RING_INTERIOR_FRACTION = 0.80


# ── geometry ───────────────────────────────────────────────────────────────────
def _orient(ax, ay, bx, by, cx, cy) -> float:
    return (by - ay) * (cx - bx) - (bx - ax) * (cy - by)


def _seg_point_dist(a: tuple[float, float], b: tuple[float, float],
                    p: tuple[float, float]) -> float:
    """Shortest distance from point `p` to segment `ab`."""
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(ax + t * dx - px, ay + t * dy - py)


def _segments_cross(p1, p2, p3, p4) -> bool:
    """True if segment p1p2 properly intersects p3p4 (shared endpoints don't count)."""
    if p1 in (p3, p4) or p2 in (p3, p4):
        return False  # adjacent edges share a node — not a crossing
    d1 = _orient(*p3, *p4, *p1)
    d2 = _orient(*p3, *p4, *p2)
    d3 = _orient(*p1, *p2, *p3)
    d4 = _orient(*p1, *p2, *p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


# ── metrics ──────────────────────────────────────────────────────────────────
def count_crossings(coords: Coords, edge_pairs: EdgePairs, max_edges: int = 350) -> dict[str, Any]:
    """
    Count edge-segment crossings. Exact when the edge count is within `max_edges`;
    otherwise a deterministic sample of edges is used and the count is flagged
    estimated (full O(E²) crossing counting is avoided on large graphs).
    """
    segs = []
    for u, v in edge_pairs:
        if u in coords and v in coords and u != v:
            segs.append((coords[u], coords[v]))
    estimated = False
    if len(segs) > max_edges:
        estimated = True
        step = len(segs) / max_edges
        segs = [segs[int(i * step)] for i in range(max_edges)]
    crossings = 0
    for i in range(len(segs)):
        a1, a2 = segs[i]
        for j in range(i + 1, len(segs)):
            b1, b2 = segs[j]
            if _segments_cross(a1, a2, b1, b2):
                crossings += 1
    return {"crossings": crossings, "edges_considered": len(segs), "estimated": estimated}


def detect_overlaps(coords: Coords, min_dist: float) -> list[tuple[str, str]]:
    """Node pairs closer than `min_dist`, found via a uniform spatial grid (O(n))."""
    cell = max(min_dist, 1.0)
    grid: dict[tuple[int, int], list[str]] = {}
    for n, (x, y) in coords.items():
        grid.setdefault((int(x // cell), int(y // cell)), []).append(n)
    pairs: list[tuple[str, str]] = []
    md2 = min_dist * min_dist
    for (gx, gy), members in grid.items():
        # compare within this cell + the 8 neighbours (each pair once)
        neigh: list[str] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                neigh.extend(grid.get((gx + dx, gy + dy), []))
        for i, a in enumerate(members):
            ax, ay = coords[a]
            for b in neigh:
                if b <= a:
                    continue  # each unordered pair once, deterministic
                bx, by = coords[b]
                if (ax - bx) ** 2 + (ay - by) ** 2 < md2:
                    pairs.append((a, b))
    return sorted(set(pairs))


# ── repair ───────────────────────────────────────────────────────────────────
def _jitter_dir(node_id: str) -> tuple[float, float]:
    """Deterministic unit direction for separating (near-)coincident nodes."""
    h = 0
    for ch in node_id:
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    ang = (h % 360) * math.pi / 180.0
    return math.cos(ang), math.sin(ang)


def repair_overlaps(coords: Coords, min_dist: float, iterations: int = 80) -> Coords:
    """
    Nudge overlapping nodes apart until none are closer than `min_dist` (or the
    iteration budget runs out). A small over-push (1.05×) and a deterministic
    jitter for coincident nodes guarantee convergence on piled-up inputs.
    Deterministic; returns a new dict, never mutates the input.
    """
    pos = {n: [float(x), float(y)] for n, (x, y) in coords.items()}
    for _ in range(iterations):
        pairs = detect_overlaps({n: (p[0], p[1]) for n, p in pos.items()}, min_dist)
        if not pairs:
            break
        # Jacobi update: accumulate every pair's separation, apply once per pass.
        # (Gauss-Seidel oscillates when nodes overlap several neighbours at once.)
        disp: dict[str, list[float]] = {n: [0.0, 0.0] for n in pos}
        for a, b in pairs:
            ax, ay = pos[a]
            bx, by = pos[b]
            dx, dy = ax - bx, ay - by
            d = math.hypot(dx, dy)
            if d < 1e-3:  # (near-)coincident — separate along deterministic directions
                ux, uy = _jitter_dir(a)
            else:
                ux, uy = dx / d, dy / d
            push = (min_dist - d) / 2.0 + 0.5  # +0.5 clears the strict "< min_dist" test
            disp[a][0] += ux * push
            disp[a][1] += uy * push
            disp[b][0] -= ux * push
            disp[b][1] -= uy * push
        for n, (dxn, dyn) in disp.items():
            pos[n][0] += dxn
            pos[n][1] += dyn
    return {n: (p[0], p[1]) for n, p in pos.items()}


# ── ring-interior protection ─────────────────────────────────────────────────
def detect_ring_interior_crossings(
    coords: Coords, edge_pairs: EdgePairs, rings: Rings,
    fraction: float = _RING_INTERIOR_FRACTION,
) -> list[tuple[str, str]]:
    """
    Edges that cut THROUGH a circular laundering ring's interior — the misleading
    crossing this module exists to forbid. An edge offends a ring when neither of
    its endpoints is on that ring (a real branch / unrelated edge) yet its segment
    passes within `fraction · radius` of the ring centre. Ring boundary edges
    (both endpoints on the ring) and spokes touching it are never flagged.
    Deterministic; returns sorted unique offenders.
    """
    offenders: set[tuple[str, str]] = set()
    for u, v in edge_pairs:
        if u == v or u not in coords or v not in coords:
            continue
        for members, centre, radius in rings:
            if u in members and v in members:
                continue  # this edge IS part of the ring boundary
            # An edge incident to the ring (one endpoint on it) is allowed to
            # touch the boundary but must not dive deep into the interior.
            incident = u in members or v in members
            limit = (fraction * 0.65 if incident else fraction) * radius
            if _seg_point_dist(coords[u], coords[v], centre) < limit:
                offenders.add((u, v))
                break
    return sorted(offenders)


def repair_ring_crossings(
    coords: Coords, edge_pairs: EdgePairs, rings: Rings,
    fraction: float = _RING_INTERIOR_FRACTION, iterations: int = 24,
) -> Coords:
    """
    Push the endpoints of any interior-cutting edge OUTWARD, clear of the ring, so
    no unrelated edge crosses a laundering circle. For each offending edge we move
    whichever endpoint is NOT a member of the crossed ring to just beyond the ring
    radius along the outward radial from the ring centre through that endpoint
    (ties / centre-coincident nodes use a deterministic direction). Ring members
    themselves are never moved (the circle is preserved). Bounded + deterministic;
    returns a new dict.
    """
    pos: Coords = dict(coords)
    member_of: dict[str, set[int]] = {}
    for ri, (members, _, _) in enumerate(rings):
        for m in members:
            member_of.setdefault(m, set()).add(ri)
    for _ in range(iterations):
        offenders = detect_ring_interior_crossings(pos, edge_pairs, rings, fraction)
        if not offenders:
            break
        for u, v in offenders:
            for ri, (members, centre, radius) in enumerate(rings):
                if u in members and v in members:
                    continue
                if _seg_point_dist(pos[u], pos[v], centre) >= fraction * radius:
                    continue
                cx, cy = centre
                clear = radius * (1.0 / fraction) + 1.0  # just outside the protected zone
                u_member = ri in member_of.get(u, set())
                v_member = ri in member_of.get(v, set())
                for endpoint, other, is_member in ((u, v, u_member), (v, u, v_member)):
                    if is_member:
                        continue  # never move a node that belongs to this ring
                    # If the OTHER end is on this ring, push outward along the radial
                    # THROUGH that ring node → the connecting edge becomes purely
                    # radial and can never re-enter the interior. Otherwise (a pure
                    # pass-by edge) push along the endpoint's own radial.
                    anchor = other if (ri in member_of.get(other, set())) else endpoint
                    ax, ay = pos[anchor]
                    ux, uy = ax - cx, ay - cy
                    d = math.hypot(ux, uy)
                    if d < 1e-6:
                        ux, uy = _jitter_dir(endpoint)
                    else:
                        ux, uy = ux / d, uy / d
                    pos[endpoint] = (cx + ux * clear, cy + uy * clear)
    return pos


# ── assessment ─────────────────────────────────────────────────────────────────
def _edge_metrics(coords: Coords, edge_pairs: EdgePairs) -> dict[str, Any]:
    """Average / max edge length + chain straightness (collinearity of pass-through
    nodes) + hub congestion (tightest angular crowding at the busiest node)."""
    lengths = []
    succ: dict[str, list[str]] = {}
    pred: dict[str, list[str]] = {}
    incident: dict[str, list[str]] = {}
    for u, v in edge_pairs:
        if u in coords and v in coords and u != v:
            ux, uy = coords[u]
            vx, vy = coords[v]
            lengths.append(math.hypot(vx - ux, vy - uy))
            succ.setdefault(u, []).append(v)
            pred.setdefault(v, []).append(u)
            incident.setdefault(u, []).append(v)
            incident.setdefault(v, []).append(u)

    avg_len = sum(lengths) / len(lengths) if lengths else 0.0
    max_len = max(lengths, default=0.0)

    # chain straightness: pass-through nodes (1 in, 1 out) that are collinear
    straight = []
    for n in coords:
        ps, ss = pred.get(n, []), succ.get(n, [])
        if len(ps) == 1 and len(ss) == 1:
            ax, ay = coords[ps[0]]
            bx, by = coords[n]
            cx, cy = coords[ss[0]]
            v1 = (bx - ax, by - ay)
            v2 = (cx - bx, cy - by)
            m1 = math.hypot(*v1) or 1e-9
            m2 = math.hypot(*v2) or 1e-9
            cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (m1 * m2)))
            straight.append((cos + 1) / 2)  # 1 = perfectly straight, 0 = reversed
    chain_straightness = sum(straight) / len(straight) if straight else 1.0

    # hub congestion: at the highest-degree node, the smallest angular gap between
    # its incident edges (small = crowded spokes). 1.0 = no hub / well-spread.
    congestion = 0.0
    if incident:
        hub = max(incident, key=lambda k: len(incident[k]))
        nbrs = incident[hub]
        if len(nbrs) >= 2:
            hx, hy = coords[hub]
            angs = sorted(math.atan2(coords[m][1] - hy, coords[m][0] - hx) for m in nbrs)
            gaps = [angs[i + 1] - angs[i] for i in range(len(angs) - 1)]
            gaps.append(2 * math.pi - (angs[-1] - angs[0]))
            ideal = 2 * math.pi / len(nbrs)
            congestion = max(0.0, 1.0 - min(gaps) / ideal)  # 0 = even, →1 = crowded
    return {
        "avg_edge_length": round(avg_len, 2),
        "max_edge_length": round(max_len, 2),
        "chain_straightness": round(chain_straightness, 4),
        "hub_congestion": round(congestion, 4),
    }


def assess_quality(
    coords: Coords, edge_pairs: EdgePairs, min_dist: float = 60.0,
    rings: Rings | None = None,
) -> dict[str, Any]:
    """
    Score a layout's readability: crossing count, node overlap, edge length,
    chain straightness, hub congestion and — when `rings` is supplied —
    ring-interior crossings (edges cutting through a laundering circle), plus a
    0–1 quality score. `pass` is True when there is no node overlap, NO ring is
    stabbed, and the crossing ratio is low. Listed `issues` explain any failure
    in plain language. `rings` defaults to None so non-ring callers are unaffected.
    """
    n = len(coords)
    cross = count_crossings(coords, edge_pairs)
    overlaps = detect_overlaps(coords, min_dist)
    ring_cuts = detect_ring_interior_crossings(coords, edge_pairs, rings) if rings else []
    e = max(1, cross["edges_considered"])
    crossing_ratio = cross["crossings"] / e
    overlap_ratio = len(overlaps) / max(1, n)
    em = _edge_metrics(coords, edge_pairs)

    issues: list[str] = []
    if overlaps:
        issues.append(f"{len(overlaps)} node pair(s) overlap (< {min_dist:g} units apart)")
    if ring_cuts:
        issues.append(f"{len(ring_cuts)} edge(s) cut through a laundering ring interior")
    if crossing_ratio > 0.5:
        issues.append(f"high edge-crossing ratio ({crossing_ratio:.2f} per edge)")
    if em["hub_congestion"] > 0.7:
        issues.append("hub spokes are crowded (starburst risk)")
    if em["chain_straightness"] < 0.6:
        issues.append("forwarding chains are not straight")

    # quality 1.0 = no overlaps, no crossings; degrades with both + ring stabs
    quality = max(
        0.0,
        1.0 - min(1.0, overlap_ratio) * 0.6 - min(1.0, crossing_ratio) * 0.4
        - (0.4 if ring_cuts else 0.0),
    )
    return {
        "node_count": n,
        "crossings": cross["crossings"],
        "crossings_estimated": cross["estimated"],
        "crossing_ratio": round(crossing_ratio, 4),
        "overlap_count": len(overlaps),
        "overlap_ratio": round(overlap_ratio, 4),
        "ring_interior_crossings": len(ring_cuts),
        "quality_score": round(quality, 4),
        "pass": not overlaps and not ring_cuts and crossing_ratio <= 0.5,
        "issues": issues,
        **em,
    }
