from __future__ import annotations
"""
Attack Library — named fraud families the evolution engine draws from.

Each FraudFamily knows how to build a *base* (deliberately detectable) genome
and declares a `category` used by the weakness map / planner. Evolution then
mutates and combines these; difficulty scales them. The registry is designed to
grow to hundreds of templates — add a builder and append to FAMILIES.

Categories align with the investigator weakness report:
  graph_structure | velocity | cash | merchant | crypto | cross_border |
  round_robin | behavior_drift | synthetic_identity | dormant | layering |
  smurfing | mule
"""
import random
from dataclasses import dataclass
from typing import Callable

from red_team.core.genome import (
    AccountsGene,
    AmountsGene,
    ChannelsGene,
    FraudGenome,
    SpecialNodesGene,
    TimingGene,
    TopologyGene,
)

Builder = Callable[[random.Random], FraudGenome]


@dataclass(frozen=True)
class FraudFamily:
    name: str
    category: str
    description: str
    build: Builder


def _genome(
    lineage_id: str,
    *,
    topo: str,
    depth: int,
    width: int,
    collectors: int,
    amounts: list[int],
    spacing: list[float],
    tod: str = "business_hours",
    ages: list[int],
    velocity: float = 0.5,
    channels: dict,
    festival: dict | None = None,
    merchant: dict | None = None,
    abandoned: dict | None = None,
    exchange: dict | None = None,
    bridge: dict | None = None,
    cash_out: str | None = None,
    cash_out_delay: int = 0,
    cross_city: bool = False,
    geo: list[str] | None = None,
    low_slow: bool = False,
    dormancy: list[dict] | None = None,
    mimics: str | None = None,
    device_diversity: bool = False,
    ip_diversity: bool = False,
    kyc_tier: str = "full",
    channel_sequence: list[str] | None = None,
) -> FraudGenome:
    sn = SpecialNodesGene(
        merchant_nodes=merchant or {"count": 0},
        abandoned_nodes=abandoned or {"count": 0, "dormancy_days": 60, "purpose": ""},
        bridge_nodes=bridge or {"count": 0, "hold_days": 1, "partial_forward": False},
        exchange_nodes=exchange or {"count": 0, "type": "crypto", "launder_rounds": 1},
        cash_out_method=cash_out,
        cash_out_delay_days=cash_out_delay,
    )
    return FraudGenome(
        lineage_id=lineage_id,
        topology=TopologyGene(
            type=topo, depth=depth, width=width, collector_count=collectors,
            mimics_legitimate=mimics,
        ),
        timing=TimingGene(
            spacing_days=spacing, time_of_day=tod, festival_timing=festival,
            festival_name=(festival or {}).get("name") if festival else None,
            low_slow=low_slow, dormancy_periods=dormancy or [],
        ),
        amounts=AmountsGene(values=[int(a) for a in amounts]),
        channels=ChannelsGene(mix=channels, channel_sequence=channel_sequence or [],
                              channel_hop=bool(channel_sequence)),
        accounts=AccountsGene(
            source_ages_days=ages, velocity_ratio=velocity, kyc_tier=kyc_tier,
            cross_city=cross_city, geographic_spread=geo or [],
            device_diversity=device_diversity, ip_diversity=ip_diversity,
        ),
        special_nodes=sn,
    )


# ── family builders ───────────────────────────────────────────────────────────

def _cash_smurfing(r: random.Random) -> FraudGenome:
    w = r.randint(5, 9)
    return _genome("cash_smurfing", topo="fan_in", depth=3, width=w, collectors=1,
                   amounts=[r.randint(45_000, 49_900) for _ in range(w)],
                   spacing=[0.3] * w, ages=[r.randint(30, 120) for _ in range(w)],
                   velocity=0.7, channels={"ach_transfer": 1.0}, cash_out="atm")


def _fan_out_burst(r: random.Random) -> FraudGenome:
    w = r.randint(5, 10)
    return _genome("fan_out_burst", topo="fan_out", depth=2, width=w, collectors=0,
                   amounts=[r.randint(8_000, 12_000) for _ in range(w)],
                   spacing=[0.05] * w, ages=[r.randint(60, 180)], velocity=0.8,
                   channels={"p2p_transfer": 1.0})


def _round_robin(r: random.Random) -> FraudGenome:
    d = r.randint(3, 6)
    base = r.randint(80_000, 200_000)
    return _genome("round_robin", topo="cycle", depth=d, width=1, collectors=1,
                   amounts=[int(base * (0.99 ** i)) for i in range(d)],
                   spacing=[0.5] * d, ages=[r.randint(100, 250) for _ in range(d)],
                   velocity=0.5, channels={"internal_transfer": 1.0})


def _velocity_burst(r: random.Random) -> FraudGenome:
    w = r.randint(8, 14)
    return _genome("velocity_burst", topo="fan_out", depth=2, width=w, collectors=0,
                   amounts=[r.randint(2_000, 6_000) for _ in range(w)],
                   spacing=[0.01] * w, ages=[r.randint(20, 90)], velocity=0.95,
                   channels={"p2p_transfer": 1.0})


def _merchant_laundering(r: random.Random) -> FraudGenome:
    w = r.randint(4, 7)
    return _genome("merchant_laundering", topo="bipartite", depth=2, width=w, collectors=1,
                   amounts=[r.randint(6_000, 14_000) for _ in range(w)],
                   spacing=[1.0] * w, ages=[r.randint(200, 400) for _ in range(w)],
                   velocity=0.3, channels={"ach_transfer": 1.0},
                   merchant={"count": 1, "mcc_codes": [5045, 5912], "invoice_pattern": True},
                   mimics="business_invoice_settlement")


def _salary_camouflage(r: random.Random) -> FraudGenome:
    w = r.randint(5, 9)
    return _genome("salary_camouflage", topo="fan_out", depth=2, width=w, collectors=0,
                   amounts=[r.randint(28_000, 45_000) for _ in range(w)],
                   spacing=[30.0] * w, tod="morning",
                   ages=[r.randint(300, 500)], velocity=0.2,
                   channels={"ach_transfer": 1.0}, mimics="payroll_disbursement")


def _synthetic_identity(r: random.Random) -> FraudGenome:
    w = r.randint(4, 8)
    return _genome("synthetic_identity", topo="fan_in", depth=2, width=w, collectors=1,
                   amounts=[r.randint(20_000, 40_000) for _ in range(w)],
                   spacing=[0.5] * w, ages=[r.randint(5, 25) for _ in range(w)],
                   velocity=0.6, channels={"p2p_transfer": 0.6, "ach_transfer": 0.4})


def _dormant_abuse(r: random.Random) -> FraudGenome:
    return _genome("dormant_abuse", topo="chain", depth=3, width=1, collectors=1,
                   amounts=[r.randint(60_000, 120_000) for _ in range(3)],
                   spacing=[45.0, 1.0], tod="night", ages=[r.randint(400, 800)],
                   velocity=0.05, channels={"ach_transfer": 1.0}, low_slow=True,
                   abandoned={"count": 1, "dormancy_days": r.randint(90, 200), "purpose": "reactivated"},
                   dormancy=[{"after_txn": 1, "duration_days": r.randint(90, 200)}])


def _mule_network(r: random.Random) -> FraudGenome:
    w = r.randint(6, 12)
    return _genome("mule_network", topo="fan_in", depth=4, width=w, collectors=2,
                   amounts=[r.randint(18_000, 35_000) for _ in range(w)],
                   spacing=[0.8] * w, ages=[r.randint(40, 150) for _ in range(w)],
                   velocity=0.6, channels={"ach_transfer": 0.5, "p2p_transfer": 0.5},
                   cash_out="crypto")


def _cross_bank_layering(r: random.Random) -> FraudGenome:
    d = r.randint(4, 7)
    base = r.randint(150_000, 400_000)
    return _genome("cross_bank_layering", topo="chain", depth=d, width=1, collectors=1,
                   amounts=[int(base * (0.97 ** i)) for i in range(d)],
                   spacing=[0.5] * (d - 1), ages=[r.randint(150, 350) for _ in range(d)],
                   velocity=0.4, channels={"wire_transfer": 0.5, "ach_transfer": 0.5},
                   cross_city=True, geo=["MH", "DL", "KA", "TN"][:max(2, d - 2)])


def _cross_border_layering(r: random.Random) -> FraudGenome:
    d = r.randint(4, 6)
    base = r.randint(200_000, 500_000)
    return _genome("cross_border_layering", topo="chain", depth=d, width=1, collectors=1,
                   amounts=[int(base * (0.96 ** i)) for i in range(d)],
                   spacing=[1.0] * (d - 1), ages=[r.randint(180, 400) for _ in range(d)],
                   velocity=0.3, channels={"wire_transfer": 0.7, "crypto_exchange": 0.3},
                   cross_city=True, geo=["MH", "AE", "SG", "HK"],
                   exchange={"count": 1, "type": "crypto", "launder_rounds": 2},
                   cash_out="crypto")


def _atm_burst(r: random.Random) -> FraudGenome:
    w = r.randint(5, 9)
    return _genome("atm_burst", topo="fan_in", depth=2, width=w, collectors=1,
                   amounts=[r.randint(9_000, 20_000) for _ in range(w)],
                   spacing=[0.1] * w, ages=[r.randint(50, 150) for _ in range(w)],
                   velocity=0.85, channels={"ach_transfer": 0.2, "atm_withdrawal": 0.8},
                   cash_out="atm")


def _upi_burst(r: random.Random) -> FraudGenome:
    w = r.randint(8, 15)
    return _genome("upi_burst", topo="fan_out", depth=2, width=w, collectors=0,
                   amounts=[r.randint(3_000, 9_000) for _ in range(w)],
                   spacing=[0.02] * w, ages=[r.randint(30, 120)], velocity=0.9,
                   channels={"p2p_transfer": 1.0})


def _micro_flood(r: random.Random) -> FraudGenome:
    w = r.randint(12, 20)
    return _genome("micro_transaction_flood", topo="fan_in", depth=2, width=w, collectors=1,
                   amounts=[r.randint(500, 2_500) for _ in range(w)],
                   spacing=[0.05] * w, ages=[r.randint(20, 100) for _ in range(w)],
                   velocity=0.9, channels={"p2p_transfer": 1.0})


def _crypto_exit(r: random.Random) -> FraudGenome:
    d = r.randint(3, 5)
    base = r.randint(120_000, 350_000)
    return _genome("crypto_exit", topo="chain", depth=d, width=1, collectors=1,
                   amounts=[int(base * (0.95 ** i)) for i in range(d)],
                   spacing=[0.3] * (d - 1), ages=[r.randint(60, 200) for _ in range(d)],
                   velocity=0.5, channels={"crypto_exchange": 0.6, "p2p_transfer": 0.4},
                   exchange={"count": 1, "type": "crypto", "launder_rounds": 3},
                   cash_out="crypto")


def _hub_and_spoke(r: random.Random) -> FraudGenome:
    w = r.randint(6, 10)
    return _genome("hub_and_spoke", topo="fan_in", depth=3, width=w, collectors=1,
                   amounts=[r.randint(15_000, 30_000) for _ in range(w)],
                   spacing=[0.4] * w, ages=[r.randint(80, 200) for _ in range(w)],
                   velocity=0.6, channels={"ach_transfer": 1.0}, cash_out="atm")


def _bridge_relay(r: random.Random) -> FraudGenome:
    d = r.randint(4, 6)
    base = r.randint(90_000, 220_000)
    return _genome("bridge_relay", topo="chain", depth=d, width=1, collectors=1,
                   amounts=[int(base * (0.98 ** i)) for i in range(d)],
                   spacing=[0.6] * (d - 1), ages=[r.randint(120, 300) for _ in range(d)],
                   velocity=0.45, channels={"internal_transfer": 0.5, "ach_transfer": 0.5},
                   bridge={"count": 1, "hold_days": 1, "partial_forward": True})


def _nested_rings(r: random.Random) -> FraudGenome:
    d = r.randint(4, 7)
    base = r.randint(100_000, 260_000)
    return _genome("nested_rings", topo="cycle", depth=d, width=2, collectors=1,
                   amounts=[int(base * (0.985 ** i)) for i in range(d)],
                   spacing=[0.7] * d, ages=[r.randint(120, 280) for _ in range(d)],
                   velocity=0.5, channels={"internal_transfer": 0.6, "p2p_transfer": 0.4})


# ── expanded family set (toward the full named taxonomy) ──────────────────────

def _cash_deposit_splitting(r: random.Random) -> FraudGenome:
    w = r.randint(6, 11)
    return _genome("cash_deposit_splitting", topo="fan_in", depth=2, width=w, collectors=1,
                   amounts=[r.randint(18_000, 24_900) for _ in range(w)],
                   spacing=[0.2] * w, ages=[r.randint(40, 130) for _ in range(w)],
                   velocity=0.7, channels={"atm_withdrawal": 0.0, "ach_transfer": 1.0},
                   cash_out="atm")


def _high_value_burst(r: random.Random) -> FraudGenome:
    w = r.randint(3, 5)
    return _genome("high_value_burst", topo="fan_out", depth=2, width=w, collectors=0,
                   amounts=[r.randint(300_000, 900_000) for _ in range(w)],
                   spacing=[0.02] * w, ages=[r.randint(80, 220)], velocity=0.7,
                   channels={"wire_transfer": 1.0})


def _low_value_burst(r: random.Random) -> FraudGenome:
    w = r.randint(12, 20)
    return _genome("low_value_burst", topo="fan_out", depth=2, width=w, collectors=0,
                   amounts=[r.randint(1_000, 4_000) for _ in range(w)],
                   spacing=[0.01] * w, ages=[r.randint(30, 120)], velocity=0.95,
                   channels={"p2p_transfer": 1.0})


def _refund_fraud(r: random.Random) -> FraudGenome:
    w = r.randint(3, 6)
    return _genome("refund_fraud", topo="bipartite", depth=2, width=w, collectors=1,
                   amounts=[r.randint(5_000, 18_000) for _ in range(w)],
                   spacing=[2.0] * w, ages=[r.randint(150, 350) for _ in range(w)],
                   velocity=0.25, channels={"debit_purchase": 0.5, "p2p_transfer": 0.5},
                   merchant={"count": 1, "mcc_codes": [5999], "invoice_pattern": True},
                   mimics="merchant_refund_reversal")


def _loan_fraud(r: random.Random) -> FraudGenome:
    d = r.randint(3, 5)
    base = r.randint(200_000, 600_000)
    return _genome("loan_fraud", topo="chain", depth=d, width=1, collectors=1,
                   amounts=[int(base * (0.9 ** i)) for i in range(d)],
                   spacing=[7.0] * (d - 1), ages=[r.randint(20, 90) for _ in range(d)],
                   velocity=0.3, channels={"ach_transfer": 1.0},
                   mimics="loan_disbursement")


def _account_takeover(r: random.Random) -> FraudGenome:
    w = r.randint(3, 6)
    return _genome("account_takeover", topo="fan_out", depth=2, width=w, collectors=0,
                   amounts=[r.randint(40_000, 120_000) for _ in range(w)], tod="night",
                   spacing=[0.01] * w, ages=[r.randint(500, 1200)], velocity=0.95,
                   channels={"p2p_transfer": 0.6, "wire_transfer": 0.4},
                   device_diversity=True, ip_diversity=True, cash_out="crypto")


def _wallet_abuse(r: random.Random) -> FraudGenome:
    w = r.randint(6, 12)
    return _genome("wallet_abuse", topo="fan_in", depth=2, width=w, collectors=1,
                   amounts=[r.randint(2_000, 9_000) for _ in range(w)],
                   spacing=[0.05] * w, ages=[r.randint(15, 80) for _ in range(w)],
                   velocity=0.85, channels={"p2p_transfer": 0.7, "bill_payment": 0.3},
                   kyc_tier="min")


def _gift_card_laundering(r: random.Random) -> FraudGenome:
    w = r.randint(5, 9)
    return _genome("gift_card_laundering", topo="bipartite", depth=2, width=w, collectors=1,
                   amounts=[r.randint(5_000, 10_000) for _ in range(w)],
                   spacing=[0.5] * w, ages=[r.randint(60, 180) for _ in range(w)],
                   velocity=0.5, channels={"debit_purchase": 1.0},
                   merchant={"count": 1, "mcc_codes": [5947], "invoice_pattern": False},
                   cash_out="gift_card")


def _qr_merchant_abuse(r: random.Random) -> FraudGenome:
    w = r.randint(8, 14)
    return _genome("qr_merchant_abuse", topo="fan_in", depth=2, width=w, collectors=1,
                   amounts=[r.randint(1_500, 6_000) for _ in range(w)],
                   spacing=[0.03] * w, ages=[r.randint(90, 220) for _ in range(w)],
                   velocity=0.8, channels={"p2p_transfer": 1.0},
                   merchant={"count": 1, "mcc_codes": [5499], "invoice_pattern": False},
                   mimics="qr_merchant_collection")


def _rtgs_layering(r: random.Random) -> FraudGenome:
    d = r.randint(4, 7)
    base = r.randint(500_000, 2_000_000)
    return _genome("rtgs_layering", topo="chain", depth=d, width=1, collectors=1,
                   amounts=[int(base * (0.98 ** i)) for i in range(d)],
                   spacing=[0.2] * (d - 1), ages=[r.randint(150, 350) for _ in range(d)],
                   velocity=0.4, channels={"wire_transfer": 1.0}, cross_city=True)


def _cheque_bounce_laundering(r: random.Random) -> FraudGenome:
    d = r.randint(3, 5)
    base = r.randint(80_000, 250_000)
    return _genome("cheque_bounce_laundering", topo="chain", depth=d, width=1, collectors=1,
                   amounts=[int(base * (0.95 ** i)) for i in range(d)],
                   spacing=[3.0] * (d - 1), ages=[r.randint(120, 300) for _ in range(d)],
                   velocity=0.3, channels={"ach_transfer": 1.0}, mimics="cheque_clearing")


def _insurance_fraud(r: random.Random) -> FraudGenome:
    w = r.randint(3, 6)
    return _genome("insurance_fraud", topo="fan_out", depth=2, width=w, collectors=0,
                   amounts=[r.randint(50_000, 200_000) for _ in range(w)],
                   spacing=[5.0] * w, ages=[r.randint(200, 500)], velocity=0.2,
                   channels={"ach_transfer": 1.0}, mimics="insurance_claim_payout")


def _trade_finance_fraud(r: random.Random) -> FraudGenome:
    d = r.randint(3, 5)
    base = r.randint(800_000, 5_000_000)
    return _genome("trade_finance_fraud", topo="chain", depth=d, width=1, collectors=1,
                   amounts=[int(base * (0.97 ** i)) for i in range(d)],
                   spacing=[10.0] * (d - 1), ages=[r.randint(300, 700) for _ in range(d)],
                   velocity=0.15, channels={"wire_transfer": 1.0}, cross_city=True,
                   geo=["MH", "AE", "SG"], mimics="trade_invoice_settlement")


def _invoice_fraud(r: random.Random) -> FraudGenome:
    w = r.randint(4, 7)
    return _genome("invoice_fraud", topo="bipartite", depth=2, width=w, collectors=1,
                   amounts=[r.randint(20_000, 80_000) for _ in range(w)],
                   spacing=[4.0] * w, ages=[r.randint(200, 450) for _ in range(w)],
                   velocity=0.2, channels={"ach_transfer": 1.0},
                   merchant={"count": 1, "mcc_codes": [5045], "invoice_pattern": True},
                   mimics="vendor_invoice")


def _invoice_layering(r: random.Random) -> FraudGenome:
    d = r.randint(4, 6)
    base = r.randint(150_000, 500_000)
    return _genome("invoice_layering", topo="chain", depth=d, width=1, collectors=1,
                   amounts=[int(base * (0.96 ** i)) for i in range(d)],
                   spacing=[6.0] * (d - 1), ages=[r.randint(180, 400) for _ in range(d)],
                   velocity=0.2, channels={"ach_transfer": 0.6, "wire_transfer": 0.4},
                   merchant={"count": 2, "mcc_codes": [5045, 7399], "invoice_pattern": True},
                   mimics="layered_vendor_invoices")


def _payroll_fraud(r: random.Random) -> FraudGenome:
    w = r.randint(8, 16)
    return _genome("payroll_fraud", topo="fan_out", depth=2, width=w, collectors=0,
                   amounts=[r.randint(25_000, 55_000) for _ in range(w)],
                   spacing=[30.0] * w, tod="morning", ages=[r.randint(300, 600)],
                   velocity=0.15, channels={"ach_transfer": 1.0}, mimics="payroll_run")


def _ghost_merchant(r: random.Random) -> FraudGenome:
    w = r.randint(6, 12)
    return _genome("ghost_merchant", topo="fan_in", depth=2, width=w, collectors=1,
                   amounts=[r.randint(3_000, 12_000) for _ in range(w)],
                   spacing=[0.4] * w, ages=[r.randint(10, 40) for _ in range(w)],
                   velocity=0.6, channels={"debit_purchase": 1.0},
                   merchant={"count": 1, "mcc_codes": [5999], "invoice_pattern": False},
                   kyc_tier="basic")


def _beneficiary_rotation(r: random.Random) -> FraudGenome:
    w = r.randint(6, 12)
    return _genome("beneficiary_rotation", topo="fan_out", depth=2, width=w, collectors=0,
                   amounts=[r.randint(15_000, 45_000) for _ in range(w)],
                   spacing=[0.3] * w, ages=[r.randint(8, 30) for _ in range(w)],
                   velocity=0.7, channels={"p2p_transfer": 0.5, "ach_transfer": 0.5})


def _device_rotation(r: random.Random) -> FraudGenome:
    w = r.randint(5, 10)
    return _genome("device_rotation", topo="fan_out", depth=2, width=w, collectors=0,
                   amounts=[r.randint(20_000, 60_000) for _ in range(w)],
                   spacing=[0.1] * w, ages=[r.randint(60, 200)], velocity=0.8,
                   channels={"p2p_transfer": 1.0}, device_diversity=True)


def _ip_rotation(r: random.Random) -> FraudGenome:
    w = r.randint(5, 10)
    return _genome("ip_rotation", topo="fan_out", depth=2, width=w, collectors=0,
                   amounts=[r.randint(20_000, 60_000) for _ in range(w)],
                   spacing=[0.1] * w, ages=[r.randint(60, 200)], velocity=0.8,
                   channels={"p2p_transfer": 1.0}, ip_diversity=True, cross_city=True,
                   geo=["MH", "DL", "KA", "TN", "WB"])


def _sim_swap(r: random.Random) -> FraudGenome:
    w = r.randint(2, 5)
    return _genome("sim_swap", topo="fan_out", depth=2, width=w, collectors=0,
                   amounts=[r.randint(80_000, 300_000) for _ in range(w)], tod="night",
                   spacing=[0.005] * w, ages=[r.randint(600, 1500)], velocity=0.98,
                   channels={"p2p_transfer": 0.5, "wire_transfer": 0.5},
                   device_diversity=True, ip_diversity=True, cash_out="crypto")


def _session_hijack(r: random.Random) -> FraudGenome:
    w = r.randint(3, 6)
    return _genome("session_hijack", topo="fan_out", depth=2, width=w, collectors=0,
                   amounts=[r.randint(50_000, 150_000) for _ in range(w)],
                   spacing=[0.003] * w, ages=[r.randint(400, 1000)], velocity=0.99,
                   channels={"p2p_transfer": 1.0}, ip_diversity=True)


def _graph_fragmentation(r: random.Random) -> FraudGenome:
    w = r.randint(4, 8)
    return _genome("graph_fragmentation", topo="bipartite", depth=2, width=w, collectors=2,
                   amounts=[r.randint(10_000, 25_000) for _ in range(w)],
                   spacing=[1.5] * w, ages=[r.randint(100, 250) for _ in range(w)],
                   velocity=0.4, channels={"ach_transfer": 0.5, "p2p_transfer": 0.5})


def _decoy_transactions(r: random.Random) -> FraudGenome:
    w = r.randint(6, 10)
    return _genome("decoy_transactions", topo="fan_in", depth=3, width=w, collectors=1,
                   amounts=[r.randint(5_000, 30_000) for _ in range(w)],
                   spacing=[1.0] * w, ages=[r.randint(150, 350) for _ in range(w)],
                   velocity=0.3, channels={"ach_transfer": 0.4, "p2p_transfer": 0.3,
                                           "bill_payment": 0.3}, mimics="mixed_legitimate")


def _hidden_core_network(r: random.Random) -> FraudGenome:
    d = r.randint(4, 6)
    base = r.randint(120_000, 300_000)
    return _genome("hidden_core_network", topo="cycle", depth=d, width=2, collectors=1,
                   amounts=[int(base * (0.99 ** i)) for i in range(d)],
                   spacing=[1.0] * d, ages=[r.randint(200, 400) for _ in range(d)],
                   velocity=0.3, channels={"internal_transfer": 0.7, "ach_transfer": 0.3},
                   bridge={"count": 1, "hold_days": 2, "partial_forward": True})


def _multi_hop_laundering(r: random.Random) -> FraudGenome:
    d = r.randint(5, 8)
    base = r.randint(150_000, 400_000)
    return _genome("multi_hop_laundering", topo="chain", depth=d, width=1, collectors=1,
                   amounts=[int(base * (0.97 ** i)) for i in range(d)],
                   spacing=[0.8] * (d - 1), ages=[r.randint(100, 300) for _ in range(d)],
                   velocity=0.4, channels={"ach_transfer": 0.4, "p2p_transfer": 0.3,
                                           "wire_transfer": 0.3})


def _star_graph(r: random.Random) -> FraudGenome:
    w = r.randint(6, 12)
    return _genome("star_graph", topo="fan_out", depth=2, width=w, collectors=0,
                   amounts=[r.randint(10_000, 30_000) for _ in range(w)],
                   spacing=[0.2] * w, ages=[r.randint(80, 220)], velocity=0.6,
                   channels={"ach_transfer": 1.0})


def _tree_graph(r: random.Random) -> FraudGenome:
    w = r.randint(6, 10)
    return _genome("tree_graph", topo="fan_out", depth=3, width=w, collectors=0,
                   amounts=[r.randint(8_000, 25_000) for _ in range(w)],
                   spacing=[0.5] * w, ages=[r.randint(100, 250)], velocity=0.5,
                   channels={"ach_transfer": 0.6, "p2p_transfer": 0.4})


def _mesh_graph(r: random.Random) -> FraudGenome:
    d = r.randint(4, 6)
    base = r.randint(60_000, 180_000)
    return _genome("mesh_graph", topo="cycle", depth=d, width=3, collectors=2,
                   amounts=[int(base * (0.98 ** i)) for i in range(d)],
                   spacing=[0.6] * d, ages=[r.randint(120, 280) for _ in range(d)],
                   velocity=0.5, channels={"internal_transfer": 0.5, "p2p_transfer": 0.5})


def _diamond_graph(r: random.Random) -> FraudGenome:
    w = r.randint(4, 6)
    return _genome("diamond_graph", topo="bipartite", depth=3, width=w, collectors=1,
                   amounts=[r.randint(20_000, 50_000) for _ in range(w)],
                   spacing=[0.7] * w, ages=[r.randint(120, 280) for _ in range(w)],
                   velocity=0.45, channels={"ach_transfer": 1.0})


def _snowflake_graph(r: random.Random) -> FraudGenome:
    w = r.randint(8, 14)
    return _genome("snowflake_graph", topo="fan_out", depth=3, width=w, collectors=0,
                   amounts=[r.randint(5_000, 18_000) for _ in range(w)],
                   spacing=[0.3] * w, ages=[r.randint(60, 200)], velocity=0.6,
                   channels={"p2p_transfer": 0.7, "ach_transfer": 0.3})


def _recursive_rings(r: random.Random) -> FraudGenome:
    d = r.randint(5, 8)
    base = r.randint(90_000, 220_000)
    return _genome("recursive_rings", topo="cycle", depth=d, width=2, collectors=1,
                   amounts=[int(base * (0.99 ** i)) for i in range(d)],
                   spacing=[0.5] * d, ages=[r.randint(150, 320) for _ in range(d)],
                   velocity=0.4, channels={"internal_transfer": 1.0})


def _time_delayed_rings(r: random.Random) -> FraudGenome:
    d = r.randint(4, 6)
    base = r.randint(100_000, 260_000)
    return _genome("time_delayed_rings", topo="cycle", depth=d, width=1, collectors=1,
                   amounts=[int(base * (0.99 ** i)) for i in range(d)],
                   spacing=[20.0] * d, ages=[r.randint(250, 500) for _ in range(d)],
                   velocity=0.1, channels={"ach_transfer": 1.0}, low_slow=True)


def _circular_transfers(r: random.Random) -> FraudGenome:
    d = r.randint(3, 5)
    base = r.randint(70_000, 180_000)
    return _genome("circular_transfers", topo="cycle", depth=d, width=1, collectors=1,
                   amounts=[int(base * (0.97 ** i)) for i in range(d)],
                   spacing=[1.0] * d, ages=[r.randint(120, 260) for _ in range(d)],
                   velocity=0.5, channels={"p2p_transfer": 1.0})


FAMILIES: dict[str, FraudFamily] = {
    f.name: f for f in [
        FraudFamily("cash_smurfing", "smurfing", "Many sub-threshold deposits → one collector → cash", _cash_smurfing),
        FraudFamily("fan_out_burst", "graph_structure", "One source sprays many destinations fast", _fan_out_burst),
        FraudFamily("round_robin", "round_robin", "Funds cycle back to origin", _round_robin),
        FraudFamily("velocity_burst", "velocity", "High transaction rate in a tiny window", _velocity_burst),
        FraudFamily("merchant_laundering", "merchant", "Fake invoice settlement via merchant node", _merchant_laundering),
        FraudFamily("salary_camouflage", "behavior_drift", "Disbursement disguised as monthly payroll", _salary_camouflage),
        FraudFamily("synthetic_identity", "synthetic_identity", "Freshly-minted coordinated account ring", _synthetic_identity),
        FraudFamily("dormant_abuse", "dormant", "Long-dormant account reactivated to relay", _dormant_abuse),
        FraudFamily("mule_network", "mule", "Deep mule fan-in with crypto exit", _mule_network),
        FraudFamily("cross_bank_layering", "layering", "Multi-bank hop chain, geographic spread", _cross_bank_layering),
        FraudFamily("cross_border_layering", "cross_border", "Cross-border wire + crypto layering", _cross_border_layering),
        FraudFamily("atm_burst", "cash", "Rapid ATM cash-out fan-in", _atm_burst),
        FraudFamily("upi_burst", "velocity", "UPI rapid-fire fan-out", _upi_burst),
        FraudFamily("micro_transaction_flood", "smurfing", "Flood of tiny transfers", _micro_flood),
        FraudFamily("crypto_exit", "crypto", "Layer then exit through a crypto exchange", _crypto_exit),
        FraudFamily("hub_and_spoke", "graph_structure", "Classic hub-and-spoke collection", _hub_and_spoke),
        FraudFamily("bridge_relay", "graph_structure", "Single bridge node relays between clusters", _bridge_relay),
        FraudFamily("nested_rings", "round_robin", "Overlapping cycles (nested rings)", _nested_rings),
        # ── expanded taxonomy ──
        FraudFamily("cash_deposit_splitting", "smurfing", "Split cash deposits below CTR threshold", _cash_deposit_splitting),
        FraudFamily("high_value_burst", "velocity", "Few very large transfers in seconds", _high_value_burst),
        FraudFamily("low_value_burst", "velocity", "Flood of small transfers in seconds", _low_value_burst),
        FraudFamily("refund_fraud", "merchant", "Fake merchant refunds/reversals", _refund_fraud),
        FraudFamily("loan_fraud", "layering", "Disbursed loan laundered through hops", _loan_fraud),
        FraudFamily("account_takeover", "account_takeover", "Hijacked old account drained at night, new device/IP", _account_takeover),
        FraudFamily("wallet_abuse", "wallet", "Min-KYC wallet aggregation", _wallet_abuse),
        FraudFamily("gift_card_laundering", "cash", "Convert funds to gift cards", _gift_card_laundering),
        FraudFamily("qr_merchant_abuse", "merchant", "QR static-merchant collection abuse", _qr_merchant_abuse),
        FraudFamily("rtgs_layering", "layering", "High-value RTGS hop chain", _rtgs_layering),
        FraudFamily("cheque_bounce_laundering", "layering", "Cheque-clearing float laundering", _cheque_bounce_laundering),
        FraudFamily("insurance_fraud", "insurance", "Fake insurance claim payouts", _insurance_fraud),
        FraudFamily("trade_finance_fraud", "trade_finance", "Over/under-invoiced cross-border trade", _trade_finance_fraud),
        FraudFamily("invoice_fraud", "merchant", "Fake vendor invoice settlement", _invoice_fraud),
        FraudFamily("invoice_layering", "layering", "Layered fake invoices across vendors", _invoice_layering),
        FraudFamily("payroll_fraud", "behavior_drift", "Ghost-employee payroll run", _payroll_fraud),
        FraudFamily("ghost_merchant", "merchant", "Freshly-minted shell merchant collection", _ghost_merchant),
        FraudFamily("beneficiary_rotation", "behavior_drift", "Constantly rotating fresh payees", _beneficiary_rotation),
        FraudFamily("device_rotation", "account_takeover", "Same actor, many devices", _device_rotation),
        FraudFamily("ip_rotation", "account_takeover", "Same actor, many IPs/cities", _ip_rotation),
        FraudFamily("sim_swap", "account_takeover", "SIM-swap takeover, instant night drain", _sim_swap),
        FraudFamily("session_hijack", "account_takeover", "Hijacked session, sub-second drain", _session_hijack),
        FraudFamily("graph_fragmentation", "graph_structure", "Split flow across disjoint collectors", _graph_fragmentation),
        FraudFamily("decoy_transactions", "behavior_drift", "Bury fraud edges in decoy legit-looking ones", _decoy_transactions),
        FraudFamily("hidden_core_network", "graph_structure", "Dense hidden core behind a bridge", _hidden_core_network),
        FraudFamily("multi_hop_laundering", "layering", "Long mixed-rail hop chain", _multi_hop_laundering),
        FraudFamily("star_graph", "graph_structure", "Star (single hub) topology", _star_graph),
        FraudFamily("tree_graph", "graph_structure", "Hierarchical tree distribution", _tree_graph),
        FraudFamily("mesh_graph", "graph_structure", "Densely interconnected mesh", _mesh_graph),
        FraudFamily("diamond_graph", "graph_structure", "Converge-then-diverge diamond", _diamond_graph),
        FraudFamily("snowflake_graph", "graph_structure", "Recursive fan-out snowflake", _snowflake_graph),
        FraudFamily("recursive_rings", "round_robin", "Rings within rings", _recursive_rings),
        FraudFamily("time_delayed_rings", "round_robin", "Slow ring over weeks", _time_delayed_rings),
        FraudFamily("circular_transfers", "round_robin", "Simple closed-loop transfers", _circular_transfers),
    ]
}

CATEGORIES = sorted({f.category for f in FAMILIES.values()})


def get_family(name: str) -> FraudFamily:
    if name not in FAMILIES:
        raise KeyError(f"Unknown attack family: {name!r}. Known: {sorted(FAMILIES)}")
    return FAMILIES[name]


def families_in_category(category: str) -> list[FraudFamily]:
    return [f for f in FAMILIES.values() if f.category == category]


def sample_family(rng: random.Random, category: str | None = None) -> FraudFamily:
    pool = families_in_category(category) if category else list(FAMILIES.values())
    if not pool:
        pool = list(FAMILIES.values())
    return rng.choice(pool)
