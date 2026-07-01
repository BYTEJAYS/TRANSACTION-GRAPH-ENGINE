"""
Case Management — constants, request models and pure business logic.

Self-contained (stdlib + pydantic only), mirroring the auth module's style so it
drops into the existing backend with no new dependencies.
"""

from __future__ import annotations

import hashlib
from typing import List, Optional

from pydantic import BaseModel

# ── Lifecycle ─────────────────────────────────────────────────────────────────
STATUSES = [
    "New", "Under Review", "Evidence Collection", "Active Investigation",
    "Escalated", "Pending Approval", "Resolved", "Closed", "False Positive", "Archived",
]
OPEN_STATUSES = {
    "New", "Under Review", "Evidence Collection", "Active Investigation",
    "Escalated", "Pending Approval",
}
CLOSED_STATUSES = {"Resolved", "Closed", "False Positive", "Archived"}

PRIORITIES = ["Critical", "High", "Medium", "Low"]
PRIORITY_RANK = {p: i for i, p in enumerate(PRIORITIES)}

# Detection categories → auto-generated case titles
CATEGORY_TITLES = {
    "Money Mule Network": "Possible Money Mule Network",
    "Circular Transactions": "Circular Transaction Investigation",
    "Account Takeover": "Suspected Account Takeover",
    "Layering Activity": "Layering & Structuring Investigation",
    "High-Risk Network": "High-Risk Transaction Cluster",
    "Suspicious Transaction Chain": "Suspicious Transaction Chain",
    "Rapid Fund Movement": "Rapid Fund Movement Investigation",
    "Suspicious Account Ring": "Suspicious Account Ring",
    "Linked Fraud Network": "Linked Fraud Network",
}
CATEGORIES = list(CATEGORY_TITLES.keys())


# ── Request models ────────────────────────────────────────────────────────────
class CreateCaseRequest(BaseModel):
    account_number: Optional[str] = None       # seed the case from an account
    category: Optional[str] = None
    title: Optional[str] = None
    risk_score: Optional[int] = None
    detection_reason: Optional[str] = None
    accounts: Optional[List[str]] = None
    priority: Optional[str] = None             # investigator override


class UpdateCaseRequest(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    title: Optional[str] = None
    risk_score: Optional[int] = None


class NoteRequest(BaseModel):
    text: str


class EvidenceRequest(BaseModel):
    type: str
    description: Optional[str] = None
    reference: Optional[str] = None            # filename / external id (hashed)


class AssignRequest(BaseModel):
    investigator_id: Optional[str] = None
    supervisor: Optional[str] = None
    department: Optional[str] = None
    due_date: Optional[str] = None


class CloseRequest(BaseModel):
    resolution: str = "Resolved"               # Resolved | Closed | False Positive
    summary: Optional[str] = None


class GraphSnapshotRequest(BaseModel):
    """Verbatim capture of the live 3D graph — node positions + camera — so a case
    reopens to EXACTLY what the investigator saw, with no force simulation re-run."""
    nodes: List[dict]                          # [{id, x, y, z, risk_score, nodeColor, …}]
    edges: List[dict] = []                     # [{source, target, …}]
    camera: Optional[dict] = None              # {position:{x,y,z}, target:{x,y,z}}
    indicators: Optional[List[str]] = None


# ── Collaboration request models ──────────────────────────────────────────────
class ParticipantRequest(BaseModel):
    investigator_id: str
    name: Optional[str] = None
    role_on_case: str = "Supporting Investigator"


class HandoverRequest(BaseModel):
    to_investigator_id: str
    to_name: Optional[str] = None
    note: Optional[str] = None


class CommentRequest(BaseModel):
    text: str
    parent_id: Optional[str] = None            # set for a threaded reply


class CommentEditRequest(BaseModel):
    text: str


class TaskRequest(BaseModel):
    label: str
    assignee: Optional[str] = None
    assignee_name: Optional[str] = None


class TaskUpdateRequest(BaseModel):
    done: Optional[bool] = None
    set_assignee: bool = False                 # True → (re)assign this task
    assignee: Optional[str] = None
    assignee_name: Optional[str] = None


class LockRequest(BaseModel):
    resource: str = "notes"                    # which sub-resource is being edited


class ApprovalRequest(BaseModel):
    note: Optional[str] = None


# ── Pure logic ────────────────────────────────────────────────────────────────
def compute_priority(risk: int, n_accounts: int, fraud_confidence: float) -> str:
    score = risk
    if n_accounts >= 5:
        score += 5
    if n_accounts >= 8:
        score += 3
    if fraud_confidence >= 0.85:
        score += 6
    if score >= 85:
        return "Critical"
    if score >= 68:
        return "High"
    if score >= 45:
        return "Medium"
    return "Low"


def pick_category(flags: List[str], risk: int) -> str:
    f = " ".join(flags).lower()
    if "cash-intensive" in f or "round-number" in f:
        return "Money Mule Network"
    if "high-velocity" in f or "night-time" in f:
        return "Rapid Fund Movement"
    if "cross-border" in f:
        return "Layering Activity"
    if "new beneficiary" in f:
        return "Account Takeover"
    if "dormant-then-active" in f:
        return "Suspicious Account Ring"
    return "High-Risk Network" if risk >= 70 else "Suspicious Transaction Chain"


def generate_title(category: str) -> str:
    return CATEGORY_TITLES.get(category, "Fraud Investigation")


def fraud_confidence_for(risk: int) -> float:
    return round(min(0.99, risk / 100 + 0.02), 2)


def detection_reason_for(category: str, flags: List[str]) -> str:
    base = {
        "Money Mule Network": "Funnel pattern: many inbound transfers consolidated then withdrawn as cash.",
        "Circular Transactions": "Closed-loop fund movement detected across linked accounts.",
        "Account Takeover": "Sudden change in behaviour with surge of new beneficiaries.",
        "Layering Activity": "Multi-hop layering with cross-border exposure obscuring fund origin.",
        "High-Risk Network": "Dense high-risk sub-network with elevated aggregate risk score.",
        "Suspicious Transaction Chain": "Chain of related transactions exceeding velocity thresholds.",
        "Rapid Fund Movement": "Rapid in-and-out movement of funds within short time windows.",
        "Suspicious Account Ring": "Dormant accounts reactivated in a coordinated ring.",
        "Linked Fraud Network": "Account linked to a previously flagged fraud network.",
    }.get(category, "Automated risk model flagged anomalous activity.")
    if flags:
        base += " Indicators: " + ", ".join(flags[:4]) + "."
    return base


def evidence_hash(reference: str) -> str:
    return "0x" + hashlib.sha256(reference.encode()).hexdigest()


def generate_ub_analysis(case: dict) -> str:
    cat = case.get("category", "")
    risk = case.get("risk_score", 0)
    n_acc = len(case.get("accounts", []))
    n_txn = len(case.get("transactions", []))
    conf = int(case.get("fraud_confidence", 0) * 100)
    pr = case.get("priority", "Medium")
    lead = case.get("accounts", ["—"])[0]
    return (
        f"UB assessment: this case presents a {cat.lower()} pattern centred on account "
        f"{lead}, spanning {n_acc} linked account(s) and {n_txn} flagged transaction(s). "
        f"The network risk score of {risk}/100 (fraud confidence {conf}%) places it at "
        f"{pr} priority. The dominant signal is consistent with {cat.lower()}; recommended "
        f"next steps are to (1) freeze high-exposure beneficiary accounts, (2) request KYC "
        f"and device evidence, and (3) anchor the current graph snapshot to the evidence "
        f"ledger before funds disperse. Escalate to a supervisor if confidence exceeds 90%."
    )
