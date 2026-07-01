"""
Heterogeneous entity + relationship taxonomy (Phase 1 / Phase 9).

TGIE's live graph is account-to-account, but a real Union Bank investigation
spans many entity kinds (customers, cards, wallets, loans, devices, identities,
merchants…) joined by many relationship kinds. This module defines that
taxonomy and a PURE PROJECTION that classifies the nodes/edges TGIE already
produces into entity categories, product types, business roles and channels —
without rewriting the graph engine or breaking any payload. Existing consumers
ignore the extra fields; new cross-product intelligence reads them.
"""
from __future__ import annotations

import enum
from typing import Any


class EntityType(str, enum.Enum):
    """The kind of thing a node represents in a heterogeneous financial graph."""
    CUSTOMER = "customer"
    SAVINGS_ACCOUNT = "savings_account"
    CURRENT_ACCOUNT = "current_account"
    SALARY_ACCOUNT = "salary_account"
    CORPORATE_ACCOUNT = "corporate_account"
    VIRTUAL_ACCOUNT = "virtual_account"
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    UPI_ID = "upi_id"
    WALLET = "wallet"
    MERCHANT = "merchant"
    LOAN = "loan"
    FIXED_DEPOSIT = "fixed_deposit"
    RECURRING_DEPOSIT = "recurring_deposit"
    BRANCH = "branch"
    ATM = "atm"
    DEVICE = "device"
    MOBILE = "mobile_number"
    EMAIL = "email"
    PAN = "pan"
    AADHAAR = "aadhaar"
    PASSPORT = "passport"
    GST = "gst"
    COMPANY = "company"
    BENEFICIARY = "beneficiary"
    EMPLOYEE = "employee"
    FOREIGN_BANK = "foreign_bank"
    SWIFT_ENTITY = "swift_entity"
    RELATIONSHIP_MANAGER = "relationship_manager"
    CASH_ENDPOINT = "cash_endpoint"
    ACCOUNT = "account"            # generic / unclassified bank account


class RelationshipType(str, enum.Enum):
    """The kind of edge joining two entities."""
    OWNS = "OWNS"
    TRANSFERRED = "TRANSFERRED"
    USES = "USES"
    LOGGED_IN_FROM = "LOGGED_IN_FROM"
    REGISTERED_WITH = "REGISTERED_WITH"
    HAS_DEVICE = "HAS_DEVICE"
    HAS_PHONE = "HAS_PHONE"
    HAS_EMAIL = "HAS_EMAIL"
    HAS_PAN = "HAS_PAN"
    HAS_AADHAAR = "HAS_AADHAAR"
    PAID = "PAID"
    WITHDREW = "WITHDREW"
    DEPOSITED = "DEPOSITED"
    LINKED_TO = "LINKED_TO"
    GUARANTOR = "GUARANTOR"
    EMPLOYED_BY = "EMPLOYED_BY"
    DIRECTOR_OF = "DIRECTOR_OF"
    BENEFICIARY_OF = "BENEFICIARY_OF"


class ProductCategory(str, enum.Enum):
    """Business grouping of a product/entity for cross-product correlation."""
    RETAIL = "retail"
    CORPORATE = "corporate"
    LOAN = "loan"
    DEPOSIT = "deposit"
    CARD = "card"
    DIGITAL = "digital"
    PAYMENT = "payment"
    IDENTITY = "identity"
    CHANNEL = "channel"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


# Which product category each entity type belongs to.
_ENTITY_CATEGORY: dict[EntityType, ProductCategory] = {
    EntityType.SAVINGS_ACCOUNT: ProductCategory.RETAIL,
    EntityType.SALARY_ACCOUNT: ProductCategory.RETAIL,
    EntityType.ACCOUNT: ProductCategory.RETAIL,
    EntityType.CURRENT_ACCOUNT: ProductCategory.CORPORATE,
    EntityType.CORPORATE_ACCOUNT: ProductCategory.CORPORATE,
    EntityType.VIRTUAL_ACCOUNT: ProductCategory.CORPORATE,
    EntityType.CREDIT_CARD: ProductCategory.CARD,
    EntityType.DEBIT_CARD: ProductCategory.CARD,
    EntityType.LOAN: ProductCategory.LOAN,
    EntityType.FIXED_DEPOSIT: ProductCategory.DEPOSIT,
    EntityType.RECURRING_DEPOSIT: ProductCategory.DEPOSIT,
    EntityType.UPI_ID: ProductCategory.PAYMENT,
    EntityType.WALLET: ProductCategory.DIGITAL,
    EntityType.MERCHANT: ProductCategory.PAYMENT,
    EntityType.DEVICE: ProductCategory.CHANNEL,
    EntityType.MOBILE: ProductCategory.IDENTITY,
    EntityType.EMAIL: ProductCategory.IDENTITY,
    EntityType.PAN: ProductCategory.IDENTITY,
    EntityType.AADHAAR: ProductCategory.IDENTITY,
    EntityType.PASSPORT: ProductCategory.IDENTITY,
    EntityType.GST: ProductCategory.IDENTITY,
    EntityType.CUSTOMER: ProductCategory.RETAIL,
    EntityType.COMPANY: ProductCategory.CORPORATE,
    EntityType.FOREIGN_BANK: ProductCategory.EXTERNAL,
    EntityType.SWIFT_ENTITY: ProductCategory.EXTERNAL,
    EntityType.CASH_ENDPOINT: ProductCategory.EXTERNAL,
    EntityType.ATM: ProductCategory.CHANNEL,
    EntityType.BRANCH: ProductCategory.CHANNEL,
}

# id-prefix → entity type. The simulator uses opaque ids today; these prefixes
# let richer datasets (and future ingestion) declare product kind in the id, and
# are applied case-insensitively before the account_type fallback.
_PREFIX_MAP: list[tuple[str, EntityType]] = [
    ("CASH", EntityType.CASH_ENDPOINT),
    ("CUST", EntityType.CUSTOMER),
    ("SAVING", EntityType.SAVINGS_ACCOUNT),
    ("SAV", EntityType.SAVINGS_ACCOUNT),
    ("SALARY", EntityType.SALARY_ACCOUNT),
    ("SAL", EntityType.SALARY_ACCOUNT),
    ("CURRENT", EntityType.CURRENT_ACCOUNT),
    ("CUR", EntityType.CURRENT_ACCOUNT),
    ("CORP", EntityType.CORPORATE_ACCOUNT),
    ("VIRTUAL", EntityType.VIRTUAL_ACCOUNT),
    ("VACC", EntityType.VIRTUAL_ACCOUNT),
    ("CREDITCARD", EntityType.CREDIT_CARD),
    ("CC", EntityType.CREDIT_CARD),
    ("DEBITCARD", EntityType.DEBIT_CARD),
    ("DC", EntityType.DEBIT_CARD),
    ("UPI", EntityType.UPI_ID),
    ("WALLET", EntityType.WALLET),
    ("WLT", EntityType.WALLET),
    ("MERCHANT", EntityType.MERCHANT),
    ("MERCH", EntityType.MERCHANT),
    ("LOAN", EntityType.LOAN),
    ("GOLDLOAN", EntityType.LOAN),
    ("HOMELOAN", EntityType.LOAN),
    ("FD", EntityType.FIXED_DEPOSIT),
    ("RD", EntityType.RECURRING_DEPOSIT),
    ("BRANCH", EntityType.BRANCH),
    ("ATM", EntityType.ATM),
    ("DEV", EntityType.DEVICE),
    ("DEVICE", EntityType.DEVICE),
    ("PHONE", EntityType.MOBILE),
    ("MOB", EntityType.MOBILE),
    ("EMAIL", EntityType.EMAIL),
    ("PAN", EntityType.PAN),
    ("AADHAAR", EntityType.AADHAAR),
    ("UID", EntityType.AADHAAR),
    ("PASSPORT", EntityType.PASSPORT),
    ("GST", EntityType.GST),
    ("COMP", EntityType.COMPANY),
    ("FBANK", EntityType.FOREIGN_BANK),
    ("SWIFT", EntityType.SWIFT_ENTITY),
    ("RM", EntityType.RELATIONSHIP_MANAGER),
]

# account_type (existing AccountType enum values) → entity type fallback.
_ACCOUNT_TYPE_MAP: dict[str, EntityType] = {
    "cash": EntityType.CASH_ENDPOINT,
    "merchant": EntityType.MERCHANT,
    "mule": EntityType.ACCOUNT,
    "high_value": EntityType.CURRENT_ACCOUNT,
    "normal": EntityType.ACCOUNT,
}

# payment_rail → (relationship, channel) for edges.
_RAIL_MAP: dict[str, tuple[RelationshipType, str]] = {
    "UPI": (RelationshipType.PAID, "upi"),
    "IMPS": (RelationshipType.TRANSFERRED, "imps"),
    "RTGS": (RelationshipType.TRANSFERRED, "rtgs"),
    "NEFT": (RelationshipType.TRANSFERRED, "neft"),
    "CASH": (RelationshipType.WITHDREW, "cash"),
    "CASH_IN": (RelationshipType.DEPOSITED, "cash"),
    "CASH_OUT": (RelationshipType.WITHDREW, "cash"),
}


def classify_entity(node: dict[str, Any]) -> EntityType:
    """Best-effort entity type for a node: id-prefix first, then account_type."""
    nid = str(node.get("id", "")).upper()
    for prefix, et in _PREFIX_MAP:
        if nid.startswith(prefix) or f"_{prefix}" in nid:
            return et
    at = str(node.get("account_type", "normal")).lower()
    return _ACCOUNT_TYPE_MAP.get(at, EntityType.ACCOUNT)


def entity_category(et: EntityType) -> ProductCategory:
    return _ENTITY_CATEGORY.get(et, ProductCategory.UNKNOWN)


def classify_node(node: dict[str, Any]) -> dict[str, Any]:
    """
    Full additive classification for a node: entity type, product category, and
    (when risk metadata is present) a business role. Returned as a dict to be
    merged into the node payload under a `taxonomy` key — purely additive.
    """
    et = classify_entity(node)
    cat = entity_category(et)
    return {
        "entity_type": et.value,
        "entity_category": cat.value,
        "product_type": et.value,
        "is_identity": cat == ProductCategory.IDENTITY,
        "is_external": cat == ProductCategory.EXTERNAL,
    }


def classify_edge(edge: dict[str, Any]) -> dict[str, Any]:
    """Additive classification for an edge: relationship type + channel. Honors an
    explicit `relationship_type` (heterogeneous/structural edges) and otherwise
    derives it from the payment rail (transaction edges)."""
    explicit = edge.get("relationship_type")
    rail = str(edge.get("payment_rail", "")).upper()
    if explicit:
        _, channel = _RAIL_MAP.get(rail, (None, rail.lower() or "structural"))
        return {"relationship_type": str(explicit), "channel": channel}
    rel, channel = _RAIL_MAP.get(rail, (RelationshipType.TRANSFERRED, rail.lower() or "unknown"))
    return {"relationship_type": rel.value, "channel": channel}


def involved_categories(nodes: list[dict], edges: list[dict]) -> set[str]:
    """The set of product categories (+ channels) a component touches — the
    primitive cross-product correlation reads to know a flow spans products."""
    cats = {entity_category(classify_entity(n)).value for n in nodes}
    cats |= {classify_edge(e)["channel"] for e in edges}
    return cats
