"""
/api/v1/cases — thin router: auth on every route, cursor pagination, read-audit.
Delegates all storage to repositories.case_repo (json or db mode).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from core.security.deps import current_user, pagination, Page
from core.security import audit
from repositories import case_repo

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("")
async def list_cases(
    request: Request,
    page: Page = Depends(pagination),
    status: Optional[str] = Query(None),
    user: dict = Depends(current_user),
):
    items = await case_repo.list_cases(page.limit, page.offset, status)
    await audit.record(user.get("sub") or user.get("employee_id", "?"),
                       "list_cases", target_ref=status, ip=request.client.host if request.client else None)
    return {
        "items": items,
        "next_cursor": page.next_cursor(len(items)),
        "limit": page.limit,
    }


@router.get("/{case_id}")
async def get_case(case_id: str, request: Request, user: dict = Depends(current_user)):
    case = await case_repo.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    await audit.record(user.get("sub") or user.get("employee_id", "?"),
                       "view_case", target_ref=case_id,
                       ip=request.client.host if request.client else None)
    return case
