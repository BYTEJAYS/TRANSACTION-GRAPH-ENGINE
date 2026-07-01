from __future__ import annotations
"""
Sandbox Blue Team — imports actual apply_indian_context from Blue Team source.
Gate logic simulated from exact Cypher/SQL conditions read from source files:
  - tier1/heuristics.py
  - tier2/bipartite_gate.py + graph/queries/bipartite_queries.py (Cypher)
  - tier2/sink_gate.py + graph/queries/sink_queries.py (Cypher)
  - tier2/cash_mule_sink_gate.py (SQL)
  - tier2/cycle_gate.py + legitimacy_filter.py
  - context/indian_adjuster.py (imported directly — pure function)
"""
import math
import sys
import os
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from red_team.core.genome import FraudGenome

logger = logging.getLogger(__name__)

# Frozen snapshot version — attack_loop.py records this in every DNA file
# so you can compare bypasses against future blue team versions.
BLUE_TEAM_VERSION = "v1.0-2026-05-19"

# ── Direct import from Blue Team source ──────────────────────────────────────
# indian_adjuster.py only imports `from datetime import datetime, timezone`
# No DB/Redis/Neo4j deps — can import directly without stubs.

_BT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "../../../", "blue team - union bank ")
)
_apply_bt_context = None

try:
    if _BT_PATH not in sys.path:
        sys.path.insert(0, _BT_PATH)
    from app.detection.context.indian_adjuster import (
        apply_indian_context as _apply_bt_context,
    )
    logger.info("Blue Team indian_adjuster imported — using exact source logic")
except Exception as _exc:
    logger.warning("Blue Team direct import failed (%s) — falling back to local replica", _exc)

# ── Thresholds sourced directly from Blue Team files ─────────────────────────

# bipartite_queries.py Cypher: size(senders) >= 5 AND density > 0.7
_BIPARTITE_MIN_SENDERS = 5
_BIPARTITE_DENSITY_THRESHOLD = 0.70
_BIPARTITE_MERCHANT_DENSITY = 0.85   # exempt if merchant AND density < this

# sink_queries.py Cypher
_SINK_MIN_INFLOW = 50_000
_SINK_MIN_RETENTION = 0.80
_SINK_MIN_DORMANCY_DAYS = 30
_SINK_MAX_AGE_DAYS = 180

# cash_mule_sink_gate.py
_CASH_MULE_MIN_INFLOW = 50_000
_CASH_MULE_CASH_RATIO = 0.80          # REQUIRES channel='ATM' in actual DB
_CASH_MULE_MAX_AGE = 180

# heuristics.py
_VELOCITY_1H_MAX = 5
_NEW_VPA_DAYS = 7
_NEW_PAYEE_ACCOUNT_DAYS = 14
_AMOUNT_SPIKE_MULTIPLIER = 5.0
_THRESHOLD_BANDS = [(49_000, 50_000), (99_000, 100_000), (990_000, 1_000_000)]
_HIGH_FREQ_OCCUPATIONS = frozenset({
    "gig_worker", "freelancer", "delivery", "merchant", "retailer",
})

# bipartite_gate.py _LEGIT_AGGREGATOR_OCCUPATIONS
_LEGIT_AGGREGATOR_OCCS = frozenset({
    "salary_processor", "payroll_processor", "insurance_company",
    "tax_collector", "utility_provider",
})

# sink_gate.py legitimacy
_LEGIT_SINK_OCCS = frozenset({"merchant", "retailer", "shopkeeper"})
_LEGIT_SINK_TYPES = frozenset({"JAN_DHAN"})

# cash_mule_sink_gate.py legitimacy
_LEGIT_CASH_HEAVY_TYPES = frozenset({"JAN_DHAN"})
_LEGIT_CASH_HEAVY_OCCS = frozenset({
    "vegetable_vendor", "daily_wage", "agricultural_worker", "street_vendor",
})

# legitimacy_filter.py
_INTERNAL_ACCOUNT_TYPES = frozenset({"INTERNAL", "TREASURY", "NOSTRO", "VOSTRO"})
_PAYROLL_OCCUPATIONS = frozenset({"employer", "corporate", "payroll_processor"})
_LEGIT_RETURN_RATIO = 0.70

# Score action thresholds
_THRESHOLD_LOG = 0.40
_THRESHOLD_REVIEW = 0.62
_THRESHOLD_HIGH_RISK = 0.80

# Rail → Blue Team channel name mapping
_RAIL_TO_CHANNEL = {
    "p2p_transfer": "UPI",
    "bill_payment": "UPI",
    "internal_transfer": "IMPS",
    "debit_purchase": "IMPS",
    "pos_transaction": "IMPS",
    "ach_transfer": "NEFT",
    "crypto_exchange": "NEFT",
    "wire_transfer": "RTGS",
    "atm_withdrawal": "ATM",
}

_DEFAULT_ACCOUNT: dict = {
    "account_age_days": 365,
    "account_type": "SAVINGS",
    "kyc_occupation": "salaried",
    "kyc_age": 35,
    "is_merchant": False,
    "avg_amount_30d": 10_000.0,
    "prior_monthly_txn_count": 10,
    "has_festival_gifting_history": False,
    "payee_vpa_age_days": 365,
    "role": "source",
}


class MockBlueTeam:
    """
    Sandbox Blue Team that directly imports real detection logic.

    Imports apply_indian_context from actual Blue Team source (pure function).
    Simulates Tier 2 gates using exact Cypher/SQL conditions from source.

    KEY BYPASSES DISCOVERED FROM SOURCE:
    - cash_mule_sink: ONLY fires if channel='ATM' in DB. Digital rails → ratio=0 → never fires.
    - abandoned_sink: requires dormancy > 30 days AND collector age < 180 AND retention > 80%.
    - bipartite: exempt if salary_processor/payroll_processor. Merchant density < 0.85 = exempt.
    - cycle: only fires on actual graph cycles. 5 legitimacy filters can explain cycles.
    - festival adjuster: REQUIRES payee_vpa_age_days < 30. Old payees = adjustment never applies.

    account_fixtures format:
        "acc_xxx": {
            "account_age_days": int,
            "account_type": str,           # SAVINGS | JAN_DHAN | CURRENT | INTERNAL
            "kyc_occupation": str,         # salaried | merchant | gig_worker | salary_processor | ...
            "kyc_age": int | None,
            "is_merchant": bool,
            "avg_amount_30d": float,
            "prior_monthly_txn_count": int,
            "has_festival_gifting_history": bool,
            "payee_vpa_age_days": int | None,  # CRITICAL: festival requires < 30
            "role": str,                        # "source" | "collector" | "sink"
        }
    """

    def __init__(self, account_fixtures: dict | None = None):
        self._fixtures = account_fixtures or {}

    def _get_account(self, account_id: str) -> dict:
        return {**_DEFAULT_ACCOUNT, **self._fixtures.get(account_id, {})}

    def _find_collector(self) -> tuple[str, dict]:
        """Find collector/sink account. Prefers explicit role='collector'/'sink'."""
        for acc_id, data in self._fixtures.items():
            if data.get("role") in ("collector", "sink"):
                return acc_id, {**_DEFAULT_ACCOUNT, **data}
        if self._fixtures:
            last_id = list(self._fixtures.keys())[-1]
            return last_id, self._get_account(last_id)
        return "", dict(_DEFAULT_ACCOUNT)

    def _find_source_accounts(self) -> list[tuple[str, dict]]:
        sources = [
            (k, {**_DEFAULT_ACCOUNT, **v})
            for k, v in self._fixtures.items()
            if v.get("role", "source") == "source"
        ]
        if not sources and self._fixtures:
            items = list(self._fixtures.items())
            sources = [(k, {**_DEFAULT_ACCOUNT, **v}) for k, v in items[:-1]]
        return sources

    def _primary_rail(self, genome: "FraudGenome") -> str:
        if genome.channels.channel_sequence:
            return genome.channels.channel_sequence[0]
        if genome.channels.mix:
            return max(genome.channels.mix, key=genome.channels.mix.get)
        return "ach_transfer"

    def _primary_channel_old(self, genome: "FraudGenome") -> str:
        return _RAIL_TO_CHANNEL.get(self._primary_rail(genome), "NEFT")

    def _genome_timestamp(self, genome: "FraudGenome") -> datetime:
        tod = genome.timing.time_of_day
        hour = {"morning": 9, "afternoon": 14, "business_hours": 11,
                "evening": 18, "night": 1}.get(tod, 11)
        if genome.timing.festival_timing:
            month = genome.timing.festival_timing.get("month", 10)
            return datetime(2026, month, 15, hour, 0, 0, tzinfo=timezone.utc)
        return datetime(2026, 5, 15, hour, 0, 0, tzinfo=timezone.utc)

    def _velocity_1h(self, genome: "FraudGenome") -> int:
        if not genome.timing.spacing_days:
            return 1
        min_spacing = min(genome.timing.spacing_days)
        if min_spacing <= 0:
            return 10
        spacing_hours = min_spacing * 24
        return max(2, int(1.0 / spacing_hours)) if spacing_hours < 1 else 1

    # ── Tier 1 ────────────────────────────────────────────────────────────────

    def _tier1_heuristics(self, genome: "FraudGenome") -> tuple[str, list[str]]:
        """Mirrors tier1_classify() from heuristics.py exactly."""
        flags: list[str] = []
        amounts = genome.amounts.values

        sources = self._find_source_accounts()
        src_data = sources[0][1] if sources else dict(_DEFAULT_ACCOUNT)
        avg_amount_30d = src_data.get("avg_amount_30d", 10_000.0)
        kyc_occupation = src_data.get("kyc_occupation", "salaried")
        src_age = src_data.get("account_age_days", 365)

        # Payee = collector in fan-in flows
        _, collector_data = self._find_collector()
        payee_account_age = collector_data.get("account_age_days", 365)
        # payee_vpa_age: age of the payee's VPA/UPI ID (not account age)
        payee_vpa_age = collector_data.get(
            "payee_vpa_age_days",
            collector_data.get("account_age_days", 365),
        )

        # new_vpa: payee_vpa_age_days < 7 (from heuristics.py)
        if payee_vpa_age is not None and payee_vpa_age < _NEW_VPA_DAYS:
            flags.append("new_vpa")

        # night: 23:00–05:00 UTC
        if genome.timing.time_of_day == "night":
            flags.append("night")

        # velocity_spike: > 5 tx/hr AND not high-freq occupation
        vel_1h = self._velocity_1h(genome)
        if vel_1h > _VELOCITY_1H_MAX and kyc_occupation not in _HIGH_FREQ_OCCUPATIONS:
            flags.append("velocity_spike")

        # threshold_proximity: amount in suspicious bands
        for amount in amounts:
            for low, high in _THRESHOLD_BANDS:
                if low <= amount < high:
                    flags.append("threshold_proximity")
                    break

        # new_payee_account: payee account < 14 days
        if payee_account_age is not None and payee_account_age < _NEW_PAYEE_ACCOUNT_DAYS:
            flags.append("new_payee_account")

        # amount_spike: txn amount > sender avg × 5
        avg_amount = sum(amounts) / len(amounts) if amounts else 0
        if avg_amount_30d > 0 and avg_amount > avg_amount_30d * _AMOUNT_SPIKE_MULTIPLIER:
            flags.append("amount_spike")

        if flags:
            return "SUSPICIOUS", flags

        # FAST_CLEAN: account old, amount modest, payee known, not night
        # payee_in_known_contacts is False for all fraud genomes
        if (
            src_age > 365
            and avg_amount_30d > 0
            and avg_amount < avg_amount_30d * 2
            and genome.timing.time_of_day not in ("night",)
        ):
            return "FAST_CLEAN", []

        return "UNCERTAIN", []

    # ── Gate simulations based on exact Cypher/SQL ────────────────────────────

    def _simulate_bipartite_data(self, genome: "FraudGenome") -> dict | None:
        """
        Simulates check_bipartite_core() from bipartite_queries.py.
        Cypher: size(senders) >= 5  AND  density > 0.70
        density = actual_edges / sender_count

        In fraud fan-in: each sender targets ONLY this collector → density = 1.0.
        In merchant bipartite: customers go to many merchants → density ≈ 0.60.
        """
        sender_count = genome.topology.width
        if sender_count < _BIPARTITE_MIN_SENDERS:
            return None  # Cypher WHERE size(senders) >= 5 fails → no result

        _, collector_data = self._find_collector()
        is_merchant = collector_data.get("is_merchant", False)
        kyc_occ = collector_data.get("kyc_occupation", "salaried")

        # Merchant receivers: customers send to many merchants → density < 0.85
        density = 0.60 if is_merchant else 1.0

        if density <= _BIPARTITE_DENSITY_THRESHOLD:
            return None  # Cypher WHERE density > 0.70 fails

        return {
            "sender_count": sender_count,
            "density": density,
            "receiver_kyc_occupation": kyc_occ,
            "receiver_is_merchant": is_merchant,
        }

    def _simulate_sink_data(self, genome: "FraudGenome") -> dict | None:
        """
        Simulates check_abandoned_sink() from sink_queries.py.
        Cypher: inflow_last_30d > 50000 AND retention_ratio > 0.80
               AND days_since_last_send > 30 AND account_age_days < 180

        Two separate code paths — different fraud signatures require different evidence:

        NEW MULE PATH (age < 180): Original Cypher. New mule accounts receive, retain >80%,
        go dormant. Single source is enough. Retention HIGH = suspicious.

        OLD DORMANT-REACTIVATED PATH (age >= 180): Abandoned node pattern.
        Removed age ceiling here, compensated with THREE narrowing conditions (NEVER-2):
          1. sender_count >= 3 — NRI (1-2 senders) and medical transfers (1 sender) protected
          2. dormancy >= 60d   — 30d dormancy on old account is normal (vacation, seasonal)
          3. has_forwarding    — old account HOLDING funds = legitimate (wedding, NRI savings);
                                 old account FORWARDING = relay = suspicious
        Retention LOW (0.50 when forwarding) vs threshold 0.40 = fires correctly for relay.
        """
        _, collector_data = self._find_collector()
        collector_age = collector_data.get("account_age_days", 365)

        total_inflow = genome.amounts.total
        if total_inflow <= _SINK_MIN_INFLOW:
            return None

        dormancy_days = genome.special_nodes.abandoned_nodes.get("dormancy_days", 0)
        if dormancy_days == 0 and genome.timing.spacing_days:
            dormancy_days = sum(genome.timing.spacing_days)

        has_forwarding = genome.topology.depth > 2
        retention = 0.50 if has_forwarding else 1.00

        if collector_age >= _SINK_MAX_AGE_DAYS:
            # OLD DORMANT-REACTIVATED PATH
            sender_count = genome.topology.width
            if sender_count < 3:
                return None  # single/dual sender to old account = NRI/family = normal
            if dormancy_days < 60:
                return None  # 30d dormancy on old account = vacation/seasonal = normal
            if not has_forwarding:
                return None  # old account holding funds = wedding/savings = legitimate
            if retention <= 0.40:
                return None  # forwarding model: retention=0.50 when depth>2
        else:
            # NEW MULE PATH (original Cypher logic)
            if dormancy_days <= _SINK_MIN_DORMANCY_DAYS:
                return None
            if retention <= _SINK_MIN_RETENTION:
                return None

        return {
            "inflow_last_30d": total_inflow,
            "retention_ratio": retention,
            "days_since_last_send": dormancy_days,
            "account_age_days": collector_age,
            "account_type": collector_data.get("account_type", "SAVINGS"),
            "kyc_occupation": collector_data.get("kyc_occupation", "salaried"),
            "reactivated_dormant": collector_age >= _SINK_MAX_AGE_DAYS,
        }

    def _simulate_cycles(self, genome: "FraudGenome") -> list[dict]:
        """
        Simulates find_cycles() from cycle_queries.py.
        Cypher: MATCH path = (start)-[:SENT*2..8]->(start)

        ONLY returns data for cycle topology — chain/fan_in/fan_out produce NO
        graph cycles in Neo4j even if the genome pattern looks cyclic.
        """
        if genome.topology.type != "cycle":
            return []

        amounts = genome.amounts.values
        account_ids = list(self._fixtures.keys())
        node_ids = account_ids[: genome.topology.depth + 1]
        if node_ids:
            node_ids = node_ids + [node_ids[0]]  # close the cycle

        return [{
            "hops": genome.topology.depth,
            "amounts": [float(a) for a in amounts[: genome.topology.depth]],
            "node_ids": node_ids,
            "timestamps": [
                f"2026-05-{15 + i:02d}T10:00:00" for i in range(genome.topology.depth)
            ],
        }]

    def _simulate_rapid_relay(self, genome: "FraudGenome") -> dict | None:
        """
        Rapid relay backstop: ≥4 sources + ≥1L inflow + dormancy ≥60d + conservation ≥95%.
        Works without account fixtures (genome-level signals only).
        Gate 2 is the primary detector when fixtures available. Gate 0 is the fallback.

        Bug fixes from initial implementation:
        - timing proxy removed: spacing_days = source gaps, NOT relay window. Attacker
          spaces sources 1d apart (normal-looking) but relays instantly → spacing gave 4320min.
          Replaced with dormancy_days ≥60 which is the actual reactivation signal.
        - conservation fix: for fan_in/bipartite, amounts[-1] is the LAST SOURCE PAYMENT
          (e.g. ₹59,870), not the forwarded amount. For fan_in, outflow = total * 0.97
          (matches to_transaction_list() forwarding logic). For chain, amounts[-1] is correct.
        """
        sources = self._find_source_accounts()
        if len(sources) < 4:
            return None

        _, collector_data = self._find_collector()
        if collector_data.get("kyc_occupation", "") in _LEGIT_AGGREGATOR_OCCS:
            return None

        total_inflow = genome.amounts.total
        if total_inflow < 100_000:
            return None

        # Reactivation signal: dormancy_days is the real relay indicator, not source spacing
        dormancy = genome.special_nodes.abandoned_nodes.get("dormancy_days", 0)
        if dormancy < 60:
            return None

        amounts = genome.amounts.values
        if not amounts:
            return None
        # fan_in/bipartite: amounts are per-source payments; outflow is aggregated forward
        if genome.topology.type in ("fan_in", "bipartite"):
            outflow = total_inflow * 0.97  # matches to_transaction_list() forwarding logic
        else:
            outflow = amounts[-1] if len(amounts) > 1 else amounts[0]
        conservation = outflow / total_inflow if total_inflow > 0 else 0
        if conservation < 0.95:
            return None

        return {
            "source_count": len(sources),
            "total_inflow": total_inflow,
            "conservation_ratio": round(conservation, 3),
            "dormancy_days": dormancy,
        }

    def _tier2_gates(self, genome: "FraudGenome") -> dict:
        """
        Runs 6 gates in order. Returns first fired gate or {'fired': False}.
        Order: rapid_relay → cycle → abandoned_sink → bipartite → cash_mule → merchant_terminal
        """

        # ── Gate 0: Rapid Relay ──────────────────────────────────────────────
        relay_data = self._simulate_rapid_relay(genome)
        if relay_data:
            return {"fired": True, "gate": "rapid_relay", "evidence": relay_data}

        # ── Gate 1: Cycle ────────────────────────────────────────────────────
        for cycle in self._simulate_cycles(genome):
            node_ids = cycle.get("node_ids", [])
            amounts_list = cycle.get("amounts", [])
            if len(amounts_list) < 2:
                continue

            entry = float(amounts_list[0])
            exit_amt = float(amounts_list[-1])
            duration = sum(genome.timing.spacing_days) if genome.timing.spacing_days else 0

            # Filter 1: Internal/Treasury account
            if any(
                self._get_account(n).get("account_type", "") in _INTERNAL_ACCOUNT_TYPES
                for n in node_ids
            ):
                continue

            # Filter 2: KYC relationship — always False for synthetic fraud genomes
            # (no KYC_RELATED edges in test graph)

            # Filter 3: Salary advance return
            origin_occ = (
                self._get_account(node_ids[0]).get("kyc_occupation", "")
                if node_ids else ""
            )
            if (
                origin_occ in _PAYROLL_OCCUPATIONS
                and duration <= 30
                and exit_amt <= entry
            ):
                continue

            # Filter 4: All-merchant settlement cycle
            if node_ids and all(
                self._get_account(n).get("is_merchant", False) for n in node_ids
            ):
                continue

            # Filter 5: Amount reduction < 70% (fee/partial repayment)
            if entry > 0 and (exit_amt / entry) < _LEGIT_RETURN_RATIO:
                continue

            return {
                "fired": True,
                "gate": "confirmed_cycle",
                "evidence": {"hops": cycle.get("hops"), "entry": entry, "exit": exit_amt},
            }

        # ── Gate 2: Abandoned Sink ───────────────────────────────────────────
        sink_data = self._simulate_sink_data(genome)
        if sink_data:
            a_type = sink_data.get("account_type", "")
            a_occ = sink_data.get("kyc_occupation", "")
            if a_type not in _LEGIT_SINK_TYPES and a_occ not in _LEGIT_SINK_OCCS:
                return {"fired": True, "gate": "abandoned_sink", "evidence": sink_data}

        # ── Gate 3: Bipartite Core ───────────────────────────────────────────
        bipartite_data = self._simulate_bipartite_data(genome)
        if bipartite_data:
            kyc_occ = bipartite_data.get("receiver_kyc_occupation", "")
            is_merchant = bipartite_data.get("receiver_is_merchant", False)
            density = bipartite_data.get("density", 1.0)

            if kyc_occ in _LEGIT_AGGREGATOR_OCCS:
                pass  # exempt: legitimate_aggregator (payroll, insurance, etc.)
            elif is_merchant and density < _BIPARTITE_MERCHANT_DENSITY:
                pass  # exempt: diverse merchant (density < 0.85)
            else:
                return {"fired": True, "gate": "bipartite_core", "evidence": bipartite_data}

        # ── Gate 4: Cash Mule Sink ───────────────────────────────────────────
        # CRITICAL: The real gate queries channel='ATM' in PostgreSQL.
        # Without atm_withdrawal in channels.mix → cash_ratio = 0 → NEVER fires.
        # This is the most important bypass: use digital rails only.
        atm_fraction = genome.channels.mix.get("atm_withdrawal", 0.0)
        if atm_fraction >= _CASH_MULE_CASH_RATIO:
            _, collector_data = self._find_collector()
            c_age = collector_data.get("account_age_days", 365)
            c_type = collector_data.get("account_type", "SAVINGS")
            c_occ = collector_data.get("kyc_occupation", "salaried")
            if (
                c_age <= _CASH_MULE_MAX_AGE
                and genome.amounts.total >= _CASH_MULE_MIN_INFLOW
                and c_type not in _LEGIT_CASH_HEAVY_TYPES
                and c_occ not in _LEGIT_CASH_HEAVY_OCCS
            ):
                return {
                    "fired": True,
                    "gate": "cash_mule_sink",
                    "evidence": {"account_age": c_age, "cash_ratio": atm_fraction},
                }

        # ── Gate 5: Merchant Terminal ────────────────────────────────────────
        # merchant_terminal_gate.py: returns False immediately when terminal_id is None.
        # FraudGenome has no terminal_id concept → always bypassed.

        return {"fired": False}

    # ── Tier 3 XGBoost score estimate ────────────────────────────────────────

    def _tier3_score(self, genome: "FraudGenome") -> float:
        """Estimates score from 87-feature set in feature_builder.py."""
        score = 0.0
        amounts = genome.amounts.values or [1]
        avg = sum(amounts) / len(amounts)

        sources = self._find_source_accounts()
        min_age = min((d.get("account_age_days", 365) for _, d in sources), default=365)

        # account_age_days (older = less suspicious)
        if min_age < 30:
            score += 0.18
        elif min_age < 90:
            score += 0.10
        elif min_age < 180:
            score += 0.05
        # > 180 days → minimal age signal

        # velocity_ratio
        score += min(0.12, genome.accounts.velocity_ratio * 0.40)

        # txn_amount_log (normalized 0–1 against ₹5L ceiling)
        amount_factor = min(1.0, math.log1p(avg) / math.log1p(500_000))
        score += amount_factor * 0.08

        # threshold proximity (XGBoost also weights this)
        for amount in amounts:
            for low, high in _THRESHOLD_BANDS:
                if low <= amount < high:
                    score += 0.06
                    break

        # Graph topology risk (maps to bipartite_score / cycle_membership features)
        topo_risk = {
            "chain": 0.04, "fan_in": 0.07, "fan_out": 0.03,
            "bipartite": 0.09, "cycle": 0.14, "layered": 0.10,
        }
        score += topo_risk.get(genome.topology.type, 0.05)

        # Depth (betweenness_centrality proxy)
        score += min(0.06, genome.topology.depth * 0.008)

        # channel_entropy: single-channel = lower entropy = more suspicious
        if len(genome.channels.mix) == 1:
            score += 0.04

        # Special node features
        if genome.special_nodes.abandoned_nodes.get("count", 0) > 0:
            score += 0.04
        if genome.special_nodes.bridge_nodes.get("count", 0) > 0:
            score += 0.03

        # low_slow reduces burst_score feature
        if genome.timing.low_slow:
            score -= 0.04

        # Geographic spread with old accounts lowers geography_switch risk
        if genome.accounts.cross_city and min_age > 200:
            score -= 0.02

        return min(1.0, max(0.0, score))

    # ── Indian Context Adjuster ───────────────────────────────────────────────

    def _apply_context(
        self, score: float, genome: "FraudGenome"
    ) -> tuple[float, dict]:
        """
        Applies Indian context adjustments.
        Uses real apply_indian_context when available (imported directly).
        Falls back to exact local replica if import failed.
        """
        amounts = genome.amounts.values or [0]
        avg_amount = sum(amounts) / len(amounts)
        ts = self._genome_timestamp(genome)
        channel_old = self._primary_channel_old(genome)

        sources = self._find_source_accounts()
        src_data = sources[0][1] if sources else dict(_DEFAULT_ACCOUNT)
        has_festival_gifting = src_data.get("has_festival_gifting_history", False)
        account_type = src_data.get("account_type", "SAVINGS")
        kyc_age = src_data.get("kyc_age", 35)
        kyc_occupation = src_data.get("kyc_occupation", "salaried")

        # CRITICAL: payee_vpa_age_days comes from PAYEE (collector) fixture.
        # Festival adjustment only fires when payee_vpa_age_days < 30.
        # This is why DNA 003 was detected: payee accounts were 200+ days old.
        _, collector_data = self._find_collector()
        payee_vpa_age: float | None = collector_data.get(
            "payee_vpa_age_days",
            float(collector_data.get("account_age_days", 365)),
        )

        daily_txn_count = self._velocity_1h(genome) * 16

        if _apply_bt_context is not None:
            adjusted, adjustments = _apply_bt_context(
                raw_score=score,
                txn_amount=avg_amount,
                txn_timestamp=ts,
                txn_channel=channel_old,
                payee_vpa_age_days=payee_vpa_age,
                account_type=account_type,
                kyc_age=kyc_age,
                kyc_occupation=kyc_occupation,
                has_festival_gifting_history=has_festival_gifting,
                daily_txn_count=daily_txn_count,
            )
        else:
            # Exact replica of indian_adjuster.py (fallback)
            adjustments: dict = {}
            is_night = ts.hour >= 23 or ts.hour < 5
            is_festival = (ts.month == 10) or (ts.month == 11 and ts.day <= 15)
            is_daytime = 11 <= ts.hour <= 23

            # Festival: REQUIRES payee_vpa_age_days < 30 (from indian_adjuster.py line 44-45)
            if (
                is_festival
                and avg_amount < 5_000
                and has_festival_gifting
                and payee_vpa_age is not None
                and payee_vpa_age < 30
            ):
                adjustments["festival_gifting"] = 0.70
                score *= 0.70

            # Gig worker velocity exemption
            if (
                daily_txn_count > 10
                and channel_old == "UPI"
                and kyc_occupation in ("gig_worker", "freelancer", "delivery")
                and is_daytime
            ):
                adjustments["gig_worker_velocity"] = 0.85
                score *= 0.85

            # JAN DHAN cash pattern
            if account_type == "JAN_DHAN":
                adjustments["jan_dhan_cash_pattern"] = 0.75
                score *= 0.75

            # Merchant batch settlement
            if (
                kyc_occupation in ("merchant", "retailer", "shopkeeper")
                and avg_amount == round(avg_amount, -2)
                and 18 <= ts.hour <= 23
            ):
                adjustments["merchant_batch_settlement"] = 0.80
                score *= 0.80

            # Senior citizen amplification
            if kyc_age is not None and kyc_age > 60:
                if is_night:
                    adjustments["senior_night_amplification"] = 1.50
                    score *= 1.50
                if payee_vpa_age is not None and payee_vpa_age < 7:
                    adjustments["senior_new_vpa_amplification"] = 1.30
                    score *= 1.30

            adjusted = min(1.0, score)

        return adjusted, adjustments

    # ── Public API ────────────────────────────────────────────────────────────

    def score(self, genome: "FraudGenome") -> list[float]:
        """Returns [champion, challenger_1, challenger_2, challenger_3]."""
        tier1, flags = self._tier1_heuristics(genome)

        if tier1 == "FAST_CLEAN":
            return [0.05, 0.05, 0.04, 0.06]

        gate = self._tier2_gates(genome)
        if gate.get("fired"):
            return [1.0, 1.0, 1.0, 1.0]

        base = self._tier3_score(genome)
        base, _ = self._apply_context(base, genome)

        # SUSPICIOUS tier1 adds XGBoost-equivalent penalty per flag
        if tier1 == "SUSPICIOUS":
            base = min(1.0, base + len(flags) * 0.04)

        return [
            round(base, 4),
            round(min(1.0, base * 0.90), 4),
            round(min(1.0, base * 1.10), 4),
            round(min(1.0, base * 0.95), 4),
        ]

    def score_action(self, scores: list[float]) -> str:
        c = scores[0]
        if c >= _THRESHOLD_HIGH_RISK:
            return "HIGH_RISK"
        if c >= _THRESHOLD_REVIEW:
            return "REVIEW"
        if c >= _THRESHOLD_LOG:
            return "LOG"
        return "PASS"

    def detailed_score(self, genome: "FraudGenome") -> dict:
        """Full scoring breakdown for debugging and bypass analysis."""
        tier1, flags = self._tier1_heuristics(genome)
        gate = self._tier2_gates(genome)
        base_t3 = self._tier3_score(genome) if not gate.get("fired") else None
        adj, ctx = (
            self._apply_context(base_t3 or 0.0, genome)
            if base_t3 is not None
            else (None, {})
        )
        scores = self.score(genome)
        return {
            "champion_score": scores[0],
            "all_scores": scores,
            "action": self.score_action(scores),
            "tier1": {"result": tier1, "flags": flags},
            "tier2_gate": gate,
            "tier3_base": base_t3,
            "context_adjustments": ctx,
            "bt_adjuster_source": "real_blue_team" if _apply_bt_context else "local_replica",
        }


class RealBlueTeam:
    """Wraps live Blue Team API at BLUE_TEAM_URL env var."""

    def __init__(self) -> None:
        self.url = os.getenv("BLUE_TEAM_URL", "")
        self.api_key = os.getenv("BLUE_TEAM_API_KEY", "")

    def score(self, genome: "FraudGenome") -> list[float]:
        if not self.url:
            raise RuntimeError("BLUE_TEAM_URL not set — use MockBlueTeam in sandbox mode")
        import httpx
        transactions = genome.to_transaction_list()
        if not transactions:
            return [0.5, 0.45, 0.55, 0.475]
        txn = transactions[0]
        try:
            resp = httpx.post(
                f"{self.url}/api/v1/score",
                json={
                    "transaction_id": f"rt_{genome.genome_id[:8]}",
                    "account_id": txn["from_account"],
                    "payee_account_id": txn["to_account"],
                    "amount": txn["amount"],
                    "channel": _RAIL_TO_CHANNEL.get(txn["payment_rail"], "NEFT"),
                    "timestamp": txn["timestamp"],
                },
                headers={"X-API-Key": self.api_key, "X-Sandbox": "true"},
                timeout=5.0,
            )
            resp.raise_for_status()
            base = float(resp.json().get("score", 0.5))
        except Exception as exc:
            logger.error("Blue Team score call failed: %s", exc)
            base = 0.5
        return [base, round(base * 0.9, 4), round(base * 1.1, 4), round(base * 0.95, 4)]

    def score_action(self, scores: list[float]) -> str:
        c = scores[0]
        if c >= _THRESHOLD_HIGH_RISK:
            return "HIGH_RISK"
        if c >= _THRESHOLD_REVIEW:
            return "REVIEW"
        if c >= _THRESHOLD_LOG:
            return "LOG"
        return "PASS"


def get_blue_team(account_fixtures: dict | None = None):
    """Select the Blue Team target for CRUCIBLE.

    Resolution order:
      1. CRUCIBLE_BLUE_TEAM=v2  → real TGIE Blue Team V2 engine (V2BlueTeam).
         Accepts aliases: "v2", "blue_team_v2", "real_v2".
      2. BLUE_TEAM_URL set       → legacy HTTP RealBlueTeam (union-bank API).
      3. default                 → frozen sandbox clone (MockBlueTeam).

    V2 ignores account_fixtures (it scores graph structure + amounts only);
    see agent_docs/sandbox_vs_production_divergences.md D-06. Default stays
    sandbox so the bypass DNAs and tests keep scoring against the clone.
    """
    engine = os.getenv("CRUCIBLE_BLUE_TEAM", "").strip().lower()
    if engine in ("v2", "blue_team_v2", "real_v2"):
        from red_team.sandbox.v2_target import V2BlueTeam
        return V2BlueTeam(account_fixtures=account_fixtures)
    if os.getenv("BLUE_TEAM_URL"):
        return RealBlueTeam()
    return MockBlueTeam(account_fixtures=account_fixtures)
