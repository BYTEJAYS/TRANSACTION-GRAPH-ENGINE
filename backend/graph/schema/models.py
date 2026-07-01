"""
Typed graph-node models (Wave 1).

These Pydantic models are the contract for what gets written to Neo4j and what
the NetworkX projection reads back. They deliberately reuse the existing
domain enums in `models.transaction` (PaymentRail, RiskLevel, AccountType) so
the new graph layer stays consistent with the engine that already ships.

PII fields (PAN/Aadhaar/Phone/Email/Address) are stored hashed/masked — never
raw — per the Phase 1 PII decision. Raw demo values, if any, live in the
Postgres PII vault (Phase 3), keyed by node id and access-audited.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

# reuse the enums the running engine already defines — do not fork them
from models.transaction import PaymentRail, RiskLevel, AccountType
from .labels import Label

_PII_SALT = os.getenv("TGIE_PII_SALT", "tgie-demo-salt")


def pii_hash(value: str) -> str:
    """Salted SHA-256 for PII natural keys (PAN/Aadhaar). Demo-grade; in prod the
    salt is a KMS-managed secret and hashing happens in the PII vault service."""
    return hashlib.sha256(f"{_PII_SALT}:{value.strip().upper()}".encode()).hexdigest()


class GraphNode(BaseModel):
    """Common envelope: every node carries id + provenance + timestamps."""
    id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    source_system: str = "tgie"

    # label is a class attribute, not a field — overridden per subclass
    label: Label

    model_config = {"use_enum_values": True}


# ── Domain A · Identity ──────────────────────────────────────────────────────
class CustomerNode(GraphNode):
    label: Label = Label.CUSTOMER
    name: str
    dob: Optional[str] = None
    customer_since: Optional[str] = None
    segment: str = "retail"            # retail | hni | business
    occupation: Optional[str] = None
    declared_income: Optional[float] = None
    residency: str = "IN"
    status: str = "active"             # active | dormant | blocked
    risk_band: RiskLevel = RiskLevel.SAFE


class KYCNode(GraphNode):
    label: Label = Label.KYC
    level: str = "full"                # min | full | video
    status: str = "verified"
    verified_at: Optional[str] = None
    expires_at: Optional[str] = None
    pep_flag: bool = False


class PANNode(GraphNode):
    label: Label = Label.PAN
    pan_hash: str
    pan_masked: str                    # ABCDE****F
    name_on_pan: Optional[str] = None
    verified: bool = False
    pii: bool = True


class AadhaarNode(GraphNode):           # DEMO ONLY
    label: Label = Label.AADHAAR
    aadhaar_hash: str
    last4: str
    verified: bool = False
    pii: bool = True
    synthetic: bool = True


class PhoneNode(GraphNode):
    label: Label = Label.PHONE
    e164: str
    type: str = "mobile"
    pii: bool = True


class EmailNode(GraphNode):
    label: Label = Label.EMAIL
    address_norm: str
    domain: str
    pii: bool = True


class AddressNode(GraphNode):
    label: Label = Label.ADDRESS
    line: str
    city: Optional[str] = None
    pincode: Optional[str] = None
    geohash: Optional[str] = None
    country: str = "IN"
    pii: bool = True


class LocationNode(GraphNode):
    label: Label = Label.LOCATION
    name: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    geohash: Optional[str] = None
    country: str = "IN"
    is_high_risk: bool = False


# ── Domain B · Accounts / Products ───────────────────────────────────────────
class AccountNode(GraphNode):
    label: Label = Label.ACCOUNT
    account_no_hash: str
    account_no_masked: str
    account_type: AccountType = AccountType.NORMAL
    status: str = "active"             # active | dormant | frozen | closed
    opened_at: Optional[str] = None
    currency: str = "INR"
    balance_band: Optional[str] = None
    dormant_since: Optional[str] = None
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)


class CardNode(GraphNode):
    label: Label = Label.CARD
    card_type: str = "debit"           # debit | credit
    network: str = "rupay"
    pan_token: Optional[str] = None
    status: str = "active"


class WalletNode(GraphNode):
    label: Label = Label.WALLET
    provider: str = "upi"
    kyc_level: str = "min"
    balance_band: Optional[str] = None


class LoanNode(GraphNode):
    label: Label = Label.LOAN
    type: str = "personal"
    principal: float = 0.0
    status: str = "active"
    dpd: int = 0                       # days past due


class FixedDepositNode(GraphNode):
    label: Label = Label.FIXED_DEPOSIT
    amount: float = 0.0
    maturity: Optional[str] = None
    auto_renew: bool = False


class InsuranceNode(GraphNode):
    label: Label = Label.INSURANCE
    type: str = "life"
    sum_assured: float = 0.0
    status: str = "active"


class ProductNode(GraphNode):
    label: Label = Label.PRODUCT
    code: str
    family: str
    risk_weight: float = 0.0


class BeneficiaryNode(GraphNode):
    label: Label = Label.BENEFICIARY
    beneficiary_account_ref: str
    added_at: Optional[str] = None
    channel_added: Optional[str] = None


# ── Domain C · Movement ──────────────────────────────────────────────────────
class TransactionNode(GraphNode):
    """Reified transaction. (Account)-[:SENT]->(Transaction)-[:RECEIVED_BY]->(Account)."""
    label: Label = Label.TRANSACTION
    amount: float
    currency: str = "INR"
    rail: PaymentRail = PaymentRail.UPI
    ts: datetime = Field(default_factory=datetime.utcnow)
    status: str = "settled"
    direction: str = "transfer"        # transfer | cash_in | cash_out
    narration: Optional[str] = None
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    fraud_pattern: str = "normal"
    is_flagged: bool = False


class CurrencyNode(GraphNode):
    label: Label = Label.CURRENCY
    code: str
    name: str
    is_crypto: bool = False


# ── Domain E · Risk / Investigation ──────────────────────────────────────────
class RiskProfileNode(GraphNode):
    label: Label = Label.RISK_PROFILE
    subject_ref: str
    score_0_100: float = 0.0
    band: RiskLevel = RiskLevel.SAFE
    model_version: str = "v1"
    computed_at: datetime = Field(default_factory=datetime.utcnow)


class SuspiciousPatternNode(GraphNode):
    label: Label = Label.SUSPICIOUS_PATTERN
    pattern_code: str
    family: str
    severity: float = 0.0
    confidence: float = 0.0
    detector_version: str = "v2"
    detected_at: datetime = Field(default_factory=datetime.utcnow)


class AlertNode(GraphNode):
    label: Label = Label.ALERT
    type: str
    severity: RiskLevel = RiskLevel.MODERATE
    status: str = "open"               # open | triage | escalated | closed | false_pos
    score: float = 0.0
    assigned_to: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CaseNode(GraphNode):
    label: Label = Label.CASE
    case_no: str
    title: str
    status: str = "open"
    priority: str = "medium"
    owner: Optional[str] = None
    opened_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: Optional[str] = None
    disposition: Optional[str] = None


class InvestigationNode(GraphNode):
    label: Label = Label.INVESTIGATION
    case_ref: str
    investigator_ref: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)


class EvidenceNode(GraphNode):
    label: Label = Label.EVIDENCE
    type: str
    sha256: str
    bels_anchor_ref: Optional[str] = None
    storage_uri: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RegulatoryReportNode(GraphNode):
    label: Label = Label.REGULATORY_REPORT
    type: str = "STR"                  # STR | CTR | FIU
    status: str = "draft"
    period: Optional[str] = None
    ref_no: Optional[str] = None
    filed_at: Optional[str] = None


class AuditEntryNode(GraphNode):
    label: Label = Label.AUDIT_ENTRY
    actor: str
    action: str
    target_ref: Optional[str] = None
    ip: Optional[str] = None
    ts: datetime = Field(default_factory=datetime.utcnow)
