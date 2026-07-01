"""
Recovery store — wires the engine to live case data + the Fraud DNA similarity
engine, caches per-case analyses, and computes the executive dashboard aggregate.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional

from case_management.store import store as case_store
from . import engine as E

# Fraud DNA similarity is optional — degrade gracefully if the module is absent.
try:
    from fraud_dna.store import store as _dna_store
except Exception:  # pragma: no cover
    _dna_store = None

_TTL = 60.0  # seconds — analyses are cheap but cache to keep the dashboard snappy


class RecoveryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: Dict[str, tuple[float, dict]] = {}

    def _similar(self, case_id: str) -> Optional[dict]:
        if not _dna_store:
            return None
        try:
            return _dna_store.similar(case_id)
        except Exception:
            return None

    def analyze(self, case_id: str, force: bool = False) -> Optional[dict]:
        case = case_store.get(case_id)
        if not case:
            return None
        now = time.time()
        with self._lock:
            hit = self._cache.get(case_id)
            if hit and not force and now - hit[0] < _TTL:
                return hit[1]
        result = E.analyze(case, self._similar(case_id), now)
        with self._lock:
            self._cache[case_id] = (now, result)
        return result

    def actions(self, case_id: str) -> Optional[List[dict]]:
        res = self.analyze(case_id)
        return res["actions"] if res else None

    def simulate(self, case_id: str, scenario: str, account: Optional[str] = None,
                 delay_hours: float = 0.0) -> Optional[dict]:
        case = case_store.get(case_id)
        if not case:
            return None
        return E.simulate(case, self._similar(case_id), scenario, account, delay_hours)

    # ── Executive dashboard ──────────────────────────────────────────────────
    def dashboard(self) -> dict:
        cases = case_store.all()
        rows: List[dict] = []
        total_recoverable = 0.0
        total_loss = 0.0
        prob_sum = 0
        act_now = 0

        for c in cases:
            res = self.analyze(c["case_id"])
            if not res:
                continue
            is_open = str(c.get("status", "")).lower() not in ("resolved", "closed", "false positive", "archived")
            recoverable = res["expected_recoverable"]
            loss = res["estimated_loss"]   # already net: originated − likely recoverable
            total_recoverable += recoverable if is_open else 0
            total_loss += loss if is_open else 0
            prob_sum += res["recovery_probability"]
            window_h = res["window_seconds"] / 3600.0
            # "act now": still open, still recoverable, and closing within 48h
            urgent = is_open and res["recovery_probability"] >= 45 and 0 < window_h <= 48
            if urgent:
                act_now += 1
            rows.append({
                "case_id": c["case_id"], "title": c.get("title"), "category": c.get("category"),
                "status": c.get("status"), "priority": c.get("priority"),
                "recovery_probability": res["recovery_probability"], "band": res["band"],
                "expected_recoverable": recoverable, "estimated_loss": loss,
                "headline_action": res["headline_action"], "window_seconds": res["window_seconds"],
                "urgent": urgent, "is_open": is_open,
            })

        n = len(rows) or 1
        rows.sort(key=lambda r: (r["urgent"], r["recovery_probability"], r["expected_recoverable"]), reverse=True)
        return {
            "total_recoverable": round(total_recoverable),
            "potential_loss_exposure": round(total_loss),
            "avg_recovery_probability": round(prob_sum / n),
            "cases_requiring_action": act_now,
            "case_count": len(rows),
            "cases": rows,
        }


store = RecoveryStore()
