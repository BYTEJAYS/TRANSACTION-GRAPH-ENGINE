"""
Simulation Engine — synthetic dataset generators.

Produces labelled components in the exact TGIE component schema
({graph_id, node_ids, nodes, edges}) so anything generated here can be fed
straight into either engine, the benchmark, or the shadow comparison.

Each generator returns (component, ground_truth) where ground_truth carries the
expected verdict and the set of fraudulent node ids, enabling precision/recall
benchmarking.

Archetypes: normal, layering, smurfing, fan_out, fan_in, mule_network,
circular, bridge_network, cashout_network, synthetic_ring, hybrid, large_org,
plus mixed (legitimate + fraud) datasets.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class GroundTruth:
    archetype: str
    expected_verdict: str               # CLEAN | LOGGED | SUSPICIOUS | FRAUD
    fraud_nodes: set[str] = field(default_factory=set)
    expected_patterns: set[str] = field(default_factory=set)


class Simulator:
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self._counter = 0
        self.base_time = datetime(2026, 5, 30, 9, 0, 0)

    # ── helpers ───────────────────────────────────────────────────────────────
    def _acc(self, prefix: str = "acc") -> str:
        self._counter += 1
        return f"{prefix}_{self._counter:05d}"

    def _edge(self, src: str, tgt: str, amount: float, minute_offset: float,
              rail: str = "IMPS") -> dict:
        ts = self.base_time + timedelta(minutes=minute_offset)
        self._eid = getattr(self, "_eid", 0) + 1
        return {
            "id": f"txn_{self._eid:06d}",
            "source": src, "target": tgt,
            "amount": round(amount, 2),
            "timestamp": ts.isoformat(),
            "payment_rail": rail,
        }

    def _component(self, graph_id: str, edges: list[dict],
                   node_meta: dict[str, dict] | None = None) -> dict:
        ids = sorted({n for e in edges for n in (e["source"], e["target"])})
        node_meta = node_meta or {}
        nodes = [{"id": nid, "risk_score": 0.0, "account_type":
                  node_meta.get(nid, {}).get("account_type", "normal"),
                  "transaction_count": node_meta.get(nid, {}).get("transaction_count", 2),
                  "detected_patterns": []} for nid in ids]
        return {"graph_id": graph_id, "node_ids": ids, "nodes": nodes, "edges": edges}

    # ── archetypes ────────────────────────────────────────────────────────────
    def normal(self, gid="GRAPH_N", n_accounts: int = 8) -> tuple[dict, GroundTruth]:
        accs = [self._acc("usr") for _ in range(n_accounts)]
        edges = []
        for i in range(n_accounts):
            for _ in range(self.rng.randint(0, 2)):
                src, tgt = self.rng.sample(accs, 2)
                amt = self.rng.uniform(200, 15_000)
                edges.append(self._edge(src, tgt, amt,
                                        self.rng.uniform(0, 60 * 24 * 30),
                                        rail=self.rng.choice(["UPI", "NEFT"])))
        if not edges:
            edges.append(self._edge(accs[0], accs[1], 2500, 5))
        return self._component(gid, edges), GroundTruth("normal", "CLEAN")

    def layering(self, gid="GRAPH_L", depth: int = 6) -> tuple[dict, GroundTruth]:
        accs = [self._acc("lay") for _ in range(depth)]
        edges, amt = [], 800_000.0
        for i in range(depth - 1):
            amt *= 0.96
            edges.append(self._edge(accs[i], accs[i + 1], amt, i * 1.5))
        gt = GroundTruth("layering", "FRAUD", set(accs), {"layering"})
        return self._component(gid, edges), gt

    def smurfing(self, gid="GRAPH_S", n: int = 8) -> tuple[dict, GroundTruth]:
        boss = self._acc("smr")
        mules = [self._acc("smr") for _ in range(n)]
        edges = []
        for i, m in enumerate(mules):
            edges.append(self._edge(boss, m, 49_000, i * 0.5))  # just below 50k
        gt = GroundTruth("smurfing", "FRAUD", {boss, *mules}, {"smurfing", "fan_out"})
        return self._component(gid, edges), gt

    def fan_out(self, gid="GRAPH_FO", n: int = 7) -> tuple[dict, GroundTruth]:
        hub = self._acc("fo")
        rec = [self._acc("fo") for _ in range(n)]
        edges = [self._edge(hub, r, 95_000, i * 0.4) for i, r in enumerate(rec)]
        gt = GroundTruth("fan_out", "FRAUD", {hub, *rec}, {"fan_out"})
        return self._component(gid, edges), gt

    def fan_in(self, gid="GRAPH_FI", n: int = 7) -> tuple[dict, GroundTruth]:
        collector = self._acc("fi")
        senders = [self._acc("fi") for _ in range(n)]
        edges = [self._edge(s, collector, 88_000, i * 0.4) for i, s in enumerate(senders)]
        gt = GroundTruth("fan_in", "FRAUD", {collector, *senders}, {"fan_in"})
        return self._component(gid, edges), gt

    def mule_network(self, gid="GRAPH_M", chains: int = 3, depth: int = 3) -> tuple[dict, GroundTruth]:
        src = self._acc("mul")
        edges, fraud = [], {src}
        amt0 = 300_000
        for c in range(chains):
            prev, amt = src, amt0
            for d in range(depth):
                nxt = self._acc("mul")
                amt *= 0.9
                edges.append(self._edge(prev, nxt, amt, (c * depth + d) * 0.6))
                fraud.add(nxt)
                prev = nxt
        gt = GroundTruth("mule_network", "FRAUD", fraud, {"mule_accounts", "fan_out"})
        return self._component(gid, edges), gt

    def circular(self, gid="GRAPH_C", n: int = 5) -> tuple[dict, GroundTruth]:
        accs = [self._acc("cir") for _ in range(n)]
        edges, amt = [], 250_000.0
        for i in range(n):
            edges.append(self._edge(accs[i], accs[(i + 1) % n], amt, i * 1.0))
        gt = GroundTruth("circular", "FRAUD", set(accs), {"circular_flow"})
        return self._component(gid, edges), gt

    def bridge_network(self, gid="GRAPH_B") -> tuple[dict, GroundTruth]:
        # two sub-rings joined by a single bridge account
        left = [self._acc("brl") for _ in range(4)]
        right = [self._acc("brr") for _ in range(4)]
        bridge = self._acc("brg")
        edges = []
        for i in range(len(left)):
            edges.append(self._edge(left[i], bridge if i == 0 else left[0], 120_000, i * 0.5))
        edges.append(self._edge(left[0], bridge, 300_000, 5))
        edges.append(self._edge(bridge, right[0], 290_000, 6))
        for i in range(1, len(right)):
            edges.append(self._edge(right[0], right[i], 70_000, 6 + i * 0.5))
        fraud = {bridge, *left, *right}
        gt = GroundTruth("bridge_network", "FRAUD", fraud, {"bridge_accounts", "fan_out"})
        return self._component(gid, edges), gt

    def cashout_network(self, gid="GRAPH_CO", n: int = 5) -> tuple[dict, GroundTruth]:
        mules = [self._acc("co") for _ in range(n)]
        cash = self._acc("cash")
        edges = [self._edge(m, cash, 120_000, i * 0.5) for i, m in enumerate(mules)]
        meta = {cash: {"account_type": "cash"}}
        fraud = {cash, *mules}
        gt = GroundTruth("cashout_network", "FRAUD", fraud, {"cashout", "fan_in"})
        return self._component(gid, edges, meta), gt

    def synthetic_ring(self, gid="GRAPH_SR", n: int = 8) -> tuple[dict, GroundTruth]:
        accs = [self._acc("syn") for _ in range(n)]
        edges = []
        # dense, uniform interconnection — engineered look
        for i in range(n):
            for j in (1, 2):
                tgt = accs[(i + j) % n]
                edges.append(self._edge(accs[i], tgt, 75_000, (i * 2 + j) * 0.4))
        meta = {a: {"account_type": "normal", "transaction_count": 1} for a in accs}
        gt = GroundTruth("synthetic_ring", "FRAUD", set(accs),
                         {"synthetic_networks", "circular_flow"})
        return self._component(gid, edges, meta), gt

    def hybrid(self, gid="GRAPH_H") -> tuple[dict, GroundTruth]:
        # origin → layering → fan-out → cashout, all in one
        o = self._acc("hyb")
        chain = [self._acc("hyb") for _ in range(3)]
        rec = [self._acc("hyb") for _ in range(5)]
        cash = self._acc("cash")
        edges, amt = [], 900_000.0
        prev = o
        for c in chain:
            amt *= 0.95
            edges.append(self._edge(prev, c, amt, len(edges) * 0.7))
            prev = c
        for r in rec:
            edges.append(self._edge(prev, r, 90_000, len(edges) * 0.5))
        for r in rec[:3]:
            edges.append(self._edge(r, cash, 80_000, len(edges) * 0.5))
        meta = {cash: {"account_type": "cash"}}
        fraud = {o, *chain, *rec, cash}
        gt = GroundTruth("hybrid", "FRAUD", fraud,
                         {"layering", "fan_out", "cashout", "hybrid_network"})
        return self._component(gid, edges, meta), gt

    def large_org(self, gid="GRAPH_ORG", controllers: int = 4,
                  mules_each: int = 8) -> tuple[dict, GroundTruth]:
        """A large criminal organisation: multiple controllers, mules, one cashout."""
        cash = self._acc("cash")
        edges, fraud = [], {cash}
        t = 0.0
        for _ in range(controllers):
            ctrl = self._acc("org")
            fraud.add(ctrl)
            mules = [self._acc("org") for _ in range(mules_each)]
            for m in mules:
                fraud.add(m)
                edges.append(self._edge(ctrl, m, self.rng.uniform(40_000, 49_000), t)); t += 0.3
                edges.append(self._edge(m, cash, self.rng.uniform(35_000, 45_000), t)); t += 0.3
        meta = {cash: {"account_type": "cash"}}
        gt = GroundTruth("large_org", "FRAUD", fraud,
                         {"smurfing", "mule_accounts", "fan_in", "cashout"})
        return self._component(gid, edges, meta), gt

    # ── dataset assembly ──────────────────────────────────────────────────────
    def mixed_dataset(self, n_fraud: int = 6, n_normal: int = 6) -> list[tuple[dict, GroundTruth]]:
        """A realistic mix of legitimate + fraudulent clusters."""
        fraud_makers = [self.layering, self.smurfing, self.fan_out, self.fan_in,
                        self.mule_network, self.circular, self.bridge_network,
                        self.cashout_network, self.synthetic_ring, self.hybrid]
        out: list[tuple[dict, GroundTruth]] = []
        for i in range(n_fraud):
            maker = fraud_makers[i % len(fraud_makers)]
            out.append(maker(gid=f"GRAPH_F{i:03d}"))
        for i in range(n_normal):
            out.append(self.normal(gid=f"GRAPH_C{i:03d}",
                                   n_accounts=self.rng.randint(4, 10)))
        self.rng.shuffle(out)
        return out

    def scale_test(self, n_nodes: int, fraud_fraction: float = 0.2) -> tuple[dict, GroundTruth]:
        """
        One big component of `n_nodes` accounts with an embedded fraud sub-network,
        for scalability benchmarking (100 → 100,000+ nodes).
        """
        accs = [self._acc("scl") for _ in range(n_nodes)]
        edges = []
        # legitimate background noise
        for _ in range(n_nodes):
            src, tgt = self.rng.sample(accs, 2)
            edges.append(self._edge(src, tgt, self.rng.uniform(500, 20_000),
                                    self.rng.uniform(0, 60 * 24 * 30),
                                    rail=self.rng.choice(["UPI", "NEFT"])))
        # embedded fraud ring
        ring_size = max(5, int(n_nodes * fraud_fraction * 0.1))
        ring = self.rng.sample(accs, min(ring_size, n_nodes))
        amt = 700_000.0
        for i in range(len(ring) - 1):
            amt *= 0.95
            edges.append(self._edge(ring[i], ring[i + 1], amt, i * 0.5))
        gt = GroundTruth("scale_test", "FRAUD", set(ring), {"layering"})
        return self._component(f"GRAPH_SCALE_{n_nodes}", edges), gt
