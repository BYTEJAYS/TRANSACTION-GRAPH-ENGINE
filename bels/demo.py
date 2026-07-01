"""
Bank demonstration mode.

Runs the full forensic workflow end-to-end so it can be shown live:

    fraud complaint arrives → evidence uploaded → registered & anchored →
    verified (proof generated) → chain of custody displayed → audit report generated
    → and finally a TAMPER is simulated so the system flags it.

Invoke via `POST /demo/run` or `python -m bels.demo`.
"""
from __future__ import annotations

import json
from typing import Any, Dict

from .models import CustodyAction, EvidenceType
from .reporting import reporter
from .service import service


def run_demo() -> Dict[str, Any]:
    steps = []

    # 1. A fraud complaint opens a case.
    case = service.create_case(
        title="Suspected mule-network laundering — complaint #FIR-2271",
        description="Customer reported unauthorised fan-out transfers across 6 accounts.",
        owner="investigator.rao",
    )
    cid = case["case_id"]
    steps.append({"step": "case_opened", "case_id": cid})

    # 2. Evidence uploaded (a transaction-record export + a screenshot + a report).
    txn_csv = (b"txn_id,from,to,amount,rail,timestamp\n"
               b"T1,ACC1001,ACC2002,480000,IMPS,2026-06-20T10:01:00Z\n"
               b"T2,ACC2002,ACC3003,475000,UPI,2026-06-20T10:03:00Z\n"
               b"T3,ACC3003,ACC4004,470000,UPI,2026-06-20T10:06:00Z\n")
    ev1 = service.upload_evidence("transactions_FIR2271.csv", txn_csv, cid,
                                  owner="investigator.rao",
                                  evidence_type=EvidenceType.TRANSACTION_RECORD,
                                  metadata={"source": "core-banking export"})

    report_pdf = b"%PDF-1.4 fake-investigation-report INTERNAL ONLY"  # stand-in artifact
    ev2 = service.upload_evidence("investigation_report.pdf", report_pdf, cid,
                                  owner="investigator.rao",
                                  evidence_type=EvidenceType.REPORT)
    steps.append({"step": "evidence_uploaded", "evidence_ids": [ev1.evidence_id, ev2.evidence_id]})

    # 3. Reviewed + verified (blockchain proof).
    service.record_custody(ev1.evidence_id, CustodyAction.REVIEW, "auditor.menon", "auditor",
                           "Reviewed transaction export against complaint")
    v1 = service.verify(ev1.evidence_id, actor="auditor.menon", role="auditor")
    steps.append({"step": "verified", "evidence_id": ev1.evidence_id, "outcome": v1.outcome.value})

    # 4. Shared with compliance + exported.
    service.record_custody(ev1.evidence_id, CustodyAction.SHARE, "auditor.menon", "auditor",
                           "Shared with compliance team")
    service.record_custody(ev1.evidence_id, CustodyAction.EXPORT, "compliance.iyer", "compliance",
                           "Exported for SAR filing")

    # 5. Simulate TAMPERING of the stored file, then re-verify → system flags it.
    tampered_path = service.provider  # noqa: F841  (keep provider warm)
    from .evidence_storage import evidence_store
    fp = evidence_store.file_path(ev2.evidence_id)
    tamper_detected = None
    if fp:
        fp.write_bytes(report_pdf + b" ALTERED-BY-INSIDER")
        v2 = service.verify(ev2.evidence_id, actor="auditor.menon", role="auditor")
        tamper_detected = v2.outcome.value
        steps.append({"step": "tamper_check", "evidence_id": ev2.evidence_id, "outcome": v2.outcome.value})

    # 6. Reports.
    audit_report = reporter.blockchain_audit()
    timeline = reporter.case_timeline(cid)

    return {
        "ok": True,
        "narrative": "Fraud complaint → evidence anchored → verified → custody tracked "
                     "→ tamper detected → audit report generated.",
        "case_id": cid,
        "evidence": [ev1.evidence_id, ev2.evidence_id],
        "verification_clean": v1.outcome.value,
        "tamper_detected": tamper_detected,
        "blockchain_status": service.blockchain_status(),
        "chain_integrity": service.chain_integrity(),
        "audit_report_evidence_count": audit_report["evidence_count"],
        "case_timeline_events": len(timeline.get("timeline", [])),
        "steps": steps,
    }


if __name__ == "__main__":
    print(json.dumps(run_demo(), indent=2, default=str))
