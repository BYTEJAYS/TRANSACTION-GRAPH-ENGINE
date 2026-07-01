"""
BlockchainProvider — the seam that decouples BELS from any specific chain.

Every concrete provider (internal ledger, Ethereum/Polygon, Hyperledger, a bank-owned
network) implements this interface. The rest of BELS only ever talks to this contract,
so migrating chains is a configuration change, not a redesign.

The method surface deliberately mirrors the EvidenceRegistry smart contract
(registerEvidence / updateCustody / verifyEvidence / getEvidenceRecord / getAuditTrail).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class TxReceipt:
    """Proof that an anchor operation was committed to the chain."""
    tx_id: str
    tx_type: str            # REGISTER | CUSTODY | VERIFY
    evidence_id: str
    block_index: int
    block_hash: str
    timestamp: str
    confirmations: int
    provider: str
    chain_id: str
    anchored_hash: str      # the SHA-256 that was anchored (file or event digest)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OnChainRecord:
    """
    The materialised evidence record as stored by the smart contract / ledger.
    Rebuilt deterministically from the chain's event history (event sourcing).
    """
    evidence_id: str
    file_hash: str
    case_id: str
    owner: str
    status: str
    timestamp: str
    metadata_hash: str
    verification_count: int
    custody_event_count: int
    last_tx_id: str
    signature: str = ""
    signer_key_id: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BlockchainProvider(ABC):
    """Abstract anchoring backend. Concrete subclasses must be deterministic."""

    name: str = "abstract"
    chain_id: str = "unknown"

    # -- writes ----------------------------------------------------------------
    @abstractmethod
    def register_evidence(
        self,
        evidence_id: str,
        file_hash: str,
        case_id: str,
        owner: str,
        metadata_hash: str,
        signature: str,
        signer_key_id: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> TxReceipt:
        ...

    @abstractmethod
    def update_custody(
        self,
        evidence_id: str,
        action: str,
        actor: str,
        detail: str,
        signature: str,
    ) -> TxReceipt:
        ...

    @abstractmethod
    def record_verification(
        self,
        evidence_id: str,
        outcome: str,
        actor: str,
        computed_hash: str,
    ) -> TxReceipt:
        ...

    # -- reads -----------------------------------------------------------------
    @abstractmethod
    def get_record(self, evidence_id: str) -> Optional[OnChainRecord]:
        ...

    @abstractmethod
    def get_audit_trail(self, evidence_id: str) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def get_transaction(self, tx_id: str) -> Optional[Dict[str, Any]]:
        ...

    @abstractmethod
    def status(self) -> Dict[str, Any]:
        ...

    @abstractmethod
    def verify_integrity(self) -> Dict[str, Any]:
        ...

    def list_evidence_ids(self) -> List[str]:  # optional convenience
        return []
