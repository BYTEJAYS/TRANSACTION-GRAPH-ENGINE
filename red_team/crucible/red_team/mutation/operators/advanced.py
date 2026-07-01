from __future__ import annotations
"""
Advanced operators derived from real Indian fraud case analysis.

5 operators targeting the 52-pattern taxonomy from operational intelligence:
  - MuleHubCreator      — hub-and-spoke with 30+ sources (Nizamabad ₹152Cr case)
  - CycleExtender       — extends 2-hop to 4-hop cycle to evade simple cycle gate
  - ThresholdFragmenter — splits amounts to ₹49K chunks below CTR threshold
  - GhostNodeInjector   — inserts a cash gap (ATM withdrawal → distant redeposit)
  - DormantActivator    — ages accounts 180+ days then simulates burst activation

These ops have higher base weights because they are grounded in confirmed real cases.
"""
import copy
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from red_team.core.genome import FraudGenome

# ── MuleHubCreator ─────────────────────────────────────────────────────────

_HUB_STATES = ["UP", "Bihar", "Gujarat", "Telangana", "Maharashtra", "Rajasthan", "MP", "Karnataka"]


def mule_hub_creator(genome: "FraudGenome") -> "FraudGenome":
    """
    Creates a hub-and-spoke topology: 30+ diverse sources → 1 hub → 1-3 sinks.
    Based on Nizamabad case: ₹152.18Cr, 46 accounts, 14 states.
    Keeps per-account amounts small (< ₹30K) to avoid spike detection.
    Blue Team bipartite gate fires at 5+ senders with density > 0.7 — but
    this is fan_in not bipartite, and the hub is the collector not a sink.
    """
    g = copy.deepcopy(genome)
    hub_width = random.randint(20, 46)
    per_account = random.uniform(10_000, 28_000)

    g.topology.type = "fan_in"
    g.topology.width = hub_width
    g.topology.collector_count = 1
    g.topology.depth = 2

    g.amounts.values = [round(per_account + random.uniform(-2000, 2000), 2) for _ in range(hub_width)]

    # Spacing: each source sends once per week — avoids velocity triggers
    g.timing.spacing_days = [7.0 + random.uniform(-1, 1) for _ in range(hub_width - 1)]
    g.timing.time_of_day = "business_hours"
    g.timing.low_slow = True

    # 200+ day accounts: bypass cash_mule_sink 180-day threshold
    g.accounts.source_ages_days = [random.randint(200, 545) for _ in range(hub_width + 1)]
    g.accounts.velocity_ratio = random.uniform(0.02, 0.06)
    g.accounts.cross_city = True
    g.accounts.geographic_spread = random.sample(_HUB_STATES, min(len(_HUB_STATES), random.randint(4, 8)))

    g.mutation_history.append("mule_hub_creator")
    g.flags.append("hub_spoke_topology")
    return g


# ── CycleExtender ──────────────────────────────────────────────────────────

def cycle_extender(genome: "FraudGenome") -> "FraudGenome":
    """
    Extends any cycle to 4+ hops so simple 2-hop cycle detection misses it.
    Blue Team's cycle gate fires on topology.type == "cycle" — we don't set
    that flag, instead we use a chain with the same source/sink account prefix
    to create a logical cycle invisible to the current gate.

    A→B→C→D and later D→A (separate genome) = structural cycle invisible to
    current implementation which only checks topology.type field.
    """
    g = copy.deepcopy(genome)

    # Force a deep chain topology — not "cycle" (which triggers the gate)
    g.topology.type = "chain"
    g.topology.depth = random.randint(4, 6)
    g.topology.width = 1

    # Spread timing across 5-8 days per hop (outside 24h velocity window)
    hop_spacing = [random.uniform(5.0, 8.0) for _ in range(g.topology.depth)]
    g.timing.spacing_days = hop_spacing
    g.timing.time_of_day = "business_hours"

    # Decrease amounts at each hop (laundering fee = ~3% per hop)
    first_amount = random.uniform(20_000, 80_000)
    g.amounts.values = [
        round(first_amount * (0.97 ** hop), 2)
        for hop in range(g.topology.depth)
    ]

    # All accounts aged >200 days
    g.accounts.source_ages_days = [random.randint(200, 400) for _ in range(g.topology.depth + 1)]
    g.accounts.velocity_ratio = random.uniform(0.05, 0.15)

    g.mutation_history.append("cycle_extender")
    g.flags.append("extended_cycle_chain")
    return g


# ── ThresholdFragmenter ────────────────────────────────────────────────────

_CTR_THRESHOLDS = [49_000, 99_500, 199_000]  # just under 50K, 1L, 2L reporting thresholds


def threshold_fragmenter(genome: "FraudGenome") -> "FraudGenome":
    """
    Fragments total amount into ₹49K chunks distributed across mules.
    Targets the ₹50K CTR (Cash Transaction Report) threshold gap.
    20 mules × ₹49K = ₹9.8L without triggering a single CTR.

    Blue Team's threshold_proximity flag fires within 5% of ₹50K, ₹2L, ₹10L.
    We target ₹49K which is 2% below ₹50K — just inside the 5% window.
    But we spread across many accounts so each account flags independently
    and the correlation requires graph analysis.
    """
    g = copy.deepcopy(genome)

    chunk = random.choice(_CTR_THRESHOLDS)
    total_target = random.uniform(200_000, 1_000_000)
    n_chunks = max(3, int(total_target / chunk))

    # Noisy chunks: each slightly different to avoid exact-match
    g.amounts.values = [
        round(chunk + random.uniform(-500, -50), 2)
        for _ in range(n_chunks)
    ]
    g.amounts.just_under_threshold = True
    g.amounts.noise_percent = random.uniform(0.005, 0.015)

    g.topology.type = "fan_in"
    g.topology.width = n_chunks
    g.topology.collector_count = 1
    g.topology.depth = 2

    # Each mule sends once — no velocity
    g.timing.spacing_days = [random.uniform(0.5, 2.0) for _ in range(n_chunks - 1)]
    g.timing.time_of_day = random.choice(["business_hours", "afternoon"])

    g.accounts.source_ages_days = [random.randint(200, 400) for _ in range(n_chunks + 1)]
    g.accounts.velocity_ratio = random.uniform(0.08, 0.15)

    g.mutation_history.append("threshold_fragmenter")
    g.flags.append("ctr_fragmentation")
    return g


# ── GhostNodeInjector ──────────────────────────────────────────────────────

_GHOST_DISTANCES_KM = [200, 350, 500, 700]  # ATM withdrawal to redeposit distance
_GHOST_CITY_PAIRS = [
    ("Mumbai", "Raipur"),
    ("Delhi", "Lucknow"),
    ("Hyderabad", "Bengaluru"),
    ("Chennai", "Coimbatore"),
    ("Kolkata", "Patna"),
]


def ghost_node_injector(genome: "FraudGenome") -> "FraudGenome":
    """
    Inserts a physical cash gap: digital outflow → ATM withdrawal → physical
    hand-off → ATM deposit 200-700km away → digital inflow.

    In the transaction graph, the cash gap appears as a disconnected edge.
    The ghost node has no digital identity — only the surrounding accounts are visible.

    The 4-hour window is realistic: Mumbai → Raipur by flight is ~2h, leaving
    time for ATM withdrawal + deposit at each end.

    Blue Team currently lacks a ghost_node_gate (this is a new attack surface).
    """
    g = copy.deepcopy(genome)

    distance_km = random.choice(_GHOST_DISTANCES_KM)
    city_pair = random.choice(_GHOST_CITY_PAIRS)
    gap_hours = max(3.5, distance_km / 200.0)  # realistic travel time

    # Cash amounts must be transportable: < ₹2L per carry (RBI reporting)
    cash_amount = random.uniform(50_000, 190_000)
    g.amounts.values = [cash_amount]

    # Very short chain: digital_out → [CASH GAP ~4hrs] → digital_in
    g.topology.type = "chain"
    g.topology.depth = 2
    g.topology.width = 1
    g.topology.collector_count = 1

    # The gap appears in timing as a very short spacing (physical travel)
    gap_days = gap_hours / 24.0
    g.timing.spacing_days = [gap_days]
    g.timing.time_of_day = "business_hours"

    # Large amount spike: single withdrawal then redeposit
    g.accounts.source_ages_days = [random.randint(200, 545), random.randint(200, 545)]
    g.accounts.velocity_ratio = 0.0  # no digital velocity — cash is untraceable
    g.accounts.cross_city = True
    g.accounts.geographic_spread = list(city_pair)

    # Mark the ghost node in special_nodes for human investigators
    g.special_nodes.cash_out_method = "atm_withdrawal_redeposit"
    g.special_nodes.cash_out_delay_days = int(gap_hours / 24.0)

    g.mutation_history.append("ghost_node_injector")
    g.flags.append("cash_gap_teleportation")
    g.flags.append(f"ghost_distance_{distance_km}km")
    return g


# ── DormantActivator ──────────────────────────────────────────────────────

def dormant_activator(genome: "FraudGenome") -> "FraudGenome":
    """
    Ages accounts 200+ days with <5 transactions (trust-building period),
    then simulates a burst activation on a specific date.

    Real pattern: accounts seasoned for 6 months transacting ₹500-5K/month,
    then suddenly used for ₹10L+ fraud on day 200+.

    Blue Team's dormancy detection looks at velocity_delta (burst_score).
    We evade by making the burst look like a salary/bonus receipt.
    """
    g = copy.deepcopy(genome)

    # Deep aging — well past the 180-day cash_mule_sink threshold
    min_age = random.randint(210, 545)
    n_accounts = genome.topology.width + genome.topology.collector_count + 1

    g.accounts.source_ages_days = [
        random.randint(min_age, min_age + 100)
        for _ in range(max(1, n_accounts))
    ]

    # Very low velocity (dormant period behavior)
    g.accounts.velocity_ratio = random.uniform(0.01, 0.04)

    # Add dormancy period in timing
    burst_after_txn = 0
    dormancy_days = random.randint(60, 150)
    g.timing.dormancy_periods = [
        {"after_txn": burst_after_txn, "duration_days": dormancy_days}
    ]
    g.timing.burst_behavior = True
    g.timing.low_slow = False  # burst is NOT slow

    # Large burst amounts to maximize fraud value after trust-building
    total_burst = random.uniform(200_000, 800_000)
    n_txns = random.randint(3, 8)
    g.amounts.values = [round(total_burst / n_txns, 2)] * n_txns

    # Disguise as salary/bonus patterns
    g.topology.mimics_legitimate = "employer_to_employees"

    g.mutation_history.append("dormant_activator")
    g.flags.append("dormant_burst_activation")
    g.flags.append(f"dormancy_period_{dormancy_days}d")
    return g
