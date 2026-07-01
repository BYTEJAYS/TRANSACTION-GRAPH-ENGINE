"""
Risk Engine configuration — tunable weights + thresholds (no hardcoding).

Loaded from _data/risk_config.json (created from DEFAULTS on first run), tunable
live via the admin API (PUT /api/risk/config) without touching source. Env vars
override at load time so a deployment can set bank-specific policy:
  TGIE_RISK_INVESTIGATION_THRESHOLD, TGIE_RISK_CRITICAL_THRESHOLD.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict

_DATA_FILE = os.getenv(
    "TGIE_RISK_CONFIG",
    os.path.join(os.path.dirname(__file__), "_data", "risk_config.json"),
)

# Per-factor MAX points (the "weight"): a factor contributes intensity[0..1]×weight.
# Sum of intensities is clamped to 0–100, so a graph that trips everything saturates
# at Critical. Tune any of these in the admin panel to match a bank's risk appetite.
DEFAULT_WEIGHTS: Dict[str, int] = {
    "amount":          25,   # value of the largest transaction
    "velocity":        25,   # transfers per time window
    "layering":        22,   # laundering / forwarding chain depth
    "fan_out":         20,   # one account → many recipients
    "fan_in":          20,   # many senders → one account
    "circular":        25,   # closed-loop money flow (highest-confidence signal)
    "cash":            18,   # cash in/out, boosted when combined with structure
    "payment_rails":   15,   # switching rails within one chain
    "dormant":         12,   # dormant account suddenly active
    "new_beneficiary": 14,   # large transfer to a just-added beneficiary
    "complexity":      12,   # network size / density / branching
    "profile_deviation": 24, # behaviour abnormal FOR THIS customer's profile (strong signal)
    "cross_bank":      10,   # entity suspicious at OTHER banks (capped — contributes, never dominates)
}

DEFAULTS: Dict[str, Any] = {
    # Risk-level boundaries (0–100). Case auto-creation uses investigation_threshold.
    "thresholds": {
        "monitor":     30,   # ≥ → recorded internally, no notification
        "suspicious":  50,   # ≥ → dashboard highlight, manual review
        "high_risk":   70,   # ≥ → Red Alert + auto Investigation Case
        "critical":    85,   # ≥ → immediate case + freeze recommendation
    },
    "investigation_threshold": 70,   # score ≥ this auto-creates a case
    "weights": DEFAULT_WEIGHTS,
    "velocity_window_seconds": 120,  # window for the velocity factor
    "velocity_txn_target":     20,   # txns-in-window that = full velocity intensity
    "suppress_false_positives": True,  # cap benign simple transfers at Monitor
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class RiskConfig:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cfg = self._load()

    def _load(self) -> dict:
        cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
        try:
            with open(_DATA_FILE, "r", encoding="utf-8") as f:
                cfg = _merge(cfg, json.load(f))
        except Exception:
            pass
        # env overrides (deployment policy)
        inv = os.getenv("TGIE_RISK_INVESTIGATION_THRESHOLD")
        crit = os.getenv("TGIE_RISK_CRITICAL_THRESHOLD")
        if inv:
            try: cfg["investigation_threshold"] = int(inv); cfg["thresholds"]["high_risk"] = int(inv)
            except ValueError: pass
        if crit:
            try: cfg["thresholds"]["critical"] = int(crit)
            except ValueError: pass
        return cfg

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(_DATA_FILE), exist_ok=True)
            tmp = f"{_DATA_FILE}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._cfg, f, indent=2)
            os.replace(tmp, _DATA_FILE)
        except Exception:
            pass

    def get(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._cfg))

    def update(self, patch: dict) -> dict:
        with self._lock:
            self._cfg = _merge(self._cfg, patch or {})
            # keep investigation_threshold and high_risk in lock-step if either set
            t = self._cfg["thresholds"]
            if "investigation_threshold" in (patch or {}):
                t["high_risk"] = self._cfg["investigation_threshold"]
            elif "thresholds" in (patch or {}) and "high_risk" in patch["thresholds"]:
                self._cfg["investigation_threshold"] = t["high_risk"]
            self._save()
            return json.loads(json.dumps(self._cfg))

    def reset(self) -> dict:
        with self._lock:
            self._cfg = json.loads(json.dumps(DEFAULTS))
            self._save()
            return json.loads(json.dumps(self._cfg))


config = RiskConfig()
