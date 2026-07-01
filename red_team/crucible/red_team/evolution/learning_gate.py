from __future__ import annotations
"""
Learning Gate — the investigator-in-control safety boundary.

ARCHITECTURAL INVARIANT (the whole point of this task):
  The Red Team NEVER automatically injects a discovered fraud into Blue Team.
  A successful (Blue-missed) attack becomes a PENDING investigator alert. Only an
  investigator can APPROVE it, and approval merely appends the pattern to a
  curated "hardening backlog" — a training/triage queue for Blue Team owners.
  Approval here does NOT call, import, retrain, or mutate Blue Team V2 in any way.

To make that guarantee structural rather than a promise, this module imports
nothing from `blue_team_v2` and exposes no path that reaches it. `self_check()`
asserts the invariant at import/startup.

The backlog persists as JSONL so an approved decision survives restarts (the
in-memory alert queue does not — alerts are session-scoped review state).
"""
import json
import logging
import os
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_BACKLOG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "data", "hardening_backlog.jsonl")
_DEFAULT_ALERTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "data", "investigator_alerts.jsonl")

PENDING, APPROVED, REJECTED = "pending", "approved", "rejected"


@dataclass
class InvestigatorAlert:
    alert_id: str
    genome_id: str
    attack_family: str
    weakness_targeted: str
    difficulty: str
    generation: int
    blue_verdict: str
    blue_confidence: float
    blue_risk: float
    rupees_at_risk: float
    genome_summary: dict[str, Any]
    scenario_summary: dict[str, Any]
    status: str = PENDING
    decision_notes: str | None = None
    decided_by: str | None = None
    decided_at: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {**self.__dict__}


class LearningGate:
    """Holds Blue-missed attacks for investigator decision. Approval-only learning."""

    def __init__(self, backlog_path: str | None = None,
                 alerts_path: str | None = None) -> None:
        self._alerts: dict[str, InvestigatorAlert] = {}
        self._lock = threading.RLock()
        self._backlog_path = backlog_path or os.getenv(
            "CRUCIBLE_HARDENING_BACKLOG", _DEFAULT_BACKLOG)
        self._alerts_path = alerts_path or os.getenv(
            "CRUCIBLE_ALERTS_STORE", _DEFAULT_ALERTS)
        self.self_check()
        self._load_alerts()

    # ── durable alert queue (survives restart) ────────────────────────────────
    def _load_alerts(self) -> None:
        """Rehydrate pending/decided alerts so the investigator queue is durable."""
        if not os.path.exists(self._alerts_path):
            return
        try:
            with open(self._alerts_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    self._alerts[d["alert_id"]] = InvestigatorAlert(**d)
        except (OSError, TypeError, json.JSONDecodeError) as exc:
            logger.error("Failed to load alerts store: %s", exc)

    def _persist_alerts(self) -> None:
        """Rewrite the alert store (small, session-scoped review state)."""
        try:
            os.makedirs(os.path.dirname(self._alerts_path), exist_ok=True)
            tmp = self._alerts_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                for alert in self._alerts.values():
                    fh.write(json.dumps(alert.to_dict()) + "\n")
            os.replace(tmp, self._alerts_path)
        except OSError as exc:
            logger.error("Failed to persist alerts store: %s", exc)

    # ── safety invariant ──────────────────────────────────────────────────────
    @staticmethod
    def self_check() -> None:
        """Fail loudly if this module ever gained a coupling to Blue Team V2.

        The guarantee is structural: this file imports nothing from `blue_team_v2`,
        so no name in its namespace should reference it and the engine module
        object must hold no such binding.
        """
        mod = sys.modules.get(__name__)
        if mod is None:
            return
        for name, value in vars(mod).items():
            assert "blue_team_v2" not in name, f"Learning gate coupled to Blue via {name!r}"
            modname = getattr(value, "__module__", "") or ""
            assert "blue_team_v2" not in modname, \
                f"Learning gate imported Blue symbol {name!r} from {modname!r}"

    # ── alert lifecycle ───────────────────────────────────────────────────────
    def register_missed_attack(
        self, *, genome_id: str, attack_family: str, weakness_targeted: str,
        difficulty: str, generation: int, blue_verdict: str, blue_confidence: float,
        blue_risk: float, rupees_at_risk: float, genome_summary: dict[str, Any],
        scenario_summary: dict[str, Any],
    ) -> InvestigatorAlert:
        """Queue a Blue-missed attack for investigator review. Does NOT train Blue."""
        alert = InvestigatorAlert(
            alert_id=str(uuid.uuid4()),
            genome_id=genome_id, attack_family=attack_family,
            weakness_targeted=weakness_targeted, difficulty=difficulty,
            generation=generation, blue_verdict=blue_verdict,
            blue_confidence=round(blue_confidence, 4), blue_risk=round(blue_risk, 4),
            rupees_at_risk=rupees_at_risk, genome_summary=genome_summary,
            scenario_summary=scenario_summary,
        )
        with self._lock:
            self._alerts[alert.alert_id] = alert
            self._persist_alerts()
        logger.info("Investigator alert queued (NOT auto-learned): %s family=%s",
                    alert.alert_id[:8], attack_family)
        return alert

    def list_alerts(self, status: str | None = None) -> list[InvestigatorAlert]:
        with self._lock:
            items = list(self._alerts.values())
        if status:
            items = [a for a in items if a.status == status]
        items.sort(key=lambda a: a.rupees_at_risk, reverse=True)
        return items

    def get_alert(self, alert_id: str) -> InvestigatorAlert | None:
        return self._alerts.get(alert_id)

    def approve(self, alert_id: str, investigator_id: str,
                notes: str | None = None) -> dict | None:
        """Investigator approves → append to hardening backlog. Blue is untouched."""
        with self._lock:
            alert = self._alerts.get(alert_id)
            if alert is None or alert.status != PENDING:
                return None
            alert.status = APPROVED
            alert.decided_by = investigator_id
            alert.decision_notes = notes
            alert.decided_at = datetime.now(timezone.utc).isoformat()
            self._persist_alerts()
        entry = {
            "approved_at": alert.decided_at,
            "approved_by": investigator_id,
            "alert_id": alert.alert_id,
            "genome_id": alert.genome_id,
            "attack_family": alert.attack_family,
            "weakness_targeted": alert.weakness_targeted,
            "difficulty": alert.difficulty,
            "blue_verdict": alert.blue_verdict,
            "genome_summary": alert.genome_summary,
            "notes": notes,
        }
        self._append_backlog(entry)
        logger.info("Alert %s APPROVED by %s → hardening backlog (Blue NOT modified)",
                    alert_id[:8], investigator_id)
        return entry

    def reject(self, alert_id: str, investigator_id: str,
               notes: str | None = None) -> InvestigatorAlert | None:
        with self._lock:
            alert = self._alerts.get(alert_id)
            if alert is None or alert.status != PENDING:
                return None
            alert.status = REJECTED
            alert.decided_by = investigator_id
            alert.decision_notes = notes
            alert.decided_at = datetime.now(timezone.utc).isoformat()
            self._persist_alerts()
        return alert

    # ── hardening backlog (the only persisted output) ─────────────────────────
    def _append_backlog(self, entry: dict) -> None:
        try:
            os.makedirs(os.path.dirname(self._backlog_path), exist_ok=True)
            with open(self._backlog_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError as exc:
            logger.error("Failed to persist hardening backlog: %s", exc)
            raise

    def hardening_backlog(self) -> list[dict]:
        if not os.path.exists(self._backlog_path):
            return []
        out: list[dict] = []
        try:
            with open(self._backlog_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        out.append(json.loads(line))
        except OSError as exc:
            logger.error("Failed to read hardening backlog: %s", exc)
        return out


# Process-wide gate used by the engine + API.
learning_gate = LearningGate()
