"""
TGIE Enterprise Transaction Event Schema (schema_version "2.0").

An optional, versioned, enterprise-grade event format that a real bank fraud
platform would consume — customer / account / product / payment / device / geo /
merchant / network / behavioural / recovery / explainability intelligence — while
remaining 100% backward compatible with the lightweight prototype format.

DESIGN
------
* Everything except the money core (from_account, to_account, amount) is OPTIONAL.
* A transaction is an EDGE, so per-side context lives in `from_party` / `to_party`.
* The old flat fields (device_id, from_customer, from_pan, …) are still accepted.
* `models/normalize.py` detects the payload shape and flattens ANY of: a bare list
  (old or enriched), or a versioned envelope, into the existing internal model +
  a per-account intelligence map that feeds the existing engines. Nothing here
  replaces the runtime model — this is the ingress contract + validation only.

The enums below are the DOCUMENTED known-values catalogue (Phase 13). Validation
is lenient by policy (unknown enum values are preserved + surfaced as warnings, not
rejected) so a demo never breaks; only the money core is strictly validated.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "2.0"


# ── enumerated catalogues (Phase 13 — known values) ───────────────────────────
class Product(str, Enum):
    SAVINGS = "savings"; CURRENT = "current"; UPI = "upi"; CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"; WALLET = "wallet"; MERCHANT = "merchant"; ATM = "atm"
    POS = "pos"; QR = "qr"; INTERNET_BANKING = "internet_banking"; MOBILE_BANKING = "mobile_banking"
    RTGS = "rtgs"; NEFT = "neft"; IMPS = "imps"; SWIFT = "swift"; FOREX = "forex"
    LOAN = "loan"; TRADE_FINANCE = "trade_finance"


class AccountCategory(str, Enum):
    SAVINGS = "savings"; CURRENT = "current"; LOAN = "loan"; CREDIT_CARD = "credit_card"
    WALLET = "wallet"; MERCHANT = "merchant"; NOSTRO = "nostro"; VOSTRO = "vostro"
    ESCROW = "escrow"; DORMANT = "dormant"; CORPORATE = "corporate"; JOINT = "joint"
    OVERDRAFT = "overdraft"; SALARY = "salary"


class Channel(str, Enum):
    BRANCH = "branch"; ATM = "atm"; POS = "pos"; QR = "qr"
    INTERNET_BANKING = "internet_banking"; MOBILE_BANKING = "mobile_banking"
    UPI_APP = "upi_app"; CALL_CENTRE = "call_centre"; AGENT = "agent"; SWIFT = "swift"


class Direction(str, Enum):
    INTERNAL = "internal"; EXTERNAL = "external"


# Customer profile keys mirror profile_intelligence.profiles.PROFILES (kept loose).
KNOWN_PROFILES = {
    "salaried_employee", "business_owner", "msme", "large_corporate", "farmer",
    "student", "pensioner", "freelancer", "government_employee", "ngo_trust",
    "retail_merchant", "ecommerce_seller", "hni", "cash_intensive_business",
    "exporter_importer", "unknown",
}
KNOWN_RAILS = {"UPI", "IMPS", "RTGS", "NEFT", "CASH", "CASH_IN", "CASH_OUT", "SWIFT"}


# ── intelligence blocks (all optional) ────────────────────────────────────────
class CustomerInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    customer_id: Optional[str] = None
    profile: Optional[str] = None            # → Profile Intelligence (e.g. "business_owner")
    segment: Optional[str] = None            # retail / sme / corporate / institution
    occupation: Optional[str] = None
    kyc_risk: Optional[str] = None           # low / medium / high
    branch: Optional[str] = None
    onboarding_channel: Optional[str] = None
    residency: Optional[str] = None          # resident / nri / foreign
    business_category: Optional[str] = None


class AccountInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    account_category: Optional[str] = None   # Phase 3 (savings/current/escrow/…)
    current_balance: Optional[float] = None
    account_status: Optional[str] = None     # active / dormant / frozen / closed
    opening_date: Optional[str] = None


class DeviceInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    device_id: Optional[str] = None
    imei: Optional[str] = None
    fingerprint: Optional[str] = None
    os: Optional[str] = None
    app_version: Optional[str] = None
    ip_address: Optional[str] = None
    proxy_or_vpn: Optional[bool] = None
    rooted_or_jailbroken: Optional[bool] = None
    trusted_device: Optional[bool] = None
    device_reputation: Optional[str] = None  # good / suspicious / known_bad


class GeoInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    country: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_from_previous_km: Optional[float] = None
    geo_anomaly: Optional[bool] = None
    impossible_travel: Optional[bool] = None


class NetworkInfo(BaseModel):
    """Shared-identity signals (Phase 9). Carry masked / tokenised values only."""
    model_config = ConfigDict(extra="allow")
    mobile_number: Optional[str] = None
    email: Optional[str] = None
    pan: Optional[str] = None
    masked_aadhaar: Optional[str] = None
    gst: Optional[str] = None
    business_registration: Optional[str] = None
    shared_address: Optional[str] = None
    shared_beneficiary: Optional[str] = None
    shared_nominee: Optional[str] = None


class BehaviourInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    historical_avg: Optional[float] = None
    historical_median: Optional[float] = None
    typical_daily_volume: Optional[float] = None
    typical_txn_count: Optional[int] = None
    preferred_rail: Optional[str] = None
    preferred_hours: Optional[List[int]] = None
    cash_preference: Optional[float] = None
    seasonality: Optional[str] = None


class PartyInfo(BaseModel):
    """One side of a transaction (the from- or to- account)."""
    model_config = ConfigDict(extra="allow")
    customer: Optional[CustomerInfo] = None
    account: Optional[AccountInfo] = None
    device: Optional[DeviceInfo] = None
    geo: Optional[GeoInfo] = None
    network: Optional[NetworkInfo] = None
    behaviour: Optional[BehaviourInfo] = None


class FxInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    base_currency: Optional[str] = None
    quote_currency: Optional[str] = None
    rate: Optional[float] = None


class PaymentInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    rail: Optional[str] = None               # UPI / IMPS / RTGS / NEFT / SWIFT / CASH…
    channel: Optional[str] = None
    purpose: Optional[str] = None
    settlement_type: Optional[str] = None    # instant / deferred / batch
    currency: Optional[str] = "INR"
    fx: Optional[FxInfo] = None
    reference_number: Optional[str] = None
    narration: Optional[str] = None
    merchant_category: Optional[str] = None
    direction: Optional[str] = None          # internal / external
    domestic: Optional[bool] = None


class MerchantInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    merchant_id: Optional[str] = None
    mcc: Optional[str] = None                # Merchant Category Code
    merchant_type: Optional[str] = None
    business_category: Optional[str] = None
    terminal_id: Optional[str] = None
    acquirer: Optional[str] = None
    pos_id: Optional[str] = None
    risk_rating: Optional[str] = None
    known_fraud_merchant: Optional[bool] = None


class RecoveryInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    settlement_status: Optional[str] = None  # cleared / pending / frozen / lien
    reversible: Optional[bool] = None
    chargeback_eligible: Optional[bool] = None
    recovery_priority: Optional[str] = None
    recovery_window_hours: Optional[float] = None


class ContextInfo(BaseModel):
    """Explainability / investigation context (Phase 12)."""
    model_config = ConfigDict(extra="allow")
    source_dataset: Optional[str] = None
    scenario_id: Optional[str] = None
    synthetic: Optional[bool] = None
    simulation_id: Optional[str] = None
    training_scenario: Optional[str] = None
    demo_scenario: Optional[str] = None
    analyst_notes: Optional[str] = None
    case_id: Optional[str] = None


# ── the event + envelope ──────────────────────────────────────────────────────
class TransactionEvent(BaseModel):
    """One enterprise transaction event. The money core is required; everything
    else is optional. The OLD flat format is a valid TransactionEvent (core only),
    and the previously-supported flat enrichment fields are still accepted."""
    model_config = ConfigDict(extra="allow")

    # money core (required)
    from_account: str
    to_account: str
    amount: float
    # core optionals
    transaction_id: Optional[str] = None
    timestamp: Optional[str] = None
    product: Optional[str] = None                 # Phase 4 — product the txn belongs to
    payment_rail: Optional[str] = None            # legacy top-level; or payment.rail

    # nested intelligence (Phases 2-12)
    payment: Optional[PaymentInfo] = None
    from_party: Optional[PartyInfo] = None
    to_party: Optional[PartyInfo] = None
    merchant: Optional[MerchantInfo] = None
    recovery: Optional[RecoveryInfo] = None
    context: Optional[ContextInfo] = None

    # ── legacy flat enrichment fields (kept for backward compatibility) ──
    device_id: Optional[str] = None
    from_entity_type: Optional[str] = None
    to_entity_type: Optional[str] = None
    from_customer: Optional[str] = None
    to_customer: Optional[str] = None
    from_phone: Optional[str] = None
    to_phone: Optional[str] = None
    from_pan: Optional[str] = None
    to_pan: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def _positive_amount(cls, v: float) -> float:
        if v is None or float(v) <= 0:
            raise ValueError("amount must be a positive number")
        return float(v)

    @field_validator("from_account", "to_account")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not str(v).strip():
            raise ValueError("from_account and to_account must be non-empty")
        return str(v)


class TransactionEnvelope(BaseModel):
    """Versioned wrapper (Phase 1). `transactions` may also be the old flat shape."""
    model_config = ConfigDict(extra="allow")
    schema_version: str = SCHEMA_VERSION
    dataset_id: Optional[str] = None
    investigation_id: Optional[str] = None
    source_system: Optional[str] = None
    ingestion_timestamp: Optional[str] = Field(default_factory=lambda: datetime.utcnow().isoformat())
    transactions: List[TransactionEvent]
    metadata: Optional[dict] = None
