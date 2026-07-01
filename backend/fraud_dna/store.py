"""
Fraud DNA store — builds & caches DNA profiles, runs the similarity engine,
comparison, trend/executive aggregates and prediction.

DNA IDs are deterministic per case; a per-case signature history is persisted so
DNA *evolution* (v1 → v2 → v3) can be tracked as a case's behaviour changes.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import Counter
from typing import Dict, List, Optional

from case_management.store import store as case_store
from . import engine as E

_DATA_FILE = os.getenv(
    "TGIE_DNA_STORE",
    os.path.join(os.path.dirname(__file__), "_data", "dna.json"),
)


class DNAStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._profiles: Dict[str, dict] = {}   # case_id -> {dna_id, type, history:[...]}
        self._load()

    def _load(self) -> None:
        try:
            with open(_DATA_FILE, "r", encoding="utf-8") as f:
                self._profiles = json.load(f).get("profiles", {})
        except Exception:
            self._profiles = {}

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(_DATA_FILE), exist_ok=True)
            tmp = f"{_DATA_FILE}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"profiles": self._profiles}, f, indent=2)
            os.replace(tmp, _DATA_FILE)
        except Exception:
            pass

    # ── build a full profile for a case ──────────────────────────────────────
    def _record_version(self, case_id: str, dna_id: str, dtype: str, sig: str, scores: List[int]) -> dict:
        with self._lock:
            p = self._profiles.get(case_id)
            now = time.time()
            if not p:
                p = {"dna_id": dna_id, "type": dtype, "history": []}
                self._profiles[case_id] = p
            if not p["history"] or p["history"][-1]["signature"] != sig:
                p["history"].append({"signature": sig, "ts": now, "scores": scores})
                self._save()
            return p

    def profile(self, case_id: str) -> Optional[dict]:
        case = case_store.get(case_id)
        if not case:
            return None
        return self._profile_from_case(case)

    def _profile_from_case(self, case: dict) -> dict:
        genes = E.build_genes(case)
        dtype = E.dna_type(case)
        dna_id = E.dna_id_for(case["case_id"], dtype)
        sig = E.signature(genes)
        impact = E.risk_impact(case, genes)
        rec = self._record_version(case["case_id"], dna_id, dtype, sig, [g["score"] for g in genes])
        return {
            "case_id": case["case_id"], "title": case["title"], "category": case["category"],
            "dna_id": dna_id, "dna_type": dtype, "signature": sig,
            "genes": genes, "vector": E.vector(genes),
            "risk_impact": impact, "version": len(rec["history"]),
            "history": rec["history"],
        }

    # ── similarity ───────────────────────────────────────────────────────────
    def similar(self, case_id: str, k: int = 5) -> dict:
        case = case_store.get(case_id)
        if not case:
            return {"case_id": case_id, "matches": [], "prediction": None}
        a_genes = E.build_genes(case)
        matches = []
        for other in case_store.all():
            if other["case_id"] == case["case_id"]:
                continue
            b_genes = E.build_genes(other)
            sim = E.similarity_pct(a_genes, b_genes)
            matches.append({
                "case_id": other["case_id"], "title": other["title"], "category": other["category"],
                "status": other["status"], "dna_id": E.dna_id_for(other["case_id"], E.dna_type(other)),
                "similarity": sim, "reasons": E.matching_reasons(a_genes, b_genes),
            })
        matches.sort(key=lambda m: m["similarity"], reverse=True)
        matches = matches[:k]
        return {
            "case_id": case_id,
            "dna_id": E.dna_id_for(case_id, E.dna_type(case)),
            "matches": matches,
            "prediction": self._predict(case, matches),
            "explanation": E.explain(case, a_genes, E.dna_type(case), matches[0] if matches else None),
        }

    def _predict(self, case: dict, matches: List[dict]) -> dict:
        if not matches:
            return {"predicted_pattern": case["category"], "confidence": 0,
                    "escalation_probability": 0, "expansion_probability": 0}
        top = matches[: min(4, len(matches))]
        cats = Counter(m["category"] for m in top)
        full = [case_store.get(m["case_id"]) for m in top]
        full = [c for c in full if c]
        escalated = sum(1 for c in full if c["status"] in ("Escalated", "Active Investigation") or c["priority"] == "Critical")
        avg_accounts = (sum(len(c["accounts"]) for c in full) / len(full)) if full else 0
        return {
            "predicted_pattern": cats.most_common(1)[0][0],
            "confidence": top[0]["similarity"],
            "escalation_probability": round(escalated / len(top) * 100),
            "expansion_probability": min(100, round(avg_accounts * 12)),
        }

    # ── comparison ───────────────────────────────────────────────────────────
    def compare(self, a_id: str, b_id: str) -> Optional[dict]:
        a, b = case_store.get(a_id), case_store.get(b_id)
        if not a or not b:
            return None
        ag, bg = E.build_genes(a), E.build_genes(b)
        deltas = E.gene_deltas(ag, bg)
        amap = {g["name"]: g["score"] for g in ag}
        bmap = {g["name"]: g["score"] for g in bg}
        dim = lambda n: 100 - abs(amap[n] - bmap[n])  # noqa: E731
        return {
            "a": {"case_id": a["case_id"], "title": a["title"], "dna_id": E.dna_id_for(a["case_id"], E.dna_type(a))},
            "b": {"case_id": b["case_id"], "title": b["title"], "dna_id": E.dna_id_for(b["case_id"], E.dna_type(b))},
            "similarity": E.similarity_pct(ag, bg),
            "matching_genes": [d["gene"] for d in deltas if d["match"]],
            "different_genes": [d["gene"] for d in deltas if not d["match"]],
            "gene_deltas": deltas,
            "risk_similarity": dim("Risk"),
            "structural_similarity": dim("Structure"),
            "behaviour_similarity": dim("Behavior"),
            "genes_a": ag, "genes_b": bg,
        }

    # ── executive aggregates ─────────────────────────────────────────────────
    def trends(self) -> dict:
        cases = case_store.all()
        rows = []
        for c in cases:
            genes = E.build_genes(c)
            rows.append({"case_id": c["case_id"], "type": E.dna_type(c),
                         "impact": E.risk_impact(c, genes), "created_at": c["created_at"],
                         "status": c["status"]})
        type_counts = Counter(r["type"] for r in rows)
        now = time.time()
        recent = [r for r in rows if now - r["created_at"] < 86400 * 14]
        emerging = Counter(r["type"] for r in recent)
        by_type_impact: Dict[str, List[int]] = {}
        for r in rows:
            by_type_impact.setdefault(r["type"], []).append(r["impact"])
        highest = sorted(((t, round(sum(v) / len(v))) for t, v in by_type_impact.items()),
                         key=lambda x: x[1], reverse=True)
        return {
            "total_dna": len(rows),
            "common_types": type_counts.most_common(),
            "emerging_types": emerging.most_common(5),
            "highest_risk_types": highest,
            "fastest_growing": emerging.most_common(3),
        }

    def high_risk(self, limit: int = 10) -> List[dict]:
        rows = []
        for c in case_store.all():
            genes = E.build_genes(c)
            rows.append({
                "case_id": c["case_id"], "title": c["title"], "category": c["category"],
                "dna_id": E.dna_id_for(c["case_id"], E.dna_type(c)), "dna_type": E.dna_type(c),
                "risk_impact": E.risk_impact(c, genes), "status": c["status"], "priority": c["priority"],
            })
        rows.sort(key=lambda r: r["risk_impact"], reverse=True)
        return rows[:limit]

    def find_by_dna(self, dna_id: str) -> List[dict]:
        out = []
        for c in case_store.all():
            if E.dna_id_for(c["case_id"], E.dna_type(c)).upper() == dna_id.upper():
                out.append(self._profile_from_case(c))
        return out

    def ensure_all(self) -> None:
        """Generate (and version) DNA for every existing case — called at startup."""
        for c in case_store.all():
            self._profile_from_case(c)


store = DNAStore()
store.ensure_all()
