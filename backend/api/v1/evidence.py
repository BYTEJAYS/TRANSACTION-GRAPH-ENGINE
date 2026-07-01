"""
/api/v1/evidence — server-side, hash-anchored evidence packages (Phase 8).
Auth on every route; build/download/verify write an AuditEntry (chain-of-custody).
Legacy /api/evidence/generate stays mounted separately.
"""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from core.security.deps import current_user
from core.security import audit
from evidence import packager, anchor, fiu

router = APIRouter(prefix="/evidence", tags=["evidence"])


def _actor(user: dict) -> str:
    return user.get("sub") or user.get("investigator_id") or user.get("employee_id", "?")


@router.post("/build/{case_id}")
async def build(case_id: str, request: Request, user: dict = Depends(current_user)):
    pkg = packager.build_package(case_id, actor=_actor(user))
    if pkg is None:
        raise HTTPException(status_code=404, detail="case not found")
    anchor.anchor_package(pkg)
    json_path = packager.render_json(pkg)
    pdf_path = packager.render_pdf(pkg)
    await audit.record(_actor(user), "build_evidence", target_ref=case_id,
                       ip=request.client.host if request.client else None)
    return {
        "package_id": pkg["package_id"],
        "sha256": pkg["integrity"]["sha256"],
        "anchor": pkg["integrity"]["anchor"],
        "sections": list(pkg["sections"].keys()),
        "artifacts": {"json": os.path.basename(json_path),
                      "pdf": os.path.basename(pdf_path) if pdf_path else None},
    }


def _load(pkg_id: str) -> dict:
    path = os.path.join(packager._STORAGE, f"{pkg_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="package not found (build it first)")
    with open(path) as f:
        return json.load(f)


@router.get("/download/{pkg_id}.json")
async def download_json(pkg_id: str, request: Request, user: dict = Depends(current_user)):
    await audit.record(_actor(user), "download_evidence_json", target_ref=pkg_id,
                       ip=request.client.host if request.client else None)
    return JSONResponse(_load(pkg_id))


@router.get("/download/{pkg_id}.pdf")
async def download_pdf(pkg_id: str, user: dict = Depends(current_user)):
    path = os.path.join(packager._STORAGE, f"{pkg_id}.pdf")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(path, media_type="application/pdf", filename=f"{pkg_id}.pdf")


@router.get("/fiu/{case_id}")
async def fiu_report(case_id: str, user: dict = Depends(current_user)):
    pkg = packager.build_package(case_id, actor=_actor(user))
    if pkg is None:
        raise HTTPException(status_code=404, detail="case not found")
    return fiu.build_str(pkg)


@router.get("/verify/{pkg_id}")
async def verify(pkg_id: str, user: dict = Depends(current_user)):
    return anchor.verify_package(_load(pkg_id))
