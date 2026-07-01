"""
Profile Intelligence Engine — behaviour evaluated RELATIVE to the customer.

Pipeline per component:
  1. extract each account's observed behaviour (degree, volume, rails, cash, counterparties)
  2. infer its customer profile (explicit KYC override → account-type prior → behaviour)
  3. evaluate behaviour against THAT profile's baseline → deviation (abnormal-for-this-customer)
     and mitigation (a big amount that is normal for this customer kind)
  4. aggregate to a component-level signal the risk engine consumes, with full explainability

Deterministic and explainable: same component → same profiles, same numbers, same reasons.
Degrades gracefully — with no usable data the signal is 0 and nothing changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .profiles import ACCOUNT_TYPE_PRIOR, CustomerProfile, get_profile

# The value at which the static (profile-blind) engine begins ramping amount risk.
# Above this, profile context decides whether the amount is alarming or routine.
_GENERIC_HIGH = 2_00_000.0


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _is_account(nid: str, account_type: str) -> bool:
    s = str(nid).upper()
    if s.startswith("CASH"):           # CASH_SOURCE / CASH_EXIT are endpoints, not customers
        return False
    return account_type not in ("cash",)


@dataclass
class AccountFeatures:
    account: str
    account_type: str = "unknown"
    out_deg: int = 0
    in_deg: int = 0
    total_out: float = 0.0
    total_in: float = 0.0
    max_txn: float = 0.0
    txn_count: int = 0
    rails: set = field(default_factory=set)
    cash: bool = False
    foreign: bool = False


def extract_features(component: dict) -> dict[str, AccountFeatures]:
    nodes = component.get("nodes", []) or [{"id": n} for n in component.get("node_ids", [])]
    acc_type = {str(n.get("id")): str(n.get("account_type", "unknown")) for n in nodes}
    feats: dict[str, AccountFeatures] = {}

    def f(acc: str) -> AccountFeatures:
        if acc not in feats:
            feats[acc] = AccountFeatures(account=acc, account_type=acc_type.get(acc, "unknown"))
        return feats[acc]

    out_peers: dict[str, set] = {}
    in_peers: dict[str, set] = {}
    for e in component.get("edges", []):
        s, t = str(e.get("source", "")), str(e.get("target", ""))
        if not s or not t:
            continue
        amt = float(e.get("amount", 0) or 0)
        rail = str(e.get("payment_rail", "")).upper()
        is_cash = s.upper().startswith("CASH") or t.upper().startswith("CASH") or "CASH" in rail
        is_foreign = rail in ("SWIFT",) or t.upper().startswith("FOREIGN") or s.upper().startswith("FOREIGN")
        fs, ft = f(s), f(t)
        fs.total_out += amt; fs.txn_count += 1; fs.max_txn = max(fs.max_txn, amt)
        ft.total_in += amt;  ft.txn_count += 1; ft.max_txn = max(ft.max_txn, amt)
        if rail:
            fs.rails.add(rail); ft.rails.add(rail)
        if is_cash:
            fs.cash = ft.cash = True
        if is_foreign:
            fs.foreign = ft.foreign = True
        out_peers.setdefault(s, set()).add(t)
        in_peers.setdefault(t, set()).add(s)

    for acc, fe in feats.items():
        fe.out_deg = len(out_peers.get(acc, set()))
        fe.in_deg = len(in_peers.get(acc, set()))
    return {a: fe for a, fe in feats.items() if _is_account(a, fe.account_type)}


# ── profile inference ─────────────────────────────────────────────────────────
def infer_profile(feat: AccountFeatures, explicit: Optional[str] = None) -> tuple[str, float, list[str]]:
    """Return (profile_key, confidence, evidence). Priority: explicit KYC → account-type
    prior → behavioural heuristic → unknown."""
    if explicit:
        return explicit, 1.0, [f"Declared customer profile: {explicit}"]

    ev: list[str] = []
    prior = ACCOUNT_TYPE_PRIOR.get(feat.account_type.lower())
    if prior:
        ev.append(f"Account type '{feat.account_type}' implies {prior}")

    # Behavioural signals refine / set the profile when account-type is uninformative.
    out_d, in_d = feat.out_deg, feat.in_deg
    big = feat.max_txn >= 5_00_000
    # Corporate-scale distributor (very large settlements to several counterparties)
    if out_d >= 4 and feat.max_txn >= 1_00_00_000:
        ev.append(f"Distributes ₹{int(feat.max_txn):,}-scale to {out_d} recipients → large_corporate")
        return "large_corporate", 0.6, ev
    # Strong outbound distributor
    if out_d >= 5 and out_d > in_d:
        key = "business_owner" if big or feat.total_out >= 20_00_000 else "retail_merchant"
        ev.append(f"Distributes to {out_d} recipients → {key}")
        return key, 0.6, ev
    # Strong inbound aggregator (merchant / collections) — but NOT a known business type
    if in_d >= 6 and in_d > out_d and not prior:
        ev.append(f"Aggregates from {in_d} sources → retail_merchant")
        return "retail_merchant", 0.55, ev
    if prior:
        return prior, 0.5, ev
    # Low-activity individual default
    if feat.txn_count <= 3 and feat.max_txn <= 80_000:
        return "student", 0.4, ["Low-volume retail activity → student-class baseline"]
    return "unknown", 0.3, ["No strong profile signal — using neutral baseline"]


# ── behaviour-vs-profile evaluation ───────────────────────────────────────────
def evaluate(profile: CustomerProfile, feat: AccountFeatures) -> dict[str, Any]:
    reasons: list[str] = []

    # amount relative to THIS profile's routine ceiling
    ratio = feat.max_txn / profile.baseline_txn_high if profile.baseline_txn_high else 0.0
    amount_excess = _clamp((ratio - 1.0) / 9.0) if ratio > 1.0 else 0.0
    if amount_excess > 0.05:
        reasons.append(f"Largest transfer ₹{int(feat.max_txn):,} is {ratio:.0f}× the routine "
                       f"ceiling (₹{int(profile.baseline_txn_high):,}) for a {profile.label}")

    # fan-out relative to profile
    fr = feat.out_deg / profile.max_fan_out_expected if profile.max_fan_out_expected else 0.0
    fanout_excess = _clamp((fr - 1.0) / 2.0) if fr > 1.0 else 0.0
    if fanout_excess > 0.05:
        reasons.append(f"Fans out to {feat.out_deg} recipients vs ~{profile.max_fan_out_expected} "
                       f"typical for a {profile.label}")

    # receiving from many unrelated sources when that is not normal for the profile
    many_to_one = 0.0
    if feat.in_deg >= 5 and not profile.many_to_one_expected:
        many_to_one = 0.7
        reasons.append(f"Receives from {feat.in_deg} sources — unusual for a {profile.label}")

    # cash when the profile is not cash-intensive
    cash_excess = 0.0
    if feat.cash and profile.cash_intensity < 0.3:
        cash_excess = 0.55
        reasons.append(f"Cash movement is atypical for a {profile.label}")

    # foreign legs when not expected
    foreign_excess = 0.0
    if feat.foreign and not profile.foreign_expected:
        foreign_excess = 0.6
        reasons.append(f"Cross-border transfer is atypical for a {profile.label}")

    deviation = _clamp(0.45 * amount_excess + 0.20 * fanout_excess + 0.20 * many_to_one
                       + 0.15 * cash_excess + 0.15 * foreign_excess)

    # mitigation: a LARGE amount that is fully within this customer's envelope is the
    # opposite of suspicious — this is what stops legitimate high-volume FPs.
    mitigation = 0.0
    if feat.max_txn >= _GENERIC_HIGH and profile.baseline_txn_high >= 2 * _GENERIC_HIGH:
        magnitude = _clamp((feat.max_txn / _GENERIC_HIGH - 1.0) / 4.0)
        mitigation = (1.0 - amount_excess) * magnitude
        if mitigation > 0.1 and not reasons:
            reasons.append(f"₹{int(feat.max_txn):,} is routine for a {profile.label} "
                           f"(up to ₹{int(profile.baseline_txn_high):,}) — not inherently suspicious")

    net = deviation - mitigation
    return {
        "deviation": round(deviation, 3),
        "mitigation": round(mitigation, 3),
        "net": round(net, 3),
        "adjustment_pct": int(round(net * 40)),   # signed, for the UI (−40%..+40%)
        "reasons": reasons,
        "expected": f"Routine ≤ ₹{int(profile.baseline_txn_high):,}, ~{profile.max_fan_out_expected} payees, "
                    f"{'cash-heavy' if profile.cash_intensity >= 0.5 else 'low cash'}",
        "current": f"Largest ₹{int(feat.max_txn):,}, {feat.out_deg} payees / {feat.in_deg} sources, "
                   f"{feat.txn_count} txns{', cash' if feat.cash else ''}",
    }


# ── component assessment ──────────────────────────────────────────────────────
def assess_component(component: dict, explicit_profiles: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """Per-account profile + behaviour evaluation, plus the two aggregate signals the
    risk engine consumes: `component_deviation` (abnormal-for-profile, raises risk) and
    `amount_mitigation` (the largest-amount account is profile-consistent, lowers FP)."""
    feats = extract_features(component)
    explicit_profiles = explicit_profiles or {}
    if not feats:
        return {"available": False, "accounts": {}, "component_deviation": 0.0,
                "amount_mitigation": 0.0, "top_account": None, "explanation": None}

    accounts: dict[str, Any] = {}
    for acc, fe in feats.items():
        key, conf, ev = infer_profile(fe, explicit_profiles.get(acc))
        profile = get_profile(key)
        eval_ = evaluate(profile, fe)
        accounts[acc] = {
            "profile": key, "label": profile.label, "segment": profile.segment,
            "confidence": round(conf, 2), "inference_evidence": ev,
            "expected_behaviour": profile.expected_behaviour,
            **eval_,
        }

    # account with the largest single transaction drives the amount mitigation
    top_amount_acc = max(feats, key=lambda a: feats[a].max_txn)
    amount_mitigation = accounts[top_amount_acc]["mitigation"] if feats[top_amount_acc].max_txn >= _GENERIC_HIGH else 0.0

    # strongest abnormal-for-profile account drives the deviation signal
    dev_acc = max(accounts, key=lambda a: accounts[a]["deviation"] * accounts[a]["confidence"])
    component_deviation = round(accounts[dev_acc]["deviation"] * accounts[dev_acc]["confidence"], 3)

    driver = accounts[dev_acc] if component_deviation > 0.1 else accounts[top_amount_acc]
    explanation = _component_explanation(dev_acc if component_deviation > 0.1 else top_amount_acc,
                                         driver, component_deviation, amount_mitigation)
    return {
        "available": True,
        "accounts": accounts,
        "component_deviation": component_deviation,
        "amount_mitigation": round(amount_mitigation, 3),
        "top_account": dev_acc if component_deviation > 0.1 else top_amount_acc,
        "explanation": explanation,
    }


def _component_explanation(acc: str, a: dict, dev: float, mit: float) -> str:
    head = f"{acc} — {a['label']}."
    if dev > 0.1 and a["reasons"]:
        return head + " Risk raised: " + "; ".join(a["reasons"][:3]) + "."
    if mit > 0.1:
        return head + f" Behaviour is consistent with the profile — risk not inflated by volume " \
                      f"({a['current']})."
    return head + " Behaviour within the expected profile envelope."
