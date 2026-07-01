from __future__ import annotations
"""
ProphecyMatcher — cosine similarity matching between Red Team predictions and
confirmed real frauds from Blue Team.

A "hit" = cosine(prediction_embedding, confirmed_fraud_embedding) >= 0.85.
This threshold means the structural topology, amounts, and timing are substantially
similar — not just the same MO category, but the same exploitation pattern.
"""
import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from red_team.core.genome import FraudGenome

logger = logging.getLogger(__name__)

MATCH_THRESHOLD = 0.85
EXACT_THRESHOLD = 0.97


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Dot product on L2-normalized vectors = cosine similarity."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a / norm_a, b / norm_b))


def match_prediction_to_fraud(
    prediction_embedding: np.ndarray,
    confirmed_embeddings: list[np.ndarray],
) -> dict:
    """
    Checks one prediction against all confirmed fraud embeddings.
    Returns the best match result dict.
    """
    if not confirmed_embeddings:
        return {"matched": False, "best_cosine": 0.0, "match_type": "no_data"}

    best_cosine = 0.0
    best_idx = -1

    for i, emb in enumerate(confirmed_embeddings):
        sim = cosine_similarity(prediction_embedding, emb)
        if sim > best_cosine:
            best_cosine = sim
            best_idx = i

    if best_cosine >= EXACT_THRESHOLD:
        match_type = "exact"
    elif best_cosine >= MATCH_THRESHOLD:
        match_type = "structural"
    else:
        match_type = "no_match"

    matched = best_cosine >= MATCH_THRESHOLD

    logger.debug(
        "Prophecy match result",
        matched=matched,
        best_cosine=round(best_cosine, 4),
        match_type=match_type,
        best_idx=best_idx,
    )

    return {
        "matched": matched,
        "best_cosine": round(best_cosine, 4),
        "match_type": match_type,
        "confirmed_fraud_index": best_idx if matched else None,
    }


def batch_match(
    predictions: list[tuple[str, np.ndarray]],
    confirmed_embeddings: list[np.ndarray],
) -> list[dict]:
    """
    Matches a batch of (genome_id, embedding) tuples against confirmed frauds.
    Returns one result dict per prediction.
    """
    results = []
    for genome_id, emb in predictions:
        result = match_prediction_to_fraud(emb, confirmed_embeddings)
        result["genome_id"] = genome_id
        results.append(result)
    return results
