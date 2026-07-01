"""
VerificationEngine — independently proves whether evidence is intact.

Process:
  1. Obtain a hash to check — either a freshly uploaded file, or the file currently
     held in the off-chain store.
  2. Retrieve the anchored record from the blockchain.
  3. Compare the on-chain hash with the computed hash.
  4. Re-validate the ledger's own integrity (so a forged record can't pass).
  5. Anchor the verification result back onto the chain (itself a custody event).

Outcomes: VERIFIED, TAMPERED, MISSING, CORRUPTED.
"""
from __future__ import annotations

from typing import Optional

from ..blockchain_ledger import get_provider
from ..evidence_storage import evidence_store
from ..models import VerificationOutcome, VerifyResultOut
from ..security import sha256_hex, utc_now_iso


class VerificationEngine:
    def __init__(self) -> None:
        self._provider = get_provider()

    def verify(self, evidence_id: str, uploaded: Optional[bytes] = None,
               provided_hash: Optional[str] = None, actor: str = "system",
               anchor_result: bool = True) -> VerifyResultOut:
        record = self._provider.get_record(evidence_id)
        if record is None:
            return VerifyResultOut(
                evidence_id=evidence_id, outcome=VerificationOutcome.MISSING,
                on_chain_hash=None, computed_hash=None, chain_integrity_ok=True,
                message="No blockchain record exists for this evidence ID.",
                verified_at=utc_now_iso(),
            )

        # Decide which hash we are checking against the chain.
        if uploaded is not None:
            computed = sha256_hex(uploaded)
            source = "uploaded file"
        elif provided_hash is not None:
            computed = provided_hash.lower().strip()
            source = "provided hash"
        else:
            computed = evidence_store.current_hash(evidence_id)
            source = "stored file"
            if computed is None:
                # Record exists on-chain but the off-chain artifact is gone.
                return VerifyResultOut(
                    evidence_id=evidence_id, outcome=VerificationOutcome.CORRUPTED,
                    on_chain_hash=record.file_hash, computed_hash=None,
                    chain_integrity_ok=self._provider.verify_integrity().get("valid", False),
                    message="Stored file is missing or unreadable — cannot recompute hash.",
                    verified_at=utc_now_iso(),
                )

        integrity = self._provider.verify_integrity()
        chain_ok = bool(integrity.get("valid", False))
        match = (computed == record.file_hash)

        if match and chain_ok:
            outcome = VerificationOutcome.VERIFIED
            message = f"Hash of {source} matches the on-chain anchor; ledger intact."
        elif not match:
            outcome = VerificationOutcome.TAMPERED
            message = (f"Hash mismatch: {source} does not match the anchored hash. "
                       f"Evidence has been altered since registration.")
        else:
            outcome = VerificationOutcome.TAMPERED
            message = f"Ledger integrity failure: {integrity.get('message','')}"

        tx_id = None
        if anchor_result:
            receipt = self._provider.record_verification(evidence_id, outcome.value, actor, computed)
            tx_id = receipt.tx_id

        return VerifyResultOut(
            evidence_id=evidence_id, outcome=outcome,
            on_chain_hash=record.file_hash, computed_hash=computed,
            chain_integrity_ok=chain_ok, message=message,
            verified_at=utc_now_iso(), verification_tx_id=tx_id,
        )


verification_engine = VerificationEngine()
