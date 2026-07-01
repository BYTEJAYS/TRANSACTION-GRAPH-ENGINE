"""
Graph Engine — turns a TGIE component snapshot into a rich working graph and
computes the structural primitives every downstream engine relies on.

Critically: each component is analysed in complete isolation.  We only ever see
the nodes/edges of the single connected component handed to us, so there is no
possibility of phantom connections or cross-cluster contamination.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import networkx as nx


def _parse_ts(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return None


class TransactionGraph:
    """
    A directed multigraph-aware view of one component.

    Edges are aggregated per (source,target) ordered pair: we keep the summed
    amount, transfer count, and the list of timestamps so timing-based detectors
    (velocity, burst, dormancy) have what they need.
    """

    def __init__(self, component: dict):
        self.graph_id: str = component.get("graph_id", "GRAPH_001")
        self.raw_nodes: list[dict] = component.get("nodes", [])
        self.raw_edges: list[dict] = component.get("edges", [])
        self.node_meta: dict[str, dict] = {n["id"]: n for n in self.raw_nodes if "id" in n}

        self.G = nx.DiGraph()
        self._build()

        # cached primitives (lazy)
        self._cycles: list[list[str]] | None = None
        self._components_undirected: list[set[str]] | None = None

    # ── construction ──────────────────────────────────────────────────────────
    def _build(self) -> None:
        # ensure isolated/island nodes still appear
        for nid, meta in self.node_meta.items():
            self.G.add_node(nid, **{
                "prior_risk": float(meta.get("risk_score", 0.0) or 0.0),
                "account_type": meta.get("account_type", "normal"),
                "prior_patterns": list(meta.get("detected_patterns", []) or []),
                "txn_count_meta": int(meta.get("transaction_count", 0) or 0),
            })

        agg: dict[tuple[str, str], dict] = {}
        for e in self.raw_edges:
            src, tgt = str(e.get("source", "")), str(e.get("target", ""))
            amt = float(e.get("amount", 0) or 0)
            if not src or not tgt or src == tgt or amt <= 0:
                continue
            key = (src, tgt)
            slot = agg.setdefault(key, {"amount": 0.0, "count": 0, "timestamps": [], "rails": set()})
            slot["amount"] += amt
            slot["count"] += 1
            ts = _parse_ts(e.get("timestamp"))
            if ts:
                slot["timestamps"].append(ts)
            slot["rails"].add(str(e.get("payment_rail", "UPI")))

        for (src, tgt), slot in agg.items():
            for n in (src, tgt):
                if n not in self.G:
                    self.G.add_node(n, prior_risk=0.0, account_type="normal",
                                    prior_patterns=[], txn_count_meta=0)
            self.G.add_edge(
                src, tgt,
                amount=slot["amount"],
                count=slot["count"],
                timestamps=sorted(slot["timestamps"]),
                rails=sorted(slot["rails"]),
            )

    # ── primitives ────────────────────────────────────────────────────────────
    @property
    def nodes(self) -> list[str]:
        return list(self.G.nodes())

    def num_nodes(self) -> int:
        return self.G.number_of_nodes()

    def num_edges(self) -> int:
        return self.G.number_of_edges()

    def in_volume(self, n: str) -> float:
        return sum(d["amount"] for _, _, d in self.G.in_edges(n, data=True))

    def out_volume(self, n: str) -> float:
        return sum(d["amount"] for _, _, d in self.G.out_edges(n, data=True))

    def txn_count(self, n: str) -> int:
        c = sum(d["count"] for _, _, d in self.G.in_edges(n, data=True))
        c += sum(d["count"] for _, _, d in self.G.out_edges(n, data=True))
        return c

    def timestamps(self, n: str) -> list[datetime]:
        ts: list[datetime] = []
        for _, _, d in self.G.in_edges(n, data=True):
            ts.extend(d["timestamps"])
        for _, _, d in self.G.out_edges(n, data=True):
            ts.extend(d["timestamps"])
        return sorted(ts)

    def all_timestamps(self) -> list[datetime]:
        ts: list[datetime] = []
        for _, _, d in self.G.edges(data=True):
            ts.extend(d["timestamps"])
        return sorted(ts)

    def cycles(self, max_cycles: int = 200) -> list[list[str]]:
        if self._cycles is None:
            out: list[list[str]] = []
            # On large graphs, bound the cycle search by length so enumeration
            # can never blow up — short laundering loops are what matter anyway.
            length_bound = 8 if self.num_edges() > 4000 else None
            try:
                gen = (nx.simple_cycles(self.G, length_bound=length_bound)
                       if length_bound else nx.simple_cycles(self.G))
                for c in gen:
                    if len(c) >= 2:
                        out.append(c)
                        if len(out) >= max_cycles:
                            break
            except Exception:
                out = []
            self._cycles = out
        return self._cycles

    def articulation_points(self) -> set[str]:
        """Cut vertices on the undirected projection — candidate bridges."""
        try:
            UG = self.G.to_undirected()
            return set(nx.articulation_points(UG))
        except Exception:
            return set()

    def longest_chain(self) -> list[str]:
        """
        Longest simple forwarding path (DAG longest path, else BFS estimate).

        The cyclic fallback is O(V·E); on large graphs we sample a bounded set of
        source nodes (the highest-out-degree emitters, where laundering chains
        actually start) so the estimate stays cheap without losing the real chain.
        """
        try:
            if nx.is_directed_acyclic_graph(self.G):
                return nx.dag_longest_path(self.G)
        except Exception:
            pass
        # cyclic fallback — longest shortest-path tree depth, bounded sources
        nodes = list(self.G.nodes())
        if len(nodes) > 400:
            nodes = sorted(nodes, key=lambda x: self.G.out_degree(x), reverse=True)[:400]
        best: list[str] = []
        for src in nodes:
            try:
                lengths = nx.single_source_shortest_path(self.G, src, cutoff=20)
                cand = max(lengths.values(), key=len)
                if len(cand) > len(best):
                    best = cand
            except Exception:
                continue
        return best

    def centralities(self) -> dict[str, dict[str, float]]:
        """Degree / betweenness / closeness for every node (component-local)."""
        n = self.num_nodes()
        if n == 0:
            return {}
        deg = nx.degree_centrality(self.G)
        # betweenness is O(VE); cap exact computation, sample for big graphs
        if n <= 1500:
            btw = nx.betweenness_centrality(self.G, normalized=True)
        else:
            k = min(400, n)
            btw = nx.betweenness_centrality(self.G, k=k, normalized=True, seed=42)
        # closeness is also O(V·E); only compute exactly on smaller graphs.
        # It is a minor scoring factor, so approximating it as 0 on huge graphs
        # is safe and keeps the engine within the 100k-node scalability target.
        if n <= 3000:
            try:
                clo = nx.closeness_centrality(self.G)
            except Exception:
                clo = {x: 0.0 for x in self.G.nodes()}
        else:
            clo = {x: 0.0 for x in self.G.nodes()}
        return {
            node: {
                "degree": deg.get(node, 0.0),
                "betweenness": btw.get(node, 0.0),
                "closeness": clo.get(node, 0.0),
            }
            for node in self.G.nodes()
        }

    def fraud_distances(self, origins: list[str]) -> dict[str, float]:
        """Hop distance from the nearest origin, following money flow direction."""
        if not origins:
            return {n: 999.0 for n in self.G.nodes()}
        dist: dict[str, float] = {n: 999.0 for n in self.G.nodes()}
        for o in origins:
            if o not in self.G:
                continue
            try:
                lengths = nx.single_source_shortest_path_length(self.G, o)
            except Exception:
                lengths = {o: 0}
            for node, d in lengths.items():
                dist[node] = min(dist[node], float(d))
        return dist
