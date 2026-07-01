from __future__ import annotations
import uuid
import copy
import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict


@dataclass
class TopologyGene:
    type: str  # fan_in | fan_out | cycle | chain | bipartite | layered
    depth: int
    width: int  # accounts per source layer
    collector_count: int
    bridge_nodes: List[dict] = field(default_factory=list)
    abandoned_nodes: List[dict] = field(default_factory=list)
    merchant_nodes: List[dict] = field(default_factory=list)
    exchange_nodes: List[dict] = field(default_factory=list)
    mimics_legitimate: Optional[str] = None
    layers: Optional[List[dict]] = None


@dataclass
class TimingGene:
    spacing_days: List[float]
    jitter: float = 0.0
    time_of_day: str = "business_hours"  # business_hours | night | afternoon | morning
    low_slow: bool = False
    dormancy_periods: List[dict] = field(default_factory=list)  # [{after_txn: int, duration_days: int}]
    festival_timing: Optional[dict] = None
    festival_name: Optional[str] = None
    burst_behavior: bool = False


@dataclass
class AmountsGene:
    values: List[float]
    pattern: str = "equal_split"  # equal_split | organic_noisy | decreasing | increasing
    just_under_threshold: bool = False
    noise_percent: float = 0.0
    round_number_avoidance: bool = False

    @property
    def total(self) -> float:
        return sum(self.values)


@dataclass
class ChannelsGene:
    mix: Dict[str, float]  # {"UPI": 0.7, "IMPS": 0.2, "NEFT": 0.1}
    channel_hop: bool = False
    channel_sequence: List[str] = field(default_factory=list)
    upi_app_diversity: bool = False
    upi_apps: List[str] = field(default_factory=list)


@dataclass
class AccountsGene:
    source_ages_days: List[int]
    velocity_ratio: float = 0.5
    kyc_tier: str = "full"  # min | basic | full
    prior_legit_transactions_per_account: int = 5
    device_diversity: bool = False
    ip_diversity: bool = False
    geographic_spread: List[str] = field(default_factory=list)
    cross_city: bool = False


@dataclass
class SpecialNodesGene:
    abandoned_nodes: dict = field(
        default_factory=lambda: {"count": 0, "dormancy_days": 60, "purpose": ""}
    )
    merchant_nodes: dict = field(
        default_factory=lambda: {"count": 0, "mcc_codes": [], "invoice_pattern": False}
    )
    bridge_nodes: dict = field(
        default_factory=lambda: {"count": 0, "hold_days": 1, "partial_forward": False}
    )
    exchange_nodes: dict = field(
        default_factory=lambda: {"count": 0, "type": "crypto", "launder_rounds": 1}
    )
    cash_out_method: Optional[str] = None
    cash_out_delay_days: int = 0


@dataclass
class FraudGenome:
    lineage_id: str
    topology: TopologyGene
    timing: TimingGene
    amounts: AmountsGene
    channels: ChannelsGene
    accounts: AccountsGene
    special_nodes: SpecialNodesGene

    genome_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_genome_id: Optional[str] = None
    generation: int = 0
    mutation_history: List[str] = field(default_factory=list)
    fitness_score: float = 0.0
    realism_score: float = 0.0
    novelty_score: float = 0.0
    status: str = "active"  # active | pending_review | approved_gate | approved_retrain | discarded
    flags: List[str] = field(default_factory=list)
    repair_recommendation: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    def clone(self) -> "FraudGenome":
        return copy.deepcopy(self)

    def _base_date(self) -> datetime:
        # Festival timing uses October base; otherwise May
        if self.timing.festival_timing:
            return datetime(2026, 10, 15, 14, 0, 0)
        return datetime(2026, 5, 1, 10, 0, 0)

    def _select_channel(self, idx: int) -> str:
        if self.channels.channel_sequence:
            return self.channels.channel_sequence[idx % len(self.channels.channel_sequence)]
        if self.channels.mix:
            return max(self.channels.mix, key=self.channels.mix.get)
        return "ach_transfer"

    @staticmethod
    def _account_id(seed: str) -> str:
        """Deterministic acc_ + 10-char hex ID from a seed string."""
        import hashlib
        return "acc_" + hashlib.md5(seed.encode()).hexdigest()[:10]

    def _compute_timestamp(self, txn_index: int) -> datetime:
        base = self._base_date()
        offset_days = 0.0
        spacing = self.timing.spacing_days
        for i in range(min(txn_index, len(spacing))):
            offset_days += spacing[i]
        # Insert dormancy periods
        for dormancy in self.timing.dormancy_periods:
            if txn_index > dormancy.get("after_txn", 999):
                offset_days += dormancy.get("duration_days", 0)
        # Clamp to a sane horizon (~100y). Evolution can stack time-dilation
        # operators and push offsets past datetime's range otherwise.
        offset_days = max(0.0, min(offset_days, 36_500.0))
        return base + timedelta(days=offset_days)

    def to_transaction_list(self) -> List[dict]:
        """Convert genome to flat list of transactions in Blue Team test format.

        Format: {from_account: acc_<10hex>, to_account: acc_<10hex>,
                 amount: int, payment_rail: str, timestamp: ISO8601}
        """
        transactions = []
        gid = self.genome_id
        topology = self.topology

        amounts = self.amounts.values
        n_amounts = len(amounts)

        def _acc(role: str) -> str:
            return self._account_id(f"{gid}_{role}")

        if topology.type in ("fan_in", "bipartite"):
            sources = [_acc(f"src{i}") for i in range(topology.width)]
            collectors = [_acc(f"col{i}") for i in range(max(1, topology.collector_count))]
            for i, src in enumerate(sources):
                collector = collectors[i % len(collectors)]
                transactions.append({
                    "from_account": src,
                    "to_account": collector,
                    "amount": int(amounts[i % n_amounts]),
                    "payment_rail": self._select_channel(i),
                    "timestamp": self._compute_timestamp(i).strftime("%Y-%m-%dT%H:%M:%S"),
                })
            if topology.depth > 2:
                sink = _acc("sink")
                for j, col in enumerate(collectors):
                    fwd_time = self._compute_timestamp(len(sources) + j + 3)
                    col_total = sum(
                        amounts[i % n_amounts]
                        for i in range(len(sources))
                        if i % len(collectors) == j
                    )
                    transactions.append({
                        "from_account": col,
                        "to_account": sink,
                        "amount": int(col_total * 0.97),
                        "payment_rail": self._select_channel(j + len(sources)),
                        "timestamp": fwd_time.strftime("%Y-%m-%dT%H:%M:%S"),
                    })

        elif topology.type == "fan_out":
            source = _acc("src0")
            targets = [_acc(f"tgt{i}") for i in range(topology.width)]
            for i, tgt in enumerate(targets):
                transactions.append({
                    "from_account": source,
                    "to_account": tgt,
                    "amount": int(amounts[i % n_amounts]),
                    "payment_rail": self._select_channel(i),
                    "timestamp": self._compute_timestamp(i).strftime("%Y-%m-%dT%H:%M:%S"),
                })

        elif topology.type == "cycle":
            # Closed ring: n0 → n1 → … → n_{k-1} → n0 (real graph cycle so Blue's
            # circular_flow detector has something to see). Format unchanged.
            k = max(2, topology.depth)
            nodes = [_acc(f"c{i}") for i in range(k)]
            for i in range(k):
                transactions.append({
                    "from_account": nodes[i],
                    "to_account": nodes[(i + 1) % k],
                    "amount": int(amounts[i % n_amounts]),
                    "payment_rail": self._select_channel(i),
                    "timestamp": self._compute_timestamp(i).strftime("%Y-%m-%dT%H:%M:%S"),
                })

        elif topology.type == "chain":
            nodes = [_acc(f"n{i}") for i in range(topology.depth + 1)]
            for i in range(len(nodes) - 1):
                transactions.append({
                    "from_account": nodes[i],
                    "to_account": nodes[i + 1],
                    "amount": int(amounts[i % n_amounts]),
                    "payment_rail": self._select_channel(i),
                    "timestamp": self._compute_timestamp(i).strftime("%Y-%m-%dT%H:%M:%S"),
                })

        elif topology.type == "layered" and topology.layers:
            prev_layer = [_acc("l0n0")]
            for layer_idx, layer_info in enumerate(topology.layers):
                curr_layer = [_acc(f"l{layer_idx+1}n{j}") for j in range(max(2, topology.width // 2))]
                for src in prev_layer:
                    for tgt in curr_layer[:2]:
                        txn_idx = len(transactions)
                        transactions.append({
                            "from_account": src,
                            "to_account": tgt,
                            "amount": int(amounts[txn_idx % n_amounts]),
                            "payment_rail": self._select_channel(txn_idx),
                            "timestamp": self._compute_timestamp(txn_idx).strftime("%Y-%m-%dT%H:%M:%S"),
                        })
                prev_layer = curr_layer

        else:
            transactions.append({
                "from_account": _acc("src0"),
                "to_account": _acc("col0"),
                "amount": int(amounts[0]),
                "payment_rail": self._select_channel(0),
                "timestamp": self._compute_timestamp(0).strftime("%Y-%m-%dT%H:%M:%S"),
            })

        return transactions
