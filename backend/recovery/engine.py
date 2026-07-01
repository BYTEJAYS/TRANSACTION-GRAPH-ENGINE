"""
Recovery Intelligence Engine (RIE) — core intelligence.

Pure, deterministic analysis over a case's transactions + graph snapshot. Answers
the question every bank manager asks after fraud is found: *can we still recover
the money?* — and, if so, how much, how fast, and what to freeze first.

DESIGN PRINCIPLE — every number is derived, reproducible and explainable.
There are no placeholder, random, or notional amounts. All money figures come
from a single conservation-correct flow-of-funds model:

    For every account:   net_balance = max(0, inbound − outbound)

    originated   = Σ outflow of SOURCE accounts (victims / fraud origins)
    in_network   = Σ net_balance over all accounts        (money still sitting)
    cashed_out   = Σ amount of cash-rail / withdrawal transactions
    exited       = originated − in_network                 (money that left)

These four quantities (and nothing else) drive recoverable amount, estimated
loss, freeze ranking, recovery paths and the recovery-probability factors. If the
case carries no usable transaction evidence the engine refuses to estimate and
returns ``insufficient_evidence`` rather than inventing values.

Every factor returns a score on 0–100 where HIGHER = better recovery prospects.
The weighted blend is the Recovery Probability. Nothing here calls the network,
so it is safe to run synchronously at case-open time.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Dict, List, Optional, Tuple

# ── Configurable assumptions ──────────────────────────────────────────────────
# Every tunable lives here so the model's behaviour is auditable in one place.
# These are *banking assumptions*, not magic numbers buried in the logic.
CONFIG = {
    # Age decay — heavy-tailed rational curve. Recovery stays *possible* for weeks
    # while funds sit in accounts, so the tail must not collapse like an exponential.
    "age_half_life_h": 48.0,     # age (hours) at which the age-only score = 50
    "age_decay_p": 0.52,         # tail exponent
    "low_recovery_floor": 30.0,  # recovery level that defines the "act now" window

    # Per-factor sensitivities (score points lost per unit of the named quantity).
    "depth_penalty_per_hop": 16,         # each laundering hop lowers traceability
    "dispersion_penalty_per_recipient": 11,
    "freeze_base_success": 92,           # freeze success for a clean, low-risk holder
    "freeze_risk_penalty": 0.8,          # success lost per risk point above 70
    "containment_penalty_per_hub": 8,    # each branching routing hub
    "containment_density_penalty": 12,   # per unit of edge density above 1.5

    # Funnel realism. likely_recoverable = Σ net · freeze_success · time_factor,
    # where time_factor blends the recovery probability with freeze success.
    "likely_prob_weight": 0.6,           # share of likely-recovery driven by P(recovery)
    "likely_freeze_weight": 0.4,         # share driven by per-account freeze success

    # Cash-out rails / reasons that imply funds have left the banking network.
    # CASH_OUT is the first-class withdrawal rail; CASH covers the legacy off-graph
    # form. A CASH_OUT edge means the funds reached a terminal cash event → not a
    # freezable balance, so it correctly lowers recoverability / raises loss.
    "cash_rails": {"CASH", "CASH_OUT", "ATM", "ATM_WITHDRAWAL", "CASH_WITHDRAWAL", "CARDLESS"},
    "withdraw_hints": ("withdraw", "atm", "cash-out", "cashout"),
    # Rails that move money outside the domestic banking network (harder to recall).
    "international_rails": {"SWIFT", "WIRE", "CRYPTO", "FOREX", "REMITTANCE"},

    "source_epsilon": 1.0,               # ₹ tolerance below which inbound ≈ 0 (a source)
}

# Factor weights (sum = 1.00). Withdrawal is heaviest — cash-out is the point of
# no return; age is next because recall windows close fast.
WEIGHTS: Dict[str, float] = {
    "age":          0.16,
    "depth":        0.11,
    "dispersion":   0.09,
    "withdrawal":   0.22,
    "freeze":       0.09,
    "containment":  0.07,
    "dna":          0.06,
    "timeline":     0.04,
    "beneficiary":  0.08,
    "disruption":   0.08,
}


# ── Small numeric helpers ─────────────────────────────────────────────────────
def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> int:
    return int(round(max(lo, min(hi, v))))


def _decay(h: float) -> float:
    """Age-only recovery score (0–100): 100 / (1 + (h/half_life)^p)."""
    return 100.0 / (1.0 + (max(0.0, h) / CONFIG["age_half_life_h"]) ** CONFIG["age_decay_p"])


def _hours_until(threshold: float, still_in: float) -> float:
    """Age (hours) at which _decay(h)*still_in falls to `threshold`."""
    if still_in <= 0:
        return 0.0
    ratio = 100.0 * still_in / threshold - 1.0
    if ratio <= 0:
        return 0.0
    return CONFIG["age_half_life_h"] * (ratio ** (1.0 / CONFIG["age_decay_p"]))


def _band(score: int) -> str:
    if score >= 81:
        return "Very High Recovery Potential"
    if score >= 61:
        return "High Recovery Potential"
    if score >= 41:
        return "Moderate Recovery Potential"
    if score >= 21:
        return "Recovery Difficult"
    return "Recovery Extremely Unlikely"


def _is_cash_out(t: dict) -> bool:
    rail = str(t.get("rail", "")).upper().replace(" ", "_")
    reason = str(t.get("reason", "")).lower()
    return rail in CONFIG["cash_rails"] or any(h in reason for h in CONFIG["withdraw_hints"])


def _fmt_age(h: float) -> str:
    if h < 1:
        return f"{int(round(h * 60))} min"
    if h < 48:
        return f"{h:.1f} h"
    return f"{h / 24:.1f} days"


def _fmt_window(h: float) -> str:
    if h <= 0:
        return "Window closed"
    hrs = int(h)
    mins = int(round((h - hrs) * 60))
    if hrs >= 24:
        return f"{hrs // 24}d {hrs % 24}h remaining"
    return f"{hrs}h {mins}m remaining"


# ══════════════════════════════════════════════════════════════════════════════
# FLOW-OF-FUNDS MODEL — the single source of every money figure
# ══════════════════════════════════════════════════════════════════════════════
def _adjacency(case: dict) -> Tuple[Dict[str, List[str]], Dict[str, List[str]], Dict[str, dict]]:
    """Directed out/in adjacency + per-node metadata, from the graph snapshot
    (preferred) supplemented by raw transactions."""
    out: Dict[str, List[str]] = defaultdict(list)
    inn: Dict[str, List[str]] = defaultdict(list)
    meta: Dict[str, dict] = {}

    gs = case.get("graph_snapshot") or {}
    for n in gs.get("nodes", []):
        meta[n["id"]] = {"risk": n.get("risk", case.get("risk_score", 50)), "role": n.get("role", "linked")}
    for e in gs.get("edges", []):
        a, b = e.get("from"), e.get("to")
        if a and b and b not in out[a]:
            out[a].append(b)
            inn[b].append(a)

    for t in case.get("transactions", []):
        a, b = t.get("from_account"), t.get("to_account")
        if a and b and b not in out[a]:
            out[a].append(b)
            inn[b].append(a)
        for acc in (a, b):
            if acc and acc not in meta:
                meta[acc] = {"risk": case.get("risk_score", 50), "role": "linked"}
    return out, inn, meta


def fund_state(case: dict) -> dict:
    """Conservation-correct flow-of-funds for the case.

    Returns per-account incoming / outgoing / cash-out / net_balance, plus the
    four headline quantities (originated, in_network, cashed_out, exited). Every
    downstream money figure is derived from this — and only this.
    """
    flows: Dict[str, dict] = {}

    def slot(a: str) -> dict:
        # incoming           = gross inbound (for display)
        # traceable_incoming = inbound that is still inside the banking network
        #                      (a cash-out / withdrawal inflow is money leaving, so
        #                       it does NOT credit the recipient as recoverable)
        return flows.setdefault(a, {"incoming": 0.0, "traceable_incoming": 0.0,
                                    "outgoing": 0.0, "cash_out": 0.0, "cash_received": 0.0,
                                    "txns": 0, "intl_out": 0.0})

    for t in case.get("transactions", []):
        amt = float(t.get("amount", 0) or 0)
        src, dst = t.get("from_account"), t.get("to_account")
        rail = str(t.get("rail", "")).upper().replace(" ", "_")
        cashed = _is_cash_out(t)
        intl = rail in CONFIG["international_rails"]
        if src:
            s = slot(src)
            s["outgoing"] += amt
            s["txns"] += 1
            if cashed:
                s["cash_out"] += amt      # this account withdrew funds out of network
            if intl:
                s["intl_out"] += amt
        if dst:
            d = slot(dst)
            d["incoming"] += amt
            d["txns"] += 1
            if cashed:
                d["cash_received"] += amt   # arrived as cash — not a freezable balance
            else:
                d["traceable_incoming"] += amt

    # ensure every graph node appears even if it carries no flagged transaction
    _, _, meta = _adjacency(case)
    for acc in meta:
        slot(acc)

    eps = CONFIG["source_epsilon"]
    for acc, f in flows.items():
        # money still sitting in THIS account = traceable inflow not yet moved on
        f["net_balance"] = max(0.0, f["traceable_incoming"] - f["outgoing"])
        f["dispersed"] = min(f["traceable_incoming"], f["outgoing"])  # forwarded onward
        f["risk"] = meta.get(acc, {}).get("risk", case.get("risk_score", 50))
        f["role"] = meta.get(acc, {}).get("role", "linked")

    # sources = accounts money originated from (victims / fraud entry points)
    sources = [a for a, f in flows.items() if f["incoming"] <= eps and f["outgoing"] > eps]
    originated = sum(flows[a]["outgoing"] for a in sources)
    if originated <= 0:
        # no clean source (e.g. a pure cycle): fall back to the flagged primary
        # account's outflow, else the single largest inbound seen.
        primary = case.get("primary_account")
        if primary and primary in flows and flows[primary]["outgoing"] > 0:
            originated = flows[primary]["outgoing"]
            sources = [primary]
        else:
            originated = max((f["incoming"] for f in flows.values()), default=0.0)

    in_network = sum(f["net_balance"] for f in flows.values())
    cashed_out = sum(f["cash_out"] for f in flows.values())
    intl_out = sum(f["intl_out"] for f in flows.values())
    # in_network can exceed originated only via fallback estimation; clamp for sanity
    in_network = min(in_network, originated) if originated > 0 else in_network
    exited = max(0.0, originated - in_network)

    return {
        "flows": flows,
        "sources": sources,
        "originated": originated,
        "in_network": in_network,
        "cashed_out": cashed_out,
        "intl_out": intl_out,
        "exited": exited,
        "still_in_fraction": (in_network / originated) if originated > 0 else 0.0,
        "withdrawn_fraction": min(1.0, (cashed_out / originated)) if originated > 0 else 0.0,
    }


def total_fraud_amount(case: dict) -> float:
    """The originated fraud principal (victim outflow), NOT the summed throughput."""
    return fund_state(case)["originated"]


def _age_hours(case: dict, now: float) -> float:
    txs = case.get("transactions", [])
    dates = [float(t.get("date", 0) or 0) for t in txs if t.get("date")]
    anchor = max(dates) if dates else float(case.get("created_at", now) or now)
    return max(0.0, (now - anchor) / 3600.0)


# ══════════════════════════════════════════════════════════════════════════════
# FACTORS  (every input now flows from fund_state / the graph — no fudge factors)
# ══════════════════════════════════════════════════════════════════════════════
def factor_age(case: dict, now: float) -> dict:
    h = _age_hours(case, now)
    score = _clamp(_decay(h), 5)
    label = ("Very High" if h < 0.5 else "High" if h < 6 else
             "Moderate" if h < 48 else "Low" if h < 168 else "Very Low")
    return {"key": "age", "name": "Transaction Age", "score": score,
            "label": label, "detail": f"{_fmt_age(h)} since last movement",
            "age_hours": round(h, 2)}


def factor_depth(case: dict) -> dict:
    out, _, _ = _adjacency(case)
    root = case.get("primary_account")
    depth = _longest_path(out, root) if root and root in out else _graph_diameter(out)
    score = _clamp(100 - depth * CONFIG["depth_penalty_per_hop"], 10)
    return {"key": "depth", "name": "Money Movement Depth", "score": score,
            "label": f"{depth} hop{'s' if depth != 1 else ''}",
            "detail": "Each laundering hop lowers traceability", "hops": depth}


def _longest_path(out: Dict[str, List[str]], root: str, cap: int = 12) -> int:
    best = 0
    stack = [(root, 0, frozenset({root}))]
    while stack:
        node, d, path = stack.pop()
        best = max(best, d)
        if d >= cap:
            continue
        for nxt in out.get(node, []):
            if nxt not in path:
                stack.append((nxt, d + 1, path | {nxt}))
    return best


def _graph_diameter(out: Dict[str, List[str]]) -> int:
    return max((_longest_path(out, n) for n in out.keys()), default=0)


def factor_dispersion(case: dict, fs: dict) -> dict:
    recipients = [a for a, f in fs["flows"].items() if f["incoming"] > 0]
    n = max(1, len(recipients))
    score = _clamp(100 - (n - 1) * CONFIG["dispersion_penalty_per_recipient"], 12)
    label = "Concentrated" if n <= 2 else "Moderately spread" if n <= 6 else "Highly distributed"
    return {"key": "dispersion", "name": "Funds Dispersion", "score": score,
            "label": label, "detail": f"Funds spread across {n} account{'s' if n != 1 else ''}",
            "recipients": n}


def factor_withdrawal(case: dict, fs: dict) -> dict:
    wf = fs["withdrawn_fraction"]
    still_in = fs["still_in_fraction"]
    score = _clamp(still_in * 100)
    status = ("Funds still in banking network" if wf < 0.25 else
              "Funds partially withdrawn" if wf < 0.7 else
              "Funds largely withdrawn (cash-out)")
    return {"key": "withdrawal", "name": "Withdrawal Status", "score": score,
            "label": status, "detail": f"{round(still_in * 100)}% still traceable in-network",
            "still_in_fraction": round(still_in, 3), "withdrawn_fraction": round(wf, 3)}


def critical_accounts(case: dict, fs: dict) -> List[dict]:
    """Accounts still HOLDING recoverable funds (net balance), ranked by freeze
    impact. Held amount is the real sitting balance — inbound minus outbound."""
    in_network = fs["in_network"] or 1.0
    still_in = fs["still_in_fraction"]
    out = []
    for acc, f in sorted(fs["flows"].items(), key=lambda kv: kv[1]["net_balance"], reverse=True):
        net = f["net_balance"]
        if net <= 0:
            continue
        risk = f["risk"]
        freeze_success = _clamp(CONFIG["freeze_base_success"] - max(0, risk - 70) * CONFIG["freeze_risk_penalty"]) \
            * (0.6 + 0.4 * still_in)
        out.append({
            "account": acc,
            "held_amount": round(net),
            "freeze_impact": round(net / in_network * 100),   # % of recoverable funds preserved
            "freeze_success": _clamp(freeze_success),          # likelihood freeze lands in time
            "risk": risk,
        })
    return out[:6]


def factor_freeze(case: dict, fs: dict) -> dict:
    crit = critical_accounts(case, fs)
    if not crit:
        return {"key": "freeze", "name": "Account Freeze Potential", "score": 18,
                "label": "No funds remain in freezable accounts",
                "detail": "Net balances have already left the holding accounts",
                "critical_accounts": []}
    top = crit[0]
    score = _clamp(0.5 * top["freeze_success"] + 0.5 * top["freeze_impact"])
    return {"key": "freeze", "name": "Account Freeze Potential", "score": score,
            "label": f"Freeze {top['account']} → preserves {top['freeze_impact']}%",
            "detail": f"Freeze success likelihood {top['freeze_success']}%",
            "critical_accounts": crit}


def factor_containment(case: dict, fs: dict) -> dict:
    out, _, meta = _adjacency(case)
    nodes = set(meta.keys())
    edges = sum(len(v) for v in out.values())
    routing = [n for n in nodes if len(out.get(n, [])) >= 2]   # branching hubs
    still_in = fs["still_in_fraction"]
    density = edges / max(1, len(nodes))
    base = 100 * still_in
    base -= len(routing) * CONFIG["containment_penalty_per_hub"]
    base -= max(0.0, density - 1.5) * CONFIG["containment_density_penalty"]
    score = _clamp(base, 10)
    label = "Network containable" if score >= 60 else "Partial containment" if score >= 35 else "Containment unlikely"
    return {"key": "containment", "name": "Network Containment", "score": score,
            "label": label, "detail": f"{len(routing)} routing hub(s), {len(nodes)} accounts",
            "routing_hubs": len(routing)}


_OUTCOME_RECOVERY = {   # historical case status → recovery proxy (Fraud DNA correlation)
    "Resolved": 88, "Closed": 70, "Escalated": 48,
    "Active": 50, "Under Investigation": 52, "New": 55, "False Positive": 60,
}


def factor_dna(case: dict, similar: Optional[dict]) -> dict:
    matches = (similar or {}).get("matches", []) if similar else []
    if not matches:
        return {"key": "dna", "name": "Fraud DNA Correlation", "score": 50,
                "label": "No historical analogue", "detail": "Scored on intrinsic factors only",
                "matches": []}
    num = den = 0.0
    enriched = []
    for m in matches[:5]:
        sim = m.get("similarity", 0) / 100.0
        status = (m.get("status") or "Active")
        rec = _OUTCOME_RECOVERY.get(status, 50)
        num += sim * rec
        den += sim
        enriched.append({"case_id": m.get("case_id"), "title": m.get("title"),
                         "similarity": m.get("similarity"), "status": status, "recovery_proxy": rec})
    score = _clamp(num / den if den else 50)
    best = enriched[0]
    return {"key": "dna", "name": "Fraud DNA Correlation", "score": score,
            "label": f"{best['similarity']}% match → {best['case_id']}",
            "detail": f"Similar cases historically recovered ~{score}%",
            "matches": enriched}


def factor_timeline(case: dict, fs: dict, now: float) -> dict:
    h = _age_hours(case, now)
    still_in = fs["still_in_fraction"]
    close_at = _hours_until(CONFIG["low_recovery_floor"], still_in)
    window_h = max(0.0, close_at - h)
    score = _clamp(100 * (window_h / close_at)) if close_at > 0 else 0
    curve = []
    for t in (0, 1, 3, 6, 12, 24, 48, 72, 168):
        proj = _clamp(_decay(h + t) * still_in, 2)
        curve.append({"hours": t, "recovery": proj})
    return {"key": "timeline", "name": "Recovery Timeline", "score": score,
            "label": _fmt_window(window_h), "detail": "Optimal action window remaining",
            "window_seconds": int(window_h * 3600), "decay_curve": curve}


def factor_beneficiary(case: dict, fs: dict) -> dict:
    out, _, _ = _adjacency(case)
    flows = fs["flows"]
    # beneficiaries = terminal accounts that received funds and send little onward
    bens = [a for a, f in flows.items() if f["incoming"] > 0 and len(out.get(a, [])) == 0]
    bens = bens or [a for a, f in flows.items() if f["incoming"] > 0]
    if not bens:
        return {"key": "beneficiary", "name": "Beneficiary Risk", "score": 50,
                "label": "Beneficiaries unidentified", "detail": "No terminal accounts resolved",
                "beneficiaries": 0}
    avg_risk = sum(flows[a]["risk"] for a in bens) / len(bens)
    score = _clamp(100 - avg_risk)
    label = ("Low-risk beneficiaries" if avg_risk < 40 else
             "Mixed beneficiary risk" if avg_risk < 70 else "High-risk beneficiaries")
    return {"key": "beneficiary", "name": "Beneficiary Risk", "score": score,
            "label": label, "detail": f"{len(bens)} beneficiary account(s), avg risk {round(avg_risk)}",
            "beneficiaries": len(bens), "avg_risk": round(avg_risk)}


def kill_node(case: dict) -> Optional[dict]:
    out, inn, meta = _adjacency(case)
    nodes = set(meta.keys())
    if not nodes:
        return None
    total_deg = sum(len(out.get(n, [])) + len(inn.get(n, [])) for n in nodes) or 1
    best = max(nodes, key=lambda n: len(out.get(n, [])) + len(inn.get(n, [])))
    deg = len(out.get(best, [])) + len(inn.get(best, []))
    if deg == 0:
        return None
    disruption = _clamp(deg / total_deg * 100 + len(out.get(best, [])) * 6)
    return {"account": best, "disruption_pct": disruption,
            "degree": deg, "risk": meta.get(best, {}).get("risk")}


def factor_disruption(case: dict, fs: dict) -> dict:
    kn = kill_node(case)
    still_in = fs["still_in_fraction"]
    if not kn:
        return {"key": "disruption", "name": "Network Disruption", "score": 30,
                "label": "No dominant routing node", "detail": "Disruption leverage limited",
                "kill_node": None}
    score = _clamp(0.6 * kn["disruption_pct"] + 40 * still_in)
    return {"key": "disruption", "name": "Network Disruption", "score": score,
            "label": f"Kill node {kn['account']} → disrupts {kn['disruption_pct']}%",
            "detail": "Highest-centrality routing account", "kill_node": kn}


# ── Confidence (in the prediction itself, distinct from probability) ──────────
def _confidence(case: dict, factors: List[dict], similar: Optional[dict]) -> int:
    txs = len(case.get("transactions", []))
    nodes = len(case.get("graph_snapshot", {}).get("nodes", []))
    matches = len((similar or {}).get("matches", []) if similar else [])
    data = min(30, txs * 4 + nodes * 2 + matches * 3)
    scores = [f["score"] for f in factors]
    spread = (max(scores) - min(scores)) if scores else 100
    agreement = max(0, 30 - spread * 0.3)
    return _clamp(50 + data + agreement, 40, 97)


# ══════════════════════════════════════════════════════════════════════════════
# DERIVED OUTPUTS — funnel, traceability, paths, reasons, obstacles
# ══════════════════════════════════════════════════════════════════════════════
def recovery_funnel(case: dict, fs: dict, prob: int, crit: List[dict]) -> dict:
    """Recoverable = funds actually still sitting in traceable accounts.
    likely_recoverable = Σ over holders of net · freeze_success · prob/freeze blend."""
    originated = fs["originated"]
    in_network = fs["in_network"]
    pw, fw = CONFIG["likely_prob_weight"], CONFIG["likely_freeze_weight"]
    likely = 0.0
    for c in crit:
        time_factor = pw * (prob / 100.0) + fw * (c["freeze_success"] / 100.0)
        likely += c["held_amount"] * time_factor
    likely = min(likely, in_network)
    return {
        "fraud_amount": round(originated),
        "still_traceable": round(in_network),
        "recoverable": round(in_network),
        "likely_recoverable": round(likely),
        "cashed_out": round(fs["cashed_out"]),
        "exited_network": round(fs["exited"]),
    }


def traceability(case: dict, fs: dict) -> List[dict]:
    """Per-account flow-of-funds: where the money currently is."""
    in_network = fs["in_network"] or 1.0
    rows = []
    for acc, f in fs["flows"].items():
        net = f["net_balance"]
        if f["incoming"] <= 0 and f["outgoing"] <= 0:
            continue
        if acc in fs["sources"]:
            status = "Source (victim/origin)"
        elif f["cash_received"] > 0 and f["traceable_incoming"] <= 0:
            status = "Cash-out destination (off-network)"
        elif f["cash_out"] > 0:
            status = "Withdrew to cash"
        elif net <= max(1.0, 0.02 * f["incoming"]):
            status = "Pass-through"
        else:
            status = "Holding funds"
        rows.append({
            "account": acc,
            "incoming": round(f["incoming"]),
            "outgoing": round(f["outgoing"]),
            "traceable_balance": round(net),
            "retained": round(net),
            "dispersed": round(f["dispersed"]),
            "cashed_out": round(f["cash_out"]),
            "status": status,
            "risk": f["risk"],
            "recovery_importance": round(net / in_network * 100),
        })
    rows.sort(key=lambda r: r["traceable_balance"], reverse=True)
    return rows


def recovery_paths(case: dict, fs: dict, limit: int = 6) -> List[dict]:
    """Ranked routes from a source to where recoverable money is now sitting.
    A path's recoverable value is the net balance currently held at its terminal."""
    out, _, _ = _adjacency(case)
    flows = fs["flows"]
    sources = fs["sources"] or [a for a, f in flows.items() if f["incoming"] <= CONFIG["source_epsilon"]]
    holders = {a for a, f in flows.items() if f["net_balance"] > 0}
    if not holders:
        return []

    # shortest route from any source to each holder (BFS over the flagged graph)
    paths: List[dict] = []
    for holder in holders:
        best_path = None
        for src in sources:
            q = deque([[src]])
            seen = {src}
            while q:
                path = q.popleft()
                node = path[-1]
                if node == holder:
                    best_path = path
                    break
                for nxt in out.get(node, []):
                    if nxt not in seen:
                        seen.add(nxt)
                        q.append(path + [nxt])
            if best_path:
                break
        path = best_path or [holder]
        paths.append({
            "path": path,
            "terminal": holder,
            "recoverable_amount": round(flows[holder]["net_balance"]),
            "hops": len(path) - 1,
            "risk": flows[holder]["risk"],
        })
    paths.sort(key=lambda p: p["recoverable_amount"], reverse=True)
    for i, p in enumerate(paths, 1):
        p["priority"] = i
    return paths[:limit]


def build_reasons(case: dict, fs: dict, factors: Dict[str, dict], prob: int,
                  crit: List[dict]) -> List[dict]:
    """Explain the probability — every bullet cites an actual computed number."""
    r: List[dict] = []
    still = round(fs["still_in_fraction"] * 100)
    wd = round(fs["withdrawn_fraction"] * 100)
    holders = [c for c in crit]
    r.append({"polarity": "positive" if still >= 50 else "negative",
              "text": f"{still}% of originated funds remain inside monitored accounts."})
    if wd > 0:
        r.append({"polarity": "negative",
                  "text": f"{wd}% has been cashed out / left the banking network."})
    else:
        r.append({"polarity": "positive", "text": "No confirmed cash withdrawal detected."})
    if holders:
        r.append({"polarity": "positive",
                  "text": f"{len(holders)} account(s) still hold recoverable balances; "
                          f"{holders[0]['account']} holds {holders[0]['freeze_impact']}% of them."})
    else:
        r.append({"polarity": "negative",
                  "text": "No account currently holds a recoverable net balance."})
    depth = factors["depth"]["hops"]
    r.append({"polarity": "positive" if depth <= 2 else "negative",
              "text": f"Layering depth is {depth} hop(s) — "
                      f"{'traceability intact' if depth <= 2 else 'traceability degraded'}."})
    age = factors["age"]
    r.append({"polarity": "positive" if age["age_hours"] < 24 else "negative",
              "text": f"{age['detail']} — recall window {'still open' if age['age_hours'] < 24 else 'narrowing'}."})
    bens = factors["beneficiary"]
    if bens.get("beneficiaries"):
        r.append({"polarity": "positive" if bens.get("avg_risk", 50) < 60 else "negative",
                  "text": f"{bens['beneficiaries']} beneficiary account(s), average risk {bens.get('avg_risk')}."})
    return r


def build_obstacles(case: dict, fs: dict, factors: Dict[str, dict]) -> List[dict]:
    """Concrete reasons recovery is reduced, each with a severity."""
    obs: List[dict] = []
    wf = fs["withdrawn_fraction"]
    if wf >= 0.7:
        obs.append({"obstacle": "Funds largely cashed out", "severity": "Critical",
                    "detail": f"{round(wf*100)}% withdrawn via cash rails."})
    elif wf >= 0.25:
        obs.append({"obstacle": "Partial cash-out confirmed", "severity": "High",
                    "detail": f"{round(wf*100)}% has left the banking network."})
    if fs["intl_out"] > 0:
        obs.append({"obstacle": "International / off-network transfer detected", "severity": "Critical",
                    "detail": f"₹{round(fs['intl_out']):,} routed via cross-border / crypto rails."})
    depth = factors["depth"]["hops"]
    if depth >= 4:
        obs.append({"obstacle": "Deep layering", "severity": "High",
                    "detail": f"{depth} laundering hops obscure the trail."})
    recip = factors["dispersion"].get("recipients", 1)
    if recip >= 7:
        obs.append({"obstacle": "Funds fragmented across many accounts", "severity": "High",
                    "detail": f"Spread across {recip} accounts — many parallel freezes required."})
    if not factors["freeze"].get("critical_accounts"):
        obs.append({"obstacle": "No recoverable balance localised", "severity": "Critical",
                    "detail": "Net balances have already moved out of holding accounts."})
    age_h = factors["age"]["age_hours"]
    if age_h >= 48:
        obs.append({"obstacle": "Aged transactions", "severity": "Medium",
                    "detail": f"{_fmt_age(age_h)} elapsed — recall windows largely closed."})
    return obs


# ── Recommended actions (ranked by expected recovery gain) ────────────────────
def _profile_recovery_action(case: dict, crit: List[dict]) -> Optional[dict]:
    """Profile-aware recovery step: tailor the freeze/investigation order to the
    customer type of the account holding the funds (corporate → settlement account
    first + shell-chain trace; retail/student → freeze the receiving mule account;
    sme/business → unwind the vendor/shell chain). Deterministic; best-effort."""
    if not crit:
        return None
    try:
        from profile_intelligence import assess_component
        edges = [{"source": t.get("from_account"), "target": t.get("to_account"),
                  "amount": t.get("amount", 0), "payment_rail": t.get("rail", "")}
                 for t in case.get("transactions", []) if t.get("from_account") and t.get("to_account")]
        if not edges:
            return None
        node_ids = sorted({e["source"] for e in edges} | {e["target"] for e in edges})
        pi = assess_component({"node_ids": node_ids, "nodes": [{"id": n} for n in node_ids], "edges": edges})
        target = crit[0]["account"]
        acc = pi.get("accounts", {}).get(target)
        if not acc:
            return None
        seg, label = acc["segment"], acc["label"]
        if seg == "corporate":
            text = (f"Freeze the corporate settlement account {target} first and trace the "
                    f"shell-company chain — {label} flows settle through a primary account.")
        elif seg == "retail":
            text = (f"Freeze the receiving account {target} immediately — a {label} acting as a "
                    f"collection point is most likely a mule; funds move out fast.")
        else:  # sme / institution / unknown
            text = (f"Investigate the vendor / shell-company chain around {target} before "
                    f"unwinding — preserve genuine {label} settlements while isolating the laundering legs.")
        return {"action": f"Profile-aware containment for {target}", "target": target,
                "type": "profile_freeze", "impact": "High", "expected_recovery_increase": 10,
                "rationale": text, "customer_profile": label}
    except Exception:
        return None


def recommend_actions(case: dict, factors: Dict[str, dict]) -> List[dict]:
    actions: List[dict] = []
    wf = factors["withdrawal"]["withdrawn_fraction"]
    crit = factors["freeze"].get("critical_accounts", [])
    kn = factors["disruption"].get("kill_node")
    age_h = factors["age"]["age_hours"]

    if crit:
        top = crit[0]
        actions.append({
            "priority": 1, "action": f"Freeze account {top['account']}",
            "target": top["account"], "type": "freeze",
            "impact": "Very High" if top["freeze_impact"] >= 50 else "High",
            "expected_recovery_increase": min(40, round(top["freeze_impact"] * 0.5 + top["freeze_success"] * 0.15)),
            "rationale": f"Holds {top['freeze_impact']}% of recoverable funds (₹{top['held_amount']:,}); "
                         f"freeze success ~{top['freeze_success']}%.",
        })
    if kn and (not crit or kn["account"] != crit[0]["account"]):
        actions.append({
            "action": f"Isolate routing node {kn['account']}", "target": kn["account"], "type": "isolate",
            "impact": "High" if kn["disruption_pct"] >= 50 else "Medium",
            "expected_recovery_increase": min(28, round(kn["disruption_pct"] * 0.3)),
            "rationale": f"Disrupts {kn['disruption_pct']}% of fraud routing.",
        })
    if age_h < 24 and wf < 0.7:
        actions.append({
            "action": "Initiate inter-bank fund recall / chargeback", "type": "recall", "target": None,
            "impact": "High", "expected_recovery_increase": min(24, round((24 - age_h) * 0.9)),
            "rationale": "Recall windows on RTGS/IMPS/NEFT are still open at this age.",
        })
    for c in crit[1:3]:
        actions.append({
            "action": f"Freeze secondary holder {c['account']}", "target": c["account"], "type": "freeze",
            "impact": "Medium", "expected_recovery_increase": min(15, round(c["freeze_impact"] * 0.4)),
            "rationale": f"Holds {c['freeze_impact']}% of recoverable funds (₹{c['held_amount']:,}).",
        })
    if wf >= 0.7:
        actions.append({
            "action": "Escalate to law enforcement & file beneficiary lookout", "type": "escalate", "target": None,
            "impact": "Medium", "expected_recovery_increase": 8,
            "rationale": "Funds largely cashed out — pivot to legal recovery and account holder lookout.",
        })
    actions.append({
        "action": "Escalate case to recovery desk & notify beneficiary banks", "type": "escalate", "target": None,
        "impact": "Medium", "expected_recovery_increase": 6,
        "rationale": "Parallel-track formal recovery so no window is missed.",
    })

    pa = _profile_recovery_action(case, crit)   # profile-aware recommendation (Phase 10)
    if pa:
        actions.append(pa)

    actions.sort(key=lambda a: a["expected_recovery_increase"], reverse=True)
    for i, a in enumerate(actions, 1):
        a["priority"] = i
    return actions


def headline_action(prob: int, factors: Dict[str, dict]) -> str:
    wf = factors["withdrawal"]["withdrawn_fraction"]
    crit = factors["freeze"].get("critical_accounts", [])
    if wf >= 0.75:
        return "Escalate to Law Enforcement"
    if crit and prob >= 40:
        return "Freeze Accounts Immediately"
    if prob >= 40:
        return "Initiate Fund Recall"
    return "Escalate Case for Manual Recovery"


def _insufficient(case: dict, now: float, reason: str) -> dict:
    """Validation refusal — the engine will not invent numbers."""
    return {
        "case_id": case.get("case_id"), "title": case.get("title"),
        "category": case.get("category"), "status": case.get("status"),
        "insufficient_evidence": True, "evidence_message": reason,
        "recovery_probability": 0, "band": "Insufficient Evidence", "confidence": 0,
        "estimated_loss": 0, "expected_recoverable": 0,
        "headline_action": "Gather transaction evidence",
        "funnel": {"fraud_amount": 0, "still_traceable": 0, "recoverable": 0,
                   "likely_recoverable": 0, "cashed_out": 0, "exited_network": 0},
        "factors": [], "weights": WEIGHTS, "critical_accounts": [], "kill_node": None,
        "decay_curve": [], "window_seconds": 0, "actions": [],
        "reasons": [], "obstacles": [], "traceability": [], "recovery_paths": [],
        "flow": {"originated": 0, "in_network": 0, "cashed_out": 0, "exited": 0},
        "generated_at": now,
    }


# ══════════════════════════════════════════════════════════════════════════════
# TOP-LEVEL ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
def analyze(case: dict, similar: Optional[dict] = None, now: Optional[float] = None) -> dict:
    now = now or time.time()

    # ── validation: refuse to estimate without usable evidence ───────────────
    if not case.get("transactions") and not (case.get("graph_snapshot") or {}).get("edges"):
        return _insufficient(case, now, "No transactions or graph edges on this case.")
    fs = fund_state(case)
    if fs["originated"] <= 0:
        return _insufficient(case, now, "No traceable fund flow could be reconstructed.")

    flist = [
        factor_age(case, now),
        factor_depth(case),
        factor_dispersion(case, fs),
        factor_withdrawal(case, fs),
        factor_freeze(case, fs),
        factor_containment(case, fs),
        factor_dna(case, similar),
        factor_timeline(case, fs, now),
        factor_beneficiary(case, fs),
        factor_disruption(case, fs),
    ]
    factors = {f["key"]: f for f in flist}
    prob = _clamp(sum(factors[k]["score"] * w for k, w in WEIGHTS.items()))
    confidence = _confidence(case, flist, similar)
    crit = factors["freeze"].get("critical_accounts", [])
    funnel = recovery_funnel(case, fs, prob, crit)
    actions = recommend_actions(case, factors)
    estimated_loss = round(max(0.0, fs["originated"] - funnel["likely_recoverable"]))

    return {
        "case_id": case.get("case_id"),
        "title": case.get("title"),
        "category": case.get("category"),
        "status": case.get("status"),
        "insufficient_evidence": False,
        "recovery_probability": prob,
        "band": _band(prob),
        "confidence": confidence,
        "estimated_loss": estimated_loss,                 # originated − likely recoverable
        "expected_recoverable": funnel["likely_recoverable"],
        "headline_action": headline_action(prob, factors),
        "funnel": funnel,
        "factors": flist,
        "weights": WEIGHTS,
        "critical_accounts": crit,
        "kill_node": factors["disruption"].get("kill_node"),
        "decay_curve": factors["timeline"]["decay_curve"],
        "window_seconds": factors["timeline"]["window_seconds"],
        "actions": actions,
        # ── new explainability surfaces (all derived from fund_state) ────────
        "reasons": build_reasons(case, fs, factors, prob, crit),
        "obstacles": build_obstacles(case, fs, factors),
        "traceability": traceability(case, fs),
        "recovery_paths": recovery_paths(case, fs),
        "flow": {
            "originated": round(fs["originated"]),
            "in_network": round(fs["in_network"]),
            "cashed_out": round(fs["cashed_out"]),
            "exited": round(fs["exited"]),
            "still_in_fraction": round(fs["still_in_fraction"], 3),
            "withdrawn_fraction": round(fs["withdrawn_fraction"], 3),
        },
        "generated_at": now,
    }


# ── Predictive simulation ─────────────────────────────────────────────────────
def simulate(case: dict, similar: Optional[dict], scenario: str,
             account: Optional[str] = None, delay_hours: float = 0.0,
             now: Optional[float] = None) -> dict:
    """Re-score under a hypothetical intervention. Deterministic perturbations of
    the baseline factors keep the result explainable to an investigator."""
    now = now or time.time()
    base = analyze(case, similar, now)
    if base.get("insufficient_evidence"):
        return {
            "case_id": case.get("case_id"), "scenario": scenario, "account": account,
            "delay_hours": delay_hours, "baseline_probability": 0, "simulated_probability": 0,
            "delta": 0, "baseline_recoverable": 0, "simulated_recoverable": 0,
            "recoverable_delta": 0, "note": "Insufficient evidence to simulate.",
        }
    factors = {f["key"]: dict(f) for f in base["factors"]}

    note = ""
    if scenario == "freeze":
        crit = base["critical_accounts"]
        target = account or (crit[0]["account"] if crit else None)
        hit = next((c for c in crit if c["account"] == target), crit[0] if crit else None)
        if hit:
            factors["withdrawal"]["score"] = _clamp(factors["withdrawal"]["score"] + hit["freeze_impact"] * 0.6)
            factors["freeze"]["score"] = _clamp(factors["freeze"]["score"] + 20)
            factors["containment"]["score"] = _clamp(factors["containment"]["score"] + 12)
            note = f"Freezing {hit['account']} preserves {hit['freeze_impact']}% of recoverable funds (₹{hit['held_amount']:,})."
        else:
            note = "No freezable holding account available."
    elif scenario == "no_action":
        for k in ("age", "timeline", "withdrawal"):
            factors[k]["score"] = _clamp(factors[k]["score"] * 0.6)
        note = "No intervention: funds continue to disperse and cash out."
    elif scenario == "delay":
        d = max(0.0, delay_hours)
        age0 = next((x["age_hours"] for x in base["factors"] if x["key"] == "age"), 0.0)
        ratio = _decay(age0 + d) / _decay(age0) if _decay(age0) > 0 else 0.0
        for k in ("age", "timeline"):
            factors[k]["score"] = _clamp(factors[k]["score"] * ratio)
        factors["withdrawal"]["score"] = _clamp(factors["withdrawal"]["score"] * (0.6 + 0.4 * ratio))
        note = f"Delaying action {int(d)}h erodes the recovery window."

    prob = _clamp(sum(factors[k]["score"] * w for k, w in WEIGHTS.items()))
    funnel = dict(base["funnel"])
    ratio = prob / max(1, base["recovery_probability"])
    funnel["likely_recoverable"] = round(min(funnel["recoverable"], funnel["likely_recoverable"] * ratio))
    return {
        "case_id": case.get("case_id"),
        "scenario": scenario,
        "account": account,
        "delay_hours": delay_hours,
        "baseline_probability": base["recovery_probability"],
        "simulated_probability": prob,
        "delta": prob - base["recovery_probability"],
        "baseline_recoverable": base["expected_recoverable"],
        "simulated_recoverable": funnel["likely_recoverable"],
        "recoverable_delta": funnel["likely_recoverable"] - base["expected_recoverable"],
        "note": note,
    }
