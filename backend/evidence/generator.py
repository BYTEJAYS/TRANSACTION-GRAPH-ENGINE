"""
Evidence package generator for fraud investigation artifacts.

Produces structured evidence dicts from Blue Team verdicts + graph data.
Used by the evidence API endpoint to populate JSON and PDF reports.
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List


# FraudPattern enum values → human-readable type names
_PATTERN_MAP: Dict[str, str] = {
    "circular_transfer": "Layering / Circular Transfer",
    "fan_out": "Fan-Out Fraud",
    "mule_chain": "Mule Account Network",
    "burst_transfer": "Burst Transfer Fraud",
    "structuring": "Smurfing / Amount Structuring",
    "rapid_microtransaction": "Rapid Micro-Transaction Fraud",
    "layering": "Layering",
}

# Keywords in suspicious_reason → fraud type
_KEYWORD_MAP: Dict[str, str] = {
    "circular": "Layering / Circular Transfer",
    "cycle": "Layering / Circular Transfer",
    "fan-out": "Fan-Out Fraud",
    "fan_out": "Fan-Out Fraud",
    "mule": "Mule Account Network",
    "burst": "Burst Transfer Fraud",
    "structur": "Smurfing / Amount Structuring",
    "rapid": "Rapid Micro-Transaction Fraud",
    "cash": "Cash Laundering",
    "layer": "Layering",
    "smur": "Smurfing / Amount Structuring",
    "chain_depth": "Layering",
    "bipartite": "Mule Account Network",
    "repeated_amount": "Smurfing / Amount Structuring",
}


class EvidenceGenerator:
    """
    Builds a self-contained evidence dict from a Blue Team verdict and
    the corresponding graph component (nodes, edges, cash events).
    """

    def generate(
        self,
        verdict: Dict[str, Any],
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        cash_events: Dict[str, List[Dict]],
    ) -> Dict[str, Any]:
        """
        Parameters
        ----------
        verdict     : GraphComponentResult dict from the Blue Team adapter
        nodes       : list of node dicts for this component (from get_connected_components)
        edges       : list of edge dicts for this component
        cash_events : {account_id: [{type, amount, timestamp}, ...]} for accounts in component
        """
        graph_id          = verdict.get("graph_id", "GRAPH_001")
        risk_score        = float(verdict.get("risk_score", 0.0))
        flagged_nodes     = verdict.get("flagged_nodes", [])
        suspicious_reason = verdict.get("suspicious_reason") or ""

        fraud_type = self._infer_fraud_type(nodes, edges, suspicious_reason)

        # Amount statistics
        amounts        = [float(e.get("amount", 0)) for e in edges]
        total_amount   = sum(amounts)
        largest        = max(amounts) if amounts else 0.0
        average        = total_amount / len(amounts) if amounts else 0.0

        accounts_involved = sorted({n["id"] for n in nodes})

        fraud_path = self._extract_fraud_path(edges, flagged_nodes)

        # Cash flow
        cash_inflows: List[Dict] = []
        cash_outflows: List[Dict] = []
        account_set = set(accounts_involved)
        for acc_id, events in cash_events.items():
            if acc_id not in account_set:
                continue
            for evt in events:
                entry = {
                    "account": acc_id,
                    "amount": float(evt["amount"]),
                    "timestamp": evt.get("timestamp", ""),
                }
                if evt["type"] == "CASH_IN":
                    cash_inflows.append({"source": "CASH_SOURCE", **entry})
                else:
                    cash_outflows.append({"destination": "CASH_EXIT", **entry})

        risk_explanation = self._build_risk_explanation(
            verdict, nodes, edges, fraud_type
        )

        confidence = (
            "HIGH" if risk_score >= 0.85
            else "MEDIUM" if risk_score >= 0.62
            else "LOW"
        )

        return {
            "case_id": f"CASE-{uuid.uuid4().hex[:8].upper()}",
            "fraud_metadata": {
                "graph_id": graph_id,
                "fraud_score": round(risk_score, 4),
                "fraud_type": fraud_type,
                "detection_timestamp": datetime.utcnow().isoformat() + "Z",
                "confidence_level": confidence,
                "verdict": verdict.get("verdict", "FRAUD"),
                "transactions_analyzed": verdict.get(
                    "transactions_scored", len(edges)
                ),
            },
            "fraud_details": {
                "fraud_type": fraud_type,
                "amounts": {
                    "total_suspicious_amount": round(total_amount, 2),
                    "largest_transfer": round(largest, 2),
                    "average_transfer": round(average, 2),
                    "total_transaction_count": len(edges),
                },
                "accounts_involved": accounts_involved,
                "fraud_path": fraud_path,
                "cash_flow": {
                    "has_cash_involvement": bool(cash_inflows or cash_outflows),
                    "cash_inflows": cash_inflows,
                    "cash_outflows": cash_outflows,
                },
                "risk_explanation": risk_explanation,
            },
            "raw_graph": {
                "nodes": [
                    {
                        "id": n["id"],
                        "account_type": n.get("account_type", "normal"),
                        "risk_score": n.get("risk_score", 0.0),
                        "is_flagged": n.get("is_flagged", False),
                        "total_sent": n.get("total_sent", 0),
                        "total_received": n.get("total_received", 0),
                        "transaction_count": n.get("transaction_count", 0),
                        "detected_patterns": n.get("detected_patterns", []),
                    }
                    for n in nodes
                ],
                "edges": [
                    {
                        "id": e.get("id", ""),
                        "source": e["source"],
                        "target": e["target"],
                        "amount": e.get("amount", 0),
                        "payment_rail": e.get("payment_rail", "UPI"),
                        "risk_score": e.get("risk_score", 0.0),
                        "timestamp": e.get("timestamp", ""),
                        "fraud_pattern": e.get("fraud_pattern", "normal"),
                    }
                    for e in edges
                ],
            },
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _infer_fraud_type(
        self,
        nodes: List[Dict],
        edges: List[Dict],
        suspicious_reason: str,
    ) -> str:
        # 1. Check detected_patterns on nodes
        for node in nodes:
            for pattern in node.get("detected_patterns", []):
                for key, label in _PATTERN_MAP.items():
                    if key in pattern:
                        return label

        # 2. Check suspicious_reason string
        reason_lower = suspicious_reason.lower()
        for keyword, label in _KEYWORD_MAP.items():
            if keyword in reason_lower:
                return label

        # 3. Check edge fraud_pattern fields
        for edge in edges:
            fp = edge.get("fraud_pattern", "normal")
            if fp and fp != "normal":
                for key, label in _PATTERN_MAP.items():
                    if key in fp:
                        return label

        return "Mixed Pattern Fraud"

    def _extract_fraud_path(
        self,
        edges: List[Dict],
        flagged_nodes: List[str],
    ) -> List[str]:
        if not edges:
            return list(flagged_nodes)

        try:
            import networkx as nx

            g = nx.DiGraph()
            for e in edges:
                g.add_edge(e["source"], e["target"])

            flagged_set = set(flagged_nodes)

            # Prefer a cycle through flagged nodes
            for cycle in nx.simple_cycles(g):
                if any(n in flagged_set for n in cycle):
                    return cycle + [cycle[0]]

            # DAG longest path
            if nx.is_directed_acyclic_graph(g):
                path = nx.dag_longest_path(g)
                if path:
                    return path

            # Topological order as fallback
            try:
                return list(nx.topological_sort(g))
            except nx.NetworkXUnfeasible:
                pass
        except Exception:
            pass

        # Last resort: edge-order dedup
        seen: List[str] = []
        seen_set: set = set()
        for e in edges:
            for acc in (e["source"], e["target"]):
                if acc not in seen_set:
                    seen.append(acc)
                    seen_set.add(acc)
        return seen

    def _build_risk_explanation(
        self,
        verdict: Dict[str, Any],
        nodes: List[Dict],
        edges: List[Dict],
        fraud_type: str,
    ) -> Dict[str, Any]:
        suspicious_reason = verdict.get("suspicious_reason") or ""
        flagged_nodes     = verdict.get("flagged_nodes", [])
        risk_score        = float(verdict.get("risk_score", 0.0))

        why_flagged = (
            suspicious_reason
            or f"Graph risk score {risk_score:.2f} exceeds fraud classification threshold"
        )

        indicators: List[str] = []

        # Cycle detection
        try:
            import networkx as nx
            g = nx.DiGraph()
            for e in edges:
                g.add_edge(e["source"], e["target"])
            cycles = list(nx.simple_cycles(g))
            if cycles:
                indicators.append(
                    f"Circular transfer path detected ({len(cycles)} cycle(s))"
                )
        except Exception:
            pass

        # High-risk nodes
        high_risk = [n["id"] for n in nodes if n.get("risk_score", 0) > 0.65]
        if high_risk:
            indicators.append(
                f"{len(high_risk)} high-risk account(s): "
                + ", ".join(high_risk[:4])
            )

        # Fan-out
        out_deg: Dict[str, int] = {}
        for e in edges:
            out_deg[e["source"]] = out_deg.get(e["source"], 0) + 1
        hubs = [k for k, v in out_deg.items() if v >= 3]
        if hubs:
            indicators.append(
                f"Fan-out detected from {', '.join(hubs[:2])} (≥3 unique targets)"
            )

        # Amount structuring
        amounts = [float(e.get("amount", 0)) for e in edges]
        repeated = {
            a: c
            for a, c in Counter(round(x, 2) for x in amounts).items()
            if c >= 3 and a >= 1000
        }
        if repeated:
            indicators.append(
                f"Amount structuring: {len(repeated)} repeated transfer value(s)"
            )

        # Cash involvement
        if any(
            n.get("cash_inflows", 0) or n.get("cash_outflows", 0)
            for n in nodes
        ):
            indicators.append("Cash rail involvement — off-graph movement detected")

        if not indicators:
            indicators.append(
                "Elevated risk score above fraud classification threshold"
            )

        return {
            "why_flagged": why_flagged,
            "anomaly_indicators": indicators,
            "suspicious_topology": self._topology_reason(nodes, edges, fraud_type),
            "propagation_behavior": self._propagation_behavior(nodes, edges),
            "flagged_accounts": flagged_nodes,
        }

    def _topology_reason(
        self, nodes: List[Dict], edges: List[Dict], fraud_type: str
    ) -> str:
        n, e = len(nodes), len(edges)
        if "Circular" in fraud_type or "Layering" in fraud_type:
            return (
                f"Directed graph contains cycles across {n} nodes — "
                "funds circulate without exiting the network"
            )
        if "Fan-Out" in fraud_type:
            return (
                f"Single source distributes to {n - 1} targets — "
                "classic structuring / smurfing topology"
            )
        if "Mule" in fraud_type:
            return (
                f"Chain of {n} accounts with sequential forwarding depth > 3 hops"
            )
        if "Burst" in fraud_type:
            return (
                f"High edge density ({e} edges across {n} nodes) indicates "
                "rapid burst transfer activity"
            )
        if "Smurfing" in fraud_type or "Structuring" in fraud_type:
            return (
                f"Multiple transfers below reporting threshold across {n} accounts"
            )
        return f"Anomalous graph topology: {n} nodes, {e} edges, elevated risk signal"

    def _propagation_behavior(
        self, nodes: List[Dict], edges: List[Dict]
    ) -> str:
        if not edges:
            return "No transaction edges recorded for this component"

        amounts = [float(e.get("amount", 0)) for e in edges]
        avg = sum(amounts) / len(amounts)
        peak = max(amounts)

        timestamps = sorted(
            e.get("timestamp", "") for e in edges if e.get("timestamp")
        )
        time_span = ""
        if len(timestamps) >= 2:
            start = timestamps[0][:10]
            end = timestamps[-1][:10]
            time_span = f" over window {start} → {end}"

        return (
            f"Funds propagate through {len(nodes)} accounts in "
            f"{len(edges)} transactions{time_span}. "
            f"Average transfer: ₹{avg:,.0f} | Peak: ₹{peak:,.0f}."
        )
