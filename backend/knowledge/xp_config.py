"""
Tunable Blue Team XP detection thresholds.

The XP detectors were hard-coded; externalising their thresholds makes Blue Team
ADAPTIVE — the Red Team→Blue Team learning loop proposes threshold changes that
close detection gaps, gated by a false-positive check and investigator approval
(Red never auto-trains Blue; see the learning loop). Defaults equal the original
hard-coded values, so behaviour is unchanged until a proposal is applied.
"""
from __future__ import annotations

from typing import Any

DEFAULT_THRESHOLDS: dict[str, Any] = {
    "xp001_min_rails": 3,          # rapid channel switching: distinct rails
    "xp001_window_hours": 24,      # …within this window
    "xp004_ratio_low": 0.7,        # wallet layering pass-through band (low)
    "xp004_ratio_high": 1.05,      # …(high)
    "xp009_min_owners": 2,         # shared device: distinct owning customers
    "xp009_min_principals": 3,     # …or distinct principals when ownership unknown
    "xp012_min_structured": 4,     # cross-product structuring: # structured txns
    "xp012_min_rails": 2,          # …spread over this many rails
    "xp014_min_categories": 3,     # multi-product velocity: distinct categories
}

# Bounds the learning loop will not relax past (safety floor — keeps a single
# transaction from ever tripping a rule, and preserves a minimum of evidence).
THRESHOLD_FLOORS: dict[str, Any] = {
    "xp001_min_rails": 2, "xp004_ratio_low": 0.5, "xp009_min_owners": 2,
    "xp009_min_principals": 2, "xp012_min_structured": 3, "xp012_min_rails": 2,
    "xp014_min_categories": 2,
}

_active: dict[str, Any] = dict(DEFAULT_THRESHOLDS)
_history: list[dict[str, Any]] = []


def get_thresholds() -> dict[str, Any]:
    return dict(_active)


def get(key: str) -> Any:
    return _active.get(key, DEFAULT_THRESHOLDS.get(key))


def set_threshold(key: str, value: Any, *, source: str = "manual") -> None:
    """Apply a threshold change and record it (the learning-gate's apply step)."""
    if key not in DEFAULT_THRESHOLDS:
        raise KeyError(key)
    old = _active.get(key)
    _active[key] = value
    _history.append({"key": key, "from": old, "to": value, "source": source})


def reset() -> None:
    _active.clear()
    _active.update(DEFAULT_THRESHOLDS)
    _history.append({"reset": True})


def history() -> list[dict[str, Any]]:
    return list(_history)
