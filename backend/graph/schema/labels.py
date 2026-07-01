"""
Single source of truth for graph node labels and relationship types.

Every writer (Neo4j loader, NetworkX projection, detectors, migration) imports
these enums instead of hard-coding strings — so a label rename is one edit, and
typos become import errors instead of silently-empty queries.

Wave 1 = Domains A (Identity), B (Accounts/Products), C (Movement),
E (Risk/Investigation). Wave 2 labels (Bank-Org D, Reference/Watchlist F) are
included but tagged so callers can gate on rollout phase.
"""
from __future__ import annotations

from enum import Enum


class Label(str, Enum):
    # ── Domain A · Identity ──
    CUSTOMER = "Customer"
    KYC = "KYC"
    PAN = "PAN"
    AADHAAR = "Aadhaar"          # DEMO ONLY — hashed, never raw
    PHONE = "Phone"
    EMAIL = "Email"
    ADDRESS = "Address"
    LOCATION = "Location"
    # ── Domain B · Accounts / Products ──
    ACCOUNT = "Account"
    CARD = "Card"
    WALLET = "Wallet"
    LOAN = "Loan"
    FIXED_DEPOSIT = "FixedDeposit"
    INSURANCE = "Insurance"
    PRODUCT = "Product"
    BENEFICIARY = "Beneficiary"
    # ── Domain C · Movement ──
    TRANSACTION = "Transaction"
    CURRENCY = "Currency"
    # ── Domain E · Risk / Investigation ──
    RISK_PROFILE = "RiskProfile"
    SUSPICIOUS_PATTERN = "SuspiciousPattern"
    ALERT = "Alert"
    CASE = "Case"
    INVESTIGATION = "Investigation"
    EVIDENCE = "Evidence"
    REGULATORY_REPORT = "RegulatoryReport"
    AUDIT_ENTRY = "AuditEntry"
    # ── Domain D · Bank Org (Wave 2) ──
    BRANCH = "Branch"
    CHANNEL = "Channel"
    EMPLOYEE = "Employee"
    RELATIONSHIP_MANAGER = "RelationshipManager"
    ORGANIZATION = "Organization"
    BUSINESS = "Business"
    MERCHANT = "Merchant"
    DEVICE = "Device"
    IP_ADDRESS = "IPAddress"
    # ── Domain F · Reference / Watchlist (Wave 2) ──
    WATCHLIST = "Watchlist"
    SANCTION_LIST = "SanctionList"
    BLACKLISTED_ENTITY = "BlacklistedEntity"
    HIGH_RISK_COUNTRY = "HighRiskCountry"


# Nodes carrying regulated PII — RBAC + read-audit must gate these (Phase 3 security).
PII_LABELS: frozenset[Label] = frozenset({
    Label.PAN, Label.AADHAAR, Label.PHONE, Label.EMAIL, Label.ADDRESS,
})

WAVE1_LABELS: frozenset[Label] = frozenset({
    Label.CUSTOMER, Label.KYC, Label.PAN, Label.AADHAAR, Label.PHONE, Label.EMAIL,
    Label.ADDRESS, Label.LOCATION, Label.ACCOUNT, Label.CARD, Label.WALLET,
    Label.LOAN, Label.FIXED_DEPOSIT, Label.INSURANCE, Label.PRODUCT, Label.BENEFICIARY,
    Label.TRANSACTION, Label.CURRENCY, Label.RISK_PROFILE, Label.SUSPICIOUS_PATTERN,
    Label.ALERT, Label.CASE, Label.INVESTIGATION, Label.EVIDENCE,
    Label.REGULATORY_REPORT, Label.AUDIT_ENTRY,
})


class Rel(str, Enum):
    # structural (asserted at ingest)
    OWNS = "OWNS"
    BELONGS_TO = "BELONGS_TO"
    HOLDS_KYC = "HOLDS_KYC"
    HAS_PAN = "HAS_PAN"
    HAS_AADHAAR = "HAS_AADHAAR"
    HAS_PHONE = "HAS_PHONE"
    HAS_EMAIL = "HAS_EMAIL"
    LOCATED_AT = "LOCATED_AT"
    RESIDES_AT = "RESIDES_AT"
    USES_PRODUCT = "USES_PRODUCT"
    ADDED_BENEFICIARY = "ADDED_BENEFICIARY"
    # movement (reified transaction)
    SENT = "SENT"
    RECEIVED_BY = "RECEIVED_BY"
    TRANSFERRED_TO = "TRANSFERRED_TO"   # DERIVED aggregate edge = legacy account→account model
    IN_CURRENCY = "IN_CURRENCY"
    # transaction context (Wave 2 targets, edges defined now)
    VIA_CHANNEL = "VIA_CHANNEL"
    USED_DEVICE = "USED_DEVICE"
    FROM_IP = "FROM_IP"
    AT_LOCATION = "AT_LOCATION"
    TO_MERCHANT = "TO_MERCHANT"
    FROM_BRANCH = "FROM_BRANCH"
    TO_BRANCH = "TO_BRANCH"
    USED_CHANNEL = "USED_CHANNEL"
    VISITED = "VISITED"
    EMPLOYED_BY = "EMPLOYED_BY"
    CONTROLLED_BY = "CONTROLLED_BY"
    MANAGES = "MANAGES"
    # derived identity collisions (computed by job)
    SHARES_DEVICE = "SHARES_DEVICE"
    SHARES_IP = "SHARES_IP"
    SHARES_PHONE = "SHARES_PHONE"
    SHARES_EMAIL = "SHARES_EMAIL"
    SHARES_ADDRESS = "SHARES_ADDRESS"
    SAME_PAN = "SAME_PAN"
    SAME_AADHAAR = "SAME_AADHAAR"
    SAME_EMPLOYER = "SAME_EMPLOYER"
    SAME_ORGANIZATION = "SAME_ORGANIZATION"
    SAME_BENEFICIARY = "SAME_BENEFICIARY"
    RELATED_TO = "RELATED_TO"
    CONNECTED_TO = "CONNECTED_TO"
    # investigation lifecycle
    HAS_RISK_PROFILE = "HAS_RISK_PROFILE"
    FLAGGED_BY = "FLAGGED_BY"
    SUPPORTS_PATTERN = "SUPPORTS_PATTERN"
    GENERATED_ALERT = "GENERATED_ALERT"
    PART_OF_CASE = "PART_OF_CASE"
    CREATE_CASE = "CREATE_CASE"
    INVESTIGATED_IN = "INVESTIGATED_IN"
    STORE_EVIDENCE = "STORE_EVIDENCE"
    REPORTED_IN = "REPORTED_IN"
    ASSIGNED_TO = "ASSIGNED_TO"
    LISTED_ON = "LISTED_ON"


# Derived relationships are written ONLY by projection/collision jobs, never at ingest.
DERIVED_RELS: frozenset[Rel] = frozenset({
    Rel.TRANSFERRED_TO, Rel.SHARES_DEVICE, Rel.SHARES_IP, Rel.SHARES_PHONE,
    Rel.SHARES_EMAIL, Rel.SHARES_ADDRESS, Rel.SAME_PAN, Rel.SAME_AADHAAR,
    Rel.SAME_EMPLOYER, Rel.SAME_ORGANIZATION, Rel.SAME_BENEFICIARY,
    Rel.RELATED_TO, Rel.CONNECTED_TO,
})
