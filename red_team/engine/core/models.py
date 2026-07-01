"""
Canonical data models for the Red Team platform.

Every artefact produced by the platform — identities, accounts, transactions,
scenarios, datasets — carries an explicit ``synthetic`` provenance stamp so
that no generated object can ever be mistaken for real-world data.

These models are deliberately independent of the Blue Team / TGIE Core models.
Duplication here is intentional: it preserves the isolation contract.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Provenance ────────────────────────────────────────────────────────────────

SYNTHETIC_WATERMARK = "TGIE-RED-TEAM-SYNTHETIC"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Provenance(BaseModel):
    """Immutable stamp proving an artefact is synthetic and Red-Team-originated."""

    watermark: str = SYNTHETIC_WATERMARK
    is_synthetic: bool = True
    generator: str = "red_team"
    seed: Optional[int] = None
    created_at: datetime = Field(default_factory=_now)
    note: str = "Synthetic research artefact. Not derived from any real entity."


# ── Enumerations ──────────────────────────────────────────────────────────────

class ComplexityLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class FraudCategory(str, Enum):
    NORMAL = "normal"
    IDENTITY_FRAUD = "identity_fraud"
    SYNTHETIC_IDENTITY = "synthetic_identity_fraud"
    TRANSACTION_LAUNDERING = "transaction_laundering"
    MULE_NETWORK = "mule_network"
    INSIDER_ABUSE = "insider_abuse"
    ACCOUNT_TAKEOVER = "account_takeover"
    STRUCTURING = "structuring"
    SMURFING = "smurfing"
    CIRCULAR_FLOW = "circular_flow"
    LAYERING = "layering"


class PaymentRail(str, Enum):
    UPI = "UPI"
    IMPS = "IMPS"
    RTGS = "RTGS"
    NEFT = "NEFT"
    CASH = "CASH"


class AccountArchetype(str, Enum):
    RETAIL = "retail"
    SALARIED = "salaried"
    MERCHANT = "merchant"
    BUSINESS = "business"
    HIGH_NET_WORTH = "high_net_worth"
    MULE = "mule"
    SHELL = "shell"


# ── Synthetic entities ──────────────────────────────────────────────────────

class DeviceFingerprint(BaseModel):
    device_id: str = Field(default_factory=lambda: f"DEV-{uuid.uuid4().hex[:10]}")
    platform: str = "mobile_android"
    user_agent: str = "synthetic-agent/1.0"
    ip_address: str = "0.0.0.0"
    is_emulator: bool = False
    is_rooted: bool = False


class BehavioralProfile(BaseModel):
    avg_session_minutes: float = 6.0
    txns_per_day: float = 2.0
    typical_hour_range: List[int] = Field(default_factory=lambda: [9, 21])
    preferred_rail: PaymentRail = PaymentRail.UPI
    velocity_baseline: float = 1.0  # txns/min under normal behaviour
    spending_dispersion: float = 0.3  # 0 = rigid, 1 = erratic


class KYCProfile(BaseModel):
    """Fully fictional KYC record. No field is derived from real data."""

    full_name: str
    date_of_birth: str
    address: str
    city: str
    document_type: str = "synthetic_id"
    document_number: str = Field(default_factory=lambda: f"SYN-{uuid.uuid4().hex[:10].upper()}")
    risk_band: str = "low"
    is_verified: bool = True
    anomaly_flags: List[str] = Field(default_factory=list)


class SyntheticIdentity(BaseModel):
    identity_id: str = Field(default_factory=lambda: f"ID-{uuid.uuid4().hex[:10].upper()}")
    kyc: KYCProfile
    behavior: BehavioralProfile = Field(default_factory=BehavioralProfile)
    devices: List[DeviceFingerprint] = Field(default_factory=list)
    is_business: bool = False
    provenance: Provenance = Field(default_factory=Provenance)


class SyntheticAccount(BaseModel):
    account_id: str = Field(default_factory=lambda: f"ACC-{uuid.uuid4().hex[:8].upper()}")
    owner_identity_id: str
    archetype: AccountArchetype = AccountArchetype.RETAIL
    opened_at: datetime = Field(default_factory=_now)
    home_city: str = "Mumbai"
    typical_amount_range: List[float] = Field(default_factory=lambda: [500.0, 20000.0])
    label: FraudCategory = FraudCategory.NORMAL  # ground-truth role in the scenario
    provenance: Provenance = Field(default_factory=Provenance)


class SyntheticTransaction(BaseModel):
    transaction_id: str = Field(default_factory=lambda: f"TXN-{uuid.uuid4().hex[:12].upper()}")
    from_account: str
    to_account: str
    amount: float
    timestamp: datetime = Field(default_factory=_now)
    payment_rail: PaymentRail = PaymentRail.UPI
    device_id: str = ""
    geo_location: str = ""
    # Ground-truth labels — for research evaluation only, never a detector output.
    fraud_category: FraudCategory = FraudCategory.NORMAL
    is_fraud: bool = False
    scenario_step: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance = Field(default_factory=Provenance)


# ── Scenario + dataset structures ─────────────────────────────────────────────

class RiskIndicator(BaseModel):
    """A measurable signal the scenario is designed to exhibit (research label)."""

    name: str
    description: str
    severity: ComplexityLevel = ComplexityLevel.BEGINNER


class ScenarioSpec(BaseModel):
    """Declarative description of a scenario before it is materialised."""

    scenario_id: str
    title: str
    category: FraudCategory
    complexity: ComplexityLevel
    description: str
    objectives: List[str] = Field(default_factory=list)
    risk_indicators: List[RiskIndicator] = Field(default_factory=list)
    expected_outcomes: List[str] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)


class GeneratedScenario(BaseModel):
    """A materialised scenario: spec + the synthetic data it produced."""

    spec: ScenarioSpec
    identities: List[SyntheticIdentity] = Field(default_factory=list)
    accounts: List[SyntheticAccount] = Field(default_factory=list)
    transactions: List[SyntheticTransaction] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_now)
    seed: Optional[int] = None
    provenance: Provenance = Field(default_factory=Provenance)

    # ── Convenience metrics (purely descriptive) ──────────────────────────────

    @property
    def num_accounts(self) -> int:
        return len(self.accounts)

    @property
    def num_transactions(self) -> int:
        return len(self.transactions)

    @property
    def total_volume(self) -> float:
        return round(sum(t.amount for t in self.transactions), 2)

    @property
    def fraud_transaction_count(self) -> int:
        return sum(1 for t in self.transactions if t.is_fraud)

    def summary(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.spec.scenario_id,
            "title": self.spec.title,
            "category": self.spec.category.value,
            "complexity": self.spec.complexity.value,
            "identities": len(self.identities),
            "accounts": self.num_accounts,
            "transactions": self.num_transactions,
            "fraud_transactions": self.fraud_transaction_count,
            "total_volume": self.total_volume,
            "seed": self.seed,
        }
