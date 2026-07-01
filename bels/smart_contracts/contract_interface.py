"""
EvidenceRegistry (Python) — the contract surface mirrored over the active provider.

This object exposes exactly the function names of EvidenceRegistry.sol so application
code calls the "smart contract" regardless of whether the active backend is the internal
ledger or a deployed Solidity contract. When BELS migrates to a real EVM chain, this
class is the only place that changes — it simply forwards to web3 contract calls.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..blockchain_ledger import get_provider
from ..blockchain_ledger.provider import OnChainRecord, TxReceipt
from ..security import signer


class EvidenceRegistry:
    def __init__(self) -> None:
        self._p = get_provider()

    # Solidity: registerEvidence(evidenceId, caseId, fileHash, metadataHash)
    def registerEvidence(self, evidence_id: str, case_id: str, file_hash: str,
                         metadata_hash: str, owner: str,
                         extra: Optional[Dict[str, Any]] = None) -> TxReceipt:
        signature = signer.sign(f"{evidence_id}|{file_hash}|{case_id}|{owner}")
        return self._p.register_evidence(
            evidence_id=evidence_id, file_hash=file_hash, case_id=case_id,
            owner=owner, metadata_hash=metadata_hash, signature=signature,
            signer_key_id=signer.public_key_id, extra=extra or {},
        )

    # Solidity: verifyEvidence(evidenceId, candidateHash) returns (bool)
    def verifyEvidence(self, evidence_id: str, candidate_hash: str, actor: str) -> TxReceipt:
        rec = self._p.get_record(evidence_id)
        matched = bool(rec and rec.file_hash == candidate_hash)
        outcome = "VERIFIED" if matched else "TAMPERED"
        return self._p.record_verification(evidence_id, outcome, actor, candidate_hash)

    # Solidity: updateCustody(evidenceId, action, detail)
    def updateCustody(self, evidence_id: str, action: str, actor: str, detail: str) -> TxReceipt:
        signature = signer.sign(f"{evidence_id}|{action}|{actor}")
        return self._p.update_custody(evidence_id, action, actor, detail, signature)

    # Solidity: getEvidenceRecord(evidenceId)
    def getEvidenceRecord(self, evidence_id: str) -> Optional[OnChainRecord]:
        return self._p.get_record(evidence_id)

    # Solidity: getAuditTrail(evidenceId)
    def getAuditTrail(self, evidence_id: str) -> List[Dict[str, Any]]:
        return self._p.get_audit_trail(evidence_id)


evidence_registry = EvidenceRegistry()
