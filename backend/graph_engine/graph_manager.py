"""
NetworkX-powered dynamic transaction graph engine.

Maintains a live directed multi-graph where accounts are nodes
and transactions are timestamped, weighted edges.
"""

import asyncio
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple, Any

import networkx as nx

from models.transaction import (
    Transaction, AccountNode, AccountType, FraudPattern, RiskLevel, PaymentRail
)
from config import settings


class TransactionGraphManager:
    """
    Central graph store — thread-safe via asyncio lock.
    Maintains both a live nx.DiGraph and per-account statistics.
    """

    def __init__(self):
        self._graph: nx.DiGraph = nx.DiGraph()
        self._lock = asyncio.Lock()

        # account_id → AccountNode
        self._accounts: Dict[str, AccountNode] = {}
        # edge_id → edge metadata
        self._edges: Dict[str, Dict] = {}
        # Recent alert IDs for dedup
        self._recent_alerts: deque = deque(maxlen=200)
        # Temporal history: deque of (timestamp, from, to, amount)
        self._temporal_log: deque = deque(maxlen=5000)
        # Cash events per account: account_id → list of {type, amount, timestamp}
        self._cash_events: Dict[str, List[Dict]] = defaultdict(list)

        self._total_transactions: int = 0
        self._total_volume: float = 0.0
        self._flagged_count: int = 0

    # ── Graph Mutation ────────────────────────────────────────────────────────

    async def add_transaction(self, txn: Transaction):
        async with self._lock:
            self._update_node(txn.from_account, txn, is_sender=True)
            self._update_node(txn.to_account, txn, is_sender=False)
            self._add_edge(txn)

            self._temporal_log.append({
                "timestamp": txn.timestamp.isoformat(),
                "from": txn.from_account,
                "to": txn.to_account,
                "amount": txn.amount,
                "rail": txn.payment_rail,
                "risk": txn.risk_score,
                "pattern": txn.fraud_pattern,
            })

            self._total_transactions += 1
            self._total_volume += txn.amount
            if txn.risk_score >= settings.ANOMALY_SCORE_THRESHOLD:
                self._flagged_count += 1

            # Prune if over limits
            if self._graph.number_of_nodes() > settings.GRAPH_MAX_NODES:
                self._prune_low_degree_nodes()

    def _update_node(self, account_id: str, txn: Transaction, is_sender: bool):
        # ── Cash-EVENT identity is RAIL-DRIVEN, not name-driven ───────────────────
        # A CASH_OUT edge's TARGET is a cash-withdrawal event (funds left the bank);
        # a CASH_IN edge's SOURCE is a cash-deposit event (funds entered). This must
        # NOT depend on the node's name — a cash-out called DIAMOND_CASHOUT is still a
        # cash event, not a bank account. The legacy name prefix CASH* is kept as a
        # fallback for synthetic datasets. Once a node is a cash event it STAYS one.
        cash_kind: Optional[str] = None
        if txn.payment_rail == PaymentRail.CASH_OUT and not is_sender:
            cash_kind = "CASH_OUT"
        elif txn.payment_rail == PaymentRail.CASH_IN and is_sender:
            cash_kind = "CASH_IN"
        elif account_id.upper().startswith("CASH"):
            cash_kind = "CASH_IN" if is_sender else "CASH_OUT"

        if account_id not in self._accounts:
            acc_type = (
                AccountType.CASH if cash_kind
                else AccountType.MULE if account_id.startswith("MUL")
                else AccountType.HIGH_VALUE if account_id.startswith("HVA")
                else AccountType.NORMAL
            )
            self._accounts[account_id] = AccountNode(
                account_id=account_id,
                account_type=acc_type,
                cash_kind=cash_kind,
                first_seen=txn.timestamp,
            )

        node = self._accounts[account_id]
        # Cash identity is sticky: a node that is a cash event never becomes a normal
        # account on a later edge (and vice-versa it can be promoted to a cash event).
        if cash_kind and node.account_type != AccountType.CASH:
            node.account_type = AccountType.CASH
            node.cash_kind = cash_kind
        node.transaction_count += 1
        node.last_seen = txn.timestamp

        if is_sender:
            node.total_sent += txn.amount
        else:
            node.total_received += txn.amount

        # Rolling risk score (exponential moving average)
        node.risk_score = 0.7 * node.risk_score + 0.3 * txn.risk_score

        if txn.fraud_pattern != FraudPattern.NORMAL and txn.fraud_pattern not in node.detected_patterns:
            node.detected_patterns.append(txn.fraud_pattern)
            node.is_flagged = True

        if txn.geo_location and txn.geo_location not in node.geo_locations:
            node.geo_locations.append(txn.geo_location)

        # Update NetworkX graph node
        self._graph.add_node(account_id, **self._node_attrs(node))

    def _node_attrs(self, node: AccountNode) -> dict:
        is_cash_event = node.account_type == AccountType.CASH
        return {
            "account_type": node.account_type.value,
            "risk_score": round(node.risk_score, 4),
            "transaction_count": node.transaction_count,
            "total_sent": node.total_sent,
            "total_received": node.total_received,
            "is_flagged": node.is_flagged,
            "risk_level": node.risk_level.value,
            "detected_patterns": [p.value for p in node.detected_patterns],
            # Cash-event semantics (first-class graph ontology). A cash event is NOT a
            # bank account: it is a boundary where money entered (CASH_IN) or left
            # (CASH_OUT, terminal) the banking system. Consumers (frontend styling,
            # node panel, recovery, case account-count, search) key off these.
            "is_cash_event": is_cash_event,
            "cash_kind": node.cash_kind,
            "is_account": not is_cash_event,
            "terminal": node.cash_kind == "CASH_OUT",
        }

    def _add_edge(self, txn: Transaction):
        edge_key = txn.transaction_id
        attrs = {
            "transaction_id": txn.transaction_id,
            "amount": txn.amount,
            "payment_rail": txn.payment_rail.value,
            "timestamp": txn.timestamp.isoformat(),
            "risk_score": txn.risk_score,
            "fraud_pattern": txn.fraud_pattern.value,
            "is_flagged": txn.risk_score >= settings.ANOMALY_SCORE_THRESHOLD,
            "geo_location": txn.geo_location,
            # Carried so cross-product / device-sharing intelligence (XP009/XP010)
            # works on live data, not just synthetic datasets. Additive.
            "device_id": txn.device_id,
            "ip_address": txn.ip_address,
        }
        self._graph.add_edge(txn.from_account, txn.to_account, key=edge_key, **attrs)
        self._edges[edge_key] = {**attrs, "source": txn.from_account, "target": txn.to_account}

    async def add_cash_event(
        self,
        parent_id: str,
        cash_type: str,
        amount: float,
        ts: datetime,
    ) -> None:
        """Register a cash movement against a parent account without creating a CASH node in the graph."""
        async with self._lock:
            if parent_id not in self._accounts:
                acc_type = (
                    AccountType.MULE if parent_id.startswith("MUL")
                    else AccountType.HIGH_VALUE if parent_id.startswith("HVA")
                    else AccountType.NORMAL
                )
                self._accounts[parent_id] = AccountNode(
                    account_id=parent_id,
                    account_type=acc_type,
                    first_seen=ts,
                )

            node = self._accounts[parent_id]
            node.transaction_count += 1
            node.last_seen = ts

            if cash_type == "CASH_IN":
                node.total_received += amount
            else:
                node.total_sent += amount

            # Cash involvement raises suspicion slightly
            node.risk_score = min(1.0, 0.80 * node.risk_score + 0.20 * 0.40)

            if parent_id not in self._graph:
                self._graph.add_node(parent_id, **self._node_attrs(node))
            else:
                for k, v in self._node_attrs(node).items():
                    self._graph.nodes[parent_id][k] = v

            self._cash_events[parent_id].append({
                "type": cash_type,
                "amount": amount,
                "timestamp": ts.isoformat(),
            })

            self._total_transactions += 1
            self._total_volume += amount

    def _prune_low_degree_nodes(self):
        """Remove lowest-activity nodes when graph exceeds size limit."""
        degrees = dict(self._graph.degree())
        sorted_nodes = sorted(degrees, key=degrees.get)
        to_remove = sorted_nodes[:max(1, len(sorted_nodes) // 10)]
        self._graph.remove_nodes_from(to_remove)
        for n in to_remove:
            self._accounts.pop(n, None)

    # ── Traversal Algorithms ──────────────────────────────────────────────────

    async def bfs(self, start: str, max_depth: int = 3) -> List[str]:
        async with self._lock:
            if start not in self._graph:
                return []
            visited, queue, result = set(), deque([(start, 0)]), []
            while queue:
                node, depth = queue.popleft()
                if node in visited or depth > max_depth:
                    continue
                visited.add(node)
                result.append(node)
                for nbr in self._graph.successors(node):
                    queue.append((nbr, depth + 1))
            return result

    async def dfs(self, start: str, max_depth: int = 4) -> List[str]:
        async with self._lock:
            if start not in self._graph:
                return []
            visited, stack, result = set(), [(start, 0)], []
            while stack:
                node, depth = stack.pop()
                if node in visited or depth > max_depth:
                    continue
                visited.add(node)
                result.append(node)
                for nbr in reversed(list(self._graph.successors(node))):
                    stack.append((nbr, depth + 1))
            return result

    async def shortest_path(self, source: str, target: str) -> List[str]:
        async with self._lock:
            try:
                return nx.shortest_path(self._graph, source, target)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                return []

    async def detect_cycles(self, node: Optional[str] = None) -> List[List[str]]:
        """Find all simple cycles, optionally limited to those involving a specific node."""
        async with self._lock:
            try:
                # Limit to subgraph for performance
                sub = self._graph
                if self._graph.number_of_nodes() > 50:
                    # Work on a relevant subgraph
                    if node and node in self._graph:
                        neighbors = (
                            set(self._graph.successors(node))
                            | set(self._graph.predecessors(node))
                        )
                        sub_nodes = {node} | neighbors
                        # Add 2nd-degree
                        for n in list(neighbors):
                            sub_nodes |= set(self._graph.successors(n))
                        sub = self._graph.subgraph(sub_nodes)
                    else:
                        # Sample recent nodes
                        recent = list(self._graph.nodes)[-80:]
                        sub = self._graph.subgraph(recent)

                cycles = list(nx.simple_cycles(sub))
                cycles = [c for c in cycles if 2 < len(c) <= settings.CYCLE_DETECTION_DEPTH]
                if node:
                    cycles = [c for c in cycles if node in c]
                return sorted(cycles, key=len)[:10]
            except Exception:
                return []

    async def detect_communities(self) -> Dict[str, int]:
        """Louvain-style community detection via NetworkX greedy modularity."""
        async with self._lock:
            if self._graph.number_of_nodes() < 3:
                return {}
            try:
                undirected = self._graph.to_undirected()
                from networkx.algorithms.community import greedy_modularity_communities
                communities = greedy_modularity_communities(undirected)
                result = {}
                for i, comm in enumerate(communities):
                    for node in comm:
                        result[node] = i
                return result
            except Exception:
                return {}

    async def multi_hop_trace(
        self, origin: str, max_hops: int = 4, min_risk: float = 0.5
    ) -> List[List[str]]:
        """Find all high-risk propagation paths from an origin account."""
        async with self._lock:
            if origin not in self._graph:
                return []
            paths = []
            stack = [[origin]]
            while stack:
                path = stack.pop()
                current = path[-1]
                if len(path) > max_hops + 1:
                    continue
                for nbr in self._graph.successors(current):
                    edge_data = self._graph.edges[current, nbr]
                    if edge_data.get("risk_score", 0) >= min_risk:
                        new_path = path + [nbr]
                        paths.append(new_path)
                        if nbr not in path:
                            stack.append(new_path)
            return paths[:20]

    # ── State Serialization ───────────────────────────────────────────────────

    async def get_graph_state(self) -> Dict[str, Any]:
        """Return serializable snapshot of graph for WebSocket broadcast."""
        async with self._lock:
            nodes = []
            for node_id, attrs in self._graph.nodes(data=True):
                acc = self._accounts.get(node_id)
                preds = list(self._graph.predecessors(node_id))
                succs = list(self._graph.successors(node_id))
                connected = list(set(preds + succs))[:20]
                # Cash analytics come from BOTH the legacy off-graph events AND
                # the new first-class cash edges (CASH_IN edge INTO a node = a cash
                # deposit it received; CASH_OUT edge OUT of a node = a withdrawal).
                cash_evts = self._cash_events.get(node_id, [])
                cash_in = sum(e["amount"] for e in cash_evts if e["type"] == "CASH_IN")
                cash_out = sum(e["amount"] for e in cash_evts if e["type"] == "CASH_OUT")
                cash_in_cnt = sum(1 for e in cash_evts if e["type"] == "CASH_IN")
                cash_out_cnt = sum(1 for e in cash_evts if e["type"] == "CASH_OUT")
                for _s, _t, _d in self._graph.in_edges(node_id, data=True):
                    if _d.get("payment_rail") == "CASH_IN":
                        cash_in += _d.get("amount", 0); cash_in_cnt += 1
                for _s, _t, _d in self._graph.out_edges(node_id, data=True):
                    if _d.get("payment_rail") == "CASH_OUT":
                        cash_out += _d.get("amount", 0); cash_out_cnt += 1
                nodes.append({
                    "id": node_id,
                    "label": node_id[:12],
                    "risk_score": attrs.get("risk_score", 0.0),
                    "risk_level": attrs.get("risk_level", "safe"),
                    "account_type": attrs.get("account_type", "normal"),
                    "transaction_count": attrs.get("transaction_count", 0),
                    "total_sent": round(attrs.get("total_sent", 0.0), 2),
                    "total_received": round(attrs.get("total_received", 0.0), 2),
                    "is_flagged": attrs.get("is_flagged", False),
                    "detected_patterns": attrs.get("detected_patterns", []),
                    "geo_locations": acc.geo_locations[:3] if acc else [],
                    "incoming_count": len(preds),
                    "outgoing_count": len(succs),
                    "connected_accounts": connected,
                    "cash_inflows": round(cash_in, 2),
                    "cash_outflows": round(cash_out, 2),
                    "cash_inflow_count": cash_in_cnt,
                    "cash_outflow_count": cash_out_cnt,
                    # Cash-event ontology (a cash event is NOT a bank account).
                    "is_cash_event": attrs.get("is_cash_event", False),
                    "cash_kind": attrs.get("cash_kind"),
                    "is_account": attrs.get("is_account", True),
                    "terminal": attrs.get("terminal", False),
                })

            edges = []
            seen_edges: Set[str] = set()
            for src, dst, data in self._graph.edges(data=True):
                eid = data.get("transaction_id", f"{src}-{dst}")
                if eid in seen_edges:
                    continue
                seen_edges.add(eid)
                edges.append({
                    "id": eid,
                    "source": src,
                    "target": dst,
                    "amount": data.get("amount", 0),
                    "payment_rail": data.get("payment_rail", "UPI"),
                    "risk_score": data.get("risk_score", 0.0),
                    "timestamp": data.get("timestamp", ""),
                    "fraud_pattern": data.get("fraud_pattern", "normal"),
                    "is_flagged": data.get("is_flagged", False),
                    "device_id": data.get("device_id", ""),
                })

            return {
                "nodes": nodes,
                "edges": edges[-settings.GRAPH_MAX_EDGES:],
                "stats": self._get_stats(),
            }

    def _get_stats(self) -> Dict[str, Any]:
        flagged_nodes = sum(1 for a in self._accounts.values() if a.is_flagged)
        return {
            "total_transactions": self._total_transactions,
            "total_volume": round(self._total_volume, 2),
            "total_nodes": self._graph.number_of_nodes(),
            "total_edges": self._graph.number_of_edges(),
            "flagged_nodes": flagged_nodes,
            "flagged_transactions": self._flagged_count,
            "throughput_estimate": self._total_transactions,
        }

    async def get_account_detail(self, account_id: str) -> Optional[Dict]:
        async with self._lock:
            if account_id not in self._accounts:
                return None
            node = self._accounts[account_id]
            metrics = {}
            if account_id in self._graph:
                metrics = {
                    "in_degree": self._graph.in_degree(account_id),
                    "out_degree": self._graph.out_degree(account_id),
                }
            return {**node.model_dump(mode="json"), **metrics}

    async def get_recent_edges(self, account_id: str, limit: int = 20) -> List[Dict]:
        async with self._lock:
            edges = []
            for src, dst, data in self._graph.edges(account_id, data=True):
                edges.append({**data, "source": src, "target": dst})
            return sorted(edges, key=lambda e: e.get("timestamp", ""), reverse=True)[:limit]

    async def get_connected_components(self) -> List[Dict[str, Any]]:
        """
        Detect disconnected graph clusters using weakly connected components.

        Returns each cluster as an independent subgraph snapshot with a unique
        graph_id (GRAPH_001, GRAPH_002 …), sorted largest-first.
        """
        async with self._lock:
            if self._graph.number_of_nodes() == 0:
                return []

            raw_components = list(nx.weakly_connected_components(self._graph))
            # Sort largest cluster first so GRAPH_001 is always the biggest
            raw_components.sort(key=len, reverse=True)

            result: List[Dict[str, Any]] = []
            for idx, component_nodes in enumerate(raw_components, start=1):
                graph_id = f"GRAPH_{idx:03d}"
                subgraph = self._graph.subgraph(component_nodes)

                nodes: List[Dict] = []
                for node_id in component_nodes:
                    attrs = self._graph.nodes[node_id]
                    acc = self._accounts.get(node_id)
                    nodes.append({
                        "id": node_id,
                        "label": node_id[:12],
                        "risk_score": attrs.get("risk_score", 0.0),
                        "risk_level": attrs.get("risk_level", "safe"),
                        "account_type": attrs.get("account_type", "normal"),
                        "transaction_count": attrs.get("transaction_count", 0),
                        "total_sent": round(attrs.get("total_sent", 0.0), 2),
                        "total_received": round(attrs.get("total_received", 0.0), 2),
                        "is_flagged": attrs.get("is_flagged", False),
                        "detected_patterns": attrs.get("detected_patterns", []),
                        "geo_locations": acc.geo_locations[:3] if acc else [],
                    })

                edges: List[Dict] = []
                seen_edge_ids: Set[str] = set()
                for src, dst, data in subgraph.edges(data=True):
                    eid = data.get("transaction_id", f"{src}-{dst}")
                    if eid in seen_edge_ids:
                        continue
                    seen_edge_ids.add(eid)
                    edges.append({
                        "id": eid,
                        "source": src,
                        "target": dst,
                        "amount": data.get("amount", 0),
                        "payment_rail": data.get("payment_rail", "UPI"),
                        "risk_score": data.get("risk_score", 0.0),
                        "timestamp": data.get("timestamp", ""),
                        "fraud_pattern": data.get("fraud_pattern", "normal"),
                        "is_flagged": data.get("is_flagged", False),
                        "device_id": data.get("device_id", ""),
                    })

                result.append({
                    "graph_id": graph_id,
                    "node_ids": list(component_nodes),
                    "nodes": nodes,
                    "edges": edges,
                })

            return result

    async def get_cash_events_for_accounts(
        self, account_ids: List[str]
    ) -> Dict[str, List[Dict]]:
        """Return cash event lists for the given account IDs."""
        async with self._lock:
            return {
                acc: list(self._cash_events[acc])
                for acc in account_ids
                if acc in self._cash_events
            }

    async def clear(self):
        """Reset graph to empty state."""
        async with self._lock:
            self._graph.clear()
            self._accounts.clear()
            self._edges.clear()
            self._temporal_log.clear()
            self._cash_events.clear()
            self._total_transactions = 0
            self._total_volume = 0.0
            self._flagged_count = 0

    @property
    def node_count(self) -> int:
        return self._graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self._graph.number_of_edges()

    @property
    def total_transactions(self) -> int:
        return self._total_transactions
