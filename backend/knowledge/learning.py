"""
Red Team → Blue Team learning loop (gated).

Closes Blue Team detection gaps on emerging/evasive cross-product attacks by
ADAPTING the XP detection thresholds — but never autonomously. Each proposed
change must (1) catch a previously-missed attack, (2) keep every baseline-battery
attack detected, and (3) introduce ZERO false positives on legitimate scenarios.
Proposals are STAGED for investigator approval (the learning gate); `apply` only
commits a change after re-validating that gate. Honest scope: adaptive,
hold-out-validated threshold tuning — not autonomous model retraining.
"""
from __future__ import annotations

from typing import Any

from . import scenarios, xp_config
from .xp_rules import detect_xp_signals
from .red_team import BATTERY, LEGIT_SCENARIOS, EMERGING_ATTACKS


def _detected(scenario: str, expect: list[str], cfg: dict) -> bool:
    fired = {s["xp_id"] for s in detect_xp_signals(scenarios.generate(scenario), config=cfg)}
    return set(expect) <= fired


def _coverage(attacks: list[dict], cfg: dict) -> int:
    return sum(_detected(a["scenario"], a["expect"], cfg) for a in attacks)


def _legit_false_positive(cfg: dict) -> bool:
    return any(detect_xp_signals(scenarios.generate(name), config=cfg) for name in LEGIT_SCENARIOS)


def _candidates(cfg: dict) -> list[tuple[str, Any]]:
    """One-step relaxations of each tunable knob, bounded by the safety floors."""
    proposed = {
        "xp012_min_structured": cfg["xp012_min_structured"] - 1,
        "xp001_min_rails": cfg["xp001_min_rails"] - 1,
        "xp014_min_categories": cfg["xp014_min_categories"] - 1,
        "xp009_min_principals": cfg["xp009_min_principals"] - 1,
        "xp004_ratio_low": round(cfg["xp004_ratio_low"] - 0.1, 2),
    }
    floors = xp_config.THRESHOLD_FLOORS
    out = []
    for k, v in proposed.items():
        floor = floors.get(k)
        if floor is not None and v < floor:
            continue
        out.append((k, v))
    return out


def _gate_ok(cand: dict) -> bool:
    """The learning gate: no battery regression AND no legitimate false positives."""
    return _coverage(BATTERY, cand) >= len(BATTERY) and not _legit_false_positive(cand)


def propose_adaptations(emerging: list[dict] | None = None) -> dict[str, Any]:
    """Evaluate threshold relaxations against the emerging attacks; STAGE the ones
    that close a gap and pass the gate. Nothing is applied here."""
    emerging = emerging if emerging is not None else EMERGING_ATTACKS
    base = xp_config.get_thresholds()
    base_emerging = _coverage(emerging, base)

    proposals = []
    for k, v in _candidates(base):
        cand = dict(base)
        cand[k] = v
        if not _gate_ok(cand):
            continue
        cand_emerging = _coverage(emerging, cand)
        if cand_emerging <= base_emerging:
            continue  # doesn't close any gap
        newly = [a["attack"] for a in emerging
                 if not _detected(a["scenario"], a["expect"], base)
                 and _detected(a["scenario"], a["expect"], cand)]
        proposals.append({
            "threshold": k, "from": base[k], "to": v,
            "attacks_newly_caught": newly,
            "emerging_coverage_before": base_emerging,
            "emerging_coverage_after": cand_emerging,
            "battery_still_full": True,
            "false_positives": 0,
            "gate_passed": True,
        })
    proposals.sort(key=lambda p: p["emerging_coverage_after"], reverse=True)
    return {
        "learning_gate": "investigator_approval_required",
        "applied": False,                       # propose NEVER auto-applies
        "current_thresholds": base,
        "baseline": {
            "battery_detected": _coverage(BATTERY, base), "battery_total": len(BATTERY),
            "emerging_detected": base_emerging, "emerging_total": len(emerging),
        },
        "proposals": proposals,
        "proposal_count": len(proposals),
    }


def apply_proposal(threshold: str, value: Any) -> dict[str, Any]:
    """Investigator-approved apply. Re-validates the gate before committing, so an
    approval can never regress the battery or introduce false positives."""
    if threshold not in xp_config.DEFAULT_THRESHOLDS:
        return {"applied": False, "reason": f"unknown threshold '{threshold}'"}
    floor = xp_config.THRESHOLD_FLOORS.get(threshold)
    if floor is not None and value < floor:
        return {"applied": False,
                "reason": f"below safety floor: {threshold} cannot go under {floor}"}
    base = xp_config.get_thresholds()
    cand = dict(base)
    cand[threshold] = value
    if not _gate_ok(cand):
        return {"applied": False, "reason": "gate failed: would regress the battery or add false positives"}
    xp_config.set_threshold(threshold, value, source="learning_loop")
    return {
        "applied": True,
        "threshold": threshold, "from": base[threshold], "to": value,
        "thresholds": xp_config.get_thresholds(),
        "emerging_now_detected": _coverage(EMERGING_ATTACKS, xp_config.get_thresholds()),
    }


def status() -> dict[str, Any]:
    cfg = xp_config.get_thresholds()
    return {
        "thresholds": cfg,
        "defaults": xp_config.DEFAULT_THRESHOLDS,
        "history": xp_config.history(),
        "battery_detected": _coverage(BATTERY, cfg),
        "battery_total": len(BATTERY),
        "emerging_detected": _coverage(EMERGING_ATTACKS, cfg),
        "emerging_total": len(EMERGING_ATTACKS),
    }
