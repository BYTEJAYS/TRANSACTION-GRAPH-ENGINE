from __future__ import annotations
"""
Novelty Critic — two-layer deduplication:
1. Bloom filter: O(1) exact fingerprint check (exact duplicates → 0.0)
2. FAISS IndexFlatIP: cosine similarity via dot product on 256-d L2-norm vectors

Thresholds:
  cosine > 0.97  → exact_duplicate   (score 0.0)
  0.85–0.97      → near_duplicate    (score 0.1)
  < 0.85         → novel             (score 1.0, linear boost above 0.85)

We use IndexFlatIP (inner product) on pre-normalized vectors so that
dot product = cosine similarity — avoids IndexFlatL2 distance → similarity conversion.
"""
import logging
from typing import TYPE_CHECKING

import numpy as np

from red_team.core.fingerprint import compute_embedding, compute_fingerprint

if TYPE_CHECKING:
    from red_team.core.genome import FraudGenome

logger = logging.getLogger(__name__)

_EXACT_THRESHOLD = 0.97
_NEAR_THRESHOLD = 0.85
_POPULATION_CAPACITY = 10_000  # max vectors before index rebuild


class NoveltyCritic:
    """
    Thread-unsafe by design — runs inside a single PBT worker process.
    If multiple workers are needed, each gets its own NoveltyCritic instance.
    """

    def __init__(self) -> None:
        self._bloom: set[str] = set()  # fingerprint strings (hex)
        self._index = None              # faiss.IndexFlatIP, lazy-init
        self._vectors: list[np.ndarray] = []  # parallel list to index
        self._genome_ids: list[str] = []

    def _ensure_index(self) -> None:
        if self._index is None:
            try:
                import faiss
                self._index = faiss.IndexFlatIP(256)
            except ImportError:
                logger.warning("faiss not available — novelty uses bloom-only mode")
                self._index = _FallbackIndex()

    def add(self, genome: "FraudGenome") -> None:
        """Register genome in both dedup layers. Call after it passes fitness threshold."""
        fp = compute_fingerprint(genome)
        self._bloom.add(fp)

        self._ensure_index()
        vec = compute_embedding(genome).astype(np.float32).reshape(1, -1)
        self._index.add(vec)
        self._vectors.append(vec)
        self._genome_ids.append(genome.genome_id)

        if len(self._vectors) > _POPULATION_CAPACITY:
            # Trim oldest 20% to keep memory bounded
            trim = _POPULATION_CAPACITY // 5
            self._vectors = self._vectors[trim:]
            self._genome_ids = self._genome_ids[trim:]
            self._rebuild_index()

    def _rebuild_index(self) -> None:
        try:
            import faiss
            self._index = faiss.IndexFlatIP(256)
        except ImportError:
            self._index = _FallbackIndex()
        if self._vectors:
            matrix = np.vstack(self._vectors).astype(np.float32)
            self._index.add(matrix)

    def score(self, genome: "FraudGenome") -> float:
        """
        Returns novelty score in [0.0, 1.0].
        0.0 = exact duplicate. 0.1 = near duplicate. 0.1–1.0 = novel (linear).
        """
        fp = compute_fingerprint(genome)

        # Layer 1: bloom exact check
        if fp in self._bloom:
            logger.debug("Bloom hit (exact duplicate)", genome_id=genome.genome_id[:8])
            return 0.0

        # Layer 2: FAISS cosine similarity
        self._ensure_index()
        if len(self._vectors) == 0:
            return 1.0  # empty index → everything is novel

        vec = compute_embedding(genome).astype(np.float32).reshape(1, -1)
        k = min(5, len(self._vectors))
        distances, _ = self._index.search(vec, k)

        max_cosine = float(distances[0][0]) if len(distances[0]) > 0 else 0.0

        if max_cosine >= _EXACT_THRESHOLD:
            logger.debug(
                "FAISS near-exact duplicate",
                genome_id=genome.genome_id[:8],
                cosine=round(max_cosine, 4),
            )
            return 0.0

        if max_cosine >= _NEAR_THRESHOLD:
            logger.debug(
                "FAISS near-duplicate",
                genome_id=genome.genome_id[:8],
                cosine=round(max_cosine, 4),
            )
            return 0.1

        # Linear novelty: 1.0 at cosine=0, 0.1 at cosine=0.85
        # Maps [0, 0.85] → [1.0, 0.1]
        novelty = 1.0 - (max_cosine / _NEAR_THRESHOLD) * 0.9
        return round(min(1.0, max(0.1, novelty)), 4)

    def __len__(self) -> int:
        return len(self._vectors)


class _FallbackIndex:
    """Pure-numpy cosine index used when faiss is not installed."""

    def __init__(self) -> None:
        self._matrix: np.ndarray | None = None

    def add(self, vectors: np.ndarray) -> None:
        if self._matrix is None:
            self._matrix = vectors
        else:
            self._matrix = np.vstack([self._matrix, vectors])

    def search(self, query: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
        if self._matrix is None or len(self._matrix) == 0:
            return np.array([[0.0]]), np.array([[0]])
        sims = (self._matrix @ query.T).flatten()
        top_k = min(k, len(sims))
        idx = np.argsort(sims)[::-1][:top_k]
        return sims[idx].reshape(1, -1), idx.reshape(1, -1)


# Module-level singleton
novelty_critic = NoveltyCritic()
