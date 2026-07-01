from __future__ import annotations
"""
Strategy Memory — Red Team's compounding learning substrate.

Every time an attack EVADES Blue Team, the winning recipe (operator lineage +
the gene fingerprint that beat specific detectors) is recorded here. The LLM
strategist is primed with the most relevant past wins as few-shot exemplars, so
the Red Team gets progressively better at defeating the detectors that are
currently firing — it remembers what worked instead of re-deriving it.

This is Red-only learning. It never touches Blue Team and is independent of the
investigator gate (which governs whether Blue *learns*, not whether Red does).
Persisted as JSONL so learning survives restarts.
"""
import json
import logging
import os
import threading
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "data", "strategy_memory.jsonl")


@dataclass
class Strategy:
    family: str
    difficulty: str
    beaten_detectors: list[str]         # what Blue was firing before this won
    operators: list[str]                # mutation lineage that produced the evasion
    gene_fingerprint: dict              # compact, human-readable winning genes
    generations: int
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class StrategyMemory:
    def __init__(self, path: str | None = None) -> None:
        self._path = path or os.getenv("CRUCIBLE_STRATEGY_MEMORY", _DEFAULT_PATH)
        self._lock = threading.Lock()
        self._items: list[Strategy] = []
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        self._items.append(Strategy(**json.loads(line)))
        except (OSError, TypeError, json.JSONDecodeError) as exc:
            logger.error("Failed to load strategy memory: %s", exc)

    def record(self, strategy: Strategy) -> None:
        with self._lock:
            self._items.append(strategy)
            try:
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                with open(self._path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(strategy.to_dict()) + "\n")
            except OSError as exc:
                logger.error("Failed to persist strategy: %s", exc)

    def __len__(self) -> int:
        return len(self._items)

    def exemplars(self, beaten_detectors: list[str], k: int = 3) -> list[Strategy]:
        """Most relevant past wins: those that beat the detectors firing right now.

        Ranked by overlap with the current detector set, then recency. Used as
        few-shot context for the LLM strategist.
        """
        target = set(beaten_detectors)
        with self._lock:
            items = list(self._items)
        if not items:
            return []
        scored = sorted(
            items,
            key=lambda s: (len(target & set(s.beaten_detectors)), s.created_at),
            reverse=True,
        )
        return scored[:k]

    def stats(self) -> dict:
        with self._lock:
            items = list(self._items)
        det = Counter(d for s in items for d in s.beaten_detectors)
        fam = Counter(s.family for s in items)
        return {
            "total_strategies": len(items),
            "most_beaten_detectors": det.most_common(8),
            "top_families": fam.most_common(8),
        }
