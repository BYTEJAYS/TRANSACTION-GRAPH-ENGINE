"""
Backend graph layout engine — server-computed node coordinates.

WHY THIS EXISTS
---------------
The graph was previously laid out entirely in the browser with a single
force-directed pass. Force-directed layout collapses regular structures into
perfect polygons / rings with crossing edges, which *hides* the very fraud
shapes investigators need to read (fan-out, chains, diamonds, cycles). It is
also non-deterministic, so the picture jitters between refreshes.

This module computes layouts on the server, structurally aware of money flow,
so each fraud topology is drawn the way an analyst expects:

  * fund_flow  — money moves strictly LEFT → RIGHT (source ➜ beneficiary).
  * layered    — same layering, drawn TOP → DOWN (investigation hierarchy).
  * community  — clusters are spatially separated, each laid out internally.
  * force      — organic relationship view (deterministic, seeded).
  * timeline   — nodes ordered by the time their money first moved.

Every mode is DETERMINISTIC for a given input (nodes are processed in sorted
order, force modes are seeded) so the layout is stable between refreshes.

The engine is additive and side-effect free: it takes plain node/edge dicts
(exactly the shape `get_graph_state()` already returns) and returns coordinates.
It never mutates the live graph and is not wired into the default broadcast.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Any

import networkx as nx

# The five backend layout strategies the frontend can switch between.
LAYOUT_MODES: tuple[str, ...] = ("force", "fund_flow", "layered", "community", "timeline")

# World-space spacing constants (the frontend fits/scales these to its viewport).
_LAYER_GAP = 220.0   # distance between successive flow layers
_NODE_GAP = 120.0    # distance between sibling nodes within a layer
_CROSSING_SWEEPS = 4 # barycenter passes to reduce edge crossings
_MIN_NODE_DIST = 60.0  # minimum readable separation; repaired if violated
_COMPONENT_GAP = 180.0  # empty band between two disconnected clusters (no overlap)
_RING_BRANCH_GAP = 138.0  # radial spacing per hop for branches hanging off a ring
_RING_SIBLING_SPREAD = 0.42  # radians between sibling spurs sharing one ring anchor
_FAN_MIN = 4              # root out-degree at/above which the radial fan-out applies
_FAN_RADIUS = 200.0       # radius of a fan's direct-children ring
_FAN_BRANCH_GAP = 150.0   # radial spacing per hop for a fan child's downstream tail
_FAN_SIBLING_SPREAD = 0.34  # radians between sibling spurs in one fan corridor


def _spring_iters(n: int) -> int:
    """Size-adaptive spring-layout iterations: full quality on small graphs,
    bounded work on large ones (spring_layout is O(n²) per iteration)."""
    return min(200, max(40, 6000 // max(1, n)))


# ── graph construction ───────────────────────────────────────────────────────
def _build_digraph(nodes: list[dict], edges: list[dict]) -> nx.DiGraph:
    """Aggregate raw node/edge dicts into a directed graph (parallel edges summed)."""
    G = nx.DiGraph()
    for n in nodes:
        nid = n.get("id")
        if nid is not None:
            # Carry cash-event identity so stage labels / boundary placement are
            # semantically correct even when the node name isn't CASH* (rail-driven).
            G.add_node(str(nid), account_type=n.get("account_type"), cash_kind=n.get("cash_kind"))
    for e in edges:
        s, t = str(e.get("source", "")), str(e.get("target", ""))
        if not s or not t or s == t:
            continue  # self-loops carry no layout information
        if s not in G:
            G.add_node(s)
        if t not in G:
            G.add_node(t)
        amt = float(e.get("amount", 0) or 0)
        if G.has_edge(s, t):
            G[s][t]["amount"] += amt
            G[s][t]["count"] += 1
        else:
            G.add_edge(s, t, amount=amt, count=1, timestamp=e.get("timestamp", ""))
    return G


# ── flow layering (shared by fund_flow + layered) ────────────────────────────
def _longest_path_layers(G: nx.DiGraph) -> dict[str, int]:
    """
    Assign each node a layer = longest directed distance from a source.

    Cycles (circular laundering) would make naive longest-path infinite, so we
    first condense strongly-connected components into a DAG, layer the DAG, then
    project the layer back onto every member node. Result: sources sit at layer
    0, each forwarding hop increments the layer — money flows monotonically
    across layers, which is exactly the fund-flow reading.
    """
    if G.number_of_nodes() == 0:
        return {}
    C = nx.condensation(G)                       # DAG of SCCs
    mapping: dict[str, int] = C.graph["mapping"]  # original node → scc id
    layer_scc: dict[int, int] = {s: 0 for s in C.nodes()}
    for s in nx.topological_sort(C):
        for _, succ in C.out_edges(s):
            if layer_scc[succ] < layer_scc[s] + 1:
                layer_scc[succ] = layer_scc[s] + 1
    return {n: layer_scc[mapping[n]] for n in G.nodes()}


def _order_within_layers(
    G: nx.DiGraph, layers: dict[str, int], method: str = "barycenter",
) -> dict[int, list[str]]:
    """
    Order each layer so connected nodes line up, cutting edge crossings.
    `method` selects the heuristic — "barycenter" (mean neighbour rank) or
    "median" (median neighbour rank); the median heuristic often beats the mean
    on heavily skewed fan-in/fan-out layers. Deterministic (stable sorted seed +
    fixed sweep count)."""
    by_layer: dict[int, list[str]] = defaultdict(list)
    for n, l in layers.items():
        by_layer[l].append(n)
    for l in by_layer:
        by_layer[l].sort()  # stable, deterministic starting order
    if not by_layer:
        return by_layer
    max_l = max(by_layer)
    rank = {n: i for l in by_layer for i, n in enumerate(by_layer[l])}

    def agg(node: str, neighbours) -> float:
        rs = sorted(rank[x] for x in neighbours if x in rank)
        if not rs:
            return rank[node]  # no neighbours in adjacent layer → hold position
        if method == "median":
            return rs[len(rs) // 2]
        return sum(rs) / len(rs)

    for _ in range(_CROSSING_SWEEPS):
        for l in range(1, max_l + 1):  # sweep down, align to predecessors above
            by_layer[l].sort(key=lambda n: agg(n, G.predecessors(n)))
            for i, n in enumerate(by_layer[l]):
                rank[n] = i
        for l in range(max_l - 1, -1, -1):  # sweep up, align to successors below
            by_layer[l].sort(key=lambda n: agg(n, G.successors(n)))
            for i, n in enumerate(by_layer[l]):
                rank[n] = i
    return by_layer


def _count_layer_crossings(G: nx.DiGraph, by_layer: dict[int, list[str]]) -> int:
    """Count edge crossings between consecutive layers given the current order
    (the standard layered-drawing crossing number). Used to pick the better of
    two ordering heuristics."""
    rank = {n: i for members in by_layer.values() for i, n in enumerate(members)}
    layer_of = {n: l for l, members in by_layer.items() for n in members}
    crossings = 0
    # group inter-layer edges, then count inversions of their lower endpoints
    seq: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for u, v in G.edges():
        lu, lv = layer_of.get(u), layer_of.get(v)
        if lu is None or lv is None or abs(lu - lv) != 1:
            continue
        top, bot = (u, v) if lu < lv else (v, u)
        seq[min(lu, lv)].append((rank[top], rank[bot]))
    for edges in seq.values():
        edges.sort()  # by upper endpoint, then lower
        for i in range(len(edges)):
            for j in range(i + 1, len(edges)):
                if edges[i][1] > edges[j][1]:
                    crossings += 1
    return crossings


def _best_order(G: nx.DiGraph, layers: dict[str, int]) -> dict[int, list[str]]:
    """Try both ordering heuristics and keep the one with fewer crossings —
    the measured 'extra optimisation pass' (item 4)."""
    bary = _order_within_layers(G, layers, "barycenter")
    if G.number_of_edges() > 4000:          # large graphs: skip the second pass
        return bary
    med = _order_within_layers(G, layers, "median")
    return med if _count_layer_crossings(G, med) < _count_layer_crossings(G, bary) else bary


def _layered_positions(G: nx.DiGraph, horizontal: bool) -> tuple[dict[str, tuple[float, float]], dict[str, int]]:
    """
    Place nodes on flow layers, one WEAKLY-CONNECTED COMPONENT at a time, and
    stack the components along the perpendicular axis so disconnected clusters
    never share space (no overlap, no inter-cluster crossings). horizontal=True →
    money flows L→R (fund_flow); else top→down (layered).
    """
    layers = _longest_path_layers(G)
    pos: dict[str, tuple[float, float]] = {}
    if G.number_of_nodes() == 0:
        return pos, layers

    wccs = sorted((sorted(c) for c in nx.weakly_connected_components(G)),
                  key=lambda c: (-len(c), c[0]))
    offset = 0.0  # running secondary offset → each component gets its own band
    for comp in wccs:
        sub = G.subgraph(comp)
        by_layer = _best_order(sub, {n: layers[n] for n in comp})
        width = max((len(m) for m in by_layer.values()), default=1)
        half = (width - 1) / 2.0
        for l, members in by_layer.items():
            span = (len(members) - 1) / 2.0
            for i, n in enumerate(members):
                primary = l * _LAYER_GAP
                secondary = (i - span) * _NODE_GAP + offset
                pos[n] = (primary, -secondary) if horizontal else (secondary, -primary)
        offset += (half * 2) * _NODE_GAP + _COMPONENT_GAP + _NODE_GAP

    # centre the whole stacked layout on the origin
    if pos:
        xs = [p[0] for p in pos.values()]
        ys = [p[1] for p in pos.values()]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        pos = {n: (x - cx, y - cy) for n, (x, y) in pos.items()}
    return pos, layers


def _is_cash_node(n: str) -> bool:
    return str(n).upper().startswith(("CASH", "CASH_OUT", "CASH_IN"))


def _circularize_cycles(G: nx.DiGraph, pos: dict[str, tuple[float, float]]) -> None:
    """
    Lay each real cycle (strongly-connected component of ≥3 nodes) out as a RING
    around its current centroid, in place, so circular laundering reads as a
    circle instead of a collapsed line. Radius is capped below half a layer gap
    so the ring never bleeds into the neighbouring layers.
    """
    for scc in nx.strongly_connected_components(G):
        members = list(scc)
        if len(members) < 3:
            continue
        member_set = set(members)
        pts = [pos[n] for n in members if n in pos]
        if not pts:
            continue
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        R = min(_LAYER_GAP * 0.42, max(_NODE_GAP, _NODE_GAP * len(members) / (2 * math.pi)))
        sub = G.subgraph(members)
        try:  # order along the cycle so consecutive ring slots are flow-adjacent
            order = list(nx.dfs_preorder_nodes(sub, source=sorted(members)[0]))
            order += [m for m in sorted(members) if m not in order]
        except Exception:
            order = sorted(members)
        k = len(order)
        base_ang = {n: 2 * math.pi * i / k for i, n in enumerate(order)}

        # ── ORIENT the ring: rotate it so the node(s) carrying its EXTERNAL edges
        #    (gateways — spurs, bridges, cash-out) face the direction of those
        #    external neighbours. This keeps every branch leaving on the OUTSIDE
        #    facing the rest of the graph, so a bridge between two rings sits
        #    between them (outward of both) instead of one ring's edge having to
        #    reach across the other ring's interior. Uses the pre-circularize
        #    layered positions of the external neighbours as the "mass" to face.
        rot = 0.0
        gateways = [n for n in order
                    if any(nb not in member_set
                           for nb in set(G.successors(n)) | set(G.predecessors(n)))]
        ext_pts: list[tuple[float, float]] = []
        for n in gateways:
            for nb in set(G.successors(n)) | set(G.predecessors(n)):
                if nb not in member_set and nb in pos:
                    ext_pts.append(pos[nb])
        if gateways and ext_pts:
            ex = sum(p[0] for p in ext_pts) / len(ext_pts) - cx
            ey = sum(p[1] for p in ext_pts) / len(ext_pts) - cy
            if math.hypot(ex, ey) > 1e-6:
                target = math.atan2(ey, ex)
                # circular mean of the gateway nodes' current ring angles
                gx = sum(math.cos(base_ang[n]) for n in gateways)
                gy = sum(math.sin(base_ang[n]) for n in gateways)
                if math.hypot(gx, gy) > 1e-6:
                    rot = target - math.atan2(gy, gx)

        for n in order:
            ang = base_ang[n] + rot
            pos[n] = (cx + R * math.cos(ang), cy + R * math.sin(ang))


def ring_geometry(
    G: nx.DiGraph, pos: dict[str, tuple[float, float]],
) -> list[tuple[set[str], tuple[float, float], float]]:
    """
    Geometry of every circular laundering motif: each strongly-connected
    component of ≥3 nodes, as (member-set, centre, radius). The radius is the
    ACTUAL farthest member from the centroid (so it bounds the drawn ring),
    floored at one node gap. Used to (a) place branches outside the ring and
    (b) validate that no unrelated edge cuts through the ring interior.
    """
    rings: list[tuple[set[str], tuple[float, float], float]] = []
    for scc in nx.strongly_connected_components(G):
        members = {m for m in scc if m in pos}
        if len(members) < 3:
            continue
        pts = [pos[m] for m in members]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        R = max((math.hypot(p[0] - cx, p[1] - cy) for p in pts), default=_NODE_GAP)
        rings.append((members, (cx, cy), max(R, _NODE_GAP)))
    return rings


def _resolve_ring_branches(G: nx.DiGraph, pos: dict[str, tuple[float, float]]) -> None:
    """
    Place every node that hangs OFF a circular laundering ring OUTSIDE that ring,
    fanned radially OUTWARD from its anchor ring node — never on the layered
    fund-flow axis where the connecting edge would stab straight through the ring
    interior (the misleading "cash-out path crosses the laundering circle" bug).

    `_circularize_cycles` only relocates the cycle members themselves; the spurs
    and tails attached to them keep their layered coordinates, so a ROUND_C →
    CIR_LAYER_001 edge ran from the ring across to the global L→R axis. Here, for
    each ring we:

      1. Multi-source BFS out from ALL ring nodes → every external node's nearest
         ring node (its anchor) and hop distance.
      2. Group external nodes by (anchor, hop) so a hub's spurs fan tangentially
         instead of stacking on one ray.
      3. Position each at `centre + outward(anchor) · (R + hop · gap)`, i.e. along
         the outward radial from the ring centre through its anchor.

    Result: a ring node → layer-1 → layer-2 → cash-out chain leaves the circle
    cleanly outward; every connecting segment stays outside the ring interior.
    This mirrors the proven frontend embedded-ring algorithm (graphLayout.ts) so
    server and client agree on the shape. In place; no-op when there is no ring.
    """
    rings = ring_geometry(G, pos)
    if not rings:
        return

    ring_of: dict[str, int] = {}
    ring_nodes: set[str] = set()
    for ri, (members, _, _) in enumerate(rings):
        for n in members:
            ring_of[n] = ri
        ring_nodes |= members

    # Multi-source BFS over the UNDIRECTED graph: nearest ring node + hop count.
    UG = G.to_undirected(as_view=True)
    hop: dict[str, int] = {n: 0 for n in ring_nodes}
    anchor: dict[str, str] = {n: n for n in ring_nodes}
    frontier = sorted(ring_nodes)
    while frontier:
        nxt: list[str] = []
        for u in frontier:
            for v in sorted(UG.neighbors(u)):
                if v not in hop:
                    hop[v] = hop[u] + 1
                    anchor[v] = anchor[u]
                    nxt.append(v)
        frontier = nxt

    # Group external nodes by (anchor, hop); siblings fan tangentially.
    groups: dict[tuple[str, int], list[str]] = defaultdict(list)
    for n in G.nodes():
        if n in ring_nodes or n not in anchor:
            continue  # isolated-from-any-ring node — left to the layered layout
        groups[(anchor[n], hop[n])].append(n)

    for (anc, h), members in groups.items():
        _, (cx, cy), R = rings[ring_of[anc]]
        ax, ay = pos[anc]
        base = math.atan2(ay - cy, ax - cx)  # outward: ring centre → anchor → beyond
        members.sort()
        for i, n in enumerate(members):
            ang = base + (i - (len(members) - 1) / 2.0) * _RING_SIBLING_SPREAD
            rr = R + h * _RING_BRANCH_GAP
            pos[n] = (cx + rr * math.cos(ang), cy + rr * math.sin(ang))


def _radialize_fans(G: nx.DiGraph, pos: dict[str, tuple[float, float]]) -> None:
    """
    Re-lay each WIDE rooted fan-out (a weakly-connected component that is a rooted
    out-tree whose root has out-degree ≥ _FAN_MIN and which has downstream tails) as
    a RADIAL fan around the root's current centroid, in place. The layered engine
    stacks a fan-with-tails into columns and pushes the branch-bearing children to
    the extremes ("one smurf shoots sideways"); a radial fan keeps every hub→child
    edge the same length and fans each child's tail OUTWARD in its own corridor so
    cash-out branches clearly exit. Mirrors `_circularize_cycles` (a motif post-pass)
    and the frontend `placeRadialFan`. No-op unless a component is exactly this shape.
    """
    for comp in nx.weakly_connected_components(G):
        members = [m for m in comp if m in pos]
        if len(members) < _FAN_MIN + 2:  # need root + ≥FAN_MIN children + ≥1 tail node
            continue
        sub = G.subgraph(comp)
        roots = [n for n in comp if sub.in_degree(n) == 0]
        if len(roots) != 1:
            continue
        root = roots[0]
        root_out = sub.out_degree(root)
        max_out = max(sub.out_degree(n) for n in comp)
        is_tree = sub.number_of_edges() == len(comp) - 1 and all(
            sub.in_degree(n) == 1 for n in comp if n != root
        )
        if not (root_out == max_out and root_out >= _FAN_MIN and is_tree
                and len(comp) > root_out + 1):
            continue

        cx = sum(pos[m][0] for m in members) / len(members)
        cy = sum(pos[m][1] for m in members) / len(members)
        children = sorted(sub.successors(root))
        k = len(children)
        pos[root] = (cx, cy)
        child_angle: dict[str, float] = {}
        for i, c in enumerate(children):
            ang = -math.pi / 2 + 2 * math.pi * i / k
            child_angle[c] = ang
            pos[c] = (cx + _FAN_RADIUS * math.cos(ang), cy + _FAN_RADIUS * math.sin(ang))
        # BFS downstream → hop + corridor (which direct child a descendant belongs to)
        hop = {root: 0}
        corridor: dict[str, str] = {}
        for c in children:
            hop[c] = 1
            corridor[c] = c
        frontier = list(children)
        while frontier:
            nxt = []
            for u in frontier:
                for v in sorted(sub.successors(u)):
                    if v not in hop:
                        hop[v] = hop[u] + 1
                        corridor[v] = corridor[u]
                        nxt.append(v)
            frontier = nxt
        groups: dict[tuple[str, int], list[str]] = defaultdict(list)
        for n in comp:
            if n == root or hop.get(n, 0) <= 1:
                continue
            groups[(corridor[n], hop[n])].append(n)
        for (c, h), mem in groups.items():
            base = child_angle[c]
            mem.sort()
            for i, n in enumerate(mem):
                ang = base + (i - (len(mem) - 1) / 2.0) * _FAN_SIBLING_SPREAD
                rr = _FAN_RADIUS + (h - 1) * _FAN_BRANCH_GAP
                pos[n] = (cx + rr * math.cos(ang), cy + rr * math.sin(ang))


def _stage_label(G: nx.DiGraph, n: str) -> str:
    """Semantic investigation stage for a node, from its flow role."""
    ind, outd = G.in_degree(n), G.out_degree(n)
    # Rail-driven cash identity (set in graph_manager) takes precedence over the name.
    ck = G.nodes[n].get("cash_kind") if n in G.nodes else None
    if ck == "CASH_IN":
        return "cash_in"
    if ck == "CASH_OUT" or G.nodes.get(n, {}).get("account_type") == "cash" or _is_cash_node(n):
        return "cash_out"
    if ind == 0 and outd > 0:
        return "origin"
    if outd == 0 and ind > 0:
        return "exit"
    if outd >= 3:
        return "distribution"
    if ind >= 3:
        return "aggregation"
    if ind == 1 and outd == 1:
        return "layering"
    return "transit"


# ── force (relationship) ─────────────────────────────────────────────────────
def _force_positions(G: nx.DiGraph, seed: int) -> dict[str, tuple[float, float]]:
    if G.number_of_nodes() == 0:
        return {}
    if G.number_of_nodes() == 1:
        return {next(iter(G.nodes())): (0.0, 0.0)}
    k = 1.0 / math.sqrt(G.number_of_nodes())
    # Seeded spring layout is deterministic and organic — edge weight by amount
    # pulls heavy-money pairs closer, surfacing the real relationship structure.
    raw = nx.spring_layout(G, seed=seed, k=k, iterations=_spring_iters(G.number_of_nodes()), weight="amount")
    scale = 240.0 + 60.0 * math.sqrt(G.number_of_nodes())
    return {n: (float(p[0]) * scale, float(p[1]) * scale) for n, p in raw.items()}


# ── community (cluster) ──────────────────────────────────────────────────────
def _community_positions(G: nx.DiGraph, seed: int) -> tuple[dict[str, tuple[float, float]], dict[str, int]]:
    """
    Spatially separated communities, ordered LEFT → RIGHT by their flow stage so
    the geometry itself tells the laundering story: origin-side clusters sit
    left, mid-flow layering clusters in the middle, and cash-out clusters far
    right. Stage = the community's average money-flow layer, pushed rightmost
    when it contains a cash-out node. Each community is laid out internally with
    a seeded spring and stacked vertically to avoid inter-cluster overlap.
    """
    UG = G.to_undirected()
    node_comm: dict[str, int] = {}
    if UG.number_of_nodes() == 0:
        return {}, node_comm
    try:
        from networkx.algorithms.community import greedy_modularity_communities
        comms = ([set(UG.nodes())] if UG.number_of_nodes() < 2
                 else [set(c) for c in greedy_modularity_communities(UG)])
    except Exception:
        comms = [set(UG.nodes())]

    # Stage score per community: average flow layer, with cash-out clusters
    # forced to the far right. Sort L→R by stage (deterministic tie-break on id).
    layers = _longest_path_layers(G)
    max_layer = max(layers.values(), default=0)

    def _is_cash(n: str) -> bool:
        return n.upper().startswith(("CASH", "CASH_OUT", "CASH_IN"))

    def _stage(c: set[str]) -> float:
        avg_layer = sum(layers.get(n, 0) for n in c) / max(1, len(c))
        if any(_is_cash(n) for n in c):
            avg_layer = max_layer + 2  # cash-out clusters belong at the far right
        return avg_layer

    comms.sort(key=lambda c: (_stage(c), -len(c), sorted(c)[0] if c else ""))

    pos: dict[str, tuple[float, float]] = {}
    n_comm = len(comms)
    col_gap = max(360.0, 2.2 * _LAYER_GAP)  # horizontal gap between stage columns
    for ci, c in enumerate(comms):
        for n in c:
            node_comm[n] = ci
        cx = (ci - (n_comm - 1) / 2.0) * col_gap if n_comm > 1 else 0.0
        cy = 0.0
        if len(c) == 1:
            pos[next(iter(c))] = (cx, cy)
            continue
        sub = UG.subgraph(c)
        local = nx.spring_layout(sub, seed=seed, k=1.0 / math.sqrt(len(c)),
                                 iterations=_spring_iters(len(c)))
        spread = 80.0 + 24.0 * math.sqrt(len(c))
        for n, p in local.items():
            pos[n] = (cx + float(p[0]) * spread, cy + float(p[1]) * spread)
    return pos, node_comm


# ── timeline (time ordered) ──────────────────────────────────────────────────
def _parse_ts(raw: Any) -> float | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw)).timestamp()
    except Exception:
        return None


def _timeline_positions(G: nx.DiGraph) -> dict[str, tuple[float, float]]:
    """x = when the node's money first moved; y = a packed lane avoiding overlap."""
    if G.number_of_nodes() == 0:
        return {}
    first_seen: dict[str, float] = {}
    for n in G.nodes():
        times = [t for _, _, d in G.in_edges(n, data=True) if (t := _parse_ts(d.get("timestamp"))) is not None]
        times += [t for _, _, d in G.out_edges(n, data=True) if (t := _parse_ts(d.get("timestamp"))) is not None]
        first_seen[n] = min(times) if times else 0.0

    lo = min(first_seen.values())
    hi = max(first_seen.values())
    span = (hi - lo) or 1.0
    width = max(800.0, _LAYER_GAP * G.number_of_nodes() ** 0.5)
    # Order by (time, id) and pack into lanes so temporally-close nodes stack
    # vertically instead of overlapping on the same x.
    ordered = sorted(G.nodes(), key=lambda n: (first_seen[n], n))
    lane_last_x: list[float] = []
    pos: dict[str, tuple[float, float]] = {}
    min_dx = width / max(1, len(ordered)) * 0.9
    for n in ordered:
        x = (first_seen[n] - lo) / span * width
        lane = next((i for i, lx in enumerate(lane_last_x) if x - lx >= min_dx), None)
        if lane is None:
            lane = len(lane_last_x)
            lane_last_x.append(x)
        else:
            lane_last_x[lane] = x
        pos[n] = (x - width / 2.0, lane * _NODE_GAP)
    # centre vertically
    if pos:
        cy = sum(p[1] for p in pos.values()) / len(pos)
        pos = {n: (x, y - cy) for n, (x, y) in pos.items()}
    return pos


# ── automatic layout selection ─────────────────────────────────────────────────
def recommend_layout(nodes: list[dict], edges: list[dict]) -> tuple[str, str]:
    """
    Choose the most investigation-appropriate layout from the graph's STRUCTURE,
    so the backend decides — the investigator never picks an algorithm. Returns
    (mode, reason). Deterministic.

      multiple disconnected clusters  → community  (separate the laundering rings)
      deep single forwarding chain    → layered    (shell-chain hierarchy)
      heavy fan-out / fan-in / cycles → fund_flow  (money movement L→R)
      flat, time-spread activity      → timeline
      otherwise                       → fund_flow  (clear money-direction default)
    """
    G = _build_digraph(nodes, edges)
    if G.number_of_nodes() == 0:
        return "fund_flow", "empty graph — default money-flow view"

    big_components = [c for c in nx.weakly_connected_components(G) if len(c) >= 3]
    layers = _longest_path_layers(G)
    max_layer = max(layers.values(), default=0)
    max_out = max((d for _, d in G.out_degree()), default=0)
    max_in = max((d for _, d in G.in_degree()), default=0)
    has_cycle = not nx.is_directed_acyclic_graph(G)

    if len(big_components) >= 2:
        return "community", f"{len(big_components)} disconnected clusters of ≥3 accounts"
    if max_layer >= 5 and max_out <= 2 and max_in <= 2:
        return "layered", f"deep {max_layer}-hop forwarding chain (shell-chain shaped)"
    if max_out >= 4 or max_in >= 4 or has_cycle:
        why = []
        if max_out >= 4:
            why.append(f"fan-out ×{max_out}")
        if max_in >= 4:
            why.append(f"fan-in ×{max_in}")
        if has_cycle:
            why.append("circular flow")
        return "fund_flow", "money-movement structure (" + ", ".join(why) + ")"
    if max_layer <= 1 and G.number_of_nodes() >= 8:
        return "timeline", "flat, time-distributed activity with little flow depth"
    return "fund_flow", "simple graph — default money-flow view"


# ── public API ───────────────────────────────────────────────────────────────
def compute_layout(
    nodes: list[dict],
    edges: list[dict],
    mode: str = "force",
    seed: int = 42,
) -> dict[str, Any]:
    """
    Compute server-side coordinates for a graph snapshot.

    Parameters
    ----------
    nodes, edges : the exact dict shape `get_graph_state()` returns.
    mode         : one of LAYOUT_MODES.
    seed         : determinism seed for force-based modes.

    Returns
    -------
    dict with:
      mode       : the resolved mode
      positions  : { node_id: {"x": float, "y": float} }
      node_meta  : { node_id: {"layer": int?, "community": int?} } (mode-dependent)
      bounds     : {minX, maxX, minY, maxY}
      node_count : int
    """
    # "auto" → the backend chooses the best layout from the graph structure.
    requested_mode = mode
    selection_reason: str | None = None
    if mode == "auto":
        mode, selection_reason = recommend_layout(nodes, edges)
    if mode not in LAYOUT_MODES:
        raise ValueError(f"unknown layout mode {requested_mode!r}; expected 'auto' or one of {LAYOUT_MODES}")

    G = _build_digraph(nodes, edges)
    node_meta: dict[str, dict[str, Any]] = defaultdict(dict)

    if mode == "force":
        coords = _force_positions(G, seed)
    elif mode in ("fund_flow", "layered"):
        coords, layers = _layered_positions(G, horizontal=(mode == "fund_flow"))
        _circularize_cycles(G, coords)      # cycles read as rings, not collapsed lines
        _resolve_ring_branches(G, coords)   # spurs/cash-out leave the ring OUTWARD, never through it
        _radialize_fans(G, coords)          # wide fan-outs read as fans, branches fan OUTWARD
        for n, l in layers.items():
            node_meta[n]["layer"] = l
            node_meta[n]["stage"] = _stage_label(G, n)  # semantic investigation stage
    elif mode == "community":
        coords, comm = _community_positions(G, seed)
        for n, c in comm.items():
            node_meta[n]["community"] = c
    else:  # timeline
        coords = _timeline_positions(G)

    # ── quality validation + automatic repair ────────────────────────────────
    # Measure readability (crossings + node overlap) and, if nodes overlap, run a
    # bounded repair pass to push them apart BEFORE returning coordinates. The
    # quality block is reported back so the caller can see (and trust) the result.
    from graph_engine.layout_quality import (
        assess_quality, repair_overlaps, repair_ring_crossings,
    )

    edge_pairs = [(u, v) for u, v in G.edges()]
    # Ring interiors are a PROTECTED no-crossing zone: an unrelated edge that cuts
    # through a laundering circle is misleading, so we validate + repair it the
    # same way we repair node overlap. Rings only exist in the flow modes.
    rings = ring_geometry(G, coords) if mode in ("fund_flow", "layered") else None
    quality = assess_quality(coords, edge_pairs, min_dist=_MIN_NODE_DIST, rings=rings)
    repaired = False
    if rings and quality["ring_interior_crossings"] > 0 and coords:
        coords = repair_ring_crossings(coords, edge_pairs, rings)
        rings = ring_geometry(G, coords)  # geometry shifts as endpoints move out
        quality = assess_quality(coords, edge_pairs, min_dist=_MIN_NODE_DIST, rings=rings)
        repaired = True
    if quality["overlap_count"] > 0 and coords:
        coords = repair_overlaps(coords, _MIN_NODE_DIST)
        quality = assess_quality(coords, edge_pairs, min_dist=_MIN_NODE_DIST, rings=rings)
        repaired = True
    quality["repaired"] = repaired

    positions = {n: {"x": round(x, 2), "y": round(y, 2)} for n, (x, y) in coords.items()}
    if positions:
        xs = [p["x"] for p in positions.values()]
        ys = [p["y"] for p in positions.values()]
        bounds = {"minX": min(xs), "maxX": max(xs), "minY": min(ys), "maxY": max(ys)}
    else:
        bounds = {"minX": 0.0, "maxX": 0.0, "minY": 0.0, "maxY": 0.0}

    return {
        "mode": mode,                              # the layout actually used
        "requested_mode": requested_mode,          # "auto" when the backend chose
        "auto_selected": requested_mode == "auto",
        "selection_reason": selection_reason,      # why the backend picked it (auto only)
        "positions": positions,
        "node_meta": {n: m for n, m in node_meta.items() if m},
        "bounds": bounds,
        "node_count": len(positions),
        "quality": quality,
    }
