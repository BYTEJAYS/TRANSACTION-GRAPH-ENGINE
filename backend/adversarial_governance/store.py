"""
Training-queue + audit store — in-memory with JSON persistence (mirrors
case_management/store.py's style: a threading lock + atomic temp-file replace).

This is the ONLY door into the Blue Team's knowledge base. A Red Team evasion the
Blue Team MISSED is enqueued here as a pending case; it becomes training data only
after an investigator's explicit "learn" decision, which is deduped against the
existing knowledge base and recorded in the audit trail.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Dict, List, Optional

_DATA_FILE = os.getenv(
    "TGIE_TRAINING_STORE",
    os.path.join(os.path.dirname(__file__), "_data", "training_queue.json"),
)

# Case lifecycle states.
PENDING, LEARNED, REJECTED, ARCHIVED, IGNORED, REVIEWING = (
    "pending", "learned", "rejected", "archived", "ignored", "reviewing"
)
_TERMINAL = {LEARNED, REJECTED, ARCHIVED, IGNORED}


def _now() -> float:
    return time.time()


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts))


def _signature(fraud_type: str, techniques: List[str]) -> str:
    """Stable identity of an attack pattern for dedup: fraud type + its technique set."""
    techs = "+".join(sorted(t for t in techniques if t and t != "(identity)"))
    return f"{(fraud_type or '').strip().lower()}|{techs}"


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class GovernanceStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cases: Dict[str, dict] = {}
        self._audit: List[dict] = []
        # signature -> knowledge-base entry {case_id, count, signature, learned_at}
        self._knowledge: Dict[str, dict] = {}
        self._seq = 0
        self._load()

    # ── persistence ──────────────────────────────────────────────────────────
    def _load(self) -> None:
        try:
            with open(_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._cases = data.get("cases", {})
            self._audit = data.get("audit", [])
            self._knowledge = data.get("knowledge", {})
            self._seq = data.get("seq", len(self._cases))
        except Exception:
            self._cases, self._audit, self._knowledge, self._seq = {}, [], {}, 0

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(_DATA_FILE), exist_ok=True)
            tmp = f"{_DATA_FILE}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"cases": self._cases, "audit": self._audit,
                           "knowledge": self._knowledge, "seq": self._seq}, f, indent=2)
            os.replace(tmp, _DATA_FILE)
        except Exception:
            pass

    def _next_id(self) -> str:
        self._seq += 1
        return f"FRAUD-{self._seq:04d}"

    def _audit_event(self, case: dict, decision: str, training_status: str,
                     investigator: str, note: str = "") -> dict:
        entry = {
            "case_id": case["case_id"],
            "candidate_id": case["candidate_id"],
            "generated_by": "Red Team",
            "blue_result": case["detection_status"],
            "investigator": investigator,
            "decision": decision,
            "training_status": training_status,
            "note": note,
            "time": _iso(_now()),
            "ts": _now(),
        }
        self._audit.insert(0, entry)
        return entry

    # ── enqueue (Red miss → Training Queue) ────────────────────────────────────
    def enqueue(self, candidate: dict) -> Optional[dict]:
        """Add a MISSED Red Team evasion to the queue. Deduped by candidate id so
        repeated /attacks calls never create duplicate queue entries. Returns the
        case (existing or new), or None if the candidate isn't a queue-worthy miss."""
        with self._lock:
            cand_id = candidate.get("id")
            if not cand_id:
                return None
            # Only Blue-MISSED, real on-graph evasions belong in the learning queue.
            if not (candidate.get("trainable") and not candidate.get("blue_catches")):
                return None
            # Dedup on candidate id (idempotent enqueue).
            for c in self._cases.values():
                if c["candidate_id"] == cand_id:
                    return c

            techniques = [t for t in (candidate.get("techniques") or []) if t]
            native = candidate.get("native", {}) or {}
            hardened = candidate.get("hardened", {}) or {}
            risk = float(native.get("risk", 0.0) or 0.0)
            sig = _signature(candidate.get("archetype", ""), techniques)
            case_id = self._next_id()
            case = {
                "case_id": case_id,
                "candidate_id": cand_id,
                "created_at": _now(),
                "created_iso": _iso(_now()),
                "detection_status": "Missed",      # only misses are enqueued
                # RT confidence = how strongly it evaded; BT confidence = its native risk.
                "red_confidence": round(1.0 - risk, 3),
                "blue_confidence": round(risk, 3),
                "fraud_type": candidate.get("archetype", "unknown"),
                "risk_score": round(risk, 3),
                "explanation": self._why_missed(candidate),
                "techniques": techniques,
                "signature": sig,
                "graph": candidate.get("graph"),
                "nodes_total": candidate.get("nodes_total"),
                "edges_total": candidate.get("edges_total"),
                "status": PENDING,
                "decided_by": None,
                "decided_at": None,
                "duplicate_of": None,
            }
            self._cases[case_id] = case
            self._audit_event(case, decision="enqueued", training_status="Pending review",
                              investigator="TGIE Adversarial Engine",
                              note="Blue Team missed a real on-graph evasion")
            self._save()
            return case

    @staticmethod
    def _why_missed(candidate: dict) -> str:
        hardened = candidate.get("hardened", {}) or {}
        sig = hardened.get("signal")
        base = candidate.get("reason", "real on-graph evasion the deployed Blue Team did not flag")
        if sig and sig != "native":
            return f"{base}. Only the hardened '{sig}' detector caught it — the deployed Blue Team did not."
        return base

    # ── dedup / similarity ─────────────────────────────────────────────────────
    def similar(self, case_id: str) -> List[dict]:
        """Cases (in any state) sharing the same signature or a close technique set."""
        with self._lock:
            target = self._cases.get(case_id)
            if not target:
                return []
            t_techs = set(target["techniques"])
            out = []
            for c in self._cases.values():
                if c["case_id"] == case_id:
                    continue
                exact = c["signature"] == target["signature"]
                jac = _jaccard(set(c["techniques"]), t_techs)
                same_type = c["fraud_type"] == target["fraud_type"]
                # Exact = identical pattern (dedup target). Similar = same fraud type
                # OR a substantial technique overlap — surfaced for investigator compare.
                if exact or same_type or jac >= 0.5:
                    out.append({**self.summary(c), "match": "exact" if exact else "similar",
                                "technique_overlap": round(jac, 2)})
            out.sort(key=lambda x: (x["match"] != "exact", -x["technique_overlap"]))
            return out

    def _known_signature(self, sig: str) -> Optional[dict]:
        return self._knowledge.get(sig)

    # ── investigator decision (the ONLY path into the knowledge base) ──────────
    def decide(self, case_id: str, action: str, investigator: str = "investigator") -> dict:
        """Apply an investigator decision. Returns {ok, case, audit, dedup?}."""
        with self._lock:
            case = self._cases.get(case_id)
            if not case:
                return {"ok": False, "error": "case not found"}
            act = (action or "").lower()

            if act in ("review", "review_first"):
                case["status"] = REVIEWING
                entry = self._audit_event(case, "review_first", "Under review", investigator)
                self._save()
                return {"ok": True, "case": case, "audit": entry}

            if act in ("reject", "ignore", "archive"):
                case["status"] = {"reject": REJECTED, "ignore": IGNORED, "archive": ARCHIVED}[act]
                case["decided_by"], case["decided_at"] = investigator, _now()
                entry = self._audit_event(case, act, "Discarded — not added to Blue Knowledge Base",
                                          investigator)
                self._save()
                return {"ok": True, "case": case, "audit": entry}

            if act in ("learn", "approve"):
                sig = case["signature"]
                existing = self._known_signature(sig)
                if existing is not None:
                    # Duplicate — merge into the existing knowledge entry rather than
                    # adding a second copy (prevents training-data bloat / over-weighting).
                    existing["count"] = int(existing.get("count", 1)) + 1
                    existing["last_merged_at"] = _now()
                    case["status"] = LEARNED
                    case["duplicate_of"] = existing["case_id"]
                    case["decided_by"], case["decided_at"] = investigator, _now()
                    entry = self._audit_event(
                        case, "learn", "Merged into existing knowledge entry", investigator,
                        note=f"duplicate of {existing['case_id']} (signature already known)")
                    self._save()
                    return {"ok": True, "case": case, "audit": entry,
                            "dedup": {"merged_into": existing["case_id"], "count": existing["count"]}}

                # New pattern → add to the Blue Knowledge Base.
                self._knowledge[sig] = {
                    "case_id": case_id, "signature": sig, "count": 1,
                    "fraud_type": case["fraud_type"], "techniques": case["techniques"],
                    "candidate_id": case["candidate_id"], "learned_at": _now(),
                }
                case["status"] = LEARNED
                case["decided_by"], case["decided_at"] = investigator, _now()
                entry = self._audit_event(case, "learn", "Added to Blue Knowledge Base", investigator)
                self._save()
                return {"ok": True, "case": case, "audit": entry,
                        "dedup": {"merged_into": None, "count": 1}}

            return {"ok": False, "error": f"unknown action {action!r}"}

    # ── queries ────────────────────────────────────────────────────────────────
    def summary(self, c: dict) -> dict:
        return {
            "case_id": c["case_id"], "candidate_id": c["candidate_id"],
            "created_iso": c["created_iso"], "detection_status": c["detection_status"],
            "red_confidence": c["red_confidence"], "blue_confidence": c["blue_confidence"],
            "fraud_type": c["fraud_type"], "risk_score": c["risk_score"],
            "explanation": c["explanation"], "techniques": c["techniques"],
            "status": c["status"], "duplicate_of": c.get("duplicate_of"),
            "nodes_total": c.get("nodes_total"), "edges_total": c.get("edges_total"),
            "signature": c.get("signature"), "graph": c.get("graph"),
        }

    def get(self, case_id: str) -> Optional[dict]:
        with self._lock:
            return self._cases.get(case_id)

    def list(self, status: Optional[str] = None) -> List[dict]:
        with self._lock:
            items = list(self._cases.values())
            if status:
                items = [c for c in items if c["status"] == status]
            items.sort(key=lambda c: c["created_at"], reverse=True)
            return [self.summary(c) for c in items]

    def audit(self, limit: int = 100) -> List[dict]:
        with self._lock:
            return list(self._audit[:limit])

    def stats(self) -> dict:
        with self._lock:
            by = {}
            for c in self._cases.values():
                by[c["status"]] = by.get(c["status"], 0) + 1
            return {
                "total": len(self._cases),
                "pending": by.get(PENDING, 0),
                "reviewing": by.get(REVIEWING, 0),
                "learned": by.get(LEARNED, 0),
                "rejected": by.get(REJECTED, 0),
                "archived": by.get(ARCHIVED, 0),
                "ignored": by.get(IGNORED, 0),
                "knowledge_base": len(self._knowledge),
                "audit_events": len(self._audit),
            }

    def reset(self) -> None:
        with self._lock:
            self._cases.clear()
            self._audit.clear()
            self._knowledge.clear()
            self._seq = 0
            self._save()


store = GovernanceStore()
