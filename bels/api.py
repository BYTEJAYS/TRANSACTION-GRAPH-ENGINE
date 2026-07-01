"""
BELS FastAPI router — all evidence, blockchain, custody, case, report and UB endpoints.

The router carries no prefix so the standalone app exposes the exact paths from the
spec (POST /evidence/upload, ...). When mounted into the main TGIE backend it can be
included under config.API_PREFIX (/bels).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from . import config
from .models import (CaseCreateRequest, CustodyUpdateRequest, EvidenceType,
                     RegisterRequest, UBQueryRequest, VerifyByHashRequest)
from .reporting import reporter
from .security import AccessDenied, audit_log, require
from .service import service
from .ub_integration import forensic_intelligence

router = APIRouter(tags=["BELS"])


def _guard(role: str, action: str) -> None:
    try:
        require(role, action)
    except AccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc))


# ── Evidence ─────────────────────────────────────────────────────────────────────
@router.post("/evidence/upload")
async def upload_evidence(
    file: UploadFile = File(...),
    case_id: str = Form(...),
    owner: str = Form("system"),
    role: str = Form("investigator"),
    evidence_type: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
):
    _guard(role, "upload")
    data = await file.read()
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {config.MAX_UPLOAD_MB} MB limit")
    import json
    meta = {}
    if metadata:
        try:
            meta = json.loads(metadata)
        except Exception:
            meta = {"note": metadata}
    etype = EvidenceType(evidence_type) if evidence_type else None
    rec = service.upload_evidence(file.filename or "artifact.bin", data, case_id,
                                  owner=owner, role=role, evidence_type=etype, metadata=meta)
    return rec.model_dump()


@router.post("/evidence/register")
async def register_evidence(req: RegisterRequest):
    _guard(req.role, "register")
    rec = service.register_hash(req.file_hash, req.case_id, req.filename,
                                req.evidence_type, req.owner, req.role, req.metadata)
    return rec.model_dump()


@router.post("/evidence/verify")
async def verify_evidence(
    evidence_id: str = Form(...),
    file: Optional[UploadFile] = File(None),
    actor: str = Form("system"),
    role: str = Form("auditor"),
):
    _guard(role, "verify")
    data = await file.read() if file is not None else None
    result = service.verify(evidence_id, uploaded=data, actor=actor, role=role)
    return result.model_dump()


@router.post("/evidence/verify-hash")
async def verify_evidence_hash(req: VerifyByHashRequest):
    _guard(req.role, "verify")
    result = service.verify(req.evidence_id, provided_hash=req.file_hash,
                            actor=req.actor, role=req.role)
    return result.model_dump()


@router.get("/evidence")
async def list_evidence():
    return [r.model_dump() for r in service.list_evidence()]


@router.get("/evidence/{evidence_id}")
async def get_evidence(evidence_id: str):
    rec = service.get_evidence(evidence_id)
    if rec is None:
        raise HTTPException(404, "evidence not found")
    return rec.model_dump()


@router.get("/evidence/{evidence_id}/certificate")
async def get_certificate(evidence_id: str):
    cert = service.certificate(evidence_id)
    if not cert:
        raise HTTPException(404, "evidence not found")
    return cert


@router.get("/evidence/audit/{evidence_id}")
async def get_audit(evidence_id: str):
    return service.get_audit(evidence_id)


@router.get("/evidence/custody/{evidence_id}")
async def get_custody(evidence_id: str):
    return service.get_custody(evidence_id)


@router.post("/evidence/custody/{evidence_id}")
async def add_custody(evidence_id: str, req: CustodyUpdateRequest):
    _guard(req.role, req.action.value.lower() if req.action.value.lower() in
           {"export", "transfer", "archive"} else "read")
    return service.record_custody(evidence_id, req.action, req.actor, req.role, req.detail)


# ── Blockchain ───────────────────────────────────────────────────────────────────
@router.get("/blockchain/status")
async def blockchain_status():
    return {**service.blockchain_status(), "integrity": service.chain_integrity()}


@router.get("/blockchain/transaction/{txid}")
async def blockchain_transaction(txid: str):
    tx = service.provider.get_transaction(txid)
    if tx is None:
        raise HTTPException(404, "transaction not found")
    return tx


@router.get("/blockchain/integrity")
async def blockchain_integrity():
    return service.chain_integrity()


# ── Cases ────────────────────────────────────────────────────────────────────────
@router.post("/cases")
async def create_case(req: CaseCreateRequest):
    _guard(req.role, "register")
    return service.create_case(req.title, req.description, req.owner)


@router.get("/cases")
async def list_cases():
    return service.list_cases()


@router.get("/cases/{case_id}")
async def get_case(case_id: str):
    case = service.get_case(case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    # serialise nested pydantic evidence records
    case = {**case, "evidence": [e.model_dump() if hasattr(e, "model_dump") else e
                                 for e in case.get("evidence", []) if e]}
    return case


# ── Reports ──────────────────────────────────────────────────────────────────────
_REPORT_BUILDERS = {
    "evidence_verification": lambda eid, cid: reporter.evidence_verification(eid),
    "chain_of_custody":      lambda eid, cid: reporter.chain_of_custody(eid),
    "case_timeline":         lambda eid, cid: reporter.case_timeline(cid),
    "blockchain_audit":      lambda eid, cid: reporter.blockchain_audit(),
    "integrity_verification": lambda eid, cid: reporter.integrity_verification(),
}


@router.get("/reports/{report_type}")
async def generate_report(report_type: str, evidence_id: str = "", case_id: str = "",
                          fmt: str = "json"):
    builder = _REPORT_BUILDERS.get(report_type)
    if builder is None:
        raise HTTPException(404, f"unknown report type. options: {list(_REPORT_BUILDERS)}")
    if fmt not in ("json", "csv", "pdf"):
        raise HTTPException(400, "fmt must be json|csv|pdf")
    report = builder(evidence_id, case_id)
    if fmt == "json":
        return JSONResponse(report)
    data = reporter.to_csv(report) if fmt == "csv" else reporter.to_pdf(report)
    media = "text/csv" if fmt == "csv" else "application/pdf"
    name = f"{report_type}_{evidence_id or case_id or 'all'}.{fmt}"
    return Response(content=data, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ── UB forensic intelligence ──────────────────────────────────────────────────────
@router.post("/ub/ask")
async def ub_ask(req: UBQueryRequest):
    return forensic_intelligence.answer(req.question)


# ── Operational audit + demo ──────────────────────────────────────────────────────
@router.get("/audit-log")
async def operational_audit(limit: int = 200):
    return audit_log.tail(limit)


@router.post("/demo/run")
async def demo_run():
    from .demo import run_demo
    return run_demo()


@router.get("/health")
async def health():
    return {"status": "ok", "service": "BELS", "provider": service.provider.name}
