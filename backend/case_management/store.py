"""
Case store — in-memory + JSON persistence, mirroring auth/store.py.

On first run (no persisted file) the store auto-creates investigation cases from
the high-risk accounts already in the intelligence registry, so the platform
reflects the "detection → case" workflow with real, internally-consistent data.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import threading
import time
import uuid
import zipfile
from typing import Dict, List, Optional, Tuple

from . import collab
from .collab import ensure_collab_fields
from .enrich import enrich_case
from .models import (
    CLOSED_STATUSES,
    OPEN_STATUSES,
    PRIORITY_RANK,
    compute_priority,
    detection_reason_for,
    evidence_hash,
    fraud_confidence_for,
    generate_title,
    generate_ub_analysis,
    pick_category,
)

_DATA_FILE = os.getenv(
    "TGIE_CASE_STORE",
    os.path.join(os.path.dirname(__file__), "_data", "cases.json"),
)
# Uploaded evidence files live next to the case store: _data/evidence/<case>/<eid>__<name>
_EVIDENCE_DIR = os.getenv(
    "TGIE_EVIDENCE_DIR",
    os.path.join(os.path.dirname(_DATA_FILE), "evidence"),
)
_YEAR = 2026


def _cross_bank_summary(verdict: dict) -> Optional[dict]:
    """Compact cross-bank intelligence for the case (from the verdict's `cross_bank`
    block, attached by the risk pipeline). None when there is no cross-bank signal —
    so a single-bank case carries nothing extra. Metadata only."""
    cb = (verdict or {}).get("cross_bank") or {}
    if not cb.get("available"):
        return None
    return {
        "risk": cb.get("cross_bank_risk"),
        "band": cb.get("band"),
        "banks_involved": cb.get("banks_involved", []),
        "linked_banks": cb.get("linked_banks", 0),
        "linked_accounts": cb.get("linked_accounts", 0),
        "shared_devices": cb.get("shared_devices", 0),
        "shared_phones": cb.get("shared_phone_numbers", 0),
        "known_suspicious_entities": cb.get("known_suspicious_entities", 0),
        "patterns": cb.get("cross_bank_patterns", []),
    }

# Map a filename / declared type → a BELS EvidenceType enum value.
_EXT_TO_BELS = {
    "pdf": "pdf", "png": "image", "jpg": "image", "jpeg": "image", "gif": "image",
    "csv": "csv", "json": "json", "txt": "log", "log": "log", "docx": "report",
    "mp4": "video", "mov": "video", "avi": "video", "mp3": "audio", "wav": "audio",
    "zip": "other",
}


def _bels_type(filename: str, declared: str = "") -> str:
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    return _EXT_TO_BELS.get(ext, "other")


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> float:
    return time.time()


class CaseStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cases: Dict[str, dict] = {}
        self._seq = 0
        existed = self._load()
        # Only auto-seed on a genuine first run (no store file yet). An existing
        # but intentionally-empty file is respected — delete the file to re-seed.
        if not self._cases and not existed:
            self._seed()
        else:
            self._migrate()

    def _migrate(self) -> None:
        """One-off: bake analysis sections into cases saved before enrichment."""
        changed = False
        for c in self._cases.values():
            if "recovery" not in c or "account_roles" not in c:
                try:
                    enrich_case(c)
                    changed = True
                except Exception:
                    pass
            # Backfill collaboration containers (participants/comments/tasks/locks)
            # onto cases created before the collaboration layer existed.
            if ensure_collab_fields(c):
                changed = True
        if changed and not _SEEDING.get("active"):
            self._save()

    # ── persistence ──────────────────────────────────────────────────────────
    def _load(self) -> bool:
        try:
            with open(_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._cases = data.get("cases", {})
            self._seq = data.get("seq", len(self._cases))
            return True
        except Exception:
            self._cases, self._seq = {}, 0
            return False

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(_DATA_FILE), exist_ok=True)
            tmp = f"{_DATA_FILE}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"cases": self._cases, "seq": self._seq}, f, indent=2)
            os.replace(tmp, _DATA_FILE)
        except Exception:
            pass

    def _next_id(self) -> str:
        self._seq += 1
        return f"TGIE-{_YEAR}-{self._seq:04d}"

    # ── timeline / risk helpers ──────────────────────────────────────────────
    def _add_timeline(self, case: dict, event: str, actor: str, detail: str = "", ts: Optional[float] = None) -> None:
        case["timeline"].insert(0, {
            "id": uuid.uuid4().hex[:10],
            "ts": ts if ts is not None else _now(),
            "event": event,
            "actor": actor,
            "detail": detail,
        })

    # ── seeding from the account registry ────────────────────────────────────
    def _seed(self) -> None:
        try:
            from auth.accounts_db import registry
        except Exception:
            return
        # highest-risk accounts become system-detected cases
        accts = sorted(registry.accounts.values(), key=lambda a: a["risk_score"], reverse=True)
        seeded = [a for a in accts if a["risk_score"] >= 72][:8]
        status_map = {
            "Escalated": "Escalated",
            "Under Investigation": "Active Investigation",
            "Monitoring": "Under Review",
            "Open": "New",
            "Cleared": "Resolved",
        }
        for a in seeded:
            self.create_from_account(a, status=status_map.get(a["investigation_status"], "New"),
                                     actor="TGIE Detection Engine", seed=True)
        self._save()

    def create_from_account(self, acct: dict, status: str = "New",
                            actor: str = "TGIE Detection Engine", seed: bool = False) -> dict:
        risk = acct["risk_score"]
        flags = acct.get("flags", [])
        category = pick_category(flags, risk)
        accounts = [acct["account_number"]] + acct.get("linked_accounts", [])[:5]
        conf = fraud_confidence_for(risk)
        created = _now() - (86400 * (3 + risk % 9) if seed else 0)

        # flagged transactions from the account's recent activity
        txns = []
        for t in acct.get("recent_activity", [])[:6]:
            if t["direction"] == "debit" and t["amount"] >= 24000:
                txns.append({
                    "txn_id": t["txn_id"], "amount": t["amount"],
                    "date": created, "from_account": acct["account_number"],
                    "to_account": t["counterparty"], "rail": t["rail"],
                    "reason": "High-value outbound transfer flagged by velocity rule",
                })
        if not txns and acct.get("recent_activity"):
            t = acct["recent_activity"][0]
            txns.append({
                "txn_id": t["txn_id"], "amount": t["amount"], "date": created,
                "from_account": acct["account_number"], "to_account": t["counterparty"],
                "rail": t["rail"], "reason": "Anomalous transaction pattern",
            })

        # evidence (hashed; anchored flag carried from the registry)
        evidence = []
        for e in acct.get("evidence", []):
            evidence.append({
                "evidence_id": e["evidence_id"], "type": e["type"],
                "hash": evidence_hash(e["evidence_id"]),
                "anchored": e.get("anchored", False),
                "added_at": created, "added_by": actor,
            })

        # graph snapshot
        nodes = [{"id": acct["account_number"], "risk": risk, "role": "primary"}]
        for ln in acct.get("linked_accounts", [])[:6]:
            ln_rec = None
            try:
                from auth.accounts_db import registry
                ln_rec = registry.get(ln)
            except Exception:
                pass
            nodes.append({"id": ln, "risk": ln_rec["risk_score"] if ln_rec else 50, "role": "linked"})
        edges = [{"from": acct["account_number"], "to": ln} for ln in acct.get("linked_accounts", [])[:6]]

        case = {
            "case_id": self._next_id(),
            "title": generate_title(category),
            "category": category,
            "status": status,
            "priority": compute_priority(risk, len(accounts), conf),
            "risk_score": risk,
            "fraud_confidence": conf,
            "detection_reason": detection_reason_for(category, flags),
            "created_at": created,
            "updated_at": created,
            "assigned_to": None,
            "assigned_name": None,
            "supervisor": None,
            "department": None,
            "due_date": None,
            "accounts": accounts,
            "primary_account": acct["account_number"],
            "transactions": txns,
            "evidence": evidence,
            "notes": [],
            "timeline": [],
            "risk_history": [
                {"ts": created, "score": max(10, risk - 12), "reason": "Initial model score"},
                {"ts": created + 3600, "score": risk, "reason": "Re-scored after graph expansion"},
            ],
            "graph_snapshot": {"nodes": nodes, "edges": edges, "indicators": flags},
            "ub_analysis": "",
        }
        case["ub_analysis"] = generate_ub_analysis(case)
        self._add_timeline(case, "Case Created", actor, case["detection_reason"], ts=created)
        self._add_timeline(case, "Risk Score Updated", "TGIE Risk Engine", f"Network risk {risk}/100", ts=created + 3600)
        self._add_timeline(case, "UB Analysis Generated", "UB Cognitive Layer", "AI investigation summary produced", ts=created + 5400)
        if evidence:
            self._add_timeline(case, "Evidence Captured", actor, f"{len(evidence)} item(s) anchored to ledger", ts=created + 7200)

        # Bake every analysis section into the case — single source of truth.
        enrich_case(case)
        ensure_collab_fields(case)

        self._cases[case["case_id"]] = case
        if not _SEEDING.get("active"):
            self._save()
        return case

    # ── CRUD ─────────────────────────────────────────────────────────────────
    def create(self, *, account: Optional[dict], category: Optional[str], title: Optional[str],
               risk_score: Optional[int], detection_reason: Optional[str],
               accounts: Optional[List[str]], priority: Optional[str], actor: str) -> dict:
        with self._lock:
            if account:
                case = self.create_from_account(account, status="New", actor=actor)
            else:
                risk = int(risk_score or 60)
                cat = category or "High-Risk Network"
                accs = accounts or []
                conf = fraud_confidence_for(risk)
                now = _now()
                case = {
                    "case_id": self._next_id(),
                    "title": title or generate_title(cat),
                    "category": cat, "status": "New",
                    "priority": compute_priority(risk, len(accs), conf),
                    "risk_score": risk, "fraud_confidence": conf,
                    "detection_reason": detection_reason or detection_reason_for(cat, []),
                    "created_at": now, "updated_at": now,
                    "assigned_to": None, "assigned_name": None, "supervisor": None,
                    "department": None, "due_date": None,
                    "accounts": accs, "primary_account": accs[0] if accs else None,
                    "transactions": [], "evidence": [], "notes": [], "timeline": [],
                    "risk_history": [{"ts": now, "score": risk, "reason": "Manual case creation"}],
                    "graph_snapshot": {"nodes": [{"id": a, "risk": risk, "role": "linked"} for a in accs],
                                       "edges": [], "indicators": []},
                    "ub_analysis": "",
                }
                case["ub_analysis"] = generate_ub_analysis(case)
                self._add_timeline(case, "Case Created", actor, case["detection_reason"])
                enrich_case(case)
                ensure_collab_fields(case)
                self._cases[case["case_id"]] = case
            if priority and priority in PRIORITY_RANK:
                case["priority"] = priority
                case["recovery"]["recommended_priority"] = priority
            self._save()
            return case

    def register_from_detection(self, *, verdict: dict, component: dict,
                                assessment: Optional[dict] = None,
                                actor: str = "TGIE Risk Engine") -> Optional[dict]:
        """Auto-create ONE investigation case for a fraud cluster above threshold.

        Deduped by the cluster's account set: if an OPEN case already covers the
        exact same accounts, we skip (one fraud = one case, no duplicates on the
        ~1s detection heartbeat). Transactions come straight from the component's
        edges, so the case is fully enriched (roles, recovery, DNA) on creation.
        `assessment` is the explainable Risk Engine result — its 0–100 score is the
        single source of truth for the case's risk, stored verbatim on the case.
        """
        with self._lock:
            node_ids = component.get("node_ids") or verdict.get("nodes") or []
            node_ids = [str(n) for n in node_ids]
            if not node_ids:
                return None

            # stable cluster identity → dedup key
            key = "det:" + "|".join(sorted(node_ids))
            for c in self._cases.values():
                if c.get("detection_key") == key and c["status"] in OPEN_STATUSES:
                    return None   # already registered & still open

            # risk = the Risk Engine's explainable 0–100 score (single source of
            # truth). Fall back to the raw verdict score only if no assessment.
            if assessment:
                risk = int(max(1, min(100, assessment.get("score", 0))))
            else:
                raw = float(verdict.get("risk_score", 0) or 0)
                risk = int(round(raw * 100)) if raw <= 1.0 else int(round(raw))
                risk = max(1, min(100, risk))
            conf = fraud_confidence_for(risk)

            node_meta = {n["id"]: n for n in component.get("nodes", []) if "id" in n}
            flagged = [str(n) for n in (verdict.get("flagged_nodes") or [])]

            # ── Cash events are NOT bank accounts ─────────────────────────────────
            # Identify cash-event nodes (rail-driven): the TARGET of a CASH_OUT edge
            # left the banking system; the SOURCE of a CASH_IN edge entered it. Also
            # honour an explicit account_type=="cash"/is_cash_event from the verdict.
            cash_ids: set[str] = {
                nid for nid, m in node_meta.items()
                if m.get("is_cash_event") or m.get("account_type") == "cash"
            }
            for e in component.get("edges", []):
                r = str(e.get("payment_rail", "")).upper()
                if r == "CASH_OUT" and e.get("target"):
                    cash_ids.add(str(e["target"]))
                elif r == "CASH_IN" and e.get("source"):
                    cash_ids.add(str(e["source"]))
            account_ids = [n for n in node_ids if n not in cash_ids]

            # primary suspect = highest-risk flagged node, else highest-risk ACCOUNT
            # (never a cash event — a withdrawal point isn't a suspect account).
            def _risk_of(nid: str) -> float:
                return float(node_meta.get(nid, {}).get("risk_score", 0) or 0)
            pool = [n for n in (flagged or node_ids) if n not in cash_ids] or account_ids or node_ids
            primary = max(pool, key=_risk_of) if pool else node_ids[0]

            indicators = sorted({
                p for n in component.get("nodes", [])
                for p in (n.get("detected_patterns") or [])
            })
            category = pick_category(indicators, risk)
            reason = verdict.get("suspicious_reason")
            detection_reason = (f"Blue Team flagged this {verdict.get('verdict', 'SUSPICIOUS').lower()} "
                                f"cluster ({reason}). " if reason else "") + detection_reason_for(category, indicators)

            now = _now()
            txns = []
            for e in component.get("edges", []):
                txns.append({
                    "txn_id": e.get("id", f"{e.get('source')}-{e.get('target')}"),
                    "amount": e.get("amount", 0),
                    "date": now,
                    "from_account": e.get("source"),
                    "to_account": e.get("target"),
                    "rail": e.get("payment_rail", "UPI"),
                    "reason": "Edge flagged by Blue Team" if e.get("is_flagged") else "Transaction in flagged cluster",
                })

            def _role(n: str) -> str:
                if n in cash_ids:
                    return "cash_out" if node_meta.get(n, {}).get("cash_kind") != "CASH_IN" else "cash_in"
                return "primary" if n == primary else "linked"
            nodes_snap = [{"id": n, "risk": int(round(_risk_of(n) * 100)) if _risk_of(n) <= 1 else int(_risk_of(n)),
                           "role": _role(n)} for n in node_ids]
            edges_snap = [{"from": e.get("source"), "to": e.get("target")} for e in component.get("edges", [])]

            # Cash events stored SEPARATELY from accounts (one row per cash edge).
            cash_events = []
            for e in component.get("edges", []):
                r = str(e.get("payment_rail", "")).upper()
                if r not in ("CASH_OUT", "CASH_IN"):
                    continue
                cash_events.append({
                    "id": e.get("id", f"{e.get('source')}-{e.get('target')}"),
                    "kind": r,
                    "amount": e.get("amount", 0),
                    "source_account": e.get("source"),
                    "event_node": e.get("target") if r == "CASH_OUT" else e.get("source"),
                    "channel": e.get("device_id") or e.get("channel") or "—",
                    "timestamp": now,
                    "terminal": r == "CASH_OUT",
                    "status": "Funds exited banking system" if r == "CASH_OUT"
                              else "Funds entered banking system",
                })

            # Priority follows the Risk Engine level when available (Critical/High),
            # else the heuristic. Explanation + factors stored verbatim on the case.
            level = (assessment or {}).get("level")
            priority = {"Critical": "Critical", "High Risk": "High"}.get(level) \
                or compute_priority(risk, len(node_ids), conf)
            if assessment and assessment.get("explanation"):
                detection_reason = assessment["explanation"]

            case = {
                "case_id": self._next_id(),
                "title": generate_title(category),
                "category": category, "status": "New",
                "priority": priority,
                "risk_score": risk, "fraud_confidence": conf,
                "detection_reason": detection_reason,
                "created_at": now, "updated_at": now,
                "assigned_to": None, "assigned_name": None, "supervisor": None,
                "department": None, "due_date": None,
                "accounts": node_ids, "primary_account": primary,
                "cash_events": cash_events, "account_count": len(account_ids),
                "cross_bank": _cross_bank_summary(verdict),  # cross-bank entity intelligence (metadata)
                "transactions": txns, "evidence": [], "notes": [], "timeline": [],
                "risk_history": [{"ts": now, "score": risk, "reason": "Risk Engine score at detection"}],
                "graph_snapshot": {"nodes": nodes_snap, "edges": edges_snap, "indicators": indicators},
                "ub_analysis": "",
                "risk_assessment": assessment,   # explainable 0–100 score + factors
                "detection_key": key,
                "source": "blue_team_auto",
                "source_graph_id": verdict.get("graph_id"),
            }
            case["ub_analysis"] = generate_ub_analysis(case)
            self._add_timeline(case, "Fraud Detected", "TGIE Risk Engine",
                               (assessment or {}).get("explanation", detection_reason), ts=now)
            self._add_timeline(case, "Case Created", actor,
                               f"Risk {risk}/100 ({level or 'High Risk'}) · {len(node_ids)} accounts", ts=now + 1)
            enrich_case(case)
            ensure_collab_fields(case)
            self._cases[case["case_id"]] = case
            if not _SEEDING.get("active"):
                self._save()
            return case

    def get(self, case_id: str) -> Optional[dict]:
        return self._cases.get((case_id or "").upper())

    def all(self) -> List[dict]:
        """All full case records (used by the Fraud DNA engine)."""
        return list(self._cases.values())

    def list(self, *, status: Optional[str] = None, priority: Optional[str] = None,
             assigned_to: Optional[str] = None, scope: Optional[str] = None,
             participant: Optional[str] = None) -> List[dict]:
        items = list(self._cases.values())
        if scope == "open":
            items = [c for c in items if c["status"] in OPEN_STATUSES]
        elif scope == "closed":
            items = [c for c in items if c["status"] in CLOSED_STATUSES]
        elif scope == "critical":
            items = [c for c in items if c["priority"] == "Critical"]
        elif scope == "available":
            # unassigned + still open → the "Available Cases" pool any investigator can claim
            items = [c for c in items if not c.get("assigned_to") and c["status"] in OPEN_STATUSES]
        elif scope == "mine" and participant:
            items = [c for c in items if c.get("assigned_to") == participant
                     or any(p.get("investigator_id") == participant for p in c.get("participants", []))]
        if status:
            items = [c for c in items if c["status"] == status]
        if priority:
            items = [c for c in items if c["priority"] == priority]
        if assigned_to:
            items = [c for c in items if c.get("assigned_to") == assigned_to]
        items.sort(key=lambda c: c["updated_at"], reverse=True)
        return [self.summary(c) for c in items]

    def summary(self, c: dict) -> dict:
        rec = c.get("recovery") or {}
        bc = c.get("blockchain") or {}
        return {
            "case_id": c["case_id"], "title": c["title"], "category": c["category"],
            "status": c["status"], "priority": c["priority"], "risk_score": c["risk_score"],
            "fraud_confidence": c["fraud_confidence"],
            "assigned_to": c.get("assigned_to"), "assigned_name": c.get("assigned_name"),
            "created_at": c["created_at"], "updated_at": c["updated_at"],
            # Cash events are not bank accounts → don't inflate the account count.
            "account_count": c.get("account_count", len(c["accounts"])),
            "cash_event_count": len(c.get("cash_events", [])),
            "primary_account": c.get("primary_account"),
            "is_open": c["status"] in OPEN_STATUSES,
            "recovery_probability": rec.get("probability"),
            "estimated_loss": rec.get("estimated_loss"),
            "evidence_count": len(c.get("evidence", [])),
            "blockchain_verified": bool(bc.get("verified")),
            "participant_count": len(c.get("participants", [])),
            "comment_count": sum(1 for cm in c.get("comments", []) if not cm.get("archived")),
            "open_tasks": sum(1 for t in c.get("tasks", []) if not t.get("done")),
            "task_total": len(c.get("tasks", [])),
            "is_locked": bool(c.get("locks")),
        }

    def update(self, case_id: str, *, actor: str, **fields) -> Optional[dict]:
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            for k in ("status", "priority", "title"):
                v = fields.get(k)
                if v:
                    if k == "status" and v != c["status"]:
                        self._add_timeline(c, "Status Changed", actor, f"{c['status']} → {v}")
                    c[k] = v
            if fields.get("risk_score") is not None:
                new = int(fields["risk_score"])
                if new != c["risk_score"]:
                    c["risk_history"].insert(0, {"ts": _now(), "score": new, "reason": f"Updated by {actor}"})
                    self._add_timeline(c, "Risk Score Updated", actor, f"{c['risk_score']} → {new}")
                    c["risk_score"] = new
            c["updated_at"] = _now()
            # Risk / status changes shift recovery + DNA — re-bake so the case
            # stays the single source of truth (never recomputed on read).
            enrich_case(c)
            self._save()
            return c

    def add_note(self, case_id: str, *, text: str, author: str, author_name: str) -> Optional[dict]:
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            note = {"id": uuid.uuid4().hex[:10], "ts": _now(), "author": author,
                    "author_name": author_name, "text": text.strip()}
            c["notes"].insert(0, note)
            self._add_timeline(c, "Investigator Added Notes", author_name, text.strip()[:80])
            c["updated_at"] = c["last_updated"] = _now()
            self._save()
            return c

    def add_evidence(self, case_id: str, *, ev_type: str, description: str, reference: str,
                     actor: str) -> Optional[dict]:
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            ref = reference or f"{case_id}-{uuid.uuid4().hex[:6]}"
            ev = {"evidence_id": f"EVD-{uuid.uuid4().hex[:6].upper()}", "type": ev_type,
                  "description": description, "hash": evidence_hash(ref),
                  "anchored": True, "added_at": _now(), "added_by": actor}
            c["evidence"].insert(0, ev)
            self._add_timeline(c, "Evidence Uploaded", actor, f"{ev_type} ({ev['evidence_id']})")
            self._add_timeline(c, "Blockchain Registration Completed", "BELS Ledger", ev["hash"][:18] + "…")
            c["updated_at"] = c["last_updated"] = _now()
            self._save()
            return c

    # ── verbatim graph snapshot (positions + camera) ──────────────────────────
    def set_graph_snapshot(self, case_id: str, *, nodes: List[dict], edges: List[dict],
                           camera: Optional[dict], indicators: Optional[List[str]],
                           actor: str) -> Optional[dict]:
        """Store the EXACT live-graph state so the case reopens verbatim (no re-sim)."""
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            prev = c.get("graph_snapshot", {}) or {}
            snap = {
                "nodes": nodes,
                "edges": edges,
                "indicators": indicators if indicators is not None else prev.get("indicators", []),
                "camera": camera,
                "captured": True,
                "captured_at": _now(),
            }
            c["graph_snapshot"] = snap
            c["raw_graph_json"] = {
                "nodes": nodes, "edges": edges,
                "indicators": snap["indicators"], "camera": camera,
            }
            self._add_timeline(c, "Graph Snapshot Captured", actor,
                               f"{len(nodes)} node(s) pinned verbatim")
            c["updated_at"] = c["last_updated"] = _now()
            self._save()
            return c

    # ── evidence FILES (real upload / download) ───────────────────────────────
    def _case_evidence_dir(self, case_id: str) -> str:
        d = os.path.join(_EVIDENCE_DIR, case_id.upper())
        os.makedirs(d, exist_ok=True)
        return d

    def add_evidence_file(self, case_id: str, *, filename: str, data: bytes,
                          ev_type: str, remarks: str, actor: str) -> Optional[dict]:
        """Persist a real uploaded file, hash it, and record it on the case."""
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            evidence_id = f"EVD-{uuid.uuid4().hex[:8].upper()}"
            safe_name = os.path.basename(filename or "artifact.bin").replace("/", "_")
            stored = os.path.join(self._case_evidence_dir(case_id), f"{evidence_id}__{safe_name}")
            with open(stored, "wb") as f:
                f.write(data)
            digest = _sha256(data)
            ev = {
                "evidence_id": evidence_id,
                "name": safe_name,
                "type": ev_type or _bels_type(safe_name),
                "uploader": actor,
                "timestamp": _now(),
                "added_at": _now(),
                "added_by": actor,
                "hash": "0x" + digest,
                "sha256": digest,
                "size_bytes": len(data),
                "remarks": remarks or "",
                "verification_status": "Unverified",
                "anchored": False,
                "stored_path": stored,
                "has_file": True,
            }
            c["evidence"].insert(0, ev)
            self._add_timeline(c, "Evidence Uploaded", actor,
                               f"{ev['type']} · {safe_name} ({evidence_id})")
            c["updated_at"] = c["last_updated"] = _now()
            self._save()
            return c

    def evidence_record(self, case_id: str, evidence_id: str) -> Optional[dict]:
        c = self.get(case_id)
        if not c:
            return None
        eid = (evidence_id or "").upper()
        return next((e for e in c.get("evidence", []) if str(e.get("evidence_id", "")).upper() == eid), None)

    def evidence_file(self, case_id: str, evidence_id: str) -> Optional[Tuple[str, str]]:
        """→ (absolute_path, download_name) for a stored evidence file, else None."""
        ev = self.evidence_record(case_id, evidence_id)
        if not ev or not ev.get("stored_path") or not os.path.exists(ev["stored_path"]):
            return None
        return ev["stored_path"], ev.get("name", os.path.basename(ev["stored_path"]))

    # ── blockchain anchoring (live BELS, internal fallback) ───────────────────
    def _bundle_manifest(self, c: dict) -> dict:
        """Canonical per-component hash manifest — this is what gets anchored."""
        comps = {
            "graph": c.get("raw_graph_json", {}),
            "transactions": c.get("raw_transaction_json", []),
            "fraud_dna": c.get("fraud_dna", {}),
            "recovery": c.get("recovery", {}),
            "accounts": c.get("account_roles", []),
            "evidence": [{"evidence_id": e.get("evidence_id"), "hash": e.get("hash")}
                         for e in c.get("evidence", [])],
        }
        hashes = {k: _sha256(_canonical(v)) for k, v in comps.items()}
        return {
            "case_id": c["case_id"],
            "component_hashes": hashes,
            "items": [{"component": k, "hash": v} for k, v in hashes.items()],
        }

    def anchor_blockchain(self, case_id: str, *, actor: str) -> Optional[dict]:
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            manifest = self._bundle_manifest(c)
            bundle_hash = _sha256(_canonical(manifest))
            ts = _now()

            from . import bels_client
            rec = bels_client.register(
                bundle_hash, c["case_id"], f"{c['case_id']}-evidence-bundle.json",
                "json", actor, metadata=manifest["component_hashes"],
            )

            if rec:
                evidence_id = rec.get("evidence_id")
                ver = bels_client.verify_hash(evidence_id, bundle_hash, actor)
                verified = bool(ver and ver.get("outcome") == "VERIFIED")
                cert = bels_client.certificate(evidence_id)
                bc = {
                    "status": "Verified" if verified else "Anchored",
                    "verified": verified,
                    "provider": "BELS",
                    "hash": "0x" + bundle_hash,
                    "evidence_id": evidence_id,
                    "txid": rec.get("anchor_tx_id"),
                    "block_index": rec.get("block_index"),
                    "block_hash": rec.get("block_hash"),
                    "certificate": cert,
                    "anchored_at": ts,
                    "verified_at": ts if verified else None,
                    "items": manifest["items"],
                }
            else:
                # Self-contained fallback so the action never fails when BELS is down.
                bc = {
                    "status": "Anchored (internal)",
                    "verified": True,
                    "provider": "internal",
                    "hash": "0x" + bundle_hash,
                    "evidence_id": f"EVD-INT-{bundle_hash[:8].upper()}",
                    "txid": "0x" + bundle_hash[:40],
                    "block_index": None,
                    "block_hash": "0x" + _sha256(bundle_hash.encode())[:32],
                    "certificate": None,
                    "anchored_at": ts,
                    "verified_at": ts,
                    "items": manifest["items"],
                }

            # Mark all current evidence as anchored under this bundle.
            for e in c.get("evidence", []):
                e["anchored"] = True
                if e.get("verification_status") == "Unverified":
                    e["verification_status"] = "Anchored"

            c["blockchain"] = bc
            provider = bc["provider"].upper()
            self._add_timeline(c, "Blockchain Uploaded", actor,
                               f"{provider} anchor {bc['hash'][:18]}…")
            if bc["verified"]:
                self._add_timeline(c, "Blockchain Verified", provider + " Ledger",
                                   f"tx {str(bc.get('txid'))[:18]}…")
            c["updated_at"] = c["last_updated"] = ts
            self._save()
            return c

    def verify_blockchain(self, case_id: str, *, actor: str) -> Optional[dict]:
        """Re-verify the anchored bundle against the (current) case state."""
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            bc = c.get("blockchain") or {}
            if not bc.get("evidence_id"):
                return {"verified": False, "message": "Case has not been anchored yet."}
            manifest = self._bundle_manifest(c)
            current_hash = "0x" + _sha256(_canonical(manifest))
            tampered = current_hash != bc.get("hash")

            from . import bels_client
            ver = bels_client.verify_hash(bc["evidence_id"], bc["hash"].lstrip("0x"), actor) \
                if bc.get("provider") == "BELS" else None
            chain_ok = (ver.get("outcome") == "VERIFIED") if ver else (bc.get("provider") != "BELS")

            verified = chain_ok and not tampered
            bc["verified"] = verified
            bc["status"] = "Verified" if verified else ("Tampered" if tampered else "Anchored")
            bc["verified_at"] = _now()
            self._add_timeline(c, "Blockchain Verified" if verified else "Blockchain Verification Failed",
                               actor, "Bundle matches ledger" if verified else "Bundle hash mismatch")
            c["updated_at"] = c["last_updated"] = _now()
            self._save()
            return {"verified": verified, "tampered": tampered,
                    "current_hash": current_hash, "anchored_hash": bc.get("hash"),
                    "provider": bc.get("provider"), "blockchain": bc}

    # ── case bundle (ZIP archive of everything) ───────────────────────────────
    def bundle_zip(self, case_id: str) -> Optional[bytes]:
        c = self.get(case_id)
        if not c:
            return None
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            base = c["case_id"]
            z.writestr(f"{base}/case.json", json.dumps(c, indent=2, default=str))
            z.writestr(f"{base}/graph.json", json.dumps(c.get("raw_graph_json", {}), indent=2, default=str))
            z.writestr(f"{base}/fraud_dna.json", json.dumps(c.get("fraud_dna", {}), indent=2, default=str))
            z.writestr(f"{base}/recovery.json", json.dumps(c.get("recovery", {}), indent=2, default=str))
            z.writestr(f"{base}/timeline.json", json.dumps(c.get("timeline", []), indent=2, default=str))
            z.writestr(f"{base}/notes.json", json.dumps(c.get("notes", []), indent=2, default=str))
            z.writestr(f"{base}/accounts.json", json.dumps(c.get("account_roles", []), indent=2, default=str))
            z.writestr(f"{base}/blockchain_receipt.json", json.dumps(c.get("blockchain", {}), indent=2, default=str))
            # transactions as both JSON and CSV
            txns = c.get("raw_transaction_json", []) or c.get("transactions", [])
            z.writestr(f"{base}/transactions.json", json.dumps(txns, indent=2, default=str))
            z.writestr(f"{base}/transactions.csv", self._txns_csv(txns))
            # actual evidence files
            for e in c.get("evidence", []):
                p = e.get("stored_path")
                if p and os.path.exists(p):
                    z.write(p, f"{base}/evidence/{os.path.basename(p)}")
            z.writestr(f"{base}/evidence/manifest.json",
                       json.dumps(c.get("evidence", []), indent=2, default=str))
        return buf.getvalue()

    @staticmethod
    def _txns_csv(txns: List[dict]) -> str:
        cols = ["txn_id", "date", "from_account", "to_account", "amount", "rail", "reason"]
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for t in txns:
            w.writerow(t)
        return out.getvalue()

    # ── global search ─────────────────────────────────────────────────────────
    def search(self, query: str, limit: int = 25) -> List[dict]:
        q = (query or "").strip().lower()
        if not q:
            return []
        hits: List[dict] = []
        for c in self._cases.values():
            field = None
            if q in c["case_id"].lower():
                field = "Case ID"
            elif any(q in a.lower() for a in c.get("accounts", [])):
                field = "Account"
            elif any(q in str(t.get("txn_id", "")).lower() for t in c.get("transactions", [])):
                field = "Transaction"
            elif any(q in str(e.get("evidence_id", "")).lower() for e in c.get("evidence", [])):
                field = "Evidence"
            elif q in str((c.get("blockchain") or {}).get("hash", "")).lower():
                field = "Blockchain hash"
            elif q in str(c.get("assigned_name", "")).lower():
                field = "Investigator"
            elif q in c.get("category", "").lower() or q in c.get("title", "").lower():
                field = "Pattern"
            elif q in c.get("status", "").lower() or q in c.get("priority", "").lower():
                field = "Status"
            if field:
                hits.append({**self.summary(c), "matched_on": field})
        hits.sort(key=lambda h: h["updated_at"], reverse=True)
        return hits[:limit]

    def assign(self, case_id: str, *, investigator_id: Optional[str], investigator_name: Optional[str],
               supervisor: Optional[str], department: Optional[str], due_date: Optional[str],
               actor: str) -> Optional[dict]:
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            if investigator_id:
                c["assigned_to"] = investigator_id
                c["assigned_name"] = investigator_name or investigator_id
                ensure_collab_fields(c)
                # the assignee becomes (or is promoted to) the primary participant
                p = self._find_participant(c, investigator_id)
                if p:
                    p["is_primary"] = True
                    p["role_on_case"] = "Primary Investigator"
                else:
                    c["participants"].append(collab.make_participant(
                        investigator_id, c["assigned_name"], "Primary Investigator",
                        is_primary=True, added_by=actor))
                for q in c["participants"]:
                    q["is_primary"] = (q["investigator_id"] == investigator_id)
            if supervisor:
                c["supervisor"] = supervisor
            if department:
                c["department"] = department
            if due_date:
                c["due_date"] = due_date
            if c["status"] == "New":
                c["status"] = "Under Review"
            self._add_timeline(c, "Case Assigned", actor,
                               f"Assigned to {c.get('assigned_name') or '—'}")
            c["updated_at"] = c["last_updated"] = _now()
            self._save()
            return c

    def close(self, case_id: str, *, resolution: str, summary: Optional[str], actor: str) -> Optional[dict]:
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            c["status"] = resolution if resolution in CLOSED_STATUSES else "Closed"
            self._add_timeline(c, "Case Closed", actor, f"{c['status']}" + (f" — {summary}" if summary else ""))
            if summary:
                c["notes"].insert(0, {"id": uuid.uuid4().hex[:10], "ts": _now(),
                                      "author": "system", "author_name": actor,
                                      "text": f"[Resolution] {summary}"})
            c["updated_at"] = c["last_updated"] = _now()
            self._save()
            return c

    # ── queries ──────────────────────────────────────────────────────────────
    def by_account(self, account_number: str) -> List[dict]:
        an = (account_number or "").upper()
        return [self.summary(c) for c in self._cases.values() if an in [a.upper() for a in c["accounts"]]]

    def stats(self, me: Optional[str] = None) -> dict:
        cases = list(self._cases.values())
        return {
            "total": len(cases),
            "open": sum(1 for c in cases if c["status"] in OPEN_STATUSES),
            "critical": sum(1 for c in cases if c["priority"] == "Critical" and c["status"] in OPEN_STATUSES),
            "assigned_to_me": sum(1 for c in cases if c.get("assigned_to") == me) if me else 0,
            "resolved": sum(1 for c in cases if c["status"] in CLOSED_STATUSES),
            "escalated": sum(1 for c in cases if c["status"] == "Escalated"),
        }

    def notifications(self, limit: int = 12) -> List[dict]:
        events = []
        for c in self._cases.values():
            for t in c["timeline"][:2]:
                events.append({"case_id": c["case_id"], "title": c["title"],
                               "event": t["event"], "detail": t["detail"], "ts": t["ts"]})
        events.sort(key=lambda e: e["ts"], reverse=True)
        return events[:limit]

    # ════════════════════════════════════════════════════════════════════════
    #  COLLABORATION  (multi-investigator: participants, comments, tasks, locks)
    #  Every method mutates under the lock, appends an IMMUTABLE timeline entry
    #  for the audit trail, persists, and returns the full case (or None / a
    #  {"_error": ...} sentinel the router maps to an HTTP status).
    # ════════════════════════════════════════════════════════════════════════
    def _find_participant(self, c: dict, inv_id: str) -> Optional[dict]:
        for p in c.get("participants", []):
            if p.get("investigator_id") == inv_id:
                return p
        return None

    def claim(self, case_id: str, *, investigator_id: str, name: str,
              role: Optional[str] = None) -> Optional[dict]:
        """An investigator self-assigns an UNASSIGNED case → primary + participant."""
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            ensure_collab_fields(c)
            if c.get("assigned_to") and c["assigned_to"] != investigator_id:
                return {"_error": "conflict", "assigned_to": c["assigned_to"],
                        "assigned_name": c.get("assigned_name")}
            c["assigned_to"] = investigator_id
            c["assigned_name"] = name
            p = self._find_participant(c, investigator_id)
            if p:
                p["is_primary"] = True
                p["role_on_case"] = "Primary Investigator"
            else:
                c["participants"].append(collab.make_participant(
                    investigator_id, name, "Primary Investigator", is_primary=True,
                    added_by=investigator_id))
            for q in c["participants"]:
                q["is_primary"] = (q["investigator_id"] == investigator_id)
            if c["status"] == "New":
                c["status"] = "Under Review"
            self._add_timeline(c, "Case Claimed", name, f"{name} claimed this case")
            c["updated_at"] = c["last_updated"] = _now()
            self._save()
            return c

    def add_participant(self, case_id: str, *, investigator_id: str, name: str,
                        role_on_case: str, actor: str) -> Optional[dict]:
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            ensure_collab_fields(c)
            p = self._find_participant(c, investigator_id)
            if p:
                if role_on_case in collab.PARTICIPANT_ROLES:
                    p["role_on_case"] = role_on_case
            else:
                c["participants"].append(collab.make_participant(
                    investigator_id, name, role_on_case, added_by=actor))
                self._add_timeline(c, "Investigator Added", actor,
                                   f"{name} added as {role_on_case}")
            c["updated_at"] = c["last_updated"] = _now()
            self._save()
            return c

    def remove_participant(self, case_id: str, *, investigator_id: str, actor: str) -> Optional[dict]:
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            ensure_collab_fields(c)
            p = self._find_participant(c, investigator_id)
            if not p:
                return c
            if p.get("is_primary"):
                return {"_error": "is_primary"}   # hand the case over first; never orphan it
            c["participants"] = [q for q in c["participants"]
                                 if q["investigator_id"] != investigator_id]
            self._add_timeline(c, "Investigator Removed", actor, f"{p['name']} removed from case")
            c["updated_at"] = c["last_updated"] = _now()
            self._save()
            return c

    def handover(self, case_id: str, *, to_id: str, to_name: str, actor: str,
                 note: Optional[str] = None) -> Optional[dict]:
        """Transfer primary ownership for a shift change. The previous owner stays
        on the case as a Supporting Investigator (nothing is lost); the new owner
        inherits notes, evidence, timeline, DNA, recovery, comments — everything."""
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            ensure_collab_fields(c)
            prev_id, prev_name = c.get("assigned_to"), c.get("assigned_name")
            c["assigned_to"], c["assigned_name"] = to_id, to_name
            for q in c["participants"]:
                q["is_primary"] = False
                if q["investigator_id"] == prev_id and prev_id != to_id:
                    q["role_on_case"] = "Supporting Investigator"
            p = self._find_participant(c, to_id)
            if p:
                p["is_primary"] = True
                p["role_on_case"] = "Primary Investigator"
            else:
                c["participants"].append(collab.make_participant(
                    to_id, to_name, "Primary Investigator", is_primary=True, added_by=actor))
            detail = f"{prev_name or '—'} → {to_name}" + (f" · {note}" if note else "")
            self._add_timeline(c, "Case Handover", actor, detail)
            c["updated_at"] = c["last_updated"] = _now()
            self._save()
            return c

    # ── comments thread (immutable: edits keep history, deletes are archives) ──
    def add_comment(self, case_id: str, *, author: str, author_name: str, text: str,
                    parent_id: Optional[str] = None) -> Optional[dict]:
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            ensure_collab_fields(c)
            c["comments"].append({
                "id": collab.gen_id("CMT-"),
                "author": author, "author_name": author_name,
                "text": text, "parent_id": parent_id,
                "mentions": collab.parse_mentions(text), "attachments": [],
                "created_at": _now(), "edited_at": None, "edit_history": [],
                "archived": False, "archived_by": None, "archived_at": None,
            })
            self._add_timeline(c, "Comment Added", author_name,
                               (text[:80] + "…") if len(text) > 80 else text)
            c["updated_at"] = c["last_updated"] = _now()
            self._save()
            return c

    def edit_comment(self, case_id: str, comment_id: str, *, text: str,
                     editor_name: str) -> Optional[dict]:
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            ensure_collab_fields(c)
            for cm in c["comments"]:
                if cm["id"] == comment_id:
                    if cm.get("archived"):
                        return {"_error": "archived"}
                    cm["edit_history"].append({"ts": _now(), "previous_text": cm["text"],
                                               "editor": editor_name})
                    cm["text"] = text
                    cm["mentions"] = collab.parse_mentions(text)
                    cm["edited_at"] = _now()
                    self._add_timeline(c, "Comment Edited", editor_name, f"edited a comment")
                    c["updated_at"] = c["last_updated"] = _now()
                    self._save()
                    return c
            return {"_error": "not_found"}

    def archive_comment(self, case_id: str, comment_id: str, *, actor: str) -> Optional[dict]:
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            ensure_collab_fields(c)
            for cm in c["comments"]:
                if cm["id"] == comment_id:
                    cm["archived"] = True
                    cm["archived_by"] = actor
                    cm["archived_at"] = _now()
                    self._add_timeline(c, "Comment Archived", actor, "a comment was archived")
                    c["updated_at"] = c["last_updated"] = _now()
                    self._save()
                    return c
            return {"_error": "not_found"}

    # ── tasks / checklist ─────────────────────────────────────────────────────
    def add_task(self, case_id: str, *, label: str, actor: str,
                 assignee: Optional[str] = None, assignee_name: Optional[str] = None) -> Optional[dict]:
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            ensure_collab_fields(c)
            c["tasks"].append({
                "id": collab.gen_id("TSK-"), "label": label, "done": False,
                "assignee": assignee, "assignee_name": assignee_name,
                "done_by": None, "done_at": None,
                "created_by": actor, "created_at": _now(),
            })
            self._add_timeline(c, "Task Added", actor, label)
            c["updated_at"] = c["last_updated"] = _now()
            self._save()
            return c

    def update_task(self, case_id: str, task_id: str, *, actor: str,
                    done: Optional[bool] = None, set_assignee: bool = False,
                    assignee: Optional[str] = None, assignee_name: Optional[str] = None) -> Optional[dict]:
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            ensure_collab_fields(c)
            for t in c["tasks"]:
                if t["id"] == task_id:
                    if done is not None and bool(done) != t["done"]:
                        t["done"] = bool(done)
                        t["done_by"] = actor if done else None
                        t["done_at"] = _now() if done else None
                        self._add_timeline(c, "Task " + ("Completed" if done else "Reopened"),
                                           actor, t["label"])
                    if set_assignee:
                        t["assignee"] = assignee
                        t["assignee_name"] = assignee_name
                        self._add_timeline(c, "Task Assigned", actor,
                                           f"{t['label']} → {assignee_name or assignee or 'unassigned'}")
                    c["updated_at"] = c["last_updated"] = _now()
                    self._save()
                    return c
            return {"_error": "not_found"}

    # ── editing locks (temporary, TTL'd — prevents silent overwrite) ──────────
    def set_lock(self, case_id: str, *, resource: str, holder_id: str, holder_name: str) -> Optional[dict]:
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            ensure_collab_fields(c)
            cur = c["locks"].get(resource)
            now = _now()
            if cur and cur["holder_id"] != holder_id and (now - cur["ts"]) < collab.LOCK_TTL_SECONDS:
                return {"_error": "locked", "holder_id": cur["holder_id"], "holder_name": cur["holder_name"]}
            c["locks"][resource] = {"holder_id": holder_id, "holder_name": holder_name, "ts": now}
            self._save()
            return {"locked": True, "resource": resource, "holder_id": holder_id, "holder_name": holder_name}

    def release_lock(self, case_id: str, *, resource: str, holder_id: str) -> Optional[dict]:
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            ensure_collab_fields(c)
            cur = c["locks"].get(resource)
            if cur and cur["holder_id"] == holder_id:
                c["locks"].pop(resource, None)
                self._save()
            return {"released": True, "resource": resource}

    def request_approval(self, case_id: str, *, actor: str, note: Optional[str] = None) -> Optional[dict]:
        with self._lock:
            c = self.get(case_id)
            if not c:
                return None
            c["status"] = "Pending Approval"
            self._add_timeline(c, "Manager Review Requested", actor,
                               note or "Submitted for manager approval")
            c["updated_at"] = c["last_updated"] = _now()
            self._save()
            return c

    # ── operations / workload (manager dashboards) ────────────────────────────
    def ops_metrics(self) -> dict:
        cases = list(self._cases.values())
        now = _now()
        day = 86400.0
        evidence_today = 0
        for c in cases:
            for e in c.get("evidence", []):
                ts = e.get("added_at") or e.get("ts") or 0
                if isinstance(ts, (int, float)) and (now - ts) < day:
                    evidence_today += 1
        open_cases = [c for c in cases if c["status"] in OPEN_STATUSES]
        active_inv = {c.get("assigned_to") for c in open_cases if c.get("assigned_to")}

        def _loss(c):
            return float((c.get("recovery") or {}).get("estimated_loss") or 0)

        def _recoverable(c):
            return float((c.get("recovery") or {}).get("expected_recoverable") or 0)

        return {
            "total_cases": len(cases),
            "open": len(open_cases),
            "critical": sum(1 for c in open_cases if c["priority"] == "Critical"),
            "unassigned": sum(1 for c in open_cases if not c.get("assigned_to")),
            "waiting_assignment": sum(1 for c in open_cases if not c.get("assigned_to")),
            "waiting_approval": sum(1 for c in cases if c["status"] == "Pending Approval"),
            "escalated": sum(1 for c in cases if c["status"] == "Escalated"),
            "resolved": sum(1 for c in cases if c["status"] in CLOSED_STATUSES),
            "potential_loss": round(sum(_loss(c) for c in open_cases), 2),
            "recovered_amount": round(sum(_recoverable(c) for c in cases if c["status"] in CLOSED_STATUSES), 2),
            "evidence_today": evidence_today,
            "blockchain_verifications": sum(1 for c in cases if (c.get("blockchain") or {}).get("verified")),
            "active_investigators": len(active_inv),
        }

    def workload(self) -> dict:
        open_cases = [c for c in self._cases.values() if c["status"] in OPEN_STATUSES]
        per: Dict[str, dict] = {}
        # seed every registered investigator so idle ones surface too
        try:
            from auth.store import store as inv_store
            for u in inv_store._users.values():
                per[u["investigator_id"]] = {
                    "investigator_id": u["investigator_id"], "name": u["name"],
                    "role": u.get("role"), "active": 0, "critical": 0, "pending": 0,
                }
        except Exception:
            pass
        for c in open_cases:
            pid = c.get("assigned_to")
            if not pid:
                continue
            row = per.setdefault(pid, {"investigator_id": pid, "name": c.get("assigned_name") or pid,
                                       "role": None, "active": 0, "critical": 0, "pending": 0})
            row["active"] += 1
            if c["priority"] == "Critical":
                row["critical"] += 1
            if c["status"] == "Pending Approval":
                row["pending"] += 1
        rows = list(per.values())
        for r in rows:
            r["overloaded"] = r["active"] >= collab.OVERLOAD_THRESHOLD
            r["idle"] = r["active"] == 0
        rows.sort(key=lambda r: r["active"], reverse=True)
        overloaded = [r for r in rows if r["overloaded"]]
        idle = [r for r in rows if r["idle"]]
        recs = []
        for o in overloaded:
            for i in idle:
                recs.append(f"Reassign a case from {o['name']} ({o['active']} open) to {i['name']} (idle)")
        return {
            "investigators": rows,
            "overloaded": [r["name"] for r in overloaded],
            "idle": [r["name"] for r in idle],
            "recommendations": recs[:5],
            "unassigned_open": sum(1 for c in open_cases if not c.get("assigned_to")),
        }

    def my_dashboard(self, investigator_id: str, name: str = "") -> dict:
        cases = list(self._cases.values())
        now = _now()
        day = 86400.0

        def mine(c):
            return c.get("assigned_to") == investigator_id

        def participating(c):
            return any(p.get("investigator_id") == investigator_id for p in c.get("participants", []))

        my_open = [c for c in cases if mine(c) and c["status"] in OPEN_STATUSES]
        today = 0
        for c in cases:
            for t in c.get("timeline", []):
                if t.get("actor") in (name, investigator_id) and (now - t.get("ts", 0)) < day:
                    today += 1
        recent = sorted([c for c in cases if mine(c)], key=lambda c: c["updated_at"], reverse=True)[:5]
        return {
            "assigned": len(my_open),
            "open": len(my_open),
            "completed": sum(1 for c in cases if (mine(c) or participating(c)) and c["status"] in CLOSED_STATUSES),
            "critical": sum(1 for c in my_open if c["priority"] == "Critical"),
            "pending_reviews": sum(1 for c in my_open if c["status"] == "Pending Approval"),
            "participating": sum(1 for c in cases if participating(c) and not mine(c) and c["status"] in OPEN_STATUSES),
            "today_activity": today,
            "recent_cases": [self.summary(c) for c in recent],
            "unread_comments": 0,   # per-user read state is a later phase
        }


# guard so the bulk seed only writes once
_SEEDING = {"active": False}


def _build_store() -> CaseStore:
    _SEEDING["active"] = True
    s = CaseStore()
    _SEEDING["active"] = False
    s._save()
    return s


store = _build_store()
