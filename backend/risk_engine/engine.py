"""
TGIE Intelligent Risk Scoring Engine.

Replaces simplistic "amount → fraud" alerting with a cumulative, explainable
multi-factor Risk Score (0–100). NO single factor (not even a huge amount) can
trigger a case on its own — a case is created only when the *cumulative* score
crosses the configured investigation threshold. Mirrors how enterprise AML /
fraud-monitoring platforms (e.g. Actimize, SAS, Featurespace) score events.

`assess(component)` consumes the connected-component dict produced by
TransactionGraphManager.get_connected_components():
   { graph_id, node_ids, nodes:[{id, risk_score, account_type, detected_patterns,
     transaction_count, ...}], edges:[{source, target, amount, payment_rail,
     timestamp, ...}] }
and returns a fully explainable assessment.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import config as _config


# ── helpers ──────────────────────────────────────────────────────────────────
def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _ts(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return None


def _amount_intensity(max_amt: float) -> float:
    # tiered, mirrors the spec's amount bands (₹)
    if max_amt < 10_000:      return 0.0
    if max_amt < 50_000:      return 0.12
    if max_amt < 2_00_000:    return 0.32
    if max_amt < 5_00_000:    return 0.60
    if max_amt < 10_00_000:   return 0.80
    return 1.0


# ── core ─────────────────────────────────────────────────────────────────────
def assess(component: Dict[str, Any], cfg: Optional[dict] = None) -> Dict[str, Any]:
    cfg = cfg or _config.get()
    W = cfg["weights"]
    th = cfg["thresholds"]

    node_ids: List[str] = [str(n) for n in (component.get("node_ids") or [])]
    nodes: List[dict] = component.get("nodes", []) or []
    edges: List[dict] = component.get("edges", []) or []
    node_meta = {str(n.get("id")): n for n in nodes if n.get("id") is not None}

    # directed adjacency
    out_adj: Dict[str, set] = {}
    in_adj: Dict[str, set] = {}
    amounts: List[float] = []
    times: List[datetime] = []
    rails: List[str] = []
    for e in edges:
        s, t = str(e.get("source", "")), str(e.get("target", ""))
        if not s or not t:
            continue
        out_adj.setdefault(s, set()).add(t)
        in_adj.setdefault(t, set()).add(s)
        in_adj.setdefault(s, in_adj.get(s, set()))
        out_adj.setdefault(t, out_adj.get(t, set()))
        amounts.append(float(e.get("amount", 0) or 0))
        dt = _ts(e.get("timestamp", ""))
        if dt:
            times.append(dt)
        if e.get("payment_rail"):
            rails.append(str(e["payment_rail"]).upper())

    n = max(len(node_ids), len(node_meta), 1)
    m = len(edges)
    max_amt = max(amounts, default=0.0)
    max_out = max((len(v) for v in out_adj.values()), default=0)
    max_in = max((len(v) for v in in_adj.values()), default=0)
    has_cycle = _has_cycle(out_adj)
    depth = _longest_path(out_adj)

    patterns = " ".join(
        p.lower() for nd in nodes for p in (nd.get("detected_patterns") or [])
    )
    acct_types = " ".join(str(nd.get("account_type", "")).lower() for nd in nodes)
    has_cash = ("cash" in acct_types) or ("cash" in patterns) or any("CASH" in r for r in rails)
    has_dormant = "dormant" in patterns
    has_new_benef = "new beneficiary" in patterns or "new-beneficiary" in patterns

    # velocity intensity
    vel_window = cfg.get("velocity_window_seconds", 120)
    vel_target = max(1, cfg.get("velocity_txn_target", 20))
    txns_in_window, vel_detail = _velocity(times, len(edges), vel_window, vel_target)
    vel_intensity = min(1.0, txns_in_window / vel_target)

    distinct_rails = len(set(rails))
    density = m / (n * (n - 1)) if n > 1 else 0.0

    # structural signals → drive cash combo + false-positive suppression
    structural = bool(has_cycle or max_out >= 3 or max_in >= 3 or depth >= 3
                      or vel_intensity >= 0.4 or has_dormant or has_new_benef)
    cash_combo = bool(has_cash and (depth >= 2 or max_out >= 3 or max_in >= 3 or vel_intensity >= 0.4))

    # ── Customer Profile Intelligence ─────────────────────────────────────────
    # Evaluate behaviour RELATIVE to each account's customer profile. Two outputs:
    #   amount_mitigation — the largest-amount account is acting within its profile's
    #                       envelope (e.g. ₹25L for a Business Owner) → the absolute
    #                       amount factor is dampened so legitimate high-volume
    #                       customers are not false-flagged.
    #   profile_deviation — behaviour abnormal FOR THIS customer (e.g. ₹25L from a
    #                       Salaried Employee) → a strong additive risk factor.
    # Graceful: with no usable data both are 0 and scoring is unchanged.
    try:
        from profile_intelligence import assess_component as _assess_profile
        profile_intel = _assess_profile(component, component.get("customer_profiles"))
    except Exception:
        profile_intel = {"available": False, "component_deviation": 0.0,
                         "amount_mitigation": 0.0, "accounts": {}, "explanation": None}
    amount_mitigation = float(profile_intel.get("amount_mitigation", 0.0) or 0.0)
    profile_deviation = float(profile_intel.get("component_deviation", 0.0) or 0.0)

    # ── Cross-Bank Intelligence (plug-in enrichment) ──────────────────────────
    # "Has this entity behaved suspiciously at OTHER banks?" A capped factor: it
    # contributes to the score but (weight 10) can never alone create a case — it
    # corroborates structural fraud, it doesn't manufacture it. Metadata-only:
    # reads the component + entity_context, never touches the graph. Fully graceful.
    try:
        from cross_bank_intelligence import analyze_component as _assess_cross_bank
        cross_bank = _assess_cross_bank(component, component.get("entity_context"))
    except Exception:
        from cross_bank_intelligence.schemas import empty_report
        cross_bank = empty_report()
    cross_bank_intensity = float(cross_bank.get("cross_bank_risk", 0) or 0) / 100.0

    # ── per-factor intensity [0..1] ──────────────────────────────────────────
    intensity = {
        # Amount is now PROFILE-RELATIVE: a big transfer that is routine for the
        # customer no longer drives risk on its own (mitigation suppresses it).
        "amount":          _amount_intensity(max_amt) * (1.0 - 0.85 * amount_mitigation),
        "profile_deviation": profile_deviation,
        "cross_bank":      cross_bank_intensity,
        "velocity":        vel_intensity,
        "layering":        min(1.0, (depth - 1) / 4.0) if depth >= 3 else 0.0,
        "fan_out":         min(1.0, (max_out - 1) / 9.0) if max_out >= 2 else 0.0,
        "fan_in":          min(1.0, (max_in - 1) / 9.0) if max_in >= 2 else 0.0,
        "circular":        1.0 if has_cycle else 0.0,
        "cash":            (0.3 + 0.7 * (1.0 if cash_combo else 0.0)) if has_cash else 0.0,
        "payment_rails":   min(1.0, (distinct_rails - 1) / 3.0) if distinct_rails >= 2 else 0.0,
        "dormant":         1.0 if has_dormant else 0.0,
        "new_beneficiary": 1.0 if has_new_benef else 0.0,
        "complexity":      (min(1.0, 0.5 * min(1.0, n / 12.0) + 0.3 * min(1.0, density * 2.5)
                               + 0.2 * min(1.0, max(max_out, max_in) / 8.0)) if n >= 4 else 0.0),
    }

    # ── factors with human-readable explanations ─────────────────────────────
    details = {
        "amount":          (f"Largest transaction ₹{int(max_amt):,}"
                            + (" — within customer profile (dampened)" if amount_mitigation > 0.1 else "")),
        "profile_deviation": (profile_intel.get("explanation")
                              or "Behaviour deviates from the customer's profile baseline"),
        "cross_bank":      (cross_bank.get("explanation")
                            or "Entity activity correlated across multiple banks"),
        "velocity":        vel_detail,
        "layering":        f"Forwarding chain depth {depth}",
        "fan_out":         f"Fan-out to {max_out} recipient account(s)",
        "fan_in":          f"Fan-in from {max_in} sender account(s)",
        "circular":        "Circular money flow (closed loop) detected",
        "cash":            ("Cash movement combined with suspicious structure" if cash_combo
                            else "Cash movement present"),
        "payment_rails":   f"{distinct_rails} payment rails used ({', '.join(sorted(set(rails))[:5])})",
        "dormant":         "Dormant account reactivated",
        "new_beneficiary": "Large transfer to a newly-added beneficiary",
        "complexity":      f"{n} accounts · {m} edges · density {density:.2f}",
    }

    factors: List[dict] = []
    raw = 0.0
    for key, inten in intensity.items():
        weight = int(W.get(key, 0))
        pts = round(inten * weight)
        if pts <= 0:
            continue
        raw += pts
        factors.append({
            "key": key,
            "label": _LABELS[key],
            "points": pts,
            "max": weight,
            "detail": details[key],
        })
    factors.sort(key=lambda f: f["points"], reverse=True)
    score = int(round(_clamp(raw)))

    # ── false-positive suppression ───────────────────────────────────────────
    suppressed = False
    suppression_reason = None
    if cfg.get("suppress_false_positives", True) and not structural and not has_cycle:
        # No structural fraud indicators → consistent with legitimate banking
        # (salary credit, EMI, vendor payout, internal settlement, normal deposit).
        if score > th["monitor"] - 1:
            suppressed = True
            suppression_reason = (
                "No structural fraud indicators (no layering, fan-out/in, cycle, "
                "velocity or cash-combination) — consistent with a legitimate "
                "transfer such as salary, EMI, vendor payout or internal settlement."
            )
            score = min(score, th["monitor"] - 1)

    level, action, priority = _classify(score, th)

    # confidence: more corroborating signals + more data → higher confidence
    active = len(factors)
    data_completeness = 0.5 + 0.25 * (1 if times else 0) + 0.25 * (1 if patterns else 0)
    confidence = int(_clamp((40 + active * 11) * data_completeness + (15 if has_cycle else 0), 5, 99))

    return {
        "score": score,
        "level": level,
        "action": action,
        "priority": priority,
        "confidence": confidence,
        "factors": factors,
        "top_indicators": [f["label"] for f in factors[:5]],
        "suppressed": suppressed,
        "suppression_reason": suppression_reason,
        "explanation": _explanation(score, level, factors, suppressed, suppression_reason),
        "should_create_case": (score >= cfg.get("investigation_threshold", th["high_risk"])) and not suppressed,
        "investigation_threshold": cfg.get("investigation_threshold", th["high_risk"]),
        "profile_intelligence": profile_intel,   # per-account profiles + deviation/mitigation
        "cross_bank": cross_bank,                 # cross-bank entity intelligence (metadata only)
        "metrics": {
            "accounts": n, "edges": m, "max_amount": max_amt, "max_fan_out": max_out,
            "max_fan_in": max_in, "layering_depth": depth, "circular": has_cycle,
            "distinct_rails": distinct_rails, "cash": has_cash, "density": round(density, 3),
        },
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }


def classify_score(score: int, cfg: Optional[dict] = None) -> Dict[str, Any]:
    cfg = cfg or _config.get()
    level, action, priority = _classify(int(score), cfg["thresholds"])
    return {"score": int(score), "level": level, "action": action, "priority": priority}


# ── classification ───────────────────────────────────────────────────────────
def _classify(score: int, th: dict):
    if score >= th["critical"]:
        return "Critical", "Immediate investigation case · recommend account freeze & transaction hold", "Critical"
    if score >= th["high_risk"]:
        return "High Risk", "Generate Red Alert · auto-create investigation case · investigator review", "High"
    if score >= th["suspicious"]:
        return "Suspicious", "Highlight in dashboard · allow manual review · no automatic case", "Medium"
    if score >= th["monitor"]:
        return "Monitor", "Record internally · no investigator notification", "Low"
    return "Safe", "No action", "Low"


def _explanation(score: int, level: str, factors: List[dict], suppressed: bool, reason: Optional[str]) -> str:
    if suppressed:
        return (f"Risk Score {score} ({level}). {reason} Suppressed below the alerting "
                f"threshold despite raw indicators.")
    if not factors:
        return f"Risk Score {score} ({level}). No risk indicators present."
    lines = " · ".join(f"{f['label']} (+{f['points']})" for f in factors[:6])
    return f"Risk Score {score} ({level}). Contributing factors: {lines}."


_LABELS = {
    "amount": "Transaction amount", "velocity": "Transaction velocity",
    "layering": "Layering depth", "fan_out": "Fan-out", "fan_in": "Fan-in",
    "circular": "Circular money flow", "cash": "Cash movement",
    "payment_rails": "Multiple payment rails", "dormant": "Dormant account activation",
    "new_beneficiary": "New beneficiary behaviour", "complexity": "Network complexity",
    "profile_deviation": "Profile deviation",
    "cross_bank": "Cross-bank intelligence",
}


# ── graph metrics ────────────────────────────────────────────────────────────
def _velocity(times: List[datetime], n_edges: int, window: int, target: int):
    if len(times) >= 2:
        ts = sorted(times)
        # densest `window`-second slice (sliding)
        best = 1
        j = 0
        for i in range(len(ts)):
            while (ts[i] - ts[j]).total_seconds() > window:
                j += 1
            best = max(best, i - j + 1)
        return best, f"{best} transfer(s) within {window}s"
    # no usable timestamps → can't measure velocity; stay conservative
    return 0, "Insufficient timing data for velocity"


def _has_cycle(out_adj: Dict[str, set]) -> bool:
    color: Dict[str, int] = {}
    for start in list(out_adj.keys()):
        if color.get(start, 0):
            continue
        stack = [(start, iter(out_adj.get(start, ())))]
        color[start] = 1
        while stack:
            node, it = stack[-1]
            advanced = False
            for nxt in it:
                c = color.get(nxt, 0)
                if c == 0:
                    color[nxt] = 1
                    stack.append((nxt, iter(out_adj.get(nxt, ()))))
                    advanced = True
                    break
                if c == 1:
                    return True
            if not advanced:
                color[node] = 2
                stack.pop()
    return False


def _longest_path(out_adj: Dict[str, set]) -> int:
    """Longest directed path length in nodes (cycle-safe; back-edges ignored)."""
    color: Dict[str, int] = {}
    best: Dict[str, int] = {}
    order: List[str] = []
    for start in list(out_adj.keys()):
        if color.get(start, 0):
            continue
        stack = [(start, iter(out_adj.get(start, ())))]
        color[start] = 1
        while stack:
            node, it = stack[-1]
            advanced = False
            for nxt in it:
                if color.get(nxt, 0) == 0:
                    color[nxt] = 1
                    stack.append((nxt, iter(out_adj.get(nxt, ()))))
                    advanced = True
                    break
            if not advanced:
                color[node] = 2
                order.append(node)
                stack.pop()
    for node in order:
        d = 0
        for nxt in out_adj.get(node, ()):  # type: ignore
            if color.get(nxt) == 2:
                d = max(d, best.get(nxt, 0) + 1)
        best[node] = d
    return (max(best.values()) + 1) if best else 1
