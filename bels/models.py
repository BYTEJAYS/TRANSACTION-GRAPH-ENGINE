"""Shared enums and Pydantic API schemas for BELS."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Enumerations ────────────────────────────────────────────────────────────────
class EvidenceType(str, Enum):
    PDF = "pdf"
    IMAGE = "image"
    SCREENSHOT = "screenshot"
    AUDIO = "audio"
    VIDEO = "video"
    LOG = "log"
    CSV = "csv"
    JSON = "json"
    TRANSACTION_RECORD = "transaction_record"
    REPORT = "report"
    OTHER = "other"


class EvidenceStatus(str, Enum):
    REGISTERED = "REGISTERED"
    VERIFIED = "VERIFIED"
    TAMPERED = "TAMPERED"
    ARCHIVED = "ARCHIVED"


class CustodyAction(str, Enum):
    UPLOAD = "UPLOAD"
    REGISTER = "REGISTER"
    REVIEW = "REVIEW"
    ACCESS = "ACCESS"
    VERIFY = "VERIFY"
    EXPORT = "EXPORT"
    TRANSFER = "TRANSFER"
    SHARE = "SHARE"
    ARCHIVE = "ARCHIVE"


class VerificationOutcome(str, Enum):
    VERIFIED = "VERIFIED"
    TAMPERED = "TAMPERED"
    MISSING = "MISSING"
    CORRUPTED = "CORRUPTED"


# ── API request/response schemas ────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    """Register an already-hashed artifact (no file upload — e.g. a TGIE alert)."""
    file_hash: str = Field(..., description="SHA-256 hex digest of the evidence")
    case_id: str
    filename: str = "external-artifact"
    evidence_type: EvidenceType = EvidenceType.OTHER
    owner: str = "system"
    role: str = "investigator"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CustodyUpdateRequest(BaseModel):
    action: CustodyAction
    actor: str
    role: str = "investigator"
    detail: str = ""


class VerifyByHashRequest(BaseModel):
    evidence_id: str
    file_hash: str
    actor: str = "system"
    role: str = "auditor"


class CaseCreateRequest(BaseModel):
    title: str
    description: str = ""
    owner: str = "system"
    role: str = "investigator"


class UBQueryRequest(BaseModel):
    question: str


class EvidenceRecordOut(BaseModel):
    evidence_id: str
    case_id: str
    filename: str
    evidence_type: str
    file_hash: str
    metadata_hash: str
    owner: str
    status: str
    size_bytes: int
    registered_at: str
    verification_count: int
    custody_event_count: int
    anchor_tx_id: str
    block_index: int
    block_hash: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VerifyResultOut(BaseModel):
    evidence_id: str
    outcome: VerificationOutcome
    on_chain_hash: Optional[str]
    computed_hash: Optional[str]
    chain_integrity_ok: bool
    message: str
    verified_at: str
    verification_tx_id: Optional[str] = None
