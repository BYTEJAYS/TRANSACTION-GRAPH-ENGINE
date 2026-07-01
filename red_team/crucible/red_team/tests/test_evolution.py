"""Tests for the Intelligent Fraud Evolution Engine.

The safety tests (investigator-gated learning, no Blue coupling) run with no
backend. The end-to-end engine tests skip cleanly if blue_team_v2 is absent.
"""
import random

import pytest

from red_team.critics.realism import RealismCritic
from red_team.evolution import library
from red_team.evolution.crossover import crossover
from red_team.evolution import difficulty as diff
from red_team.evolution import failure_analysis
from red_team.evolution.blue_target import BlueVerdict
from red_team.evolution.learning_gate import LearningGate
from red_team.evolution.weakness import WeaknessMap
from red_team.sandbox.v2_target import _resolve_backend_path

_HAS_V2 = _resolve_backend_path() is not None
needs_v2 = pytest.mark.skipif(not _HAS_V2, reason="blue_team_v2 backend not found")


# ── library / crossover (no backend needed) ───────────────────────────────────
def test_library_families_build_valid_graphs():
    r = random.Random(0)
    for fam in library.FAMILIES.values():
        g = fam.build(r)
        txns = g.to_transaction_list()
        assert txns, f"{fam.name} produced no transactions"
        for t in txns:
            assert t["from_account"].startswith("acc_")
            assert isinstance(t["amount"], int)


def test_cycle_topology_forms_real_ring():
    g = library.get_family("round_robin").build(random.Random(1))
    txns = g.to_transaction_list()
    senders = {t["from_account"] for t in txns}
    receivers = {t["to_account"] for t in txns}
    assert senders == receivers  # closed ring: every node both sends and receives


def test_crossover_unions_capabilities():
    r = random.Random(2)
    a = library.get_family("cash_smurfing").build(r)
    b = library.get_family("crypto_exit").build(r)
    child = crossover(a, b, r)
    assert "crossover" in child.mutation_history
    assert child.generation == max(a.generation, b.generation) + 1
    # exit method survives from the crypto parent
    assert child.special_nodes.cash_out_method is not None


# ── failure analysis ──────────────────────────────────────────────────────────
def test_failure_analysis_maps_detector_to_counter_ops():
    v = BlueVerdict(graph_id="x", verdict="FRAUD", risk=0.9, confidence=0.8,
                    evidence_patterns=["smurfing", "fan_in"], flagged_nodes=["a", "b"])
    rep = failure_analysis.analyze(v)
    assert rep.detected
    assert rep.recommended_operators  # non-empty, ranked
    assert any("threshold" in op or "amount" in op or "bipartite" in op
               for op in rep.recommended_operators)


def test_failure_analysis_generic_when_no_pattern():
    v = BlueVerdict(graph_id="x", verdict="SUSPICIOUS", risk=0.7, confidence=0.5,
                    evidence_patterns=[], flagged_nodes=[])
    rep = failure_analysis.analyze(v)
    assert rep.recommended_operators  # falls back to generic evasions


# ── difficulty ────────────────────────────────────────────────────────────────
def test_difficulty_scales_and_spreads():
    r = random.Random(3)
    g = library.get_family("mule_network").build(r)
    base_width = g.topology.width
    base_span = sum(g.timing.spacing_days)
    diff.apply(g, diff.get_profile("nation_state"), r)
    assert g.topology.width >= base_width
    assert sum(g.timing.spacing_days) > base_span  # multi-day spread


# ── SAFETY: investigator-gated learning, no Blue coupling ─────────────────────
def test_learning_gate_has_no_blue_coupling():
    LearningGate.self_check()  # asserts module has no blue_team_v2 binding
    import red_team.evolution.learning_gate as lg
    src = open(lg.__file__).read()
    assert "import blue_team_v2" not in src
    assert "from blue_team_v2" not in src


def test_missed_attack_requires_approval_to_reach_backlog(tmp_path):
    gate = LearningGate(backlog_path=str(tmp_path / "backlog.jsonl"))
    alert = gate.register_missed_attack(
        genome_id="g1", attack_family="cash_smurfing", weakness_targeted="smurfing",
        difficulty="hard", generation=3, blue_verdict="CLEAN", blue_confidence=0.9,
        blue_risk=0.1, rupees_at_risk=250000, genome_summary={}, scenario_summary={})
    # Queued but NOT yet learned.
    assert gate.list_alerts(status="pending")
    assert gate.hardening_backlog() == []
    # Approval is the ONLY path into the backlog.
    entry = gate.approve(alert.alert_id, "investigator_01", "looks exploitable")
    assert entry["genome_id"] == "g1"
    assert len(gate.hardening_backlog()) == 1
    # Double-approve is a no-op (idempotent-ish: already decided).
    assert gate.approve(alert.alert_id, "investigator_01") is None


def test_rejected_alert_never_reaches_backlog(tmp_path):
    gate = LearningGate(backlog_path=str(tmp_path / "b.jsonl"),
                        alerts_path=str(tmp_path / "a.jsonl"))
    a = gate.register_missed_attack(
        genome_id="g2", attack_family="x", weakness_targeted="velocity",
        difficulty="easy", generation=1, blue_verdict="CLEAN", blue_confidence=1.0,
        blue_risk=0.0, rupees_at_risk=1000, genome_summary={}, scenario_summary={})
    assert gate.reject(a.alert_id, "investigator_01", "false alarm") is not None
    assert gate.hardening_backlog() == []


def test_alert_queue_is_durable_across_restart(tmp_path):
    """A fresh gate on the same store rehydrates the investigator queue."""
    store = str(tmp_path / "alerts.jsonl")
    g1 = LearningGate(backlog_path=str(tmp_path / "b.jsonl"), alerts_path=store)
    a = g1.register_missed_attack(
        genome_id="g3", attack_family="sim_swap", weakness_targeted="account_takeover",
        difficulty="impossible", generation=2, blue_verdict="CLEAN", blue_confidence=0.9,
        blue_risk=0.05, rupees_at_risk=500000, genome_summary={}, scenario_summary={})
    # Simulate restart: new gate, same path.
    g2 = LearningGate(backlog_path=str(tmp_path / "b.jsonl"), alerts_path=store)
    reloaded = g2.list_alerts(status="pending")
    assert [x.alert_id for x in reloaded] == [a.alert_id]
    # Decisions persist too.
    g2.approve(a.alert_id, "investigator_01")
    g3 = LearningGate(backlog_path=str(tmp_path / "b.jsonl"), alerts_path=store)
    assert g3.list_alerts(status="approved")
    assert g3.list_alerts(status="pending") == []


def test_expanded_library_covers_taxonomy():
    # the expanded set is substantial and spans many categories
    assert len(library.FAMILIES) >= 45
    assert len(library.CATEGORIES) >= 12
    for name in ("sim_swap", "trade_finance_fraud", "snowflake_graph",
                 "beneficiary_rotation", "gift_card_laundering"):
        assert name in library.FAMILIES


def test_weakness_planner_biases_to_weak_spots():
    wm = WeaknessMap()
    # crypto is a blind spot (always missed); velocity is strong (always caught).
    for _ in range(20):
        wm.record("crypto", detected=False, detectors=[], generations=2)
        wm.record("velocity", detected=True, detectors=["velocity"], generations=1)
    r = random.Random(0)
    picks = [wm.plan_target_category(r) for _ in range(300)]
    assert picks.count("crypto") > picks.count("velocity")
    rep = wm.report()
    assert rep["categories"]["velocity"]["status"] == "strong"
    assert rep["categories"]["crypto"]["status"] == "blind_spot"


# ── end-to-end against real V2 ─────────────────────────────────────────────────
# ── Ollama strategist: validation / apply / memory (no Ollama needed) ─────────
def test_llm_validation_sanitizes_untrusted_output():
    from red_team.evolution.llm_strategist import LLMStrategist
    # A hostile/sloppy LLM response: bad rails, out-of-range values, junk operators.
    obj = {
        "reasoning": "x" * 1000,
        "operators": ["layered_mixing", "DROP TABLE", "time_dilation", "nope", "amount_noise", "channel_hop"],
        "gene_overrides": {
            "channels": {"ach_transfer": 2.0, "bitcoin_rail": 5.0, "p2p_transfer": 1.0},
            "spacing_days": [-5, 9999, 1.5, "x"],
            "time_of_day": "lunchtime",
            "velocity_ratio": 8.0,
            "source_age_min_days": 999999,
            "amount_pattern": "spiral",
            "amount_scale": 50.0,
            "topology_type": "klein_bottle",
            "topology_width": 9999,
            "evil_key": "ignored",
        },
    }
    plan = LLMStrategist._validate(obj)
    assert len(plan.reasoning) <= 400
    assert len(plan.operators) <= 4
    assert all(o in {op.__name__ for op in __import__(
        "red_team.mutation.operators", fromlist=["ALL_OPERATORS"]).ALL_OPERATORS} for o in plan.operators)
    ov = plan.gene_overrides
    # only the 9 valid rails survive, renormalised to sum 1
    assert set(ov["channels"]) <= {"ach_transfer", "p2p_transfer"}
    assert abs(sum(ov["channels"].values()) - 1.0) < 1e-6
    assert all(0.001 <= x <= 365 for x in ov["spacing_days"])
    assert "time_of_day" not in ov                 # invalid enum dropped
    assert 0.0 <= ov["velocity_ratio"] <= 1.0
    assert ov["source_age_min_days"] <= 3000
    assert "amount_pattern" not in ov               # invalid enum dropped
    assert 0.2 <= ov["amount_scale"] <= 3.0
    assert "topology_type" not in ov                # invalid enum dropped
    assert ov["topology_width"] <= 40
    assert "evil_key" not in ov


def test_llm_apply_respects_locked_format():
    from red_team.evolution.llm_strategist import LLMStrategist, EvasionPlan
    strat = LLMStrategist()
    g = library.get_family("cash_smurfing").build(random.Random(1))
    plan = EvasionPlan(reasoning="diversify + slow", operators=["channel_hop"],
                       gene_overrides={"channels": {"p2p_transfer": 0.5, "ach_transfer": 0.5},
                                       "source_age_min_days": 300, "velocity_ratio": 0.2,
                                       "amount_scale": 1.0})
    child, applied = strat.apply(g, plan, RealismCritic())
    assert "llm_strategist" in child.mutation_history
    assert set(child.channels.mix) <= {"p2p_transfer", "ach_transfer"}
    assert all(isinstance(t["amount"], int) for t in child.to_transaction_list())
    assert min(child.accounts.source_ages_days) >= 300


def test_strategy_memory_roundtrip_and_exemplars(tmp_path):
    from red_team.evolution.strategy_memory import Strategy, StrategyMemory
    path = str(tmp_path / "mem.jsonl")
    m = StrategyMemory(path=path)
    m.record(Strategy("cash_smurfing", "hard", ["smurfing", "fan_in"],
                       ["amount_noise"], {"topology": "fan_in"}, 3))
    m.record(Strategy("crypto_exit", "easy", ["cashout"], ["cash_out_disguise"],
                      {"topology": "chain"}, 2))
    # reload from disk
    m2 = StrategyMemory(path=path)
    assert len(m2) == 2
    # exemplar ranking prefers overlap with the firing detectors
    ex = m2.exemplars(["smurfing"], k=1)
    assert ex and ex[0].family == "cash_smurfing"


def test_strategist_unavailable_is_graceful():
    """A bad Ollama host → available() False, propose() returns None (no raise)."""
    from red_team.evolution.llm_client import OllamaClient
    from red_team.evolution.llm_strategist import LLMStrategist
    from red_team.evolution.failure_analysis import analyze
    strat = LLMStrategist(client=OllamaClient(host="http://127.0.0.1:1", timeout=1))
    assert strat.available() is False
    v = BlueVerdict(graph_id="x", verdict="FRAUD", risk=0.9, confidence=0.8,
                    evidence_patterns=["smurfing"], flagged_nodes=["a"])
    assert strat.propose({"topology": "fan_in"}, analyze(v), []) is None


@needs_v2
def test_llm_default_on_when_available():
    """Default engine enables the strategist iff Ollama is available; budget is 3."""
    from red_team.evolution import EvolutionEngine
    assert EvolutionEngine(seed=1, use_llm=False).use_llm is False
    eng = EvolutionEngine(seed=1)  # default mirrors Ollama availability
    assert eng.use_llm == eng.llm.available()
    assert eng.max_llm_calls_per_attack == 3


@needs_v2
def test_engine_runs_attack_and_records():
    from red_team.evolution import EvolutionEngine
    eng = EvolutionEngine(seed=11, use_llm=False)  # deterministic; LLM covered separately
    run = eng.run_attack(family="cash_smurfing", difficulty="medium")
    assert run.status in ("evaded", "contained")
    assert run.generations
    # every generation carries a Blue verdict
    assert all(g.verdict for g in run.generations)


@needs_v2
def test_engine_campaign_populates_dashboard(tmp_path):
    from red_team.evolution import EvolutionEngine
    from red_team.evolution.learning_gate import LearningGate
    gate = LearningGate(backlog_path=str(tmp_path / "b.jsonl"),  # isolated, not the
                        alerts_path=str(tmp_path / "a.jsonl"))   # shared singleton
    eng = EvolutionEngine(seed=5, use_llm=False, gate=gate)
    state = eng.run_campaign(6, difficulty="hard")
    m = state["metrics"]
    assert m["attacks"] == 6
    assert m["blue_detection_rate"] is not None
    # any evaded attack must have produced exactly one pending alert (not auto-injected)
    assert state["pending_alerts"] == m["evaded"]


@needs_v2
def test_background_runner_feeds_queue():
    """The continuous runner launches attacks on the shared engine and stops cleanly."""
    import time
    from red_team.evolution import EvolutionEngine
    from red_team.evolution.runner import BackgroundCampaignRunner
    eng = EvolutionEngine(seed=3, use_llm=False)
    runner = BackgroundCampaignRunner(eng)
    runner.start(difficulty="impossible", interval_seconds=0.1)
    deadline = time.time() + 5
    while runner.status().attacks_launched < 3 and time.time() < deadline:
        time.sleep(0.1)
    st = runner.stop()
    assert not st.running
    assert st.attacks_launched >= 3
    # whatever evaded is now pending for the investigator (shared gate)
    assert eng.gate.list_alerts(status="pending") or st.evaded == 0


@needs_v2
def test_evaded_attack_creates_alert_not_backlog():
    """A successful attack alerts the investigator; it does NOT train Blue."""
    from red_team.evolution import EvolutionEngine
    from red_team.evolution.learning_gate import LearningGate
    gate = LearningGate(backlog_path="/tmp/crucible_test_backlog.jsonl")
    import os
    if os.path.exists(gate._backlog_path):
        os.remove(gate._backlog_path)
    eng = EvolutionEngine(gate=gate, seed=99, use_llm=False)
    eng.run_campaign(10, difficulty="impossible")  # easy to evade → alerts
    pending = gate.list_alerts(status="pending")
    # Whatever evaded is pending; nothing is in the backlog without approval.
    assert gate.hardening_backlog() == []
    if pending:
        gate.approve(pending[0].alert_id, "investigator_01")
        assert len(gate.hardening_backlog()) == 1
