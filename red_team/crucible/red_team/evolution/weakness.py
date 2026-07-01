from __future__ import annotations
"""
Blue Team Weakness Discovery + AI Attack Planner.

The engine records every attack's outcome here. The map maintains, per fraud
category and per V2 detector, how often Blue caught vs missed. From that it builds
a live Weakness Report (detection % per category) and a planner that deliberately
samples the WEAKEST categories — attacking where Blue is blind rather than at
random. Unexplored categories get optimistic priority so coverage stays broad.
"""
import random
from collections import defaultdict
from dataclasses import dataclass, field

from red_team.evolution import library


@dataclass
class CategoryStat:
    attempts: int = 0
    detections: int = 0           # Blue caught the BEST (evolved) variant
    evasions: int = 0             # Blue missed it (a successful attack)
    generations_to_evade: list[int] = field(default_factory=list)

    @property
    def detection_rate(self) -> float:
        return round(self.detections / self.attempts, 4) if self.attempts else 0.0

    @property
    def evasion_rate(self) -> float:
        return round(self.evasions / self.attempts, 4) if self.attempts else 0.0


class WeaknessMap:
    """Live model of where Blue Team V2 is strong vs blind."""

    def __init__(self) -> None:
        self._cats: dict[str, CategoryStat] = defaultdict(CategoryStat)
        self._detector_fires: dict[str, int] = defaultdict(int)
        self._detector_misses: dict[str, int] = defaultdict(int)

    def record(self, category: str, detected: bool, detectors: list[str],
               generations: int) -> None:
        stat = self._cats[category]
        stat.attempts += 1
        if detected:
            stat.detections += 1
        else:
            stat.evasions += 1
            stat.generations_to_evade.append(generations)
        for det in detectors:
            self._detector_fires[det] += 1

    def detection_rate(self, category: str) -> float:
        return self._cats[category].detection_rate if category in self._cats else 0.0

    def report(self) -> dict:
        """Weakness report: detection % per category + detector strength."""
        cats = {}
        for cat in library.CATEGORIES:
            s = self._cats.get(cat)
            if s is None:
                cats[cat] = {"attempts": 0, "detection_rate": None, "status": "unexplored"}
            else:
                avg_gen = (round(sum(s.generations_to_evade) / len(s.generations_to_evade), 2)
                           if s.generations_to_evade else None)
                cats[cat] = {
                    "attempts": s.attempts,
                    "detections": s.detections,
                    "evasions": s.evasions,
                    "detection_rate": s.detection_rate,
                    "avg_generations_to_evade": avg_gen,
                    "status": self._status(s.detection_rate),
                }
        ranked = sorted(
            (c for c in cats if cats[c]["detection_rate"] is not None),
            key=lambda c: cats[c]["detection_rate"],
        )
        return {
            "categories": cats,
            "weakest": ranked[:5],
            "strongest": list(reversed(ranked[-5:])),
            "detector_strength": dict(sorted(self._detector_fires.items(),
                                             key=lambda kv: kv[1], reverse=True)),
        }

    @staticmethod
    def _status(rate: float) -> str:
        if rate >= 0.9:
            return "strong"
        if rate >= 0.6:
            return "moderate"
        if rate >= 0.3:
            return "weak"
        return "blind_spot"

    # ── planner ──────────────────────────────────────────────────────────────
    def plan_target_category(self, rng: random.Random) -> str:
        """Pick a category to attack, biased toward Blue's weak spots.

        Unexplored categories get high optimistic weight (explore); explored ones
        are weighted by (1 - detection_rate) so blind spots are hammered hardest.
        """
        weights = []
        for cat in library.CATEGORIES:
            s = self._cats.get(cat)
            if s is None or s.attempts == 0:
                weights.append((cat, 1.0))                       # optimistic explore
            else:
                weights.append((cat, 0.05 + (1.0 - s.detection_rate)))  # exploit weakness
        cats = [c for c, _ in weights]
        w = [x for _, x in weights]
        return rng.choices(cats, weights=w, k=1)[0]
