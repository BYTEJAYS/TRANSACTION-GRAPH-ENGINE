from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import uuid


class PaymentRail(str, Enum):
    UPI = "UPI"
    IMPS = "IMPS"
    RTGS = "RTGS"
    NEFT = "NEFT"
    CASH = "CASH"        # legacy: off-graph cash event (direction inferred from name)
    CASH_IN = "CASH_IN"  # first-class cash DEPOSIT  (CASH_SOURCE → account)
    CASH_OUT = "CASH_OUT"  # first-class cash WITHDRAWAL (account → CASH_EXIT)


class FraudPattern(str, Enum):
    NORMAL = "normal"
    CIRCULAR = "circular_transfer"
    FAN_OUT = "fan_out"
    LAYERING = "layering"
    RAPID_MICRO = "rapid_microtransaction"
    MULE_CHAIN = "mule_chain"
    BURST = "burst_transfer"
    STRUCTURING = "structuring"


class RiskLevel(str, Enum):
    SAFE = "safe"            # 0.0 - 0.3
    MODERATE = "moderate"    # 0.3 - 0.6
    HIGH = "high"            # 0.6 - 0.8
    CRITICAL = "critical"    # 0.8 - 1.0


class AccountType(str, Enum):
    NORMAL = "normal"
    MERCHANT = "merchant"
    MULE = "mule"
    HIGH_VALUE = "high_value"
    CASH = "cash"          # virtual cash endpoint (CASH_SOURCE / CASH_EXIT) — first-class node


class Transaction(BaseModel):
    transaction_id: str = Field(default_factory=lambda: f"TXN-{uuid.uuid4().hex[:12].upper()}")
    from_account: str
    to_account: str
    amount: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payment_rail: PaymentRail
    device_id: str
    ip_address: str
    geo_location: str
    risk_score: float = Field(ge=0.0, le=1.0, default=0.0)
    fraud_pattern: FraudPattern = FraudPattern.NORMAL
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def risk_level(self) -> RiskLevel:
        if self.risk_score < 0.3:
            return RiskLevel.SAFE
        elif self.risk_score < 0.6:
            return RiskLevel.MODERATE
        elif self.risk_score < 0.8:
            return RiskLevel.HIGH
        return RiskLevel.CRITICAL


class AccountNode(BaseModel):
    account_id: str
    account_type: AccountType = AccountType.NORMAL
    # When this node is a cash EVENT (not a bank account): "CASH_IN" = money entered
    # the banking system here, "CASH_OUT" = money left it (terminal). None = a real
    # account. Set rail-driven at graph-build time, NOT by name — so a cash-out whose
    # name isn't CASH* (e.g. DIAMOND_CASHOUT) is still a cash event, not an account.
    cash_kind: Optional[str] = None
    risk_score: float = Field(ge=0.0, le=1.0, default=0.0)
    transaction_count: int = 0
    total_sent: float = 0.0
    total_received: float = 0.0
    unique_counterparties: int = 0
    velocity_score: float = 0.0      # transactions per minute
    fan_out_score: float = 0.0       # degree of outgoing connections
    is_flagged: bool = False
    detected_patterns: List[FraudPattern] = Field(default_factory=list)
    geo_locations: List[str] = Field(default_factory=list)
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    embedding: Optional[List[float]] = None

    @property
    def risk_level(self) -> RiskLevel:
        if self.risk_score < 0.3:
            return RiskLevel.SAFE
        elif self.risk_score < 0.6:
            return RiskLevel.MODERATE
        elif self.risk_score < 0.8:
            return RiskLevel.HIGH
        return RiskLevel.CRITICAL


class FraudAlert(BaseModel):
    alert_id: str = Field(default_factory=lambda: f"ALT-{uuid.uuid4().hex[:8].upper()}")
    alert_type: FraudPattern
    severity: RiskLevel
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    accounts_involved: List[str]
    transaction_ids: List[str]
    description: str
    risk_score: float = Field(ge=0.0, le=1.0)
    shap_explanation: Dict[str, float] = Field(default_factory=dict)
    propagation_path: List[str] = Field(default_factory=list)
    total_amount: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    edge_id: str
    source: str
    target: str
    amount: float
    payment_rail: str
    risk_score: float
    timestamp: str
    fraud_pattern: str
    is_flagged: bool = False


class GraphState(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    stats: Dict[str, Any]
    alerts: List[Dict[str, Any]]
    timestamp: str


class WindowMetrics(BaseModel):
    window_start: datetime
    window_end: datetime
    transaction_count: int
    total_volume: float
    unique_senders: int
    unique_receivers: int
    avg_amount: float
    max_amount: float
    velocity_anomalies: int
    fan_out_accounts: List[str]


class WSMessage(BaseModel):
    type: str  # "transaction" | "graph_update" | "fraud_alert" | "stats_update" | "ping"
    data: Any
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class SimulationControl(BaseModel):
    action: str          # "start" | "stop" | "burst" | "inject_fraud"
    rate: Optional[float] = None
    fraud_pattern: Optional[FraudPattern] = None
    duration: Optional[int] = None


class ManualTransactionInput(BaseModel):
    from_account: str
    to_account: str
    amount: float
    payment_rail: str = "UPI"
    timestamp: Optional[str] = None
    # ── Optional heterogeneous / cross-product context (all backward compatible) ──
    # When supplied, ingestion records product types, ownership and shared
    # identities into a per-session entity-context store (separate from the
    # rendered money graph) so the cross-product / customer-risk / investigation
    # intelligence runs on real traffic. Omitting them keeps the legacy behaviour.
    device_id: Optional[str] = None
    from_entity_type: Optional[str] = None
    to_entity_type: Optional[str] = None
    from_customer: Optional[str] = None
    to_customer: Optional[str] = None
    from_phone: Optional[str] = None
    to_phone: Optional[str] = None
    from_pan: Optional[str] = None
    to_pan: Optional[str] = None
    # Owning bank of each account (cross-bank intelligence). Optional; when absent
    # the account defaults to UNION_BANK. Never enters the rendered money graph.
    from_bank: Optional[str] = None
    to_bank: Optional[str] = None
