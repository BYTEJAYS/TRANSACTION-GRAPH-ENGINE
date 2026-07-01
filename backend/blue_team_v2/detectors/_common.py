"""
Small shared helpers for the Wave-1 topology detectors.

Kept dependency-free and pure so detectors stay self-contained and testable.
Reporting thresholds are read from risk_engine.config when available, else fall
back to sensible Indian-banking defaults (configurable per Phase 4 §11).
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

# Night window (local-naive hours). Investigator-tunable; geo-aware refinement is Wave 2.
NIGHT_START, NIGHT_END = 0, 5

# Reporting / structuring band defaults (₹).
DEFAULT_REPORT_THRESHOLD = 10_00_000   # ₹10 lakh — RTGS / large-value reporting band
NEAR_BAND = 0.80                        # "just under" = [0.80·T, T)


def report_threshold() -> float:
    try:
        from risk_engine.config import config as _c  # optional
        return float(getattr(_c, "REPORT_THRESHOLD", DEFAULT_REPORT_THRESHOLD))
    except Exception:
        return float(DEFAULT_REPORT_THRESHOLD)


def night_fraction(timestamps: Iterable[datetime]) -> float:
    ts = list(timestamps)
    if not ts:
        return 0.0
    n = sum(1 for t in ts if NIGHT_START <= t.hour < NIGHT_END)
    return n / len(ts)


def weekend_fraction(timestamps: Iterable[datetime]) -> float:
    ts = list(timestamps)
    if not ts:
        return 0.0
    n = sum(1 for t in ts if t.weekday() >= 5)
    return n / len(ts)


def edge_amounts(tg) -> list[float]:
    return [d["amount"] for _, _, d in tg.G.edges(data=True)]


def has_rail(tg, u: str, v: str, *rails: str) -> bool:
    if not tg.G.has_edge(u, v):
        return False
    edge_rails = set(tg.G[u][v].get("rails", []))
    return any(r in edge_rails for r in rails)
