"""
Payload normalization — the single ingress that makes BOTH formats work.

`normalize_payload(raw)` accepts ANY of:
  * the legacy lightweight LIST  [{from_account,to_account,amount,payment_rail,timestamp}, …]
  * an enriched LIST of TransactionEvent objects (nested intelligence blocks)
  * a versioned ENVELOPE  {schema_version, dataset_id, …, transactions:[…]}
and returns a `NormalizedBatch`:
  * transactions    — List[ManualTransactionInput]  (the existing internal model; the
                      whole downstream pipeline consumes this unchanged)
  * account_intel   — {account_id: {profile, kyc_risk, account_category, products, geo, …}}
                      the richer per-account metadata for the engines + the UI
  * customer_profiles — {account_id: profile_key}  → feeds Profile Intelligence directly
  * batch_meta      — envelope-level context (dataset_id, investigation_id, scenario, …)
  * warnings        — non-fatal issues (unknown enum value, …) surfaced for transparency

Strict only where it matters (Phase 13): positive amount, non-empty endpoints, valid
timestamps, no duplicate transaction IDs. Unknown enum values are preserved + warned,
never rejected, so demos never break.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List

from .event_schema import (KNOWN_PROFILES, KNOWN_RAILS, TransactionEnvelope,
                           TransactionEvent)
from .transaction import ManualTransactionInput

# product → the rail it settles on, when an explicit rail is not given
_PRODUCT_TO_RAIL = {
    "rtgs": "RTGS", "neft": "NEFT", "imps": "IMPS", "upi": "UPI", "swift": "SWIFT",
}
# account_category → the entity-graph type used by the cross-product engine
_CATEGORY_TO_ENTITY = {
    "savings": "savings_account", "salary": "salary_account", "current": "current_account",
    "corporate": "corporate_account", "credit_card": "credit_card", "wallet": "wallet",
    "merchant": "merchant", "loan": "loan",
}


@dataclass
class NormalizedBatch:
    transactions: List[ManualTransactionInput]
    account_intel: dict = field(default_factory=dict)
    customer_profiles: dict = field(default_factory=dict)
    batch_meta: dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


def _merge_account(intel: dict, acc: str, party, *, product=None, channel=None,
                   merchant=None, recovery=None) -> None:
    """Fold one side's declared context into the per-account intelligence map."""
    rec = intel.setdefault(acc, {"products": set(), "channels": set()})
    if product:
        rec["products"].add(str(product).lower())
    if channel:
        rec["channels"].add(str(channel).lower())
    if merchant is not None:
        md = merchant.model_dump(exclude_none=True) if hasattr(merchant, "model_dump") else merchant
        if md:
            rec["merchant"] = md
    if recovery is not None:
        rd = recovery.model_dump(exclude_none=True) if hasattr(recovery, "model_dump") else recovery
        if rd:
            rec["recovery"] = rd
    if party is None:
        return

    def put(key, val):
        if val is not None and rec.get(key) in (None, "", []):
            rec[key] = val

    if party.customer:
        c = party.customer
        put("profile", c.profile); put("segment", c.segment); put("occupation", c.occupation)
        put("kyc_risk", c.kyc_risk); put("branch", c.branch); put("residency", c.residency)
        put("business_category", c.business_category); put("customer_id", c.customer_id)
        put("onboarding_channel", c.onboarding_channel)
    if party.account:
        a = party.account
        put("account_category", a.account_category); put("account_status", a.account_status)
        put("current_balance", a.current_balance); put("opening_date", a.opening_date)
    if party.device:
        d = party.device
        put("device_id", d.device_id); put("device_reputation", d.device_reputation)
        if d.proxy_or_vpn is not None: put("proxy_or_vpn", d.proxy_or_vpn)
        if d.rooted_or_jailbroken is not None: put("rooted_or_jailbroken", d.rooted_or_jailbroken)
        if d.trusted_device is not None: put("trusted_device", d.trusted_device)
    if party.geo:
        g = party.geo
        loc = ", ".join(x for x in (g.city, g.state, g.country) if x)
        put("geo", loc or None)
        if g.geo_anomaly is not None: put("geo_anomaly", g.geo_anomaly)
        if g.impossible_travel is not None: put("impossible_travel", g.impossible_travel)
    if party.network:
        nd = party.network.model_dump(exclude_none=True)
        if nd:
            rec.setdefault("network", {}).update(nd)


def _finalize_intel(intel: dict) -> dict:
    out = {}
    for acc, rec in intel.items():
        r = dict(rec)
        r["products"] = sorted(rec.get("products", set()))
        r["channels"] = sorted(rec.get("channels", set()))
        if not r["products"]:
            r.pop("products")
        if not r["channels"]:
            r.pop("channels")
        out[acc] = r
    return out


def _resolve_rail(ev: TransactionEvent, warnings: List[str]) -> str:
    rail = (ev.payment.rail if ev.payment and ev.payment.rail else None) or ev.payment_rail
    if not rail and ev.product and str(ev.product).lower() in _PRODUCT_TO_RAIL:
        rail = _PRODUCT_TO_RAIL[str(ev.product).lower()]
    if not rail:
        return "UPI"
    rail = str(rail).upper()
    if rail not in KNOWN_RAILS:
        warnings.append(f"Unknown payment rail '{rail}' on {ev.from_account}→{ev.to_account}; kept as-is")
    return rail


def _entity_type(party, legacy) -> Any:
    if party and party.account and party.account.account_category:
        cat = str(party.account.account_category).lower()
        return _CATEGORY_TO_ENTITY.get(cat, cat)
    return legacy


def normalize_payload(raw: Any) -> NormalizedBatch:
    warnings: List[str] = []
    batch_meta: dict = {}

    # ── detect shape ──────────────────────────────────────────────────────────
    if isinstance(raw, dict) and ("transactions" in raw or "schema_version" in raw):
        env = TransactionEnvelope.model_validate(raw)
        events = env.transactions
        batch_meta = {
            "schema_version": env.schema_version, "dataset_id": env.dataset_id,
            "investigation_id": env.investigation_id, "source_system": env.source_system,
            "ingestion_timestamp": env.ingestion_timestamp, "metadata": env.metadata or {},
        }
    elif isinstance(raw, list):
        events = [TransactionEvent.model_validate(x) for x in raw]
        batch_meta = {"schema_version": "1.0-legacy" if events and _is_legacy(raw[0]) else "2.0"}
    else:
        raise ValueError("payload must be a transaction list or a versioned envelope object")

    if not events:
        raise ValueError("no transactions provided")

    # ── flatten + collect intelligence ────────────────────────────────────────
    txns: List[ManualTransactionInput] = []
    intel: dict = {}
    customer_profiles: dict = {}
    seen_ids: set = set()

    for ev in events:
        if ev.transaction_id:
            if ev.transaction_id in seen_ids:
                raise ValueError(f"duplicate transaction_id '{ev.transaction_id}'")
            seen_ids.add(ev.transaction_id)
        if ev.timestamp:
            try:
                datetime.fromisoformat(ev.timestamp)
            except ValueError:
                warnings.append(f"Invalid timestamp '{ev.timestamp}' on {ev.from_account}→{ev.to_account}; using now")
                ev.timestamp = None

        rail = _resolve_rail(ev, warnings)
        fp, tp = ev.from_party, ev.to_party
        product = ev.product or (ev.payment.merchant_category if ev.payment else None)
        channel = ev.payment.channel if ev.payment else None

        txns.append(ManualTransactionInput(
            from_account=ev.from_account, to_account=ev.to_account, amount=ev.amount,
            payment_rail=rail, timestamp=ev.timestamp,
            device_id=(fp.device.device_id if fp and fp.device else None) or ev.device_id,
            from_entity_type=_entity_type(fp, ev.from_entity_type),
            to_entity_type=_entity_type(tp, ev.to_entity_type),
            from_customer=(fp.customer.customer_id if fp and fp.customer else None) or ev.from_customer,
            to_customer=(tp.customer.customer_id if tp and tp.customer else None) or ev.to_customer,
            from_phone=(fp.network.mobile_number if fp and fp.network else None) or ev.from_phone,
            to_phone=(tp.network.mobile_number if tp and tp.network else None) or ev.to_phone,
            from_pan=(fp.network.pan if fp and fp.network else None) or ev.from_pan,
            to_pan=(tp.network.pan if tp and tp.network else None) or ev.to_pan,
        ))

        _merge_account(intel, ev.from_account, fp, product=product, channel=channel)
        _merge_account(intel, ev.to_account, tp, product=product, channel=channel,
                       merchant=ev.merchant, recovery=ev.recovery)

        for acc, party in ((ev.from_account, fp), (ev.to_account, tp)):
            prof = party.customer.profile if (party and party.customer) else None
            if prof:
                if prof not in KNOWN_PROFILES:
                    warnings.append(f"Unknown customer profile '{prof}' for {acc}; kept as-is")
                customer_profiles[acc] = prof

    return NormalizedBatch(
        transactions=txns, account_intel=_finalize_intel(intel),
        customer_profiles=customer_profiles, batch_meta=batch_meta, warnings=warnings,
    )


def _is_legacy(first: Any) -> bool:
    """A bare flat dict with only core (+ legacy flat) keys → the 1.0 format."""
    if not isinstance(first, dict):
        return False
    enterprise_keys = {"from_party", "to_party", "payment", "merchant", "recovery",
                       "context", "product"}
    return not (enterprise_keys & set(first.keys()))
