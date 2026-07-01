"""
CustodyEngine — records and reconstructs the chain of custody.

Every custody action (upload, review, access, export, transfer, share, archive,
verify) is anchored as an immutable CUSTODY transaction on the ledger. The blockchain
is the single source of truth; this engine signs each event and renders the ordered,
verifiable timeline that investigators and auditors read.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..blockchain_ledger import get_provider
from ..blockchain_ledger.provider import TxReceipt
from ..models import CustodyAction
from ..security import signer, sha256_of_obj, utc_now_iso


class CustodyEngine:
    def __init__(self) -> None:
        self._provider = get_provider()

    def record(self, evidence_id: str, action: CustodyAction | str, actor: str,
               detail: str = "") -> TxReceipt:
        """Sign and anchor one custody event. Returns the on-chain receipt."""
        act = action.value if isinstance(action, CustodyAction) else str(action)
        message = sha256_of_obj({
            "evidence_id": evidence_id, "action": act, "actor": actor,
            "detail": detail, "ts": utc_now_iso(),
        })
        signature = signer.sign(message)
        return self._provider.update_custody(evidence_id, act, actor, detail, signature)

    def timeline(self, evidence_id: str) -> List[Dict[str, Any]]:
        """Ordered custody timeline reconstructed from the immutable ledger."""
        events: List[Dict[str, Any]] = []
        for tx in self._provider.get_audit_trail(evidence_id):
            label = tx["type"]
            payload = tx["payload"]
            if tx["type"] == "CUSTODY":
                label = payload.get("action", "CUSTODY")
                summary = payload.get("detail") or label.title()
                actor = payload.get("actor", "system")
            elif tx["type"] == "REGISTER":
                label = "REGISTER"
                summary = f"Evidence registered & anchored (case {payload.get('case_id','?')})"
                actor = payload.get("owner", "system")
            else:  # VERIFY
                label = "VERIFY"
                summary = f"Integrity check → {payload.get('outcome','?')}"
                actor = payload.get("actor", "system")
            events.append({
                "action": label,
                "actor": actor,
                "summary": summary,
                "timestamp": tx["timestamp"],
                "tx_id": tx["tx_id"],
                "block_index": tx["block_index"],
                "block_hash": tx["block_hash"],
            })
        return events


custody_engine = CustodyEngine()
