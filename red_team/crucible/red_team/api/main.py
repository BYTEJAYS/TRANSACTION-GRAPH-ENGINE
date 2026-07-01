from __future__ import annotations
"""
Red Team API — FastAPI app.

Endpoints:
  POST /api/v1/red_team/receive_fraud_dna     ← Blue Team sends confirmed fraud
  GET  /api/v1/red_team/queue                 ← Human gate queue (sorted by impact)
  POST /api/v1/red_team/review/{genome_id}    ← Investigator approves/discards
  GET  /api/v1/red_team/prophecy/stats        ← Hit rates, days-ahead
  GET  /api/v1/red_team/lineages              ← All lineage scores + weights
  GET  /api/v1/demo/run_prophecy_match        ← Manual trigger for demo
  GET  /api/v1/demo/evolution_replay          ← Show generation 0→50 evolution
  GET  /health                                ← Liveness probe
"""
import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CRUCIBLE Red Team",
    description="Adversarial fraud genome evolution engine for BLING Blue Team",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Intelligent Fraud Evolution Engine (investigator-gated; targets Blue Team V2).
# Router is self-contained; its engine singleton lazy-loads Blue Team V2 on first use.
from red_team.evolution.api import mount as _mount_evolution  # noqa: E402

_mount_evolution(app)

# ── Singletons (lazy-loaded on first request) ───────────────────────────

_blue_team = None
_engine = None


def _get_blue_team():
    global _blue_team
    if _blue_team is None:
        from red_team.sandbox.blue_clone import get_blue_team
        _blue_team = get_blue_team()
    return _blue_team


def _get_engine():
    global _engine
    if _engine is None:
        from red_team.demo.seed_data import SEED_GENOMES
        from red_team.mutation.engine import MutationEngine
        from red_team.prophecy.ledger import ledger
        _engine = MutationEngine(
            blue_team=_get_blue_team(),
            seed_genomes=list(SEED_GENOMES),
            ledger=ledger,
            generations=50,  # short run for API demo; nightly worker does 10k
        )
    return _engine


# ── Pydantic models ──────────────────────────────────────────────────────

class Transaction(BaseModel):
    from_account: str
    to_account: str
    amount: float
    payment_rail: str
    timestamp: str


class FraudDnaPayload(BaseModel):
    fraud_id: str
    transactions: list[Transaction]
    confirmed_at: str | None = None
    source: str = "blue_team"


class ReviewPayload(BaseModel):
    reviewer_id: str
    decision: str  # "approve" | "discard" | "needs_more_info"
    notes: str | None = None


# ── Health ───────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "crucible-red-team"}


# ── Core endpoints ───────────────────────────────────────────────────────

@app.post("/api/v1/red_team/receive_fraud_dna")
def receive_fraud_dna(payload: FraudDnaPayload) -> dict[str, Any]:
    """
    Blue Team sends confirmed real fraud here.
    Red Team stores it in Prophecy Ledger for overnight matching.
    Also adds to seed bank if Red Team never predicted this pattern.
    """
    from red_team.prophecy.ledger import ledger

    transactions = [t.model_dump() for t in payload.transactions]
    ledger.receive_confirmed_fraud(
        fraud_id=payload.fraud_id,
        transaction_data=transactions,
    )
    logger.info("Fraud DNA received", fraud_id=payload.fraud_id[:8])
    return {"status": "received", "fraud_id": payload.fraud_id}


@app.get("/api/v1/red_team/queue")
def get_queue(limit: int = 20) -> dict[str, Any]:
    """Returns pending human gate items sorted by impact score (₹_at_risk × ease × scale)."""
    from red_team.human_gate.queue import human_gate_queue

    # Ensure some genomes are in the queue — run a quick evolution if empty
    if len(human_gate_queue) == 0:
        _seed_queue_from_engine()

    items = human_gate_queue.get_sorted(pending_only=True)[:limit]
    return {
        "pending": len(human_gate_queue),
        "items": [
            {
                "genome_id": item.genome_id,
                "priority_score": item.priority_score,
                "rupees_at_risk": item.rupees_at_risk,
                "ease": item.ease_label,
                "scalability": item.scalability_label,
                "requires_senior_review": item.requires_senior,
                "flags": item.flags,
                "enqueued_at": item.enqueued_at.isoformat(),
                "summary": item.genome_summary,
            }
            for item in items
        ],
    }


@app.post("/api/v1/red_team/review/{genome_id}")
def review_genome(genome_id: str, payload: ReviewPayload) -> dict[str, Any]:
    """Investigator approves or discards a genome. Approved → repair recommendation generated."""
    from red_team.human_gate.queue import human_gate_queue
    from red_team.human_gate.router import counterfactual_repair_test

    item = human_gate_queue.record_review(
        genome_id=genome_id,
        reviewer_id=payload.reviewer_id,
        decision=payload.decision,
        notes=payload.notes,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Genome not found in queue")

    result: dict[str, Any] = {
        "genome_id": genome_id,
        "decision": payload.decision,
        "reviewer": payload.reviewer_id,
    }

    if payload.decision == "approve":
        # Generate repair recommendation for Blue Team
        engine = _get_engine()
        top = dict(engine.top_genomes(n=50))
        genome = None
        for g, _ in engine.top_genomes(n=100):
            if g.genome_id == genome_id:
                genome = g
                break

        if genome:
            fitness = item.genome_summary.get("fitness", 0.05)
            repair = counterfactual_repair_test(genome, fitness)
            result["repair_recommendation"] = repair
        else:
            result["repair_recommendation"] = {"recommendation": "not_found"}

    return result


@app.get("/api/v1/red_team/prophecy/stats")
def prophecy_stats() -> dict[str, Any]:
    """Returns prophecy ledger stats: hit rates, matched predictions, active lineages."""
    from red_team.prophecy.ledger import ledger
    stats = ledger.get_stats()
    stats["days_ahead_sample"] = ledger.days_ahead_distribution()[:10]
    return stats


@app.get("/api/v1/red_team/lineages")
def lineage_scores() -> dict[str, Any]:
    """Returns all lineage weights for the PBT selection distribution."""
    from red_team.prophecy.ledger import ledger
    from red_team.learning.operator_weights import operator_tracker
    from red_team.learning.lineage_weights import LineageWeightManager

    mgr = LineageWeightManager(ledger, operator_tracker)
    return {
        "lineage_weights": ledger.get_lineage_weights(),
        "operator_boosts": ledger.get_operator_boosts(),
        "combined_weights": mgr.get_combined_weights(),
        "operator_stats": operator_tracker.get_stats(),
    }


# ── Demo endpoints ───────────────────────────────────────────────────────

@app.get("/api/v1/demo/run_prophecy_match")
def demo_run_prophecy_match() -> dict[str, Any]:
    """Manual trigger — runs prophecy matching and returns match results."""
    from red_team.prophecy.ledger import ledger

    # Seed some demo confirmed frauds if empty
    _ensure_demo_confirmed_frauds()
    result = ledger.nightly_matching_job()
    result["stats"] = ledger.get_stats()
    return result


@app.get("/api/v1/demo/evolution_replay")
def demo_evolution_replay() -> dict[str, Any]:
    """
    Shows fitness improving from generation 0 → 50.
    Runs a quick 50-generation evolution and snapshots every 10 gens.
    """
    from red_team.demo.seed_data import SEED_GENOMES
    from red_team.mutation.engine import MutationEngine
    from red_team.prophecy.ledger import ProphecyLedger

    bt = _get_blue_team()
    engine = MutationEngine(
        blue_team=bt,
        seed_genomes=list(SEED_GENOMES),
        ledger=ProphecyLedger(),
        generations=50,
    )

    snapshots = []
    for checkpoint in [10, 20, 30, 40, 50]:
        engine.run(generations=10)
        top = engine.top_genomes(n=3)
        snapshots.append({
            "generation": checkpoint,
            "top_fitness": round(top[0][1], 6) if top else 0.0,
            "population_size": len(engine._population),
            "top_genome_id": top[0][0].genome_id[:8] if top else None,
            "top_flags": top[0][0].flags[:3] if top else [],
        })

    return {"evolution_replay": snapshots}


# ── Test DNA endpoint ─────────────────────────────────────────────────────

@app.get("/api/v1/test_dna/{dna_id}")
def get_test_dna(dna_id: str) -> dict[str, Any]:
    """Returns a pre-generated test DNA transaction chain by ID (001, 002, 003)."""
    import json
    import os

    path = os.path.join(
        os.path.dirname(__file__),
        "..", "test_dna", "outputs", f"dna_{dna_id}.json"
    )
    path = os.path.normpath(path)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"DNA {dna_id} not found")
    with open(path) as f:
        return json.load(f)


# ── Helpers ───────────────────────────────────────────────────────────────

def _seed_queue_from_engine() -> None:
    from red_team.human_gate.queue import human_gate_queue
    engine = _get_engine()
    engine.run(generations=50)
    for genome, fitness in engine.top_genomes(n=10):
        human_gate_queue.enqueue(genome, fitness)


def _ensure_demo_confirmed_frauds() -> None:
    from red_team.prophecy.ledger import ledger
    import json
    import os

    if ledger._confirmed_frauds:
        return

    path = os.path.join(
        os.path.dirname(__file__),
        "..", "demo", "confirmed_frauds_mock.json",
    )
    path = os.path.normpath(path)
    if not os.path.exists(path):
        return

    with open(path) as f:
        frauds = json.load(f)

    for fraud in frauds:
        ledger.receive_confirmed_fraud(
            fraud_id=fraud["fraud_id"],
            transaction_data=fraud.get("transactions", []),
        )
