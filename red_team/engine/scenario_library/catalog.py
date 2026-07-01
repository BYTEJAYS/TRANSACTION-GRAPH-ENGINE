"""
Scenario catalog.

A curated, expandable repository of synthetic fraud scenarios spanning three
complexity tiers. Each entry is a :class:`ScenarioSpec` carrying a description,
objectives, ground-truth risk indicators, expected research outcomes, and the
parameters the :class:`FraudSimulator` uses to materialise it.

Adding a scenario is intentionally trivial: append a ``ScenarioSpec`` to
``_SCENARIOS``. Nothing else in the platform needs to change.
"""

from __future__ import annotations

from typing import Dict, List

from red_team.core.models import (
    ComplexityLevel,
    FraudCategory,
    RiskIndicator,
    ScenarioSpec,
)


def _ri(name: str, desc: str, sev: ComplexityLevel = ComplexityLevel.BEGINNER) -> RiskIndicator:
    return RiskIndicator(name=name, description=desc, severity=sev)


_SCENARIOS: List[ScenarioSpec] = [
    # ── Beginner ──────────────────────────────────────────────────────────────
    ScenarioSpec(
        scenario_id="B01-single-suspicious-transfer",
        title="Single Suspicious Transfer",
        category=FraudCategory.STRUCTURING,
        complexity=ComplexityLevel.BEGINNER,
        description=(
            "A small cluster of transfers sitting just below a reporting "
            "threshold between two accounts, embedded in normal activity."
        ),
        objectives=[
            "Provide a minimal positive example for threshold-based heuristics.",
            "Establish a benign baseline a detector must not over-flag.",
        ],
        risk_indicators=[
            _ri("sub_threshold_amount", "Amounts cluster just under round reporting limits."),
            _ri("repeated_counterparty", "Same sender/receiver pair repeats rapidly."),
        ],
        expected_outcomes=[
            "Threshold and velocity rules should flag the structuring batch.",
            "Baseline normal transactions should remain unflagged.",
        ],
        parameters={"population": 30, "baseline_transactions": 40, "count": 5, "instances": 1},
    ),
    ScenarioSpec(
        scenario_id="B02-account-takeover-burst",
        title="Account Takeover Burst",
        category=FraudCategory.ACCOUNT_TAKEOVER,
        complexity=ComplexityLevel.BEGINNER,
        description=(
            "A single salaried account suddenly drains funds in an atypical burst "
            "of large outgoing transfers to many recipients."
        ),
        objectives=[
            "Model a sudden deviation from an account's behavioural baseline.",
        ],
        risk_indicators=[
            _ri("amount_vs_baseline", "Transfers far exceed the account's typical range."),
            _ri("outgoing_velocity_spike", "Unusually high outgoing transaction velocity."),
        ],
        expected_outcomes=["Behavioural-baseline models should surface the burst."],
        parameters={"population": 35, "baseline_transactions": 50, "count": 10, "instances": 1},
    ),

    # ── Intermediate ──────────────────────────────────────────────────────────
    ScenarioSpec(
        scenario_id="I01-coordinated-smurfing",
        title="Coordinated Smurfing Fan-Out",
        category=FraudCategory.SMURFING,
        complexity=ComplexityLevel.INTERMEDIATE,
        description=(
            "A mule source distributes a large sum across many recipients in "
            "near-equal shares to stay beneath per-transaction scrutiny."
        ),
        objectives=[
            "Exercise fan-out / out-degree anomaly detection.",
            "Test resilience to many small, individually-benign transfers.",
        ],
        risk_indicators=[
            _ri("high_fan_out", "One account pays an abnormal number of distinct recipients.",
                ComplexityLevel.INTERMEDIATE),
            _ri("near_equal_shares", "Recipient amounts are suspiciously uniform."),
        ],
        expected_outcomes=["Graph out-degree and amount-uniformity features should fire."],
        parameters={"population": 60, "baseline_transactions": 80, "recipients": 12, "instances": 1},
    ),
    ScenarioSpec(
        scenario_id="I02-circular-flow",
        title="Circular Money Movement",
        category=FraudCategory.CIRCULAR_FLOW,
        complexity=ComplexityLevel.INTERMEDIATE,
        description=(
            "Funds traverse a ring of mule accounts and return to the origin "
            "after several hops, with slight amount decay to disguise the loop."
        ),
        objectives=["Exercise cycle-detection on the transaction graph."],
        risk_indicators=[
            _ri("closed_cycle", "A directed cycle returns funds to the origin.",
                ComplexityLevel.INTERMEDIATE),
            _ri("amount_decay", "Per-hop amounts decay slightly along the ring."),
        ],
        expected_outcomes=["Strongly-connected-component / cycle features should detect the ring."],
        parameters={"population": 50, "baseline_transactions": 70, "depth": 4, "instances": 1},
    ),
    ScenarioSpec(
        scenario_id="I03-synthetic-identity-ring",
        title="Synthetic Identity Cluster",
        category=FraudCategory.SYNTHETIC_IDENTITY,
        complexity=ComplexityLevel.INTERMEDIATE,
        description=(
            "A cluster of fabricated identities with thin-file histories and "
            "shared device fingerprints funds and fans out value."
        ),
        objectives=["Provide labelled synthetic-identity KYC anomalies for research."],
        risk_indicators=[
            _ri("thin_file_history", "Identities have minimal credible history.",
                ComplexityLevel.INTERMEDIATE),
            _ri("shared_device_cluster", "Multiple identities share device fingerprints."),
        ],
        expected_outcomes=["Identity-clustering and device-sharing features should group the ring."],
        parameters={"population": 55, "baseline_transactions": 60, "recipients": 6, "instances": 1},
    ),

    # ── Advanced ──────────────────────────────────────────────────────────────
    ScenarioSpec(
        scenario_id="A01-multi-stage-laundering",
        title="Multi-Stage Laundering (Placement → Layering → Integration)",
        category=FraudCategory.TRANSACTION_LAUNDERING,
        complexity=ComplexityLevel.ADVANCED,
        description=(
            "A high-value origin splits funds across many intermediaries over "
            "several layers, then reconsolidates into a clean destination — a "
            "textbook placement/layering/integration topology."
        ),
        objectives=[
            "Stress multi-hop path tracing and value-reconstruction analytics.",
            "Provide a hard positive embedded in heavy benign noise.",
        ],
        risk_indicators=[
            _ri("multi_layer_split", "Value fragments across multiple sequential layers.",
                ComplexityLevel.ADVANCED),
            _ri("reconsolidation", "Fragments recombine at a single destination.",
                ComplexityLevel.ADVANCED),
        ],
        expected_outcomes=[
            "Path-based and flow-conservation analytics should reconstruct the route.",
            "Naive pairwise rules should miss it — a stress test for the methodology.",
        ],
        parameters={"population": 90, "baseline_transactions": 150, "layers": 4, "split": 4, "instances": 1},
    ),
    ScenarioSpec(
        scenario_id="A02-mule-network",
        title="Long-Duration Mule Network",
        category=FraudCategory.MULE_NETWORK,
        complexity=ComplexityLevel.ADVANCED,
        description=(
            "Multiple overlapping mule chains route value from high-net-worth "
            "origins through shared intermediaries to retail endpoints."
        ),
        objectives=["Exercise community detection over overlapping chains."],
        risk_indicators=[
            _ri("shared_intermediaries", "Chains reuse the same mule accounts.",
                ComplexityLevel.ADVANCED),
            _ri("long_hop_chains", "Value traverses many sequential hops.",
                ComplexityLevel.ADVANCED),
        ],
        expected_outcomes=["Community-detection should reveal the overlapping mule cluster."],
        parameters={"population": 100, "baseline_transactions": 160, "hops": 6, "instances": 3},
    ),
    ScenarioSpec(
        scenario_id="A03-hybrid-operation",
        title="Hybrid Multi-Vector Operation",
        category=FraudCategory.LAYERING,
        complexity=ComplexityLevel.ADVANCED,
        description=(
            "A blended operation combining layering, smurfing and structuring "
            "within one population to mimic an evolving, adaptive adversary."
        ),
        objectives=[
            "Test detectors against simultaneous, interacting fraud topologies.",
        ],
        risk_indicators=[
            _ri("multi_vector", "Several distinct fraud topologies coexist.",
                ComplexityLevel.ADVANCED),
        ],
        expected_outcomes=[
            "End-to-end methodology evaluation across mixed signal types.",
        ],
        parameters={"population": 120, "baseline_transactions": 200, "layers": 3, "split": 4, "instances": 2},
    ),
]


class ScenarioCatalog:
    """Read-only access to the built-in scenario repository."""

    def __init__(self, scenarios: List[ScenarioSpec] | None = None):
        self._scenarios: Dict[str, ScenarioSpec] = {
            s.scenario_id: s for s in (scenarios if scenarios is not None else _SCENARIOS)
        }

    def all(self) -> List[ScenarioSpec]:
        return list(self._scenarios.values())

    def get(self, scenario_id: str) -> ScenarioSpec:
        if scenario_id not in self._scenarios:
            raise KeyError(f"Unknown scenario '{scenario_id}'. Use list-scenarios to see options.")
        return self._scenarios[scenario_id]

    def by_complexity(self, level: ComplexityLevel) -> List[ScenarioSpec]:
        return [s for s in self._scenarios.values() if s.complexity == level]

    def register(self, spec: ScenarioSpec) -> None:
        """Add a custom scenario at runtime (e.g. from the evolution engine)."""
        self._scenarios[spec.scenario_id] = spec

    def ids(self) -> List[str]:
        return list(self._scenarios.keys())
