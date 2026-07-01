"""
Cluster Intelligence Engine — discovers the structural hierarchy of a cluster
and assigns every node a single dominant role plus all qualifying traits.

This is the heart of fixing the "every node has the same risk" problem: roles
give each node a *different* structural base risk before any scoring weights are
applied, so an origin and a peripheral receiver never collapse to one number.
"""
from __future__ import annotations

from ...types import ClusterIntelligence, ClusterRole
from ..graph_engine.builder import TransactionGraph

FAN_THRESHOLD = 4          # ≥4 unique counterparties = fan in/out
PASS_THROUGH_BALANCE = 0.6  # min(in,out)/max(in,out) above this = relay

# Dominant-role precedence (first match wins) — most-incriminating first.
_PRECEDENCE = [
    ClusterRole.ORIGIN,
    ClusterRole.CASHOUT,
    ClusterRole.COLLECTION,
    ClusterRole.DISTRIBUTION,
    ClusterRole.BRIDGE,
    ClusterRole.CIRCULAR,
    ClusterRole.MULE,
    ClusterRole.LAYERING,
    ClusterRole.PASS_THROUGH,
    ClusterRole.SINK,
    ClusterRole.TERMINAL,
    ClusterRole.PERIPHERAL,
    ClusterRole.NORMAL,
]


class ClusterEngine:
    def __init__(self, tg: TransactionGraph):
        self.tg = tg
        self.G = tg.G
        self._cycle_nodes: set[str] = set()
        for c in tg.cycles():
            self._cycle_nodes.update(c)
        self._articulation = tg.articulation_points()

    # ── origin discovery ──────────────────────────────────────────────────────
    def discover_origins(self) -> list[str]:
        """
        An origin injects funds: little/no inflow, meaningful outflow, and it
        reaches a large portion of the cluster downstream.
        """
        import networkx as nx
        n = self.tg.num_nodes()

        # First pass: cheap filter to emitter candidates (no graph traversal).
        raw: list[tuple[str, float]] = []
        for node in self.G.nodes():
            in_v = self.tg.in_volume(node)
            out_v = self.tg.out_volume(node)
            in_deg = self.G.in_degree(node)
            if out_v <= 0:
                continue
            if in_deg == 0 or (in_v > 0 and out_v / in_v > 3.0 and in_deg <= 1):
                raw.append((node, out_v))

        # Second pass: compute expensive downstream reach only for the strongest
        # emitters, so origin discovery stays cheap on 100k-node graphs.
        raw.sort(key=lambda x: x[1], reverse=True)
        candidates: list[tuple[str, float]] = []
        for node, out_v in raw[:50]:
            try:
                reach = len(nx.descendants(self.G, node))
            except Exception:
                reach = self.G.out_degree(node)
            candidates.append((node, out_v * (1 + reach / max(1, n))))
        # remaining emitters keep a degree-only approximation
        for node, out_v in raw[50:]:
            candidates.append((node, out_v * (1 + self.G.out_degree(node) / max(1, n))))
        candidates.sort(key=lambda x: x[1], reverse=True)
        # take the strongest emitter(s); cap to avoid labelling everything origin
        if not candidates:
            return []
        top = candidates[0][1]
        return [c for c, s in candidates if s >= top * 0.5][:5]

    # ── full assignment ───────────────────────────────────────────────────────
    def assign(self) -> tuple[ClusterIntelligence, dict[str, set[ClusterRole]]]:
        ci = ClusterIntelligence(graph_id=self.tg.graph_id)
        origins = set(self.discover_origins())
        traits: dict[str, set[ClusterRole]] = {n: set() for n in self.G.nodes()}

        for node in self.G.nodes():
            in_v = self.tg.in_volume(node)
            out_v = self.tg.out_volume(node)
            fan_in = self.G.in_degree(node)
            fan_out = self.G.out_degree(node)
            acct_type = str(self.G.nodes[node].get("account_type", "normal")).lower()
            t = traits[node]

            if node in origins:
                t.add(ClusterRole.ORIGIN)
            if node in self._cycle_nodes:
                t.add(ClusterRole.CIRCULAR)
            if fan_in >= FAN_THRESHOLD and fan_in > fan_out:
                t.add(ClusterRole.COLLECTION)
            if fan_out >= FAN_THRESHOLD and fan_out > fan_in:
                t.add(ClusterRole.DISTRIBUTION)
            if node in self._articulation and fan_in >= 1 and fan_out >= 1:
                t.add(ClusterRole.BRIDGE)

            # pass-through / mule: forwards most of what it receives
            if in_v > 0 and out_v > 0:
                balance = min(in_v, out_v) / max(in_v, out_v)
                if balance >= PASS_THROUGH_BALANCE:
                    t.add(ClusterRole.PASS_THROUGH)
                    if fan_in >= 1 and fan_out >= 1:
                        t.add(ClusterRole.MULE)

            # cashout: large inflow that exits (cash account, or terminal sink of value)
            is_cashy = acct_type in ("cash", "atm", "merchant", "cashout")
            if (is_cashy and in_v > 0) or (fan_out == 0 and in_v > 0 and out_v == 0
                                           and in_v >= 100_000 and fan_in >= 2):
                t.add(ClusterRole.CASHOUT)

            if fan_out == 0 and in_v > 0:
                t.add(ClusterRole.SINK)
                t.add(ClusterRole.TERMINAL)
            elif fan_out == 0:
                t.add(ClusterRole.TERMINAL)

            if (fan_in + fan_out) <= 1 and node not in origins:
                t.add(ClusterRole.PERIPHERAL)

            if not t:
                t.add(ClusterRole.NORMAL)

        # layering: pass-through nodes that are deep in the chain
        chain = self.tg.longest_chain()
        for depth, node in enumerate(chain):
            if depth >= 2 and depth < len(chain) - 1:
                if ClusterRole.PASS_THROUGH in traits[node] or ClusterRole.MULE in traits[node]:
                    traits[node].add(ClusterRole.LAYERING)

        # collapse traits → dominant role + populate hierarchy buckets
        for node, t in traits.items():
            dominant = next((r for r in _PRECEDENCE if r in t), ClusterRole.NORMAL)
            ci.roles[node] = dominant.value
            if ClusterRole.ORIGIN in t:        ci.origin.append(node)
            if ClusterRole.COLLECTION in t:    ci.collection.append(node)
            if ClusterRole.DISTRIBUTION in t:  ci.distribution.append(node)
            if ClusterRole.BRIDGE in t:        ci.bridges.append(node)
            if ClusterRole.MULE in t:          ci.mules.append(node)
            if ClusterRole.CASHOUT in t:       ci.cashout.append(node)
            if ClusterRole.SINK in t:          ci.sinks.append(node)
            if ClusterRole.TERMINAL in t:      ci.terminals.append(node)
            if ClusterRole.CIRCULAR in t:      ci.circular.append(node)
            if ClusterRole.LAYERING in t:      ci.layering.append(node)

        return ci, traits


# Structural base risk per dominant role — a *mild prior*, not a verdict.
# Roles differentiate nodes from one another, but on their own must never push a
# node past the LOG band (0.38): real risk is earned from evidence + anomalies.
# This keeps benign clusters (structure but no laundering signal) clean.
ROLE_BASE_RISK: dict[ClusterRole, float] = {
    ClusterRole.ORIGIN: 0.30,
    ClusterRole.CIRCULAR: 0.34,
    ClusterRole.CASHOUT: 0.28,
    ClusterRole.COLLECTION: 0.24,
    ClusterRole.DISTRIBUTION: 0.24,
    ClusterRole.MULE: 0.24,
    ClusterRole.BRIDGE: 0.22,
    ClusterRole.LAYERING: 0.22,
    ClusterRole.PASS_THROUGH: 0.12,
    ClusterRole.SINK: 0.10,
    ClusterRole.TERMINAL: 0.06,
    ClusterRole.PERIPHERAL: 0.04,
    ClusterRole.NORMAL: 0.03,
}
