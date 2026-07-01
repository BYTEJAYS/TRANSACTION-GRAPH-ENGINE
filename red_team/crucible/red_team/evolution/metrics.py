from __future__ import annotations
"""
Performance Metrics — the measurable output of the adversarial campaign.

Tracks Blue's detection rate, false positives/negatives, evolution effort, and
which mutations/detectors matter most. Everything here is descriptive analytics
over completed attacks; it changes nothing in Blue or Red.
"""
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class CampaignMetrics:
    attacks: int = 0
    detected: int = 0                 # Blue caught the best evolved variant
    evaded: int = 0                   # a successful (missed) attack
    false_positives: int = 0          # legit nodes Blue flagged
    false_negatives: int = 0          # fraud nodes Blue missed on an evaded attack
    total_generations: int = 0
    gens_to_detection: list[int] = field(default_factory=list)
    gens_to_evasion: list[int] = field(default_factory=list)
    bypassed_detectors: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    effective_mutations: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    timeline: list[int] = field(default_factory=list)  # 1=detected, 0=evaded, per attack

    def record(self, *, detected: bool, generations: int, false_positives: int,
               false_negatives: int, last_evidence: list[str],
               winning_mutation: str | None) -> None:
        self.attacks += 1
        self.total_generations += generations
        self.false_positives += false_positives
        self.timeline.append(1 if detected else 0)
        if detected:
            self.detected += 1
            self.gens_to_detection.append(generations)
            for det in last_evidence:
                self.bypassed_detectors[det] += 0  # seen but not bypassed
        else:
            self.evaded += 1
            self.false_negatives += false_negatives
            self.gens_to_evasion.append(generations)
            # The detectors that were firing but the final variant slipped past.
            for det in last_evidence:
                self.bypassed_detectors[det] += 1
            if winning_mutation:
                self.effective_mutations[winning_mutation] += 1

    @staticmethod
    def _avg(xs: list[int]) -> float | None:
        return round(sum(xs) / len(xs), 2) if xs else None

    @staticmethod
    def _top(d: dict[str, int]) -> str | None:
        items = [(k, v) for k, v in d.items() if v > 0]
        return max(items, key=lambda kv: kv[1])[0] if items else None

    def learning_curve(self, window: int = 10) -> dict:
        """Rolling Blue detection rate over time — falls as Red gets harder to catch."""
        tl = self.timeline
        if not tl:
            return {"window": window, "points": [], "first": None, "last": None,
                    "improving": None}
        pts = [round(sum(tl[max(0, i - window + 1):i + 1])
                     / len(tl[max(0, i - window + 1):i + 1]), 3)
               for i in range(len(tl))]
        first = round(sum(tl[:window]) / len(tl[:window]), 3)
        last = round(sum(tl[-window:]) / len(tl[-window:]), 3)
        return {"window": window, "points": pts[-60:], "first": first, "last": last,
                "improving": last < first}

    def snapshot(self, weakness_report: dict | None = None) -> dict:
        detection_rate = round(self.detected / self.attacks, 4) if self.attacks else None
        weakest = strongest = None
        if weakness_report:
            weakest = (weakness_report.get("weakest") or [None])[0]
            strongest = (weakness_report.get("strongest") or [None])[0]
        return {
            "attacks": self.attacks,
            "blue_detection_rate": detection_rate,
            "detected": self.detected,
            "evaded": self.evaded,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "avg_generations_to_detection": self._avg(self.gens_to_detection),
            "avg_generations_to_evasion": self._avg(self.gens_to_evasion),
            "avg_evolution_count": (round(self.total_generations / self.attacks, 2)
                                    if self.attacks else None),
            "weakest_category": weakest,
            "strongest_category": strongest,
            "top_bypassed_detector": self._top(self.bypassed_detectors),
            "most_effective_mutation": self._top(self.effective_mutations),
        }
