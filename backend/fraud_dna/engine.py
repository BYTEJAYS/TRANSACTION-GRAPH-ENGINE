"""
Fraud DNA Engine — behavioural fingerprinting.

Turns a case into an 8-gene behavioural profile (a DNA vector + signature),
then supports similarity, comparison, risk-impact and prediction. Pure-Python
(stdlib only); deterministic given the same case data.
"""

from __future__ import annotations

import hashlib
import math
from statistics import mean
from typing import Dict, List, Optional, Tuple

GENES = ["Velocity", "Amount", "Structure", "Behavior", "Temporal", "Flow", "Risk", "Outcome"]

# weights for the weighted-cosine similarity (structure/flow/risk matter most)
GENE_WEIGHTS = {
    "Velocity": 1.1, "Amount": 1.0, "Structure": 1.3, "Behavior": 1.0,
    "Temporal": 0.9, "Flow": 1.2, "Risk": 1.3, "Outcome": 0.8,
}
GENE_REASON = {
    "Velocity": "Same transaction velocity",
    "Amount": "Same amount patterning",
    "Structure": "Same network structure",
    "Behavior": "Same account lifecycle",
    "Temporal": "Same timing signature",
    "Flow": "Same money-flow pattern",
    "Risk": "Same risk profile",
    "Outcome": "Same investigation outcome",
}

CATEGORY_TYPE = {
    "Money Mule Network": "MULE", "Circular Transactions": "RING",
    "Suspicious Account Ring": "RING", "Layering Activity": "LAYER",
    "Account Takeover": "ATO", "Rapid Fund Movement": "RAPID",
    "High-Risk Network": "NET", "Suspicious Transaction Chain": "CHAIN",
    "Linked Fraud Network": "NET",
}
TOPOLOGY = {
    "Money Mule Network": "Hub-and-spoke funnel", "Circular Transactions": "Ring / cyclic",
    "Suspicious Account Ring": "Ring / cyclic", "Layering Activity": "Layered tree",
    "Rapid Fund Movement": "Linear chain", "Suspicious Transaction Chain": "Linear chain",
    "Account Takeover": "Star (takeover hub)", "High-Risk Network": "Dense cluster",
    "Linked Fraud Network": "Dense cluster",
}
FLOW_LABEL = {
    "Money Mule Network": "Convergence (funnel)", "Circular Transactions": "Circular movement",
    "Suspicious Account Ring": "Circular movement", "Layering Activity": "Multi-hop layering",
    "Rapid Fund Movement": "Pass-through", "Suspicious Transaction Chain": "Pass-through",
    "Account Takeover": "Distribution (fan-out)", "High-Risk Network": "Mixed flow",
    "Linked Fraud Network": "Mixed flow",
}


def _clamp(v: float) -> int:
    return int(max(0, min(100, round(v))))


def _account(case: dict) -> Optional[dict]:
    try:
        from auth.accounts_db import registry
        return registry.get(case.get("primary_account") or "")
    except Exception:
        return None


# ── gene computations ─────────────────────────────────────────────────────────
def _velocity(case: dict, acct: Optional[dict]) -> Tuple[int, dict, str]:
    hours = [a["hours_ago"] for a in acct.get("recent_activity", [])] if acct else []
    tcount = acct["transaction_count"] if acct else len(case.get("transactions", []))
    tpd = tcount / 365
    recent24 = sum(1 for h in hours if h < 24)
    gaps = [b - a for a, b in zip(sorted(hours), sorted(hours)[1:])] if len(hours) > 1 else [99]
    avg_gap = mean(gaps) if gaps else 99
    score = _clamp(26 + min(34, tpd * 0.6) + recent24 * 6 + (12 if avg_gap < 6 else 0))
    label = "Bursty / rapid" if score >= 65 else "Steady" if score >= 40 else "Low"
    return score, {"tx_per_day": round(tpd, 1), "burst_24h": recent24, "avg_gap_h": round(avg_gap, 1)}, label


def _amount(case: dict, acct: Optional[dict]) -> Tuple[int, dict, str]:
    amts = [t["amount"] for t in case.get("transactions", [])]
    if acct:
        amts += [a["amount"] for a in acct.get("recent_activity", [])]
    if not amts:
        return 30, {"rounded": 0, "structured": 0, "repeated": 0}, "Sparse"
    rounded = sum(1 for a in amts if a % 1000 == 0) / len(amts)
    structured = sum(1 for a in amts if any(abs(a - thr) / thr < 0.03 and a <= thr for thr in (10000, 50000, 100000, 200000))) / len(amts)
    repeated = (max(amts.count(a) for a in set(amts)) / len(amts))
    score = _clamp(18 + rounded * 38 + structured * 40 + repeated * 28)
    label = "Structured / smurfing" if structured > 0.3 else "Rounded" if rounded > 0.5 else "Irregular"
    return score, {"rounded": round(rounded, 2), "structured": round(structured, 2), "repeated": round(repeated, 2)}, label


def _structure(case: dict, acct: Optional[dict]) -> Tuple[int, dict, str]:
    snap = case.get("graph_snapshot", {})
    n = len(snap.get("nodes", [])) or len(case.get("accounts", [])) or 1
    e = len(snap.get("edges", [])) or max(0, n - 1)
    density = e / (n * (n - 1) / 2) if n > 1 else 0
    topo = TOPOLOGY.get(case.get("category", ""), "Mixed")
    score = _clamp(28 + n * 4 + density * 36 + (10 if "Ring" in topo or "Layer" in topo else 0))
    return score, {"nodes": n, "edges": e, "density": round(density, 2)}, topo


def _behavior(case: dict, acct: Optional[dict]) -> Tuple[int, dict, str]:
    flags = [f.lower() for f in case.get("graph_snapshot", {}).get("indicators", [])]
    age_years = 0
    if acct and acct.get("opened_on"):
        try:
            age_years = max(0, 2026 - int(acct["opened_on"][:4]))
        except Exception:
            age_years = 0
    dormancy = any("dormant" in f for f in flags)
    new_act = any("new beneficiary" in f for f in flags)
    score = _clamp(24 + (24 if dormancy else 0) + (20 if new_act else 0) + (18 if age_years <= 2 else 0))
    label = "Dormant-then-active" if dormancy else "Newly activated" if new_act else "Established"
    return score, {"account_age_years": age_years, "dormancy": dormancy, "new_activation": new_act}, label


def _temporal(case: dict, acct: Optional[dict]) -> Tuple[int, dict, str]:
    flags = [f.lower() for f in case.get("graph_snapshot", {}).get("indicators", [])]
    hours = [a["hours_ago"] for a in acct.get("recent_activity", [])] if acct else []
    night = any("night" in f for f in flags)
    # crude time-of-day inference from hours_ago modulo 24
    nightish = sum(1 for h in hours if (h % 24) < 6 or (h % 24) >= 22)
    regularity = 0
    if len(hours) > 2:
        gaps = [b - a for a, b in zip(sorted(hours), sorted(hours)[1:])]
        regularity = 1 - (min(1, (max(gaps) - min(gaps)) / (mean(gaps) + 1))) if gaps else 0
    score = _clamp(28 + (32 if night else 0) + nightish * 4 + regularity * 20)
    label = "Night-active" if night or nightish >= 2 else "Scheduled" if regularity > 0.6 else "Business hours"
    return score, {"night_activity": night, "night_txns": nightish, "regularity": round(regularity, 2)}, label


def _flow(case: dict, acct: Optional[dict]) -> Tuple[int, dict, str]:
    txns = case.get("transactions", [])
    dests = {t["to_account"] for t in txns}
    srcs = {t["from_account"] for t in txns}
    cat = case.get("category", "")
    convergence = len(srcs) > len(dests)
    circular = "Ring" in TOPOLOGY.get(cat, "") or "Circular" in cat
    conc = (1 - len(dests) / max(1, len(txns))) if txns else 0.4
    score = _clamp(30 + conc * 38 + (26 if circular else 0) + (8 if convergence else 0))
    return score, {"sources": len(srcs), "destinations": len(dests), "circular": circular,
                   "concentration": round(conc, 2)}, FLOW_LABEL.get(cat, "Mixed flow")


def _risk(case: dict, acct: Optional[dict]) -> Tuple[int, dict, str]:
    risk = int(case.get("risk_score", 50))
    conf = case.get("fraud_confidence", 0.5)
    inds = case.get("graph_snapshot", {}).get("indicators", [])
    score = _clamp(risk * 0.85 + conf * 12 + min(12, len(inds) * 3))
    label = "Critical" if score >= 80 else "Elevated" if score >= 55 else "Moderate"
    return score, {"risk_score": risk, "fraud_confidence": conf, "indicators": len(inds)}, label


_OUTCOME_SCORE = {
    "Escalated": 85, "Active Investigation": 70, "Evidence Collection": 62, "Under Review": 55,
    "New": 50, "Pending Approval": 60, "Resolved": 92, "Closed": 80, "False Positive": 6, "Archived": 40,
}


def _outcome(case: dict, acct: Optional[dict]) -> Tuple[int, dict, str]:
    st = case.get("status", "New")
    score = _OUTCOME_SCORE.get(st, 50)
    if st in ("Resolved", "Escalated"):
        label = "Confirmed fraud"
    elif st == "False Positive":
        label = "False positive"
    elif st in ("Closed", "Archived"):
        label = "Closed"
    else:
        label = "Under investigation"
    return score, {"status": st, "confirmed": st in ("Resolved", "Escalated")}, label


_GENE_FUNCS = {
    "Velocity": _velocity, "Amount": _amount, "Structure": _structure, "Behavior": _behavior,
    "Temporal": _temporal, "Flow": _flow, "Risk": _risk, "Outcome": _outcome,
}


# ── DNA assembly ──────────────────────────────────────────────────────────────
def build_genes(case: dict) -> List[dict]:
    acct = _account(case)
    out = []
    for name in GENES:
        score, feats, label = _GENE_FUNCS[name](case, acct)
        out.append({"name": name, "score": score, "label": label, "features": feats})
    return out


def dna_type(case: dict) -> str:
    return CATEGORY_TYPE.get(case.get("category", ""), "NET")


def dna_id_for(case_id: str, dtype: str) -> str:
    h = int(hashlib.sha256(case_id.encode()).hexdigest(), 16)
    return f"FDNA-{dtype}-{h % 1000:03d}"


def signature(genes: List[dict]) -> str:
    raw = "-".join(str(g["score"]) for g in genes)
    return "0x" + hashlib.sha256(raw.encode()).hexdigest()[:6].upper()


def vector(genes: List[dict]) -> List[float]:
    return [g["score"] / 100 for g in genes]


def risk_impact(case: dict, genes: List[dict]) -> int:
    gs = {g["name"]: g["score"] for g in genes}
    funds = sum(t["amount"] for t in case.get("transactions", []))
    funds_norm = min(100, (math.log10(funds + 1) / 7) * 100)
    severity = {"Critical": 100, "High": 75, "Medium": 50, "Low": 25}.get(case.get("priority", "Medium"), 50)
    val = (0.38 * gs["Risk"] + 0.18 * gs["Structure"] + 0.16 * gs["Flow"]
           + 0.14 * funds_norm + 0.14 * severity)
    return _clamp(val)


# ── similarity ────────────────────────────────────────────────────────────────
def weighted_cosine(a: List[float], b: List[float]) -> float:
    wa = [GENE_WEIGHTS[GENES[i]] for i in range(len(a))]
    num = sum(wa[i] * a[i] * b[i] for i in range(len(a)))
    da = math.sqrt(sum(wa[i] * a[i] ** 2 for i in range(len(a))))
    db = math.sqrt(sum(wa[i] * b[i] ** 2 for i in range(len(b))))
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


def similarity_pct(a_genes: List[dict], b_genes: List[dict]) -> int:
    return _clamp(weighted_cosine(vector(a_genes), vector(b_genes)) * 100)


def matching_reasons(a_genes: List[dict], b_genes: List[dict], tol: int = 12) -> List[str]:
    reasons = []
    bmap = {g["name"]: g["score"] for g in b_genes}
    for g in a_genes:
        if abs(g["score"] - bmap.get(g["name"], -99)) <= tol:
            reasons.append(GENE_REASON[g["name"]])
    return reasons


def gene_deltas(a_genes: List[dict], b_genes: List[dict]) -> List[dict]:
    bmap = {g["name"]: g for g in b_genes}
    out = []
    for g in a_genes:
        bg = bmap.get(g["name"], {"score": 0, "label": "—"})
        delta = abs(g["score"] - bg["score"])
        out.append({"gene": g["name"], "a": g["score"], "b": bg["score"],
                    "a_label": g["label"], "b_label": bg.get("label", "—"),
                    "delta": delta, "match": delta <= 12})
    return out


# ── natural-language explanation ──────────────────────────────────────────────
def explain(case: dict, genes: List[dict], dtype: str, top_match: Optional[dict]) -> str:
    gs = sorted(genes, key=lambda g: g["score"], reverse=True)
    dom = ", ".join(f"{g['name'].lower()} ({g['score']})" for g in gs[:3])
    base = (f"This case carries a {dtype} fraud-DNA signature. Its strongest behavioural "
            f"genes are {dom}. The structure gene reads '{next(g['label'] for g in genes if g['name'] == 'Structure')}' "
            f"and the money-flow gene reads '{next(g['label'] for g in genes if g['name'] == 'Flow')}', which is "
            f"characteristic of this fraud methodology.")
    if top_match:
        base += (f" It is a {top_match['similarity']}% behavioural match to {top_match['case_id']} "
                 f"({top_match['title']}); the genes driving the match are: "
                 f"{', '.join(top_match['reasons'][:4]) or 'overall profile'}.")
    return base
