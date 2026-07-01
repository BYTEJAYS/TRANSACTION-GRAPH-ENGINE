"""
UB integration — the forensic-intelligence layer.

Exposes a small natural-language router so UB (the TGIE voice/RAG copilot) can answer
evidence questions by calling structured BELS reads. It is intentionally rule-based (no
LLM dependency) so it runs offline and deterministically; UB can wrap richer phrasing
around the structured `data` returned here.

Recognised intents:
  • "show evidence for case <id>"
  • "verify evidence <id>"  /  "verify evidence status <id>"
  • "explain chain of custody <id>"
  • "summarize investigation timeline <case>"
  • "audit summary"  /  "generate audit summary"
  • "blockchain verification result <id>"
"""
from __future__ import annotations

import re
from typing import Any, Dict

from .reporting import reporter
from .service import service

_EVID = re.compile(r"(EV-\d{8}-[A-Z0-9]{8})", re.I)
_CASE = re.compile(r"(CASE-\d{8}-[A-Z0-9]{6})", re.I)


def _first(pattern: re.Pattern, text: str) -> str | None:
    m = pattern.search(text)
    return m.group(1).upper() if m else None


class BELSForensicIntelligence:
    def answer(self, question: str) -> Dict[str, Any]:
        q = question.strip()
        ql = q.lower()
        eid = _first(_EVID, q)
        cid = _first(_CASE, q)

        if "custody" in ql and eid:
            events = service.get_custody(eid)
            return self._wrap(
                f"Chain of custody for {eid}: {len(events)} immutable events, from "
                f"'{events[0]['action']}' to '{events[-1]['action']}'." if events
                else f"No custody record found for {eid}.",
                {"evidence_id": eid, "custody_events": events})

        if "verify" in ql and eid:
            result = service.verify(eid, actor="UB", role="auditor")
            return self._wrap(
                f"Verification of {eid}: {result.outcome.value}. {result.message}",
                {"verification": result.model_dump()})

        if "timeline" in ql and cid:
            report = reporter.case_timeline(cid)
            n = len(report.get("timeline", []))
            return self._wrap(
                f"Investigation {cid}: {report.get('evidence_count',0)} evidence items, "
                f"{n} custody events across the case timeline.",
                report)

        if "evidence" in ql and cid:
            case = service.get_case(cid)
            if not case:
                return self._wrap(f"No case {cid} found.", {})
            items = ", ".join(case["evidence_ids"]) or "none"
            return self._wrap(
                f"Case {cid} ('{case['title']}') holds {len(case['evidence_ids'])} "
                f"evidence items: {items}.", {"case": case})

        if "audit" in ql:
            report = reporter.blockchain_audit()
            integ = report["integrity"]
            return self._wrap(
                f"Blockchain audit: {report['evidence_count']} evidence records anchored "
                f"across {report['blockchain_status']['blocks']} blocks. Ledger integrity: "
                f"{'INTACT' if integ.get('valid') else 'COMPROMISED'}.", report)

        if "blockchain" in ql and eid:
            rec = service.get_evidence(eid)
            if not rec:
                return self._wrap(f"No evidence {eid} on chain.", {})
            return self._wrap(
                f"{eid} is anchored in block {rec.block_index} "
                f"(tx {rec.anchor_tx_id[:14]}…), status {rec.status}.",
                {"evidence": rec.model_dump()})

        return self._wrap(
            "I can: show evidence for a case, verify evidence, explain chain of custody, "
            "summarize an investigation timeline, or generate an audit summary. "
            "Reference an EV- or CASE- id.", {"intents": [
                "show evidence for case <CASE-ID>", "verify evidence <EV-ID>",
                "explain chain of custody <EV-ID>", "summarize investigation timeline <CASE-ID>",
                "generate audit summary", "blockchain verification result <EV-ID>"]})

    @staticmethod
    def _wrap(answer: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return {"answer": answer, "data": data}


forensic_intelligence = BELSForensicIntelligence()
