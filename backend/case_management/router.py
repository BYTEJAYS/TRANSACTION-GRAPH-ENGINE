"""
Case Management API — all routes under /api/cases (rides the existing /api proxy).
Authentication is reused from the investigator auth module.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response

from auth.router import require_auth
from auth.store import store as inv_store
from .models import (
    AssignRequest,
    CloseRequest,
    CreateCaseRequest,
    EvidenceRequest,
    GraphSnapshotRequest,
    NoteRequest,
    UpdateCaseRequest,
    ParticipantRequest,
    HandoverRequest,
    CommentRequest,
    CommentEditRequest,
    TaskRequest,
    TaskUpdateRequest,
    LockRequest,
    ApprovalRequest,
    CATEGORIES,
    PRIORITIES,
    STATUSES,
)
from . import collab
from .store import store

import logging

logger = logging.getLogger("tgie.cases")

# python-multipart is required by Starlette/FastAPI to parse multipart/form-data,
# which only the evidence FILE-UPLOAD endpoint uses. It is an OPTIONAL capability:
# if the package is absent we must STILL expose the entire rest of the case API
# (list, detail, create, notes, assign, close, blockchain, search, …). Previously a
# missing python-multipart made `include_router` raise, which main.py's fail-safe
# swallowed — taking the WHOLE Investigations module offline (every /api/cases call
# 404'd) even though cases were being written to disk. So we probe for it here and
# register the upload route conditionally; the core API can never be held hostage
# by one optional sub-feature again.
try:
    import multipart as _multipart  # noqa: F401  (import name of python-multipart)
    _HAS_MULTIPART = True
except Exception:  # pragma: no cover
    _HAS_MULTIPART = False

router = APIRouter(tags=["Cases"])


def _actor(ctx: dict) -> tuple[str, str]:
    u = ctx["user"]
    return u["investigator_id"], u["name"]


def _cap(ctx: dict, capability: str) -> None:
    """Raise 403 unless the caller's role grants the capability (RBAC gate)."""
    role = ctx["user"].get("role")
    if not collab.can(role, capability):
        raise HTTPException(403, f"Your role ({role}) lacks permission for this action ({capability}).")


async def _emit(case_id: str, event: str, payload: Optional[dict] = None) -> None:
    """Best-effort real-time push to everyone subscribed to this case's WS room.
    Never raises — collaboration features must not depend on a live socket."""
    try:
        from main import app_state
        b = app_state.get("broadcaster")
        if b:
            await b.broadcast_case_event((case_id or "").upper(), event, payload or {})
    except Exception:
        pass


# ── collection ────────────────────────────────────────────────────────────────
@router.get("/api/cases")
async def list_cases(
    scope: Optional[str] = Query(None, description="open | closed | critical | assigned"),
    status: Optional[str] = None,
    priority: Optional[str] = None,
    ctx: dict = Depends(require_auth),
):
    assigned = ctx["user"]["investigator_id"] if scope == "assigned" else None
    real_scope = None if scope == "assigned" else scope
    return {
        "cases": store.list(scope=real_scope, status=status, priority=priority, assigned_to=assigned),
        "meta": {"statuses": STATUSES, "priorities": PRIORITIES, "categories": CATEGORIES},
    }


@router.get("/api/cases/stats")
async def case_stats(ctx: dict = Depends(require_auth)):
    return store.stats(me=ctx["user"]["investigator_id"])


@router.get("/api/cases/notifications")
async def case_notifications(ctx: dict = Depends(require_auth)):
    return {"notifications": store.notifications(limit=12)}


@router.get("/api/cases/by-account/{account_number}")
async def cases_by_account(account_number: str, ctx: dict = Depends(require_auth)):
    return {"account_number": account_number, "cases": store.by_account(account_number)}


@router.get("/api/cases/search")
async def search_cases(q: str = Query("", description="case id / account / txn / evidence / hash / investigator / pattern / status"),
                       ctx: dict = Depends(require_auth)):
    return {"query": q, "results": store.search(q)}


@router.post("/api/cases/create", status_code=201)
async def create_case(body: CreateCaseRequest, ctx: dict = Depends(require_auth)):
    _, name = _actor(ctx)
    account = None
    if body.account_number:
        from auth.accounts_db import registry
        resolved = registry.resolve(body.account_number)
        account = registry.get(resolved) if resolved else None
        if not account:
            raise HTTPException(404, f"Account '{body.account_number}' not found")
    case = store.create(
        account=account, category=body.category, title=body.title,
        risk_score=body.risk_score, detection_reason=body.detection_reason,
        accounts=body.accounts, priority=body.priority, actor=name,
    )
    return case


# ── single case ───────────────────────────────────────────────────────────────
@router.get("/api/cases/{case_id}")
async def get_case(case_id: str, ctx: dict = Depends(require_auth)):
    c = store.get(case_id)
    if not c:
        raise HTTPException(404, f"Case '{case_id}' not found")
    return c


@router.put("/api/cases/{case_id}")
async def update_case(case_id: str, body: UpdateCaseRequest, ctx: dict = Depends(require_auth)):
    _, name = _actor(ctx)
    c = store.update(case_id, actor=name, status=body.status, priority=body.priority,
                     title=body.title, risk_score=body.risk_score)
    if not c:
        raise HTTPException(404, f"Case '{case_id}' not found")
    await _emit(case_id, "case_updated", {"status": c.get("status"), "priority": c.get("priority"), "by": name})
    return c


@router.post("/api/cases/{case_id}/notes", status_code=201)
async def add_note(case_id: str, body: NoteRequest, ctx: dict = Depends(require_auth)):
    uid, name = _actor(ctx)
    if not body.text.strip():
        raise HTTPException(400, "Note text is required")
    c = store.add_note(case_id, text=body.text, author=uid, author_name=name)
    if not c:
        raise HTTPException(404, f"Case '{case_id}' not found")
    await _emit(case_id, "note_added", {"author": name})
    return c


@router.post("/api/cases/{case_id}/evidence", status_code=201)
async def add_evidence(case_id: str, body: EvidenceRequest, ctx: dict = Depends(require_auth)):
    _, name = _actor(ctx)
    c = store.add_evidence(case_id, ev_type=body.type, description=body.description or "",
                           reference=body.reference or "", actor=name)
    if not c:
        raise HTTPException(404, f"Case '{case_id}' not found")
    return c


# ── evidence files (real upload / download) ─────────────────────────────────────
_MAX_UPLOAD_MB = 50


if _HAS_MULTIPART:
    @router.post("/api/cases/{case_id}/evidence/upload", status_code=201)
    async def upload_evidence_file(
        case_id: str,
        file: UploadFile = File(...),
        type: str = Form(""),
        remarks: str = Form(""),
        ctx: dict = Depends(require_auth),
    ):
        _, name = _actor(ctx)
        data = await file.read()
        if len(data) > _MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(413, f"File exceeds {_MAX_UPLOAD_MB} MB limit")
        if not data:
            raise HTTPException(400, "Empty file")
        c = store.add_evidence_file(case_id, filename=file.filename or "artifact.bin",
                                    data=data, ev_type=type, remarks=remarks, actor=name)
        if not c:
            raise HTTPException(404, f"Case '{case_id}' not found")
        return c
else:  # pragma: no cover - degraded mode when python-multipart is absent
    # Register a NON-multipart stub at the same path so the route still EXISTS
    # (returns a clear 503 instead of a confusing 404) while leaving every other
    # case route fully operational. Installing python-multipart + restarting
    # transparently restores real uploads.
    logger.warning(
        "python-multipart not installed — evidence FILE-UPLOAD runs in degraded "
        "mode (HTTP 503 on POST /api/cases/{id}/evidence/upload). Every other case "
        "route is fully active. `pip install python-multipart` to enable uploads."
    )

    @router.post("/api/cases/{case_id}/evidence/upload", status_code=503)
    async def upload_evidence_file_unavailable(case_id: str, ctx: dict = Depends(require_auth)):
        raise HTTPException(
            503,
            "Evidence file upload is unavailable: the server is missing the "
            "'python-multipart' package. All other case features work normally. "
            "Run `pip install python-multipart` and restart the backend to enable it.",
        )


@router.get("/api/cases/{case_id}/evidence/{evidence_id}/download")
async def download_evidence_file(case_id: str, evidence_id: str, ctx: dict = Depends(require_auth)):
    found = store.evidence_file(case_id, evidence_id)
    if not found:
        raise HTTPException(404, "Evidence file not found")
    path, dl_name = found
    return FileResponse(path, filename=dl_name, media_type="application/octet-stream")


# ── verbatim graph snapshot ─────────────────────────────────────────────────────
@router.post("/api/cases/{case_id}/graph-snapshot", status_code=201)
async def save_graph_snapshot(case_id: str, body: GraphSnapshotRequest, ctx: dict = Depends(require_auth)):
    _, name = _actor(ctx)
    c = store.set_graph_snapshot(case_id, nodes=body.nodes, edges=body.edges,
                                 camera=body.camera, indicators=body.indicators, actor=name)
    if not c:
        raise HTTPException(404, f"Case '{case_id}' not found")
    return c


# ── case bundle (ZIP of everything) ─────────────────────────────────────────────
@router.get("/api/cases/{case_id}/bundle")
async def download_case_bundle(case_id: str, ctx: dict = Depends(require_auth)):
    data = store.bundle_zip(case_id)
    if data is None:
        raise HTTPException(404, f"Case '{case_id}' not found")
    return Response(
        content=data, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{case_id.upper()}-case-bundle.zip"'},
    )


# ── blockchain (live BELS anchor / verify / receipt) ────────────────────────────
@router.post("/api/cases/{case_id}/blockchain/anchor")
async def anchor_case(case_id: str, ctx: dict = Depends(require_auth)):
    _, name = _actor(ctx)
    c = store.anchor_blockchain(case_id, actor=name)
    if not c:
        raise HTTPException(404, f"Case '{case_id}' not found")
    return c


@router.get("/api/cases/{case_id}/blockchain/verify")
async def verify_case_anchor(case_id: str, ctx: dict = Depends(require_auth)):
    _, name = _actor(ctx)
    result = store.verify_blockchain(case_id, actor=name)
    if result is None:
        raise HTTPException(404, f"Case '{case_id}' not found")
    return result


@router.get("/api/cases/{case_id}/blockchain/receipt")
async def download_blockchain_receipt(case_id: str, ctx: dict = Depends(require_auth)):
    c = store.get(case_id)
    if not c:
        raise HTTPException(404, f"Case '{case_id}' not found")
    bc = c.get("blockchain") or {}
    if not bc.get("anchored_at"):
        raise HTTPException(400, "Case has not been anchored to the blockchain yet")
    import json as _json
    receipt = _json.dumps({"case_id": c["case_id"], **bc}, indent=2, default=str).encode()
    return Response(
        content=receipt, media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{case_id.upper()}-blockchain-receipt.json"'},
    )


@router.post("/api/cases/{case_id}/assign")
async def assign_case(case_id: str, body: AssignRequest, ctx: dict = Depends(require_auth)):
    uid, name = _actor(ctx)
    inv_id = body.investigator_id or uid
    # Assigning the case to ANYONE but yourself is a manager action; assigning it
    # to yourself is a self-claim that every investigator may do.
    if inv_id != uid:
        _cap(ctx, collab.CAP_ASSIGN_OTHERS)
    profile = inv_store.public_profile(inv_id)
    inv_name = profile["name"] if profile else inv_id
    c = store.assign(case_id, investigator_id=inv_id, investigator_name=inv_name,
                     supervisor=body.supervisor, department=body.department,
                     due_date=body.due_date, actor=name)
    if not c:
        raise HTTPException(404, f"Case '{case_id}' not found")
    await _emit(case_id, "case_assigned", {"assigned_to": inv_id, "assigned_name": inv_name, "by": name})
    return c


@router.post("/api/cases/{case_id}/close")
async def close_case(case_id: str, body: CloseRequest, ctx: dict = Depends(require_auth)):
    _, name = _actor(ctx)
    c = store.close(case_id, resolution=body.resolution, summary=body.summary, actor=name)
    if not c:
        raise HTTPException(404, f"Case '{case_id}' not found")
    await _emit(case_id, "case_closed", {"status": c.get("status"), "by": name})
    return c


@router.get("/api/cases/{case_id}/timeline")
async def case_timeline(case_id: str, ctx: dict = Depends(require_auth)):
    c = store.get(case_id)
    if not c:
        raise HTTPException(404, f"Case '{case_id}' not found")
    return {"case_id": c["case_id"], "timeline": c["timeline"]}


# ══════════════════════════════════════════════════════════════════════════════
#  COLLABORATION ENDPOINTS  (multi-investigator: claim / participants / handover,
#  comments, tasks, locks, per-investigator + ops dashboards). Every mutation is
#  RBAC-gated and broadcasts a real-time event to the case's WS room.
#  NOTE: the literal collection paths below (/me, /my, /ops) have MORE segments
#  than /api/cases/{case_id}, so they are never shadowed by it.
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/api/cases/me/capabilities")
async def my_capabilities(ctx: dict = Depends(require_auth)):
    role = ctx["user"].get("role")
    return {"role": role, "tier": collab.normalize_role(role),
            "capabilities": collab.capabilities_for(role)}


@router.get("/api/cases/my/dashboard")
async def my_dashboard(ctx: dict = Depends(require_auth)):
    uid, name = _actor(ctx)
    return store.my_dashboard(uid, name)


@router.get("/api/cases/ops/metrics")
async def ops_metrics(ctx: dict = Depends(require_auth)):
    _cap(ctx, collab.CAP_OPS)
    return store.ops_metrics()


@router.get("/api/cases/ops/workload")
async def ops_workload(ctx: dict = Depends(require_auth)):
    _cap(ctx, collab.CAP_OPS)
    return store.workload()


# ── per-case collaboration reads ──────────────────────────────────────────────
@router.get("/api/cases/{case_id}/participants")
async def list_participants(case_id: str, ctx: dict = Depends(require_auth)):
    c = store.get(case_id)
    if not c:
        raise HTTPException(404, f"Case '{case_id}' not found")
    return {"case_id": c["case_id"], "participants": c.get("participants", [])}


@router.get("/api/cases/{case_id}/comments")
async def list_comments(case_id: str, include_archived: bool = Query(True),
                        ctx: dict = Depends(require_auth)):
    c = store.get(case_id)
    if not c:
        raise HTTPException(404, f"Case '{case_id}' not found")
    items = c.get("comments", [])
    if not include_archived:
        items = [cm for cm in items if not cm.get("archived")]
    return {"case_id": c["case_id"], "comments": items}


@router.get("/api/cases/{case_id}/tasks")
async def list_tasks(case_id: str, ctx: dict = Depends(require_auth)):
    c = store.get(case_id)
    if not c:
        raise HTTPException(404, f"Case '{case_id}' not found")
    tasks = c.get("tasks", [])
    return {"case_id": c["case_id"], "tasks": tasks,
            "completed": sum(1 for t in tasks if t.get("done")), "total": len(tasks)}


@router.get("/api/cases/{case_id}/activity")
async def case_activity(case_id: str, ctx: dict = Depends(require_auth)):
    c = store.get(case_id)
    if not c:
        raise HTTPException(404, f"Case '{case_id}' not found")
    return {"case_id": c["case_id"], "activity": c.get("timeline", [])}


# ── assignment workflow: claim / participants / handover / approval ───────────
@router.post("/api/cases/{case_id}/claim")
async def claim_case(case_id: str, ctx: dict = Depends(require_auth)):
    _cap(ctx, collab.CAP_CLAIM)
    uid, name = _actor(ctx)
    c = store.claim(case_id, investigator_id=uid, name=name, role=ctx["user"].get("role"))
    if c is None:
        raise HTTPException(404, f"Case '{case_id}' not found")
    if c.get("_error") == "conflict":
        raise HTTPException(409, f"Case already claimed by {c.get('assigned_name') or c.get('assigned_to')}.")
    await _emit(case_id, "case_claimed", {"by": name, "investigator_id": uid})
    return c


@router.post("/api/cases/{case_id}/participants", status_code=201)
async def add_case_participant(case_id: str, body: ParticipantRequest, ctx: dict = Depends(require_auth)):
    _cap(ctx, collab.CAP_COMMENT)   # any active investigator can pull in a colleague
    _, name = _actor(ctx)
    pname = body.name
    if not pname:
        prof = inv_store.public_profile(body.investigator_id)
        pname = prof["name"] if prof else body.investigator_id
    c = store.add_participant(case_id, investigator_id=body.investigator_id, name=pname,
                              role_on_case=body.role_on_case, actor=name)
    if not c:
        raise HTTPException(404, f"Case '{case_id}' not found")
    await _emit(case_id, "participant_added",
                {"investigator_id": body.investigator_id, "name": pname, "role": body.role_on_case})
    return c


@router.delete("/api/cases/{case_id}/participants/{investigator_id}")
async def remove_case_participant(case_id: str, investigator_id: str, ctx: dict = Depends(require_auth)):
    uid, name = _actor(ctx)
    if investigator_id != uid:                 # removing others requires manager rights
        _cap(ctx, collab.CAP_ASSIGN_OTHERS)
    c = store.remove_participant(case_id, investigator_id=investigator_id, actor=name)
    if c is None:
        raise HTTPException(404, f"Case '{case_id}' not found")
    if isinstance(c, dict) and c.get("_error") == "is_primary":
        raise HTTPException(409, "Cannot remove the primary investigator — hand the case over first.")
    await _emit(case_id, "participant_removed", {"investigator_id": investigator_id})
    return c


@router.post("/api/cases/{case_id}/handover")
async def handover_case(case_id: str, body: HandoverRequest, ctx: dict = Depends(require_auth)):
    _cap(ctx, collab.CAP_HANDOVER)
    uid, name = _actor(ctx)
    cur = store.get(case_id)
    if not cur:
        raise HTTPException(404, f"Case '{case_id}' not found")
    # only the current owner or a manager may hand a case over
    if cur.get("assigned_to") not in (uid, None) and not collab.can(ctx["user"].get("role"), collab.CAP_REASSIGN):
        raise HTTPException(403, "Only the current owner or a manager can hand this case over.")
    to_name = body.to_name
    if not to_name:
        prof = inv_store.public_profile(body.to_investigator_id)
        to_name = prof["name"] if prof else body.to_investigator_id
    c = store.handover(case_id, to_id=body.to_investigator_id, to_name=to_name, actor=name, note=body.note)
    if not c:
        raise HTTPException(404, f"Case '{case_id}' not found")
    await _emit(case_id, "case_handover", {"to": body.to_investigator_id, "to_name": to_name, "by": name})
    return c


@router.post("/api/cases/{case_id}/request-approval")
async def request_case_approval(case_id: str, body: ApprovalRequest, ctx: dict = Depends(require_auth)):
    _cap(ctx, collab.CAP_COMMENT)
    _, name = _actor(ctx)
    c = store.request_approval(case_id, actor=name, note=body.note)
    if not c:
        raise HTTPException(404, f"Case '{case_id}' not found")
    await _emit(case_id, "approval_requested", {"by": name})
    return c


# ── comments (immutable: edit keeps history, delete = archive) ────────────────
@router.post("/api/cases/{case_id}/comments", status_code=201)
async def add_case_comment(case_id: str, body: CommentRequest, ctx: dict = Depends(require_auth)):
    _cap(ctx, collab.CAP_COMMENT)
    uid, name = _actor(ctx)
    if not body.text.strip():
        raise HTTPException(400, "Comment text is required")
    c = store.add_comment(case_id, author=uid, author_name=name, text=body.text, parent_id=body.parent_id)
    if not c:
        raise HTTPException(404, f"Case '{case_id}' not found")
    await _emit(case_id, "comment_added", {"author": name})
    return c


@router.put("/api/cases/{case_id}/comments/{comment_id}")
async def edit_case_comment(case_id: str, comment_id: str, body: CommentEditRequest,
                            ctx: dict = Depends(require_auth)):
    _cap(ctx, collab.CAP_COMMENT)
    uid, name = _actor(ctx)
    cur = store.get(case_id)
    if not cur:
        raise HTTPException(404, f"Case '{case_id}' not found")
    cm = next((x for x in cur.get("comments", []) if x["id"] == comment_id), None)
    if cm and cm["author"] != uid and not collab.can(ctx["user"].get("role"), collab.CAP_APPROVE):
        raise HTTPException(403, "Only the comment author or a manager can edit it.")
    c = store.edit_comment(case_id, comment_id, text=body.text, editor_name=name)
    if c is None:
        raise HTTPException(404, f"Case '{case_id}' not found")
    if isinstance(c, dict) and c.get("_error"):
        raise HTTPException(409 if c["_error"] == "archived" else 404, f"Comment {c['_error']}")
    await _emit(case_id, "comment_edited", {"comment_id": comment_id})
    return c


@router.post("/api/cases/{case_id}/comments/{comment_id}/archive")
async def archive_case_comment(case_id: str, comment_id: str, ctx: dict = Depends(require_auth)):
    _cap(ctx, collab.CAP_COMMENT)
    uid, name = _actor(ctx)
    cur = store.get(case_id)
    if not cur:
        raise HTTPException(404, f"Case '{case_id}' not found")
    cm = next((x for x in cur.get("comments", []) if x["id"] == comment_id), None)
    if cm and cm["author"] != uid and not collab.can(ctx["user"].get("role"), collab.CAP_APPROVE):
        raise HTTPException(403, "Only the comment author or a manager can archive it.")
    c = store.archive_comment(case_id, comment_id, actor=name)
    if c is None or (isinstance(c, dict) and c.get("_error")):
        raise HTTPException(404, "Comment not found")
    await _emit(case_id, "comment_archived", {"comment_id": comment_id})
    return c


# ── tasks / checklist ─────────────────────────────────────────────────────────
@router.post("/api/cases/{case_id}/tasks", status_code=201)
async def add_case_task(case_id: str, body: TaskRequest, ctx: dict = Depends(require_auth)):
    _cap(ctx, collab.CAP_TASK)
    _, name = _actor(ctx)
    aname = body.assignee_name
    if body.assignee and not aname:
        prof = inv_store.public_profile(body.assignee)
        aname = prof["name"] if prof else body.assignee
    c = store.add_task(case_id, label=body.label, actor=name, assignee=body.assignee, assignee_name=aname)
    if not c:
        raise HTTPException(404, f"Case '{case_id}' not found")
    await _emit(case_id, "task_added", {"label": body.label})
    return c


@router.put("/api/cases/{case_id}/tasks/{task_id}")
async def update_case_task(case_id: str, task_id: str, body: TaskUpdateRequest,
                           ctx: dict = Depends(require_auth)):
    _cap(ctx, collab.CAP_TASK)
    _, name = _actor(ctx)
    aname = body.assignee_name
    if body.set_assignee and body.assignee and not aname:
        prof = inv_store.public_profile(body.assignee)
        aname = prof["name"] if prof else body.assignee
    c = store.update_task(case_id, task_id, actor=name, done=body.done,
                          set_assignee=body.set_assignee, assignee=body.assignee, assignee_name=aname)
    if c is None:
        raise HTTPException(404, f"Case '{case_id}' not found")
    if isinstance(c, dict) and c.get("_error"):
        raise HTTPException(404, "Task not found")
    await _emit(case_id, "task_updated", {"task_id": task_id, "done": body.done})
    return c


# ── editing locks (prevent silent overwrite) ──────────────────────────────────
@router.post("/api/cases/{case_id}/lock")
async def acquire_case_lock(case_id: str, body: LockRequest, ctx: dict = Depends(require_auth)):
    _cap(ctx, collab.CAP_COMMENT)
    uid, name = _actor(ctx)
    r = store.set_lock(case_id, resource=body.resource, holder_id=uid, holder_name=name)
    if r is None:
        raise HTTPException(404, f"Case '{case_id}' not found")
    if r.get("_error") == "locked":
        raise HTTPException(423, f"'{body.resource}' is being edited by {r.get('holder_name')}.")
    await _emit(case_id, "lock_acquired", {"resource": body.resource, "holder_name": name})
    return r


@router.delete("/api/cases/{case_id}/lock")
async def release_case_lock(case_id: str, resource: str = Query("notes"),
                            ctx: dict = Depends(require_auth)):
    uid, name = _actor(ctx)
    r = store.release_lock(case_id, resource=resource, holder_id=uid)
    if r is None:
        raise HTTPException(404, f"Case '{case_id}' not found")
    await _emit(case_id, "lock_released", {"resource": resource})
    return r
