"""
Node Intelligence Engine — computes the 18-factor independent analysis for
every node in a component.

It only *measures*; turning measurements into the final risk number is the job
of the scoring engine.  Keeping them separate means we can re-weight scoring
without recomputing graph metrics, and the explanation engine can read raw
factors directly.
"""
from __future__ import annotations

import math

from ...types import ClusterRole, NodeMetrics
from ..anomaly_engine.anomalies import AnomalyEngine
from ..cluster_engine.roles import ClusterEngine
from ..graph_engine.builder import TransactionGraph


def _log_norm(value: float, scale: float) -> float:
    """Saturating log-normalisation to [0,1)."""
    if value <= 0:
        return 0.0
    return 1.0 - math.exp(-value / scale)


class RiskEngine:
    def __init__(self, tg: TransactionGraph):
        self.tg = tg
        self.anomaly = AnomalyEngine(tg)
        self.cluster_engine = ClusterEngine(tg)

    def compute(self) -> tuple[dict[str, NodeMetrics], object, dict]:
        tg = self.tg
        centralities = tg.centralities()
        cluster_intel, traits = self.cluster_engine.assign()
        origins = cluster_intel.origin
        fraud_dist = tg.fraud_distances(origins)
        chain = tg.longest_chain()
        layer_index = {node: i for i, node in enumerate(chain)}
        cycle_nodes: set[str] = set()
        for c in tg.cycles():
            cycle_nodes.update(c)

        metrics: dict[str, NodeMetrics] = {}
        for node in tg.nodes:
            sig = self.anomaly.node_signals(node)
            cen = centralities.get(node, {"degree": 0, "betweenness": 0, "closeness": 0})
            in_v = tg.in_volume(node)
            out_v = tg.out_volume(node)
            fan_in = tg.G.in_degree(node)
            fan_out = tg.G.out_degree(node)
            balance = (min(in_v, out_v) / max(in_v, out_v)) if max(in_v, out_v) > 0 else 0.0

            m = NodeMetrics(
                node_id=node,
                transaction_velocity=sig["velocity"],
                transaction_frequency=tg.txn_count(node),
                incoming_volume=round(in_v, 2),
                outgoing_volume=round(out_v, 2),
                fan_in_count=fan_in,
                fan_out_count=fan_out,
                degree_centrality=round(cen["degree"], 4),
                betweenness_centrality=round(cen["betweenness"], 4),
                closeness_centrality=round(cen["closeness"], 4),
                fraud_distance=fraud_dist.get(node, 999.0),
                layer_distance=layer_index.get(node, 0),
                circular_participation=node in cycle_nodes,
                burst_activity=round(sig["burst"], 4),
                historical_behavior=float(tg.G.nodes[node].get("prior_risk", 0.0)),
                bridge_importance=round(cen["betweenness"], 4),
                cluster_role=ClusterRole(cluster_intel.roles.get(node, "normal")),
                pass_through_ratio=round(balance, 4),
                dormancy_reactivation=round(sig["dormancy"], 4),
            )
            metrics[node] = m

        # ── risk inheritance: diffuse risk one hop from origins/high-prior nodes ─
        self._propagate_inheritance(metrics)

        meta = {
            "centralities": centralities,
            "origins": origins,
            "chain": chain,
            "cycle_nodes": cycle_nodes,
            "traits": traits,
        }
        return metrics, cluster_intel, meta

    def _propagate_inheritance(self, metrics: dict[str, NodeMetrics], hops: int = 3) -> None:
        """
        Diffuse risk outward from origins along money-flow direction with decay,
        so proximity to a fraud source raises (but never dominates) a node.
        """
        tg = self.tg
        # seed: origin nodes + nodes carrying prior risk
        seed = {n: (0.9 if m.cluster_role == ClusterRole.ORIGIN else m.historical_behavior)
                for n, m in metrics.items()
                if m.cluster_role == ClusterRole.ORIGIN or m.historical_behavior > 0.3}
        if not seed:
            return
        decay = 0.55
        frontier = dict(seed)
        inherited: dict[str, float] = {n: 0.0 for n in metrics}
        for _ in range(hops):
            nxt: dict[str, float] = {}
            for node, val in frontier.items():
                for succ in tg.G.successors(node):
                    passed = val * decay
                    if passed > inherited[succ]:
                        inherited[succ] = passed
                        nxt[succ] = max(nxt.get(succ, 0.0), passed)
            if not nxt:
                break
            frontier = nxt
        for node, val in inherited.items():
            metrics[node].risk_inheritance = round(val, 4)
