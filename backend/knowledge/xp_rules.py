"""
Cross-Product (XP) rule family + detector (Phase 4).

XP rules name fraud that SPANS products/identities/channels rather than living
inside one account's transaction graph — the gap the AML001–024 catalogue can't
express. The catalogue is reference knowledge (description / severity / recovery
levers / analyst explanation); `detect_xp_signals` fires the subset that is
detectable on the data TGIE already carries today (payment rails, device id,
amounts, timing, entity types), and degrades gracefully when richer
identity/product edges are absent. Self-describing output mirrors the motif
schema so existing consumers render it unchanged.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from .entities import classify_entity, EntityType, entity_category

# ── XP rule catalogue ───────────────────────────────────────────────────────
XP_RULES: dict[str, dict[str, Any]] = {
    "XP001": {"name": "Rapid Product / Channel Switching", "severity": "HIGH",
              "recovery": ["limit_transfer", "step_up_auth"],
              "description": "One account moves money across many products/rails in a short window."},
    "XP002": {"name": "Savings → Credit-Card Cycling", "severity": "HIGH",
              "recovery": ["suspend_card", "review_refunds"],
              "description": "Funds cycle between savings and a credit card to fabricate activity/limits."},
    "XP003": {"name": "Loan Laundering", "severity": "CRITICAL",
              "recovery": ["flag_loan_review", "hold_disbursement"],
              "description": "Loan disbursement immediately exits through other products/foreign rails."},
    "XP004": {"name": "Wallet Layering", "severity": "HIGH",
              "recovery": ["limit_wallet", "freeze_wallet"],
              "description": "Funds are layered through one or more wallets to break the trail."},
    "XP005": {"name": "Merchant Refund Abuse", "severity": "HIGH",
              "recovery": ["review_refunds", "escalate_merchant_monitoring"],
              "description": "Card/merchant refunds are used as a laundering route back to an account."},
    "XP006": {"name": "Deposit Layering", "severity": "MEDIUM",
              "recovery": ["flag_review", "prevent_premature_closure"],
              "description": "Funds are parked in deposits then moved to obscure origin."},
    "XP007": {"name": "Premature FD Liquidation", "severity": "HIGH",
              "recovery": ["prevent_premature_closure", "flag_review"],
              "description": "A fixed deposit is broken early and rapidly cashed out."},
    "XP008": {"name": "Corporate Expense Diversion", "severity": "HIGH",
              "recovery": ["vendor_review", "pause_rtgs"],
              "description": "Corporate funds diverted through vendors/employees to personal accounts."},
    "XP009": {"name": "Shared Device Across Customers", "severity": "HIGH",
              "recovery": ["enhanced_kyc", "freeze"],
              "description": "One device transacts across many otherwise-unrelated accounts."},
    "XP010": {"name": "Shared Mobile Number", "severity": "HIGH",
              "recovery": ["enhanced_kyc"],
              "description": "One mobile number is registered against many accounts/customers."},
    "XP011": {"name": "Shared PAN / Identity", "severity": "CRITICAL",
              "recovery": ["enhanced_kyc", "freeze"],
              "description": "One PAN/identity links many accounts — synthetic-identity signature."},
    "XP012": {"name": "Cross-Product Structuring", "severity": "HIGH",
              "recovery": ["limit_transfer", "notify_fraud_ops"],
              "description": "Amounts kept just below thresholds across multiple products/rails."},
    "XP013": {"name": "Loan Payoff Through Mule", "severity": "HIGH",
              "recovery": ["flag_loan_review", "freeze"],
              "description": "A loan is repaid via mule accounts to launder illicit funds."},
    "XP014": {"name": "Multiple-Product Velocity", "severity": "HIGH",
              "recovery": ["limit_transfer", "step_up_auth"],
              "description": "An account interacts with several product categories at high velocity."},
    "XP015": {"name": "Dormant Product Activation", "severity": "MEDIUM",
              "recovery": ["step_up_auth", "flag_review"],
              "description": "A long-idle product suddenly transacts at volume."},
}

_SEVERITY_SCORE = {"LOW": 0.4, "MEDIUM": 0.55, "HIGH": 0.75, "CRITICAL": 0.9}
# round structuring bands (just-below common reporting/round thresholds, INR)
_STRUCTURING_BANDS = [(45000, 50000), (90000, 100000), (190000, 200000), (900000, 1000000)]


def _parse_ts(raw: Any) -> float | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def _signal(xp_id: str, entities: list[str], evidence: dict, confidence: float,
            explanation: str) -> dict[str, Any]:
    meta = XP_RULES[xp_id]
    return {
        "xp_id": xp_id,
        "name": meta["name"],
        "severity": meta["severity"],
        "severity_score": _SEVERITY_SCORE[meta["severity"]],
        "confidence": round(confidence, 3),
        "entities": sorted(set(entities)),
        "evidence": evidence,
        "recovery_recommendation": meta["recovery"],
        "analyst_explanation": explanation,
        "triggered": True,
    }


def detect_xp_signals(component: dict, config: dict | None = None) -> list[dict[str, Any]]:
    """
    Detect cross-product fraud signals on one component using the data TGIE
    already carries. Returns self-describing XP signal objects, strongest first.
    Fires only on clear evidence, so legitimate single-product activity yields
    nothing. `config` overrides the tunable thresholds (defaults = original
    hard-coded values), letting the learning loop evaluate candidate thresholds.
    """
    from .hetero import is_transaction_edge
    from . import xp_config
    cfg = config or xp_config.get_thresholds()

    nodes = component.get("nodes", []) or [{"id": n} for n in component.get("node_ids", [])]
    all_edges = component.get("edges", [])
    if not all_edges:
        return []

    # split money-moving edges from structural/identity edges (OWNS, HAS_*, …)
    edges = [e for e in all_edges if is_transaction_edge(e)]
    struct = [e for e in all_edges if not is_transaction_edge(e)]

    etype = {str(n.get("id")): classify_entity(n) for n in nodes}

    def et(nid: str) -> EntityType:
        return etype.get(str(nid), EntityType.ACCOUNT)

    # ownership map (product → owning customer), so "shared device" means shared
    # across DIFFERENT principals — not one customer's own accounts/merchant payees.
    owner_of: dict[str, str] = {}
    for e in struct:
        if e.get("relationship_type") == "OWNS":
            owner_of[str(e.get("target"))] = str(e.get("source"))

    signals: list[dict[str, Any]] = []

    # ── XP009 Shared device across DIFFERENT customers ──
    # Associate a device with the ACTOR (sender) of each transaction + explicit
    # HAS_DEVICE links; counterparties (merchants, cash endpoints) don't count.
    by_device: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        dev = e.get("device_id")
        if dev and str(dev).upper() != "MANUAL":
            by_device[str(dev)].add(str(e.get("source")))
    for e in struct:
        if e.get("relationship_type") == "HAS_DEVICE":
            by_device[str(e.get("target"))].add(str(e.get("source")))
    for dev, raw in by_device.items():
        accts = {a for a in raw if a and et(a) not in (EntityType.MERCHANT, EntityType.CASH_ENDPOINT)}
        if len(accts) < 2:
            continue
        owners = {owner_of[a] for a in accts if a in owner_of}
        unowned = [a for a in accts if a not in owner_of]
        # distinct principals = distinct owners + each unowned account on its own
        principals = len(owners) + len(unowned)
        shared = len(owners) >= cfg["xp009_min_owners"] or principals >= cfg["xp009_min_principals"]
        if shared:
            n = max(len(owners), principals)
            signals.append(_signal(
                "XP009", sorted(accts) + [dev],
                {"device_id": dev, "account_count": len(accts), "distinct_principals": n},
                min(0.95, 0.5 + 0.1 * n),
                f"Device {dev} is shared across {n} distinct principals — shared-device mule ring."))

    # ── XP010 shared mobile / XP011 shared PAN: one identity → ≥2 owners ──
    for rel, xp_id, label in (("HAS_PHONE", "XP010", "mobile number"),
                              ("HAS_PAN", "XP011", "PAN")):
        by_identity: dict[str, set[str]] = defaultdict(set)
        for e in struct:
            if e.get("relationship_type") == rel:
                by_identity[str(e.get("target"))].add(str(e.get("source")))
        for ident, owners in by_identity.items():
            if len(owners) >= 2:
                signals.append(_signal(
                    xp_id, sorted(owners) + [ident],
                    {"identity": ident, "owner_count": len(owners)},
                    min(0.95, 0.55 + 0.12 * len(owners)),
                    f"{label.capitalize()} {ident} is shared across {len(owners)} "
                    f"accounts/customers — shared-identity signature."))

    # ── per-account rail / product / timing profile ──
    out_rails: dict[str, set[str]] = defaultdict(set)
    out_times: dict[str, list[float]] = defaultdict(list)
    out_cats: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        s = str(e.get("source"))
        rail = str(e.get("payment_rail", "")).upper()
        if rail:
            out_rails[s].add(rail)
        ts = _parse_ts(e.get("timestamp"))
        if ts is not None:
            out_times[s].append(ts)
        out_cats[s].add(entity_category(et(str(e.get("target")))).value)

    for acct, rails in out_rails.items():
        times = sorted(out_times.get(acct, []))
        window_h = ((times[-1] - times[0]) / 3600.0) if len(times) >= 2 else 0.0
        # XP001 rapid channel switching: ≥N rails, mostly within the window
        if len(rails) >= cfg["xp001_min_rails"] and (window_h <= cfg["xp001_window_hours"] or not times):
            signals.append(_signal(
                "XP001", [acct],
                {"rails": sorted(rails), "window_hours": round(window_h, 2)},
                min(0.9, 0.5 + 0.1 * len(rails)),
                f"{acct} moves funds over {len(rails)} rails ({', '.join(sorted(rails))}) "
                f"within {window_h:.1f}h — rapid channel switching."))
        # XP014 multiple-product velocity: ≥3 distinct product categories downstream
        cats = {c for c in out_cats.get(acct, set()) if c and c != "unknown"}
        if len(cats) >= cfg["xp014_min_categories"]:
            signals.append(_signal(
                "XP014", [acct],
                {"product_categories": sorted(cats)},
                min(0.9, 0.5 + 0.12 * len(cats)),
                f"{acct} interacts with {len(cats)} product categories "
                f"({', '.join(sorted(cats))}) at velocity."))

    # ── XP004 Wallet layering: a wallet/upi entity that receives and forwards ──
    in_deg: dict[str, int] = defaultdict(int)
    fwd: dict[str, float] = defaultdict(float)
    rcv: dict[str, float] = defaultdict(float)
    for e in edges:
        amt = float(e.get("amount", 0) or 0)
        rcv[str(e.get("target"))] += amt
        fwd[str(e.get("source"))] += amt
        in_deg[str(e.get("target"))] += 1
    for nid in etype:
        if et(nid) in (EntityType.WALLET, EntityType.UPI_ID) and rcv[nid] > 0 and fwd[nid] > 0:
            ratio = fwd[nid] / rcv[nid] if rcv[nid] else 0
            if cfg["xp004_ratio_low"] <= ratio <= cfg["xp004_ratio_high"]:  # near pass-through = layering hop
                signals.append(_signal(
                    "XP004", [nid],
                    {"received": round(rcv[nid], 2), "forwarded": round(fwd[nid], 2),
                     "pass_through_ratio": round(ratio, 3)},
                    0.7,
                    f"{nid} ({et(nid).value}) forwards {ratio*100:.0f}% of what it receives — wallet layering hop."))

    # ── XP005 Merchant refund abuse: merchant pays BACK a counterparty it received from ──
    pairs = {(str(e.get("source")), str(e.get("target"))) for e in edges}
    for s, t in pairs:
        if et(s) == EntityType.MERCHANT and (t, s) in pairs and et(t) != EntityType.MERCHANT:
            signals.append(_signal(
                "XP005", [s, t],
                {"merchant": s, "counterparty": t},
                0.7,
                f"Merchant {s} refunds {t} which also paid it — refund-abuse laundering route."))

    # ── XP012 Cross-product structuring: ≥4 amounts sitting just below thresholds, ≥2 rails ──
    structured = [e for e in edges
                  if any(lo <= float(e.get("amount", 0) or 0) < hi for lo, hi in _STRUCTURING_BANDS)]
    if (len(structured) >= cfg["xp012_min_structured"]
            and len({str(e.get("payment_rail", "")).upper() for e in structured}) >= cfg["xp012_min_rails"]):
        ents = {str(e.get("source")) for e in structured} | {str(e.get("target")) for e in structured}
        signals.append(_signal(
            "XP012", sorted(ents),
            {"structured_txn_count": len(structured),
             "rails": sorted({str(e.get("payment_rail", "")).upper() for e in structured})},
            min(0.9, 0.55 + 0.05 * len(structured)),
            f"{len(structured)} transfers kept just below reporting thresholds across "
            f"multiple rails — cross-product structuring."))

    # ── XP003 Loan laundering: a loan that disburses then funds reach an external
    #    / foreign / shell destination (immediate exit of disbursed credit) ──
    loan_nodes = [nid for nid in etype if et(nid) == EntityType.LOAN and fwd.get(nid, 0) > 0]
    external = sorted(nid for nid in etype
                      if et(nid) in (EntityType.FOREIGN_BANK, EntityType.SWIFT_ENTITY)
                      or (et(nid) == EntityType.CORPORATE_ACCOUNT and nid not in owner_of))
    if loan_nodes and external:
        signals.append(_signal(
            "XP003", loan_nodes + external,
            {"loans": loan_nodes, "external_destinations": external},
            0.78,
            f"Loan disbursement from {', '.join(loan_nodes)} is routed toward "
            f"external/shell destination(s) {', '.join(external)} — loan laundering."))

    signals.sort(key=lambda s: (s["severity_score"], s["confidence"]), reverse=True)
    return signals
