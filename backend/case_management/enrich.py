"""
Case enrichment — the "single source of truth" layer.

Bakes the output of every analysis engine directly INTO the case object at
creation time (and as a one-off migration for older cases), so opening a case
NEVER recalculates anything:

  • recovery          — projection of recovery.engine.analyze(case)
  • fraud_dna         — projection of fraud_dna.engine.build_genes(case)
  • account_roles     — per-account role / risk / in-out / status table
  • roles             — suspect / victim / intermediary / destination buckets
  • payment_rails     — distinct rails used
  • financials        — total / recoverable / loss / probability / timeline
  • raw_graph_json    — full graph payload (verbatim-restore ready)
  • raw_transaction_json
  • graph_snapshot.camera — schema slot for the verbatim camera (frontend fills)
  • blockchain        — anchor/verify/receipt slot (BELS phase fills)

All engine calls are LAZY (imported inside functions) so there is no module-load
import cycle with recovery / fraud_dna, which themselves read the case store.
Everything is best-effort: a failing engine degrades to sane defaults rather than
breaking case creation.
"""

from __future__ import annotations

import time
from typing import Dict, List, Tuple


def _now() -> float:
    return time.time()


# ── account registry (best-effort) ──────────────────────────────────────────
def _registry_meta(account: str) -> dict:
    """{risk, status} for an account from the auth registry, if available."""
    try:
        from auth.accounts_db import registry
        resolved = registry.resolve(account) or account
        rec = registry.get(resolved)
        if rec:
            return {
                "risk": int(rec.get("risk_score", 50)),
                "status": rec.get("freeze_status")
                or rec.get("investigation_status")
                or "Active",
                "dormant": "dormant" in " ".join(rec.get("flags", [])).lower(),
            }
    except Exception:
        pass
    return {}


# ── per-account flow stats from the transaction list ────────────────────────
def _account_stats(case: dict) -> Dict[str, dict]:
    stats: Dict[str, dict] = {}

    def slot(a: str) -> dict:
        return stats.setdefault(a, {"incoming": 0.0, "outgoing": 0.0, "txns": 0})

    for t in case.get("transactions", []):
        src = t.get("from_account")
        dst = t.get("to_account")
        amt = float(t.get("amount", 0) or 0)
        if src:
            s = slot(src); s["outgoing"] += amt; s["txns"] += 1
        if dst:
            d = slot(dst); d["incoming"] += amt; d["txns"] += 1
    # Make sure every listed account appears even with no flagged txns.
    for a in case.get("accounts", []):
        slot(a)
    return stats


# ── directed adjacency + graph metrics ──────────────────────────────────────
def _adjacency(case: dict) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    out: Dict[str, List[str]] = {}
    inn: Dict[str, List[str]] = {}
    pairs = set()
    for t in case.get("transactions", []):
        s, d = t.get("from_account"), t.get("to_account")
        if s and d and (s, d) not in pairs:
            pairs.add((s, d))
    # graph_snapshot edges fill in structure the txn list may not carry
    for e in case.get("graph_snapshot", {}).get("edges", []):
        s, d = e.get("from"), e.get("to")
        if s and d and (s, d) not in pairs:
            pairs.add((s, d))
    for s, d in pairs:
        out.setdefault(s, []).append(d)
        out.setdefault(d, [])
        inn.setdefault(d, []).append(s)
        inn.setdefault(s, [])
    return out, inn


def _longest_path(out: Dict[str, List[str]]) -> int:
    """Longest directed path length (layering depth), cycle-safe."""
    color: Dict[str, int] = {}          # 0=unseen 1=on-stack 2=done
    best: Dict[str, int] = {}
    order: List[str] = []
    nodes = list(out.keys())
    for start in nodes:
        if color.get(start, 0) != 0:
            continue
        stack = [(start, 0)]
        color[start] = 1
        while stack:
            node, i = stack[-1]
            succ = out.get(node, [])
            if i < len(succ):
                stack[-1] = (node, i + 1)
                nxt = succ[i]
                c = color.get(nxt, 0)
                if c == 0:
                    color[nxt] = 1
                    stack.append((nxt, 0))
                # c == 1 → back-edge (cycle), skip; c == 2 → already resolved
            else:
                color[node] = 2
                order.append(node)
                stack.pop()
    # DAG-ish longest path via reverse-finish order (back-edges ignored)
    for node in order:
        d = 0
        for nxt in out.get(node, []):
            if color.get(nxt) == 2:
                d = max(d, best.get(nxt, 0) + 1)
        best[node] = d
    return (max(best.values()) + 1) if best else 1


def _graph_metrics(case: dict) -> dict:
    out, inn = _adjacency(case)
    nodes = set(out) | set(inn) | set(case.get("accounts", []))
    n = len(nodes) or 1
    edges = sum(len(v) for v in out.values())
    fan_out = max((len(v) for v in out.values()), default=0)
    fan_in = max((len(v) for v in inn.values()), default=0)
    # circular = a node reachable back to itself (any cycle present)
    circular = _has_cycle(out)
    density = round(edges / (n * (n - 1) / 2), 3) if n > 1 else 0.0
    return {
        "accounts": n,
        "edges": edges,
        "fan_out": fan_out,
        "fan_in": fan_in,
        "layering_depth": _longest_path(out),
        "circular_transfers": circular,
        "density": density,
        "network_complexity": "High" if density >= 0.5 or n >= 9 else "Medium" if n >= 5 else "Low",
    }


def _has_cycle(out: Dict[str, List[str]]) -> bool:
    color: Dict[str, int] = {}
    for start in list(out.keys()):
        if color.get(start, 0) != 0:
            continue
        stack = [(start, 0)]
        color[start] = 1
        while stack:
            node, i = stack[-1]
            succ = out.get(node, [])
            if i < len(succ):
                stack[-1] = (node, i + 1)
                nxt = succ[i]
                c = color.get(nxt, 0)
                if c == 0:
                    color[nxt] = 1
                    stack.append((nxt, 0))
                elif c == 1:
                    return True
            else:
                color[node] = 2
                stack.pop()
    return False


# ── role classification ─────────────────────────────────────────────────────
def _classify_roles(case: dict, stats: Dict[str, dict]) -> Tuple[List[dict], dict]:
    primary = case.get("primary_account")
    case_risk = int(case.get("risk_score", 50))
    rows: List[dict] = []
    buckets = {"primary_suspects": [], "victims": [], "intermediaries": [], "destinations": []}

    for acc, st in stats.items():
        meta = _registry_meta(acc)
        risk = meta.get("risk", case_risk if acc == primary else max(20, case_risk - 25))
        status = meta.get("status", "Active")
        inc, outg = st["incoming"], st["outgoing"]

        if acc == primary:
            role = "Primary Source"
            buckets["primary_suspects"].append(acc)
        elif outg > 0 and inc == 0:
            # money enters the network here: high-risk → suspect source, else victim
            if risk >= 70:
                role = "Primary Source"; buckets["primary_suspects"].append(acc)
            else:
                role = "Victim"; buckets["victims"].append(acc)
        elif inc > 0 and outg == 0:
            role = "Destination"; buckets["destinations"].append(acc)
        elif inc > 0 and outg > 0:
            role = "Intermediary"; buckets["intermediaries"].append(acc)
        else:
            role = "Linked"

        rows.append({
            "account": acc,
            "role": role,
            "risk": risk,
            "transactions": st["txns"],
            "incoming": round(inc),
            "outgoing": round(outg),
            "status": status,
        })

    # Highest-risk / most-connected first
    rows.sort(key=lambda r: (r["risk"], r["transactions"]), reverse=True)
    return rows, buckets


# ── recovery projection ─────────────────────────────────────────────────────
def _fmt_timeline(window_seconds: int) -> str:
    h = max(0, int(window_seconds // 3600))
    if h <= 0:
        return "Action window closed"
    if h >= 24:
        return f"~{h // 24}d {h % 24}h optimal action window"
    return f"~{h}h optimal action window"


def build_recovery(case: dict) -> dict:
    try:
        from recovery.engine import analyze
        a = analyze(case)
        crit = a.get("critical_accounts", []) or []
        freeze = [c["account"] for c in crit]
        # most / least recoverable branch by freeze impact
        most = crit[0]["account"] if crit else None
        least = (a.get("kill_node") or {}).get("account") if a.get("kill_node") else (
            crit[-1]["account"] if crit else None)
        return {
            "probability": a.get("recovery_probability", 0),
            "band": a.get("band"),
            "confidence": a.get("confidence"),
            "estimated_loss": a.get("estimated_loss", 0),
            "expected_recoverable": a.get("expected_recoverable", 0),
            "timeline": _fmt_timeline(a.get("window_seconds", 0)),
            "window_seconds": a.get("window_seconds", 0),
            "accounts_to_freeze": freeze,
            "critical_accounts": crit,
            "most_recoverable_branch": most,
            "least_recoverable_branch": least,
            "headline_action": a.get("headline_action"),
            "recommended_priority": case.get("priority"),
            "generated_at": a.get("generated_at", _now()),
        }
    except Exception:
        return {
            "probability": 0, "band": None, "confidence": 0,
            "estimated_loss": 0, "expected_recoverable": 0,
            "timeline": "Pending analysis", "window_seconds": 0,
            "accounts_to_freeze": [], "critical_accounts": [],
            "most_recoverable_branch": None, "least_recoverable_branch": None,
            "headline_action": None, "recommended_priority": case.get("priority"),
            "generated_at": _now(),
        }


# ── fraud DNA projection ────────────────────────────────────────────────────
def build_dna(case: dict, metrics: dict) -> dict:
    genes_by_name: Dict[str, dict] = {}
    dtype = "NET"
    explanation = ""
    try:
        from fraud_dna.engine import build_genes, dna_type, dna_id_for, signature, explain
        genes = build_genes(case)
        genes_by_name = {g["name"]: g for g in genes}
        dtype = dna_type(case)
        dna_id = dna_id_for(case.get("case_id", ""), dtype)
        sig = signature(genes)
        explanation = explain(case, genes, dtype, None)
    except Exception:
        genes, dna_id, sig = [], None, None

    flow = genes_by_name.get("Flow", {}).get("features", {})
    behavior = genes_by_name.get("Behavior", {})
    velocity = genes_by_name.get("Velocity", {})

    return {
        "dna_id": dna_id,
        "type": dtype,
        "signature": sig,
        "genes": [{"name": g["name"], "score": g["score"], "label": g["label"]} for g in genes],
        "behavior_summary": behavior.get("label", "Behavioural profile pending"),
        "money_movement_style": _movement_style(case, metrics, flow),
        "layering_depth": metrics["layering_depth"],
        "fan_out": metrics["fan_out"],
        "fan_in": metrics["fan_in"],
        "circular_transfers": metrics["circular_transfers"] or bool(flow.get("circular")),
        "dormant_accounts": case.get("_dormant_count", 0),
        "velocity": velocity.get("label", "—"),
        "velocity_score": velocity.get("score", 0),
        "network_complexity": metrics["network_complexity"],
        "explanation": explanation,
        "suggested_action": _suggested_action(case),
        "known_similar_cases": _similar_cases(case),
    }


def _movement_style(case: dict, metrics: dict, flow: dict) -> str:
    if metrics["circular_transfers"]:
        return "Circular / closed-loop laundering"
    if metrics["fan_out"] >= 3 and metrics["fan_in"] >= 3:
        return "Fan-out then fan-in consolidation"
    if metrics["fan_out"] >= 3:
        return "Fan-out dispersion"
    if metrics["fan_in"] >= 3:
        return "Fan-in aggregation"
    if metrics["layering_depth"] >= 3:
        return "Multi-hop layering chain"
    return "Direct transfer"


def _suggested_action(case: dict) -> str:
    rec = case.get("recovery") or {}
    if rec.get("headline_action"):
        return rec["headline_action"]
    freeze = (rec.get("accounts_to_freeze") or [])[:2]
    if freeze:
        return f"Freeze {', '.join(freeze)} and anchor evidence before funds disperse."
    return "Collect KYC/device evidence and anchor the graph snapshot to the ledger."


def _similar_cases(case: dict) -> List[dict]:
    try:
        from fraud_dna.store import store as dna_store
        sim = dna_store.similar(case.get("case_id", ""), k=3)
        return [
            {"case_id": m.get("case_id"), "title": m.get("title"),
             "similarity": m.get("similarity"), "status": m.get("status")}
            for m in (sim.get("matches", []) if isinstance(sim, dict) else [])
        ]
    except Exception:
        return []


# ── orchestration ───────────────────────────────────────────────────────────
def enrich_case(case: dict) -> dict:
    """Mutate `case` in place, attaching every baked analysis section."""
    stats = _account_stats(case)
    metrics = _graph_metrics(case)

    # role table + buckets
    account_roles, role_buckets = _classify_roles(case, stats)
    dormant = sum(1 for r in account_roles if str(r["status"]).lower().startswith("dormant"))
    case["_dormant_count"] = dormant

    # recovery FIRST (DNA's suggested_action reads it)
    case["recovery"] = build_recovery(case)
    case["fraud_dna"] = build_dna(case, metrics)
    case.pop("_dormant_count", None)

    case["account_roles"] = account_roles
    case["roles"] = role_buckets
    case["graph_metrics"] = metrics

    # payment rails
    rails = []
    for t in case.get("transactions", []):
        r = t.get("rail")
        if r and r not in rails:
            rails.append(r)
    case["payment_rails"] = rails

    # financials (top-level convenience mirror of recovery)
    total = sum(float(t.get("amount", 0) or 0) for t in case.get("transactions", []))
    case["financials"] = {
        "total_amount": round(total),
        "estimated_recoverable": case["recovery"]["expected_recoverable"],
        "estimated_loss": case["recovery"]["estimated_loss"],
        "recovery_probability": case["recovery"]["probability"],
        "recovery_timeline": case["recovery"]["timeline"],
    }

    # raw payloads (verbatim-restore ready)
    snap = case.get("graph_snapshot", {}) or {}
    snap.setdefault("camera", None)        # frontend fills the verbatim camera later
    case["graph_snapshot"] = snap
    case["raw_graph_json"] = {
        "nodes": snap.get("nodes", []),
        "edges": snap.get("edges", []),
        "indicators": snap.get("indicators", []),
        "camera": snap.get("camera"),
    }
    case["raw_transaction_json"] = case.get("transactions", [])

    # blockchain anchor slot — never clobber an existing receipt
    case.setdefault("blockchain", {
        "status": "Not Anchored", "verified": False, "hash": None,
        "txid": None, "certificate": None, "anchored_at": None, "items": [],
    })

    case["last_updated"] = case.get("updated_at", _now())
    return case
