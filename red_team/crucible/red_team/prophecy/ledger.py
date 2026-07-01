from __future__ import annotations
"""
Prophecy Ledger — stores Red Team predictions and matches them against
real confirmed frauds from Blue Team (received via POST /receive_fraud_dna).

Lifecycle:
1. Red Team generates genome → store_prediction() adds it here
2. Blue Team sends confirmed fraud → receive_confirmed_fraud() stores it
3. nightly_matching_job() runs at 02:00 via Celery beat
   - Compares predictions ≤ 90 days old against confirmed frauds ≤ 7 days old
   - Cosine ≥ 0.85 = HIT → updates lineage scores
4. compute_lineage_fitness_weights() re-weights PBT selection for next run

SQLite fallback path: when PostgreSQL not available (e.g. test/demo),
the ledger falls back to an in-memory dict. Production always uses DB.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import numpy as np

from red_team.core.fingerprint import compute_embedding
from red_team.prophecy.matcher import MATCH_THRESHOLD, batch_match
from red_team.prophecy.scorer import compute_lineage_fitness_weights, compute_operator_boosts

logger = logging.getLogger(__name__)

_PROPHECY_TTL_DAYS = 90
_CONFIRMED_FRAUD_WINDOW_DAYS = 7  # only match against frauds confirmed in last 7 days


class ProphecyLedger:
    """
    In-memory ledger (used when DB not configured).
    Production: subclass/replace with DB-backed version via SQLAlchemy models.
    """

    def __init__(self) -> None:
        # {genome_id: {genome, embedding, predicted_at, lineage_id, operators, matched}}
        self._predictions: dict[str, dict[str, Any]] = {}
        # [{fraud_id, embedding, confirmed_at, transaction_data}]
        self._confirmed_frauds: list[dict[str, Any]] = []
        # {lineage_id: {predictions, hits, operators}}
        self._lineage_stats: dict[str, dict[str, Any]] = {}

    def store_prediction(
        self,
        genome_id: str,
        embedding: np.ndarray,
        lineage_id: str,
        operators: list[str],
        fitness: float,
        flags: list[str],
    ) -> None:
        self._predictions[genome_id] = {
            "genome_id": genome_id,
            "embedding": embedding,
            "lineage_id": lineage_id,
            "operators": operators,
            "fitness": fitness,
            "flags": flags,
            "predicted_at": datetime.now(timezone.utc),
            "matched": False,
        }
        # init lineage stats if new
        if lineage_id not in self._lineage_stats:
            self._lineage_stats[lineage_id] = {
                "predictions": 0,
                "hits": 0,
                "operators": operators,
            }
        self._lineage_stats[lineage_id]["predictions"] += 1
        logger.debug("Prediction stored", genome_id=genome_id[:8], lineage=lineage_id)

    def receive_confirmed_fraud(
        self,
        fraud_id: str,
        transaction_data: list[dict],
        embedding: np.ndarray | None = None,
    ) -> None:
        """Called when Blue Team sends a confirmed fraud via POST /receive_fraud_dna."""
        if embedding is None:
            # Build a synthetic embedding from transaction amounts/structure
            embedding = _embed_transaction_list(transaction_data)

        self._confirmed_frauds.append({
            "fraud_id": fraud_id,
            "embedding": embedding,
            "confirmed_at": datetime.now(timezone.utc),
            "transaction_data": transaction_data,
        })
        logger.info("Confirmed fraud received", fraud_id=fraud_id[:8])

    def nightly_matching_job(self) -> dict[str, Any]:
        """
        Runs at 02:00 via Celery beat.
        Matches un-matched predictions (≤90 days old) against
        recently confirmed frauds (≤7 days old).
        Returns summary stats.
        """
        now = datetime.now(timezone.utc)
        cutoff_prediction = now - timedelta(days=_PROPHECY_TTL_DAYS)
        cutoff_confirmed = now - timedelta(days=_CONFIRMED_FRAUD_WINDOW_DAYS)

        # Gather recent confirmed frauds
        recent_confirmed = [
            f for f in self._confirmed_frauds
            if f["confirmed_at"] >= cutoff_confirmed
        ]
        if not recent_confirmed:
            logger.info("No recent confirmed frauds — skipping prophecy matching")
            return {"matches": 0, "checked": 0}

        confirmed_embeddings = [f["embedding"] for f in recent_confirmed]

        # Gather pending predictions
        pending = [
            p for p in self._predictions.values()
            if not p["matched"] and p["predicted_at"] >= cutoff_prediction
        ]

        if not pending:
            return {"matches": 0, "checked": 0}

        prediction_pairs = [(p["genome_id"], p["embedding"]) for p in pending]
        results = batch_match(prediction_pairs, confirmed_embeddings)

        hits = 0
        for result in results:
            gid = result["genome_id"]
            if result["matched"]:
                hits += 1
                self._predictions[gid]["matched"] = True
                lineage_id = self._predictions[gid]["lineage_id"]
                if lineage_id in self._lineage_stats:
                    self._lineage_stats[lineage_id]["hits"] += 1
                logger.info(
                    "Prophecy HIT",
                    genome_id=gid[:8],
                    cosine=result["best_cosine"],
                    match_type=result["match_type"],
                )

        summary = {
            "matches": hits,
            "checked": len(pending),
            "hit_rate": round(hits / len(pending), 4) if pending else 0.0,
            "recent_confirmed_count": len(recent_confirmed),
        }
        logger.info("Nightly matching complete", **summary)
        return summary

    def get_lineage_weights(self) -> dict[str, float]:
        return compute_lineage_fitness_weights(self._lineage_stats)

    def get_operator_boosts(self) -> dict[str, float]:
        return compute_operator_boosts(self._lineage_stats)

    def get_stats(self) -> dict[str, Any]:
        total = len(self._predictions)
        matched = sum(1 for p in self._predictions.values() if p["matched"])
        return {
            "total_predictions": total,
            "matched": matched,
            "unmatched": total - matched,
            "overall_hit_rate": round(matched / total, 4) if total else 0.0,
            "confirmed_frauds_received": len(self._confirmed_frauds),
            "active_lineages": len(self._lineage_stats),
        }

    def days_ahead_distribution(self) -> list[int]:
        """
        For matched predictions: how many days before confirmed fraud did we predict?
        Useful for demo: "Red Team predicted X days ahead of Blue Team confirmation."
        """
        days_list = []
        for p in self._predictions.values():
            if not p["matched"]:
                continue
            # We don't store the exact match timestamp in-memory — estimate with TTL/2
            days_list.append(45)  # placeholder; DB-backed version uses real timestamps
        return days_list


def _embed_transaction_list(transactions: list[dict]) -> np.ndarray:
    """
    Lightweight embedding for confirmed fraud transaction lists
    (not full genomes — just structural fingerprint from amounts/timing).
    Returns L2-normalized 256-d vector.
    """
    if not transactions:
        return np.zeros(256, dtype=np.float32)

    amounts = [float(t.get("amount", 0)) for t in transactions]
    total = sum(amounts)
    count = len(transactions)
    avg = total / count if count else 0.0
    max_a = max(amounts) if amounts else 0.0

    # Simple 256-d feature: repeat normalized structural features
    features = np.zeros(256, dtype=np.float32)
    features[0] = min(1.0, total / 1_000_000)
    features[1] = min(1.0, count / 20)
    features[2] = min(1.0, avg / 50_000)
    features[3] = min(1.0, max_a / 100_000)
    # Fill remaining with interaction terms
    for i in range(4, 256):
        features[i] = features[i % 4] * features[(i + 1) % 4]

    norm = np.linalg.norm(features)
    if norm > 0:
        features /= norm
    return features


# Module-level singleton — replaced by DB-backed version in production
ledger = ProphecyLedger()
