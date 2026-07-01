from __future__ import annotations
"""
Intelligent Fraud Evolution Engine — the orchestrator.

Implements the required investigator-in-control architecture:

    plan weakest category → build/hybridise attack → apply difficulty
        │
        ▼   (per generation, automatically)
    run against Blue Team V2
        │
    Blue detects? ──── YES ──→ failure analysis → DIRECTED mutation (Red learns) → next gen
        │
        └──────────── NO  ──→ SUCCESS: queue an investigator alert (NEVER auto-inject).
                                The investigator alone approves learning (learning_gate).

Mutation/evolution is automatic; *learning by Blue is not* — only an approved
alert reaches the hardening backlog, and even then Blue Team V2 is never modified
by this engine. Each attack keeps a full per-generation evolution history.
"""
import logging
import os
import random
import threading
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from red_team.critics.realism import RealismCritic
from red_team.evolution import difficulty as diff
from red_team.evolution import failure_analysis, library
from red_team.evolution.blue_target import BlueTeamV2Target, BlueVerdict
from red_team.evolution.crossover import crossover
from red_team.evolution.learning_gate import LearningGate, learning_gate
from red_team.evolution.legit_traffic import build_scenario
from red_team.evolution.llm_strategist import LLMStrategist
from red_team.evolution.metrics import CampaignMetrics
from red_team.evolution.strategy_memory import Strategy, StrategyMemory
from red_team.evolution.weakness import WeaknessMap
from red_team.mutation.operators import ALL_OPERATORS
from red_team.core.genome import FraudGenome

logger = logging.getLogger(__name__)

_OPS_BY_NAME = {op.__name__: op for op in ALL_OPERATORS}


@dataclass
class Generation:
    index: int
    operator: str | None
    verdict: str
    risk: float
    confidence: float
    detected: bool
    triggered_detectors: list[str]
    causes: list[str]
    recommended_next: list[str]
    strategist: str = "heuristic"   # "heuristic" | "llm"
    llm_reasoning: str | None = None


@dataclass
class AttackRun:
    attack_id: str
    family: str
    category: str
    difficulty: str
    weakness_targeted: str
    is_hybrid: bool
    status: str = "evolving"  # evolving | evaded | contained
    generations: list[Generation] = field(default_factory=list)
    scenario_summary: dict[str, Any] = field(default_factory=dict)
    final_genome_summary: dict[str, Any] = field(default_factory=dict)
    final_transactions: list[dict] = field(default_factory=list)  # penetrating pattern edges (sample)
    alert_id: str | None = None
    rupees_at_risk: float = 0.0
    false_positives: int = 0
    false_negatives: int = 0

    def to_dict(self) -> dict:
        return {
            "attack_id": self.attack_id,
            "family": self.family,
            "category": self.category,
            "difficulty": self.difficulty,
            "weakness_targeted": self.weakness_targeted,
            "is_hybrid": self.is_hybrid,
            "status": self.status,
            "generation_count": len(self.generations),
            "generations": [g.__dict__ for g in self.generations],
            "scenario": self.scenario_summary,
            "final_genome": self.final_genome_summary,
            "final_transactions": self.final_transactions,
            "alert_id": self.alert_id,
            "rupees_at_risk": self.rupees_at_risk,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
        }


def _gene_fingerprint(g: FraudGenome) -> dict:
    """Compact, human-readable winning genes for strategy memory / LLM few-shot."""
    ages = g.accounts.source_ages_days or [0]
    return {
        "topology": g.topology.type, "width": g.topology.width, "depth": g.topology.depth,
        "channels": g.channels.mix, "time_of_day": g.timing.time_of_day,
        "velocity": g.accounts.velocity_ratio, "min_age": min(ages),
        "amount_pattern": g.amounts.pattern,
    }


def _genome_summary(g: FraudGenome) -> dict:
    return {
        "genome_id": g.genome_id,
        "lineage_id": g.lineage_id,
        "topology": g.topology.type,
        "depth": g.topology.depth,
        "width": g.topology.width,
        "total_amount": g.amounts.total,
        "channels": g.channels.mix,
        "time_of_day": g.timing.time_of_day,
        "generation": g.generation,
        "mutation_history": g.mutation_history,
    }


class EvolutionEngine:
    """Drives controlled adversarial campaigns against Blue Team V2."""

    def __init__(self, blue: BlueTeamV2Target | None = None,
                 gate: LearningGate | None = None, seed: int | None = None,
                 use_llm: bool | None = None, llm: LLMStrategist | None = None,
                 strategy_memory: StrategyMemory | None = None) -> None:
        self.blue = blue or BlueTeamV2Target()
        self.gate = gate or learning_gate
        self.realism = RealismCritic()
        self.weakness = WeaknessMap()
        self.metrics = CampaignMetrics()
        self.rng = random.Random(seed)
        self.runs: dict[str, AttackRun] = {}
        self._lock = threading.RLock()  # run_attack + reads share state across threads
        # Ollama-powered strategist + cross-attack learning memory. ON BY DEFAULT
        # when Ollama is available — an A/B benchmark showed the LLM (under greedy
        # candidate acceptance) makes Red strictly stronger: same evasions, lower
        # mean Blue risk, never derails a working attack. The strategist competes
        # with the heuristic each step and only wins when Blue scores it lower, so
        # it can help but not hurt. Disable with CRUCIBLE_LLM_AUTO=0, use_llm=False,
        # or the dashboard toggle. If Ollama is down it transparently falls back.
        self.llm = llm or LLMStrategist()
        self.memory = strategy_memory or StrategyMemory()
        if use_llm is None:
            forced_off = os.getenv("CRUCIBLE_LLM_AUTO", "").lower() in ("0", "false", "no")
            self.use_llm = False if forced_off else self.llm.available()
        else:
            self.use_llm = bool(use_llm) and self.llm.available()
        self.llm_invocations = 0
        # cap LLM calls per attack (proven-stronger budget); greedy acceptance
        # means extra calls can only help, bounded so the loop stays responsive.
        self.max_llm_calls_per_attack = 3
        # Elitist beam search: evaluate this many heuristic candidates per step and
        # keep the best; always evolve from the best genome found so far (no regress).
        # 12 is the swept sweet spot — on the 80-attack benchmark it reached 100%
        # evasion (vs 32/80 at beam=1) at the LOWEST per-attack cost (wider beam
        # evades in fewer generations); 16/25 add negligible gain for more compute.
        self.beam_width = 12

    # ── attack construction ───────────────────────────────────────────────────
    def _build_attack(self, profile: diff.DifficultyProfile, family: str | None,
                      category: str | None) -> tuple[FraudGenome, str, str, bool]:
        if family:
            fam = library.get_family(family)
            target_cat = fam.category
        else:
            target_cat = category or self.weakness.plan_target_category(self.rng)
            fam = library.sample_family(self.rng, target_cat)

        is_hybrid = False
        if self.rng.random() < profile.hybridization_prob:
            other = library.sample_family(self.rng)
            genome = crossover(fam.build(self.rng), other.build(self.rng), self.rng)
            fam_label = f"{fam.name}+{other.name}"
            is_hybrid = True
        else:
            genome = fam.build(self.rng)
            fam_label = fam.name

        diff.apply(genome, profile, self.rng)
        return genome, fam_label, target_cat, is_hybrid

    # ── directed mutation (the learning step) ─────────────────────────────────
    def _heuristic_candidates(self, genome: FraudGenome, recommended: list[str],
                              k: int) -> list[tuple[FraudGenome, str]]:
        """Up to k distinct, valid counter-mutations aimed at the firing detectors.

        Beam search: instead of returning the first valid operator, we materialise
        several so the caller can keep whichever Blue scores lowest. Recommended
        (highest-leverage) operators are tried first, then random exploration.
        """
        out: list[tuple[FraudGenome, str]] = []
        seen: set[str] = set()
        ranked = [n for n in recommended if n in _OPS_BY_NAME]
        pool = ranked + self.rng.sample(list(_OPS_BY_NAME), k=len(_OPS_BY_NAME))
        for name in pool:
            if name in seen:
                continue
            seen.add(name)
            try:
                child = _OPS_BY_NAME[name](deepcopy(genome))
            except Exception:  # operator may not apply to this genome shape
                continue
            child.genome_id = str(uuid.uuid4())
            child.parent_genome_id = genome.genome_id
            child.generation += 1
            if name not in child.mutation_history:
                child.mutation_history.append(name)
            valid, _ = self.realism.hard_validate(child)
            if valid:
                out.append((child, name))
            if len(out) >= k:
                break
        if not out:  # nothing applied cleanly — no-op so the loop still progresses
            out.append((deepcopy(genome), "noop"))
        return out

    def _candidate_risk(self, cand: FraudGenome, profile: diff.DifficultyProfile) -> float:
        """Blue's risk for a candidate mutation — used to greedily pick the best one."""
        scn = build_scenario(cand.to_transaction_list(), profile.legit_noise_ratio,
                             self.rng, blend_into_graph=profile.blend_legit_into_graph)
        comp = self.blue.to_component(scn.graph_txns, f"rt_{cand.genome_id[:8]}")
        if not comp.get("edges"):
            return 0.0
        return self.blue.judge_component(comp).risk

    # ── one full attack ───────────────────────────────────────────────────────
    def run_attack(self, *, family: str | None = None, category: str | None = None,
                   difficulty: str = "medium") -> AttackRun:
        # Serialise attacks so the background runner and API requests don't
        # interleave mutations of the shared rng / runs / weakness / metrics.
        with self._lock:
            return self._run_attack_locked(family=family, category=category,
                                           difficulty=difficulty)

    def _run_attack_locked(self, *, family: str | None, category: str | None,
                           difficulty: str) -> AttackRun:
        profile = diff.get_profile(difficulty)
        genome, fam_label, target_cat, is_hybrid = self._build_attack(profile, family, category)

        run = AttackRun(
            attack_id=str(uuid.uuid4()), family=fam_label, category=target_cat,
            difficulty=profile.level, weakness_targeted=target_cat, is_hybrid=is_hybrid,
        )
        self.runs[run.attack_id] = run

        last_verdict: BlueVerdict | None = None
        winning_mutation: str | None = None
        next_ops: list[str] = []
        applied_op: str | None = None
        cur_strategist = "heuristic"      # how the CURRENT genome was produced
        cur_reasoning: str | None = None
        llm_calls = 0
        prev_risk = 1.0
        beaten_detectors: list[str] = []  # detectors firing on the last DETECTED gen
        best_genome = genome              # elitism: strongest genome seen so far
        best_risk = 2.0

        for gen_idx in range(profile.max_generations):
            scenario = build_scenario(
                genome.to_transaction_list(), profile.legit_noise_ratio, self.rng,
                blend_into_graph=profile.blend_legit_into_graph,
            )
            comp = self.blue.to_component(scenario.graph_txns, f"rt_{genome.genome_id[:8]}")
            verdict = self.blue.judge_component(comp) if comp.get("edges") \
                else BlueVerdict(graph_id="empty", verdict="CLEAN", risk=0.0, confidence=1.0)
            last_verdict = verdict
            if verdict.risk < best_risk:        # elitism: remember the strongest genome
                best_risk, best_genome = verdict.risk, genome

            report = failure_analysis.analyze(verdict)
            run.generations.append(Generation(
                index=gen_idx, operator=applied_op, verdict=verdict.verdict,
                risk=round(verdict.risk, 4), confidence=round(verdict.confidence, 4),
                detected=verdict.detected, triggered_detectors=verdict.evidence_patterns,
                causes=report.causes, recommended_next=report.recommended_operators[:5],
                strategist=cur_strategist, llm_reasoning=cur_reasoning,
            ))

            if not verdict.detected:
                # SUCCESS — Blue missed it. Stop and hand to the investigator.
                run.status = "evaded"
                winning_mutation = applied_op
                run.false_negatives = len(scenario.fraud_nodes - set(verdict.flagged_nodes))
                run.scenario_summary = scenario.summary()
                break

            # Detected → false positives = flagged legit nodes; learn and mutate.
            run.false_positives += len(set(verdict.flagged_nodes) & scenario.legit_nodes)
            beaten_detectors = list(verdict.evidence_patterns)
            next_ops = report.recommended_operators

            # Elitist beam search from the BEST genome so far (never regress). The
            # heuristic contributes up to `beam_width` candidates; when the LLM is on
            # (first detection or when stalled) it adds a rival candidate. We keep
            # whichever candidate Blue scores LOWEST — so more candidates and the
            # strategist can only help, never derail a working trajectory.
            candidates: list[tuple] = [  # (genome, strategist, applied_op, reasoning)
                (g, "heuristic", op, None)
                for g, op in self._heuristic_candidates(best_genome, next_ops, self.beam_width)
            ]
            stalled = verdict.risk >= prev_risk - 0.02
            if (self.use_llm and llm_calls < self.max_llm_calls_per_attack
                    and (gen_idx == 0 or stalled)):
                exemplars = self.memory.exemplars(beaten_detectors, k=3)
                plan = self.llm.propose(_genome_summary(best_genome), report, exemplars)
                llm_calls += 1
                self.llm_invocations += 1
                if plan is not None:
                    llm_g, applied = self.llm.apply(best_genome, plan, self.realism)
                    op = "llm:" + (",".join(applied["operators"]) or "genes")
                    candidates.append((llm_g, "llm", op, plan.reasoning))

            # Evaluate each candidate once against Blue; keep the lowest risk
            # (ties preserve candidate order ⇒ heuristic before LLM).
            evals = sorted(
                ((self._candidate_risk(c[0], profile), i, c) for i, c in enumerate(candidates)),
                key=lambda e: (e[0], e[1]),
            )
            genome, cur_strategist, applied_op, cur_reasoning = evals[0][2]

            prev_risk = verdict.risk
            run.scenario_summary = scenario.summary()
        else:
            run.status = "contained"  # Blue held across the whole budget

        # Report the STRONGEST genome found (elitism), not the last one tried.
        run.final_genome_summary = _genome_summary(best_genome)
        run.final_transactions = best_genome.to_transaction_list()[:16]  # forensic sample
        run.rupees_at_risk = best_genome.amounts.total

        # ── bookkeeping (weakness map + metrics) ──
        detected = run.status != "evaded"
        evidence = last_verdict.evidence_patterns if last_verdict else []
        self.weakness.record(target_cat, detected, evidence, len(run.generations))
        self.metrics.record(
            detected=detected, generations=len(run.generations),
            false_positives=run.false_positives, false_negatives=run.false_negatives,
            last_evidence=evidence, winning_mutation=winning_mutation,
        )

        # ── Red learns: store the winning recipe (Red-only; not Blue training) ──
        if run.status == "evaded" and beaten_detectors:
            self.memory.record(Strategy(
                family=fam_label, difficulty=profile.level,
                beaten_detectors=beaten_detectors,
                operators=list(best_genome.mutation_history),
                gene_fingerprint=_gene_fingerprint(best_genome),
                generations=len(run.generations),
            ))

        # ── investigator alert ONLY (never auto-inject into Blue) ──
        if run.status == "evaded" and last_verdict is not None:
            alert = self.gate.register_missed_attack(
                genome_id=best_genome.genome_id, attack_family=fam_label,
                weakness_targeted=target_cat, difficulty=profile.level,
                generation=len(run.generations), blue_verdict=last_verdict.verdict,
                blue_confidence=last_verdict.confidence, blue_risk=last_verdict.risk,
                rupees_at_risk=best_genome.amounts.total,
                genome_summary=_genome_summary(best_genome),
                scenario_summary=run.scenario_summary,
            )
            run.alert_id = alert.alert_id

        logger.info("Attack %s [%s/%s] → %s in %d gens",
                    run.attack_id[:8], fam_label, profile.level, run.status,
                    len(run.generations))
        return run

    # ── campaign ──────────────────────────────────────────────────────────────
    def run_campaign(self, n_attacks: int = 10, difficulty: str = "medium") -> dict:
        for _ in range(n_attacks):
            self.run_attack(difficulty=difficulty)
        return self.dashboard_state()

    def dashboard_state(self) -> dict:
        with self._lock:
            report = self.weakness.report()
            return {
                "metrics": self.metrics.snapshot(report),
                "learning_curve": self.metrics.learning_curve(),
                "weakness_report": report,
                "recent_attacks": [r.to_dict() for r in list(self.runs.values())[-10:]],
                "pending_alerts": len(self.gate.list_alerts(status="pending")),
                "blue_engine_version": self.blue.version,
                "strategist": {
                    "use_llm": self.use_llm,
                    "model": self.llm.model,
                    "available": self.llm.available(),
                    "invocations": self.llm_invocations,
                    "strategy_memory": len(self.memory),
                },
            }

    def set_llm(self, enabled: bool) -> dict:
        """Investigator toggle for the Ollama strategist (no effect if unavailable)."""
        with self._lock:
            self.use_llm = bool(enabled) and self.llm.available()
            return {"use_llm": self.use_llm, "available": self.llm.available(),
                    "model": self.llm.model}
