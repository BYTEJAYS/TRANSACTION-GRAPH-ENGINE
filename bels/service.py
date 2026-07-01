"""
BELSService — the orchestrator investigators and the API talk to.

Implements the full evidence lifecycle:
  upload → generate Evidence ID → SHA-256 → extract metadata → timestamp →
  blockchain anchor → secure store → verification certificate.

Also owns case management and the read models (records, audit, custody) that the
dashboard, reports and UB layer consume.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import config
from .blockchain_ledger import get_provider
from .chain_of_custody import custody_engine
from .evidence_storage import evidence_store
from .evidence_storage.storage import classify
from .models import CustodyAction, EvidenceRecordOut, EvidenceType, VerifyResultOut
from .security import audit_log, signer, sha256_hex, utc_now_iso
from .smart_contracts import evidence_registry
from .verification_engine import verification_engine


def _gen_evidence_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"EV-{stamp}-{uuid.uuid4().hex[:8].upper()}"


def _gen_case_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"CASE-{stamp}-{uuid.uuid4().hex[:6].upper()}"


class BELSService:
    def __init__(self) -> None:
        self.provider = get_provider()
        self._lock = threading.RLock()
        self.cases: Dict[str, Dict[str, Any]] = {}
        config.ensure_dirs()
        self._load_cases()

    # ── case management ──────────────────────────────────────────────────────
    def _load_cases(self) -> None:
        if config.CASES_FILE.exists():
            self.cases = json.loads(config.CASES_FILE.read_text(encoding="utf-8"))

    def _save_cases(self) -> None:
        config.CASES_FILE.write_text(json.dumps(self.cases, indent=2), encoding="utf-8")

    def create_case(self, title: str, description: str = "", owner: str = "system",
                    case_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            cid = case_id or _gen_case_id()
            self.cases[cid] = {
                "case_id": cid, "title": title, "description": description,
                "owner": owner, "created_at": utc_now_iso(), "evidence_ids": [],
            }
            self._save_cases()
            audit_log.record("case.create", owner, "investigator", cid, title=title)
            return self.cases[cid]

    def _attach(self, case_id: str, evidence_id: str) -> None:
        case = self.cases.get(case_id)
        if not case:
            case = self.create_case(title=f"Auto case {case_id}", case_id=case_id)
        if evidence_id not in case["evidence_ids"]:
            case["evidence_ids"].append(evidence_id)
            self._save_cases()

    def get_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        case = self.cases.get(case_id)
        if not case:
            return None
        return {**case, "evidence": [self.get_evidence(e) for e in case["evidence_ids"]]}

    def list_cases(self) -> List[Dict[str, Any]]:
        return [{**c, "evidence_count": len(c["evidence_ids"])} for c in self.cases.values()]

    # ── evidence upload / registration ───────────────────────────────────────
    def upload_evidence(self, filename: str, data: bytes, case_id: str,
                        owner: str = "system", role: str = "investigator",
                        evidence_type: Optional[EvidenceType] = None,
                        metadata: Optional[Dict[str, Any]] = None) -> EvidenceRecordOut:
        """Full upload flow: store off-chain, anchor on-chain, open chain of custody."""
        with self._lock:
            evidence_id = _gen_evidence_id()
            etype = evidence_type or classify(filename)
            meta = {**(metadata or {}), "evidence_type": etype.value, "uploader": owner}

            # 1-5. store + hash + metadata + timestamp
            stored = evidence_store.save(evidence_id, filename, data, meta)

            # 6-7. anchor on the blockchain via the contract surface
            receipt = evidence_registry.registerEvidence(
                evidence_id=evidence_id, case_id=case_id, file_hash=stored.sha256,
                metadata_hash=stored.metadata_hash, owner=owner,
                extra={"filename": stored.filename, "evidence_type": etype.value,
                       "size_bytes": stored.size_bytes},
            )

            # 8. chain of custody: UPLOAD then REGISTER
            custody_engine.record(evidence_id, CustodyAction.UPLOAD, owner,
                                  f"Uploaded {stored.filename} ({stored.size_bytes} bytes)")
            self._attach(case_id, evidence_id)
            audit_log.record("evidence.upload", owner, role, evidence_id,
                             case_id=case_id, sha256=stored.sha256)

            # 9. verification certificate
            self._write_certificate(evidence_id)
            return self.get_evidence(evidence_id)  # type: ignore[return-value]

    def register_hash(self, file_hash: str, case_id: str, filename: str,
                      evidence_type: EvidenceType, owner: str, role: str,
                      metadata: Optional[Dict[str, Any]] = None) -> EvidenceRecordOut:
        """Anchor an already-hashed artifact (e.g. a TGIE fraud alert) — no file upload."""
        with self._lock:
            evidence_id = _gen_evidence_id()
            from .security import sha256_of_obj
            meta = {**(metadata or {}), "evidence_type": evidence_type.value, "external": True}
            metadata_hash = sha256_of_obj(meta)
            evidence_registry.registerEvidence(
                evidence_id=evidence_id, case_id=case_id, file_hash=file_hash.lower().strip(),
                metadata_hash=metadata_hash, owner=owner,
                extra={"filename": filename, "evidence_type": evidence_type.value,
                       "size_bytes": 0, "external": True, "user_metadata": meta},
            )
            custody_engine.record(evidence_id, CustodyAction.REGISTER, owner,
                                  f"Registered external hash for {filename}")
            self._attach(case_id, evidence_id)
            audit_log.record("evidence.register_hash", owner, role, evidence_id, case_id=case_id)
            self._write_certificate(evidence_id)
            return self.get_evidence(evidence_id)  # type: ignore[return-value]

    # ── reads ────────────────────────────────────────────────────────────────
    def get_evidence(self, evidence_id: str) -> Optional[EvidenceRecordOut]:
        rec = self.provider.get_record(evidence_id)
        if rec is None:
            return None
        manifest = evidence_store.manifest(evidence_id) or {}
        # locate the REGISTER tx for block coordinates
        trail = self.provider.get_audit_trail(evidence_id)
        reg = next((t for t in trail if t["type"] == "REGISTER"), trail[0] if trail else None)
        return EvidenceRecordOut(
            evidence_id=evidence_id,
            case_id=rec.case_id,
            filename=rec.extra.get("filename", manifest.get("original_filename", "—")),
            evidence_type=rec.extra.get("evidence_type", manifest.get("evidence_type", "other")),
            file_hash=rec.file_hash,
            metadata_hash=rec.metadata_hash,
            owner=rec.owner,
            status=rec.status,
            size_bytes=int(rec.extra.get("size_bytes", manifest.get("size_bytes", 0))),
            registered_at=rec.timestamp,
            verification_count=rec.verification_count,
            custody_event_count=rec.custody_event_count,
            anchor_tx_id=reg["tx_id"] if reg else "",
            block_index=reg["block_index"] if reg else -1,
            block_hash=reg["block_hash"] if reg else "",
            metadata=manifest.get("user_metadata", rec.extra.get("user_metadata", {})),
        )

    def list_evidence(self) -> List[EvidenceRecordOut]:
        out = []
        for eid in self.provider.list_evidence_ids():
            rec = self.get_evidence(eid)
            if rec:
                out.append(rec)
        return sorted(out, key=lambda r: r.registered_at, reverse=True)

    def get_audit(self, evidence_id: str) -> List[Dict[str, Any]]:
        return self.provider.get_audit_trail(evidence_id)

    def get_custody(self, evidence_id: str) -> List[Dict[str, Any]]:
        return custody_engine.timeline(evidence_id)

    def record_custody(self, evidence_id: str, action: CustodyAction, actor: str,
                       role: str, detail: str = "") -> Dict[str, Any]:
        receipt = custody_engine.record(evidence_id, action, actor, detail)
        audit_log.record(f"custody.{action.value.lower()}", actor, role, evidence_id)
        return receipt.to_dict()

    # ── verification ─────────────────────────────────────────────────────────
    def verify(self, evidence_id: str, uploaded: Optional[bytes] = None,
               provided_hash: Optional[str] = None, actor: str = "system",
               role: str = "auditor") -> VerifyResultOut:
        result = verification_engine.verify(evidence_id, uploaded, provided_hash, actor)
        audit_log.record("evidence.verify", actor, role, evidence_id, outcome=result.outcome.value)
        return result

    # ── certificate ──────────────────────────────────────────────────────────
    def _write_certificate(self, evidence_id: str) -> Dict[str, Any]:
        cert = self.certificate(evidence_id)
        path = config.CERTS_DIR / f"{evidence_id}_certificate.json"
        path.write_text(json.dumps(cert, indent=2), encoding="utf-8")
        return cert

    def certificate(self, evidence_id: str) -> Dict[str, Any]:
        rec = self.get_evidence(evidence_id)
        if rec is None:
            return {}
        return {
            "certificate_type": "BELS Evidence Verification Certificate",
            "evidence_id": rec.evidence_id,
            "case_id": rec.case_id,
            "file_hash_sha256": rec.file_hash,
            "metadata_hash": rec.metadata_hash,
            "registered_at": rec.registered_at,
            "owner": rec.owner,
            "blockchain": {
                "provider": self.provider.name,
                "chain_id": self.provider.chain_id,
                "anchor_tx_id": rec.anchor_tx_id,
                "block_index": rec.block_index,
                "block_hash": rec.block_hash,
            },
            "signature": {
                "scheme": signer.scheme,
                "signer_key_id": signer.public_key_id,
            },
            "issued_at": utc_now_iso(),
            "statement": ("This certificate attests that the above evidence hash was "
                          "anchored to the ledger at the stated time and can be "
                          "independently verified against block " + rec.block_hash[:16] + "."),
        }

    # ── status ───────────────────────────────────────────────────────────────
    def blockchain_status(self) -> Dict[str, Any]:
        return self.provider.status()

    def chain_integrity(self) -> Dict[str, Any]:
        return self.provider.verify_integrity()


service = BELSService()
