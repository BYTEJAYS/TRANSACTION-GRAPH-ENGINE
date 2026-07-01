"""
Recovery playbooks — product-aware recovery actions (Phase 7 reference layer).

Each lever is a self-explaining action with why / expected impact / risk
reduction / customer impact / confidence, so the recovery + recommendation
engines can compose product-appropriate responses (e.g. block UPI but keep
salary credits flowing) instead of a blunt account freeze. Pure reference data.
"""
from __future__ import annotations

from typing import Any

# lever-id → action template. `confidence` is the playbook's prior; callers
# scale it by the actual evidence strength.
RECOVERY_ACTIONS: dict[str, dict[str, Any]] = {
    "freeze": {
        "action": "FREEZE_ACCOUNT", "why": "High-confidence fraud; stop further loss immediately.",
        "expected_impact": "Halts all debits/credits on the account.",
        "risk_reduction": 0.9, "customer_impact": "high", "confidence": 0.9},
    "block_upi": {
        "action": "BLOCK_UPI", "why": "UPI is the active exfiltration rail.",
        "expected_impact": "Stops instant UPI outflow; other rails unaffected.",
        "risk_reduction": 0.6, "customer_impact": "medium", "confidence": 0.8},
    "block_upi_allow_credit": {
        "action": "BLOCK_UPI_ALLOW_CREDIT", "why": "Salary account misused as a mule; preserve legitimate pay-ins.",
        "expected_impact": "Blocks UPI debits while allowing salary credits.",
        "risk_reduction": 0.55, "customer_impact": "low", "confidence": 0.75},
    "limit_transfer": {
        "action": "LIMIT_TRANSFER", "why": "Velocity above baseline; cap exposure without full freeze.",
        "expected_impact": "Caps per-txn / daily transfer limits.",
        "risk_reduction": 0.4, "customer_impact": "low", "confidence": 0.7},
    "suspend_card": {
        "action": "SUSPEND_CARD", "why": "Card used in refund-abuse / fraudulent spend.",
        "expected_impact": "Blocks further card authorisations.",
        "risk_reduction": 0.7, "customer_impact": "medium", "confidence": 0.8},
    "review_refunds": {
        "action": "REVIEW_REFUNDS", "why": "Refund pattern indicates laundering route.",
        "expected_impact": "Holds and manually reviews pending refunds.",
        "risk_reduction": 0.5, "customer_impact": "low", "confidence": 0.7},
    "step_up_auth": {
        "action": "STEP_UP_AUTH", "why": "Anomalous channel/device; raise authentication.",
        "expected_impact": "Forces additional verification on transactions.",
        "risk_reduction": 0.35, "customer_impact": "low", "confidence": 0.65},
    "pause_rtgs": {
        "action": "PAUSE_RTGS", "why": "High-value real-time rail used for layering.",
        "expected_impact": "Pauses RTGS while other rails continue.",
        "risk_reduction": 0.6, "customer_impact": "medium", "confidence": 0.75},
    "flag_loan_review": {
        "action": "FLAG_LOAN_REVIEW", "why": "Disbursed loan exits immediately — possible loan laundering.",
        "expected_impact": "Routes the loan to fraud-ops review; future tranches held.",
        "risk_reduction": 0.5, "customer_impact": "medium", "confidence": 0.7},
    "hold_disbursement": {
        "action": "HOLD_DISBURSEMENT", "why": "Prevent funds leaving before review completes.",
        "expected_impact": "Holds the pending disbursement.",
        "risk_reduction": 0.8, "customer_impact": "high", "confidence": 0.75},
    "prevent_premature_closure": {
        "action": "PREVENT_PREMATURE_FD_CLOSURE", "why": "Early FD break feeding rapid cash-out.",
        "expected_impact": "Blocks premature closure pending review.",
        "risk_reduction": 0.6, "customer_impact": "medium", "confidence": 0.7},
    "limit_wallet": {
        "action": "LIMIT_WALLET", "why": "Wallet used as a layering hop.",
        "expected_impact": "Caps wallet load/transfer limits.",
        "risk_reduction": 0.45, "customer_impact": "low", "confidence": 0.7},
    "freeze_wallet": {
        "action": "FREEZE_WALLET", "why": "Wallet is the active layering vehicle.",
        "expected_impact": "Freezes wallet balance and transfers.",
        "risk_reduction": 0.7, "customer_impact": "medium", "confidence": 0.75},
    "escalate_merchant_monitoring": {
        "action": "ESCALATE_MERCHANT_MONITORING", "why": "Merchant implicated in refund/settlement abuse.",
        "expected_impact": "Raises merchant to enhanced monitoring; settlements reviewed.",
        "risk_reduction": 0.5, "customer_impact": "low", "confidence": 0.7},
    "hold_settlement": {
        "action": "HOLD_MERCHANT_SETTLEMENT", "why": "Prevent payout of suspicious merchant volume.",
        "expected_impact": "Holds the next settlement cycle for review.",
        "risk_reduction": 0.6, "customer_impact": "medium", "confidence": 0.7},
    "enhanced_kyc": {
        "action": "TRIGGER_ENHANCED_KYC", "why": "Identity/CDD gaps (shared device, phone or PAN).",
        "expected_impact": "Forces re-KYC before further activity.",
        "risk_reduction": 0.4, "customer_impact": "medium", "confidence": 0.7},
    "vendor_review": {
        "action": "VENDOR_REVIEW", "why": "Corporate funds diverted via vendor accounts.",
        "expected_impact": "Audits vendor relationships and recent payouts.",
        "risk_reduction": 0.45, "customer_impact": "low", "confidence": 0.65},
    "atm_limit": {
        "action": "LOWER_ATM_LIMIT", "why": "Card linked to cash-out behaviour.",
        "expected_impact": "Reduces daily ATM withdrawal ceiling.",
        "risk_reduction": 0.35, "customer_impact": "low", "confidence": 0.65},
    "flag_review": {
        "action": "FLAG_FOR_REVIEW", "why": "Behaviour outside baseline; needs analyst eyes.",
        "expected_impact": "Adds to the fraud-ops review queue.",
        "risk_reduction": 0.2, "customer_impact": "none", "confidence": 0.6},
    "notify_fraud_ops": {
        "action": "NOTIFY_FRAUD_OPS", "why": "Escalate to the financial-crime team.",
        "expected_impact": "Opens a fraud-ops ticket with the evidence bundle.",
        "risk_reduction": 0.25, "customer_impact": "none", "confidence": 0.8},
}


def action_for(lever: str, evidence_confidence: float = 1.0) -> dict[str, Any] | None:
    """Materialise a recovery action for a lever, scaling its confidence by the
    strength of the evidence that triggered it."""
    tmpl = RECOVERY_ACTIONS.get(lever)
    if not tmpl:
        return None
    out = dict(tmpl)
    out["lever"] = lever
    out["confidence"] = round(min(0.99, tmpl["confidence"] * max(0.0, min(1.0, evidence_confidence))), 3)
    return out
