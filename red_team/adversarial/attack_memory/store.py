"""
Attack Memory Database.

Stores every successful attack with enough provenance to (a) feed the Blue Team
hard examples during self-play, (b) cluster attacks into families, and (c) build
an attack genealogy. Persisted as JSON-lines so it survives across runs and is
trivially inspectable; an index keeps in-memory clustering cheap.

A "family" is keyed by the set of agents an attack uses (its technique
signature). The genealogy links a record to its parents via the genome's agent
lineage and the AttackGraph parent_ids.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..config import DATA_DIR


@dataclass
class AttackRecord:
    attack_id: str
    archetype: str
    target_engine: str
    genome: list[tuple[str, float]]       # [(agent, intensity), ...]
    agents: list[str]                      # technique signature (sorted unique)
    family: str                            # frozenset signature as a stable string
    baseline_verdict: str
    final_verdict: str
    detection_score: float
    cluster_risk: float
    distortion: float
    num_components: int
    residual_detectors: list[str]
    objective_ok: bool
    generation: int = 0
    parent_ids: list[str] = field(default_factory=list)
    ts: float = field(default_factory=time.time)


class AttackMemory:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else (DATA_DIR / "attack_memory.jsonl")
        self.records: list[AttackRecord] = []
        self._by_family: dict[str, list[AttackRecord]] = defaultdict(list)
        if self.path.exists():
            self._load()

    # ── persistence ──
    def _load(self) -> None:
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            rec = AttackRecord(**d)
            self.records.append(rec)
            self._by_family[rec.family].append(rec)

    def _append(self, rec: AttackRecord) -> None:
        with self.path.open("a") as fh:
            fh.write(json.dumps(asdict(rec)) + "\n")

    # ── api ──
    def remember(self, *, attack_id: str, archetype: str, target_engine: str,
                 genome, baseline_verdict: str, final_verdict: str,
                 detection_score: float, cluster_risk: float, distortion: float,
                 num_components: int, residual_detectors, objective_ok: bool,
                 generation: int = 0, parent_ids=None) -> AttackRecord:
        agents = sorted({m.agent for m in genome})
        rec = AttackRecord(
            attack_id=attack_id, archetype=archetype, target_engine=target_engine,
            genome=[(m.agent, round(m.intensity, 3)) for m in genome],
            agents=agents, family="+".join(agents) or "(identity)",
            baseline_verdict=baseline_verdict, final_verdict=final_verdict,
            detection_score=round(detection_score, 4), cluster_risk=round(cluster_risk, 4),
            distortion=round(distortion, 4), num_components=num_components,
            residual_detectors=sorted(residual_detectors), objective_ok=objective_ok,
            generation=generation, parent_ids=list(parent_ids or []),
        )
        self.records.append(rec)
        self._by_family[rec.family].append(rec)
        self._append(rec)
        return rec

    def families(self) -> dict[str, int]:
        """Attack families (technique signatures) → population size."""
        return {fam: len(recs) for fam, recs in sorted(
            self._by_family.items(), key=lambda kv: -len(kv[1]))}

    def genealogy(self) -> dict:
        """
        Group successful attacks into a family tree: each technique-family node,
        the archetypes it defeats, and its cheapest (lowest-distortion) exemplar.
        """
        tree: dict[str, dict] = {}
        for fam, recs in self._by_family.items():
            best = min(recs, key=lambda r: r.distortion)
            tree[fam] = {
                "size": len(recs),
                "agents": best.agents,
                "defeats_archetypes": sorted({r.archetype for r in recs}),
                "cheapest_distortion": best.distortion,
                "best_verdict": min((r.final_verdict for r in recs),
                                    key=lambda v: {"CLEAN": 0, "LOGGED": 1,
                                                   "SUSPICIOUS": 2, "FRAUD": 3}.get(v, 3)),
            }
        return dict(sorted(tree.items(), key=lambda kv: -kv[1]["size"]))

    def hard_examples(self, limit: int | None = None) -> list[AttackRecord]:
        """Successful (evading, objective-intact) attacks for Blue Team retraining."""
        ev = [r for r in self.records
              if r.objective_ok and r.final_verdict in ("CLEAN", "LOGGED")]
        ev.sort(key=lambda r: (r.detection_score, r.distortion))
        return ev[:limit] if limit else ev
