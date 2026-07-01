"""
Union Bank Knowledge Base — the reusable banking-intelligence data layer
(Phase 10).

This is NOT hard-coded detection logic. It is reference knowledge — products,
channels, fraud typologies, recovery playbooks and regulatory mappings — that
the Blue Team, rule engine, recommendation/recovery engines, case intelligence
and narratives all READ instead of each re-encoding the same banking facts.
Pure data + lookups; additive; no behaviour of existing modules changes until
they choose to consult it.
"""
from __future__ import annotations

from typing import Any

from .entities import ProductCategory

# ── Products & channels ─────────────────────────────────────────────────────
# Each product carries its category, the channels it transacts over, its
# inherent fraud exposure, and the recovery levers available on it (referenced by
# the recovery engine so freezes are product-appropriate).
PRODUCTS: dict[str, dict[str, Any]] = {
    "savings_account": {"category": ProductCategory.RETAIL.value, "channels": ["upi", "imps", "neft", "atm", "branch"],
                        "inherent_risk": 0.3, "recovery_levers": ["freeze", "limit_transfer", "enhanced_kyc"]},
    "salary_account": {"category": ProductCategory.RETAIL.value, "channels": ["upi", "imps", "neft"],
                       "inherent_risk": 0.25, "recovery_levers": ["block_upi_allow_credit", "limit_transfer"]},
    "current_account": {"category": ProductCategory.CORPORATE.value, "channels": ["rtgs", "neft", "imps", "branch"],
                        "inherent_risk": 0.4, "recovery_levers": ["pause_rtgs", "freeze", "enhanced_kyc"]},
    "corporate_account": {"category": ProductCategory.CORPORATE.value, "channels": ["rtgs", "neft", "swift"],
                          "inherent_risk": 0.5, "recovery_levers": ["pause_rtgs", "vendor_review", "freeze"]},
    "credit_card": {"category": ProductCategory.CARD.value, "channels": ["pos", "online", "refund"],
                    "inherent_risk": 0.45, "recovery_levers": ["suspend_card", "review_refunds", "step_up_auth"]},
    "debit_card": {"category": ProductCategory.CARD.value, "channels": ["pos", "atm"],
                   "inherent_risk": 0.35, "recovery_levers": ["suspend_card", "atm_limit"]},
    "upi_id": {"category": ProductCategory.PAYMENT.value, "channels": ["upi"],
               "inherent_risk": 0.5, "recovery_levers": ["block_upi", "limit_transfer", "step_up_auth"]},
    "wallet": {"category": ProductCategory.DIGITAL.value, "channels": ["upi", "wallet"],
               "inherent_risk": 0.55, "recovery_levers": ["limit_wallet", "freeze_wallet", "enhanced_kyc"]},
    "loan": {"category": ProductCategory.LOAN.value, "channels": ["disbursement", "neft"],
             "inherent_risk": 0.5, "recovery_levers": ["flag_loan_review", "hold_disbursement"]},
    "fixed_deposit": {"category": ProductCategory.DEPOSIT.value, "channels": ["branch", "online"],
                      "inherent_risk": 0.3, "recovery_levers": ["prevent_premature_closure", "flag_review"]},
    "recurring_deposit": {"category": ProductCategory.DEPOSIT.value, "channels": ["branch", "online"],
                          "inherent_risk": 0.25, "recovery_levers": ["flag_review"]},
    "merchant": {"category": ProductCategory.PAYMENT.value, "channels": ["pos", "online", "upi"],
                 "inherent_risk": 0.5, "recovery_levers": ["escalate_merchant_monitoring", "hold_settlement"]},
}

CHANNELS: dict[str, dict[str, Any]] = {
    "upi": {"realtime": True, "reversible": False, "typical_use": "P2P / P2M instant transfer", "risk": 0.5},
    "imps": {"realtime": True, "reversible": False, "typical_use": "instant interbank", "risk": 0.4},
    "neft": {"realtime": False, "reversible": False, "typical_use": "batched interbank", "risk": 0.3},
    "rtgs": {"realtime": True, "reversible": False, "typical_use": "high-value real-time", "risk": 0.45},
    "cash": {"realtime": True, "reversible": False, "typical_use": "cash in/out (off-network)", "risk": 0.7},
    "wallet": {"realtime": True, "reversible": False, "typical_use": "stored-value transfer", "risk": 0.55},
    "swift": {"realtime": False, "reversible": False, "typical_use": "cross-border", "risk": 0.6},
    "refund": {"realtime": False, "reversible": True, "typical_use": "merchant/card refund", "risk": 0.55},
}

# ── Cross-product fraud typologies ──────────────────────────────────────────
# The named multi-product laundering schemes investigators recognise. Each maps
# its stages, the products it spans, and the XP rules it would trip — so a
# detected cross-product flow can be named, narrated and routed to recovery.
TYPOLOGIES: dict[str, dict[str, Any]] = {
    "wallet_layering": {
        "label": "Wallet Layering",
        "stages": ["savings", "upi", "wallet", "wallet", "merchant", "cash_out"],
        "products": ["savings_account", "upi_id", "wallet", "merchant"],
        "xp_rules": ["XP004", "XP002"],
        "narrative": "Funds hop savings→UPI→wallet→wallet→merchant before cash-out to break the trail.",
    },
    "loan_laundering": {
        "label": "Loan Laundering",
        "stages": ["loan", "savings", "shell_company", "foreign_transfer"],
        "products": ["loan", "savings_account", "corporate_account", "foreign_bank"],
        "xp_rules": ["XP003", "XP013"],
        "narrative": "Loan disbursement is immediately routed out through a shell to a foreign account.",
    },
    "merchant_refund_abuse": {
        "label": "Merchant Refund Abuse",
        "stages": ["credit_card", "merchant", "refund", "savings", "exit"],
        "products": ["credit_card", "merchant", "savings_account"],
        "xp_rules": ["XP005"],
        "narrative": "Card spend is reversed as refunds into a savings account and cashed out.",
    },
    "salary_mule": {
        "label": "Salary-Account Mule",
        "stages": ["salary", "wallet", "wallet", "merchant", "mule"],
        "products": ["salary_account", "wallet", "merchant"],
        "xp_rules": ["XP004", "XP015"],
        "narrative": "A salary account suddenly behaves like a mule, fanning pay into wallets and merchants.",
    },
    "fd_liquidation": {
        "label": "Premature FD Liquidation",
        "stages": ["savings", "fixed_deposit", "premature_closure", "current", "cash_withdrawal"],
        "products": ["fixed_deposit", "savings_account", "current_account"],
        "xp_rules": ["XP007", "XP006"],
        "narrative": "A fixed deposit is broken early and the proceeds are rapidly withdrawn as cash.",
    },
    "corporate_diversion": {
        "label": "Corporate Expense Diversion",
        "stages": ["corporate", "vendor", "employee", "personal"],
        "products": ["corporate_account", "merchant", "savings_account"],
        "xp_rules": ["XP008"],
        "narrative": "Corporate funds are diverted through vendors/employees into personal accounts.",
    },
    "shared_identity_ring": {
        "label": "Shared-Identity Mule Ring",
        "stages": ["device", "many_accounts", "collection", "cash_out"],
        "products": ["savings_account", "upi_id", "wallet"],
        "xp_rules": ["XP009", "XP010", "XP011"],
        "narrative": "One device / phone / PAN controls many otherwise-unrelated accounts acting as mules.",
    },
}

# ── Regulatory mapping ──────────────────────────────────────────────────────
# Coarse mapping from a typology/category to the Indian AML/regulatory hooks an
# analyst cites in an STR/SAR. Reference only.
REGULATORY: dict[str, dict[str, Any]] = {
    "structuring": {"framework": "PMLA 2002", "report": "STR", "authority": "FIU-IND",
                    "note": "Transactions structured below ₹10L reporting threshold."},
    "cash_intensive": {"framework": "PMLA 2002 / RBI KYC", "report": "CTR", "authority": "FIU-IND",
                       "note": "Cash transactions ≥ ₹10L must be reported."},
    "cross_border": {"framework": "FEMA 1999", "report": "STR", "authority": "FIU-IND / RBI",
                     "note": "Outbound foreign transfers require purpose verification."},
    "mule": {"framework": "RBI Master Direction on Fraud", "report": "STR", "authority": "FIU-IND",
             "note": "Mule-account indicators must be flagged and frozen per RBI norms."},
    "identity": {"framework": "RBI KYC Master Direction", "report": "internal", "authority": "Bank Compliance",
                 "note": "Shared identity/device across customers fails CDD; trigger enhanced KYC."},
}


def product(name: str) -> dict[str, Any]:
    return PRODUCTS.get(name, {})


def channel(name: str) -> dict[str, Any]:
    return CHANNELS.get(name, {})


def typology(name: str) -> dict[str, Any]:
    return TYPOLOGIES.get(name, {})


def recovery_levers(product_name: str) -> list[str]:
    return PRODUCTS.get(product_name, {}).get("recovery_levers", [])


def match_typologies(categories: set[str]) -> list[dict[str, Any]]:
    """Typologies whose product categories are (mostly) present in a flow —
    used to NAME a detected cross-product scheme. Returns strongest-overlap first."""
    out = []
    for key, t in TYPOLOGIES.items():
        prods = set(t["products"])
        cats = {PRODUCTS.get(p, {}).get("category") for p in prods} | set(t["stages"])
        overlap = len(cats & categories)
        if overlap >= 2:
            out.append({"typology": key, **t, "overlap": overlap})
    out.sort(key=lambda x: x["overlap"], reverse=True)
    return out
