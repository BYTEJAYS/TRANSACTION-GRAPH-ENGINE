"""
Red Team cross-product attack battery + Blue Team evaluation (Phase 6).

A fixed battery of synthetic cross-product attacks with the XP rules each SHOULD
trip, plus an evaluation harness that runs the Blue Team (XP detection) against
them and reports detection coverage — and, critically, checks that legitimate
activity produces NO false positives. This validates Blue Team after every
change; an online retraining loop (Blue Team improving weights per attack) is a
future increment, so this is honest detection-coverage evaluation, not learning.
"""
from __future__ import annotations

from typing import Any

from . import scenarios
from .xp_rules import detect_xp_signals, XP_RULES

# (scenario, XP rules the attack should reveal)
BATTERY: list[dict[str, Any]] = [
    {"attack": "Wallet Layering", "scenario": "wallet_layering", "expect": ["XP004", "XP012"]},
    {"attack": "Shared-Device Mule Ring", "scenario": "shared_device_ring", "expect": ["XP009"]},
    {"attack": "Loan Laundering", "scenario": "loan_laundering", "expect": ["XP003"]},
    {"attack": "Shared-Identity Ring", "scenario": "shared_identity_ring", "expect": ["XP010", "XP011"]},
]
LEGIT_SCENARIOS = ["legit_customer"]

# Emerging / evasive attacks Blue Team does NOT yet catch at default thresholds —
# the input the learning loop adapts to (gated by the false-positive check).
EMERGING_ATTACKS: list[dict[str, Any]] = [
    {"attack": "Evasive Cross-Rail Structuring", "scenario": "evasive_structuring", "expect": ["XP012"]},
]


def evaluate_blue_team() -> dict[str, Any]:
    """Run the battery; report per-attack detection + overall coverage + FP check."""
    attacks = []
    caught_rules = expected_rules = 0
    fully = 0
    for atk in BATTERY:
        comp = scenarios.generate(atk["scenario"])
        fired = sorted({s["xp_id"] for s in detect_xp_signals(comp)})
        expect = set(atk["expect"])
        hits = expect & set(fired)
        success = hits == expect
        fully += int(success)
        caught_rules += len(hits)
        expected_rules += len(expect)
        attacks.append({
            "attack": atk["attack"],
            "scenario": atk["scenario"],
            "expected_rules": sorted(expect),
            "detected_rules": fired,
            "caught": sorted(hits),
            "missed": sorted(expect - set(fired)),
            "detected": success,
        })

    false_positives = []
    for name in LEGIT_SCENARIOS:
        fired = sorted({s["xp_id"] for s in detect_xp_signals(scenarios.generate(name))})
        if fired:
            false_positives.append({"scenario": name, "false_signals": fired})

    return {
        "attacks": attacks,
        "total_attacks": len(BATTERY),
        "attacks_fully_detected": fully,
        "rule_coverage": round(caught_rules / expected_rules, 3) if expected_rules else 0.0,
        "false_positives": false_positives,
        "false_positive_count": len(false_positives),
        "clean_on_legitimate": not false_positives,
        "xp_rules_available": len(XP_RULES),
    }
