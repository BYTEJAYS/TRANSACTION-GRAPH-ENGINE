from __future__ import annotations
"""
Background Campaign Runner — continuous, autonomous adversarial evolution.

Runs the EvolutionEngine in a daemon thread, launching one evolved attack every
`interval_seconds`, forever, until stopped. Every Blue-missed attack lands in the
SAME investigator queue the API/dashboard serve (shared engine + learning_gate),
so the investigator sees discoveries appear live. It still never auto-trains Blue.

Why in-process (not Celery): the investigator queue and engine state live in the
API process; an in-process daemon shares them directly, so alerts are immediately
visible. The durable alert store (learning_gate) means discoveries also survive a
restart. For an offline Celery batch, call `EvolutionEngine.run_campaign` from a
task and point `CRUCIBLE_ALERTS_STORE` at the same shared path.
"""
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from red_team.evolution.difficulty import LEVELS

if TYPE_CHECKING:
    from red_team.evolution.engine import EvolutionEngine

logger = logging.getLogger(__name__)


@dataclass
class RunnerStatus:
    running: bool
    difficulty: str
    rotate_difficulty: bool
    interval_seconds: float
    attacks_launched: int
    evaded: int
    started_at: float | None
    last_attack: dict | None = field(default=None)


class BackgroundCampaignRunner:
    """Drives the engine continuously in a daemon thread."""

    def __init__(self, engine: "EvolutionEngine") -> None:
        self._engine = engine
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._difficulty = "medium"
        self._rotate = False
        self._interval = 2.0
        self._count = 0
        self._evaded = 0
        self._started_at: float | None = None
        self._last: dict | None = None

    # ── control ────────────────────────────────────────────────────────────────
    def start(self, difficulty: str = "medium", interval_seconds: float = 2.0,
              rotate_difficulty: bool = False) -> RunnerStatus:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self.status()  # already running; idempotent
            self._difficulty = difficulty
            self._rotate = rotate_difficulty
            self._interval = max(0.1, float(interval_seconds))
            self._stop.clear()
            self._started_at = time.time()
            self._thread = threading.Thread(target=self._loop, name="crucible-runner",
                                            daemon=True)
            self._thread.start()
            logger.info("Background runner started (difficulty=%s interval=%.1fs rotate=%s)",
                        difficulty, self._interval, rotate_difficulty)
            return self.status()

    def stop(self) -> RunnerStatus:
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=self._interval + 5.0)
        with self._lock:
            self._thread = None
            logger.info("Background runner stopped after %d attacks", self._count)
            return self.status()

    def status(self) -> RunnerStatus:
        running = bool(self._thread and self._thread.is_alive())
        return RunnerStatus(
            running=running, difficulty=self._difficulty, rotate_difficulty=self._rotate,
            interval_seconds=self._interval, attacks_launched=self._count,
            evaded=self._evaded, started_at=self._started_at, last_attack=self._last,
        )

    # ── loop ───────────────────────────────────────────────────────────────────
    def _next_difficulty(self) -> str:
        if not self._rotate:
            return self._difficulty
        # Ramp through difficulty levels so the campaign gets progressively harder.
        return LEVELS[self._count % len(LEVELS)]

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                run = self._engine.run_attack(difficulty=self._next_difficulty())
                self._count += 1
                if run.status == "evaded":
                    self._evaded += 1
                self._last = {
                    "attack_id": run.attack_id, "family": run.family,
                    "difficulty": run.difficulty, "status": run.status,
                    "generations": len(run.generations), "alert_id": run.alert_id,
                }
            except Exception as exc:  # never let one bad attack kill the loop
                logger.exception("Runner attack failed: %s", exc)
            # Interruptible sleep.
            self._stop.wait(self._interval)
