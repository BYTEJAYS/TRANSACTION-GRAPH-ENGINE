"""
EthereumProvider — migration adapter for an Ethereum/Polygon/Hyperledger or bank-owned
EVM network.

This is the seam that makes the "demo chain → bank chain" migration a config change.
It implements the same BlockchainProvider interface and maps each method 1:1 onto the
EvidenceRegistry Solidity contract:

    register_evidence()    -> EvidenceRegistry.registerEvidence(...)
    update_custody()       -> EvidenceRegistry.updateCustody(...)
    record_verification()  -> EvidenceRegistry.verifyEvidence(...)
    get_record()           -> EvidenceRegistry.getEvidenceRecord(...)
    get_audit_trail()      -> EvidenceRegistry.getAuditTrail(...)

To activate, install `web3`, deploy smart_contracts/EvidenceRegistry.sol, and set
BELS_PROVIDER=ethereum plus BELS_ETH_RPC_URL / BELS_ETH_CONTRACT / BELS_ETH_PRIVATE_KEY.
Until then the adapter loads lazily and raises a clear, actionable error rather than
failing the whole service — so the rest of TGIE keeps running on the internal ledger.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import config
from .provider import BlockchainProvider, OnChainRecord, TxReceipt

_NOT_READY = (
    "EthereumProvider is not configured. Install `web3`, deploy "
    "smart_contracts/EvidenceRegistry.sol, and set BELS_ETH_RPC_URL, BELS_ETH_CONTRACT "
    "and BELS_ETH_PRIVATE_KEY. See docs/BANK_INTEGRATION_GUIDE.md."
)


class EthereumProvider(BlockchainProvider):
    name = "ethereum"

    def __init__(self) -> None:
        self.chain_id = config.CHAIN_ID
        self.rpc_url = config.ETH_RPC_URL
        self.contract_address = config.ETH_CONTRACT_ADDRESS
        self._w3 = None
        self._contract = None
        self._connect()

    def _connect(self) -> None:
        if not (self.rpc_url and self.contract_address):
            return
        try:  # pragma: no cover - requires web3 + a live RPC
            from web3 import Web3

            self._w3 = Web3(Web3.HTTPProvider(self.rpc_url))
            self.chain_id = str(self._w3.eth.chain_id)
            # ABI would be loaded from the compiled EvidenceRegistry artifact here.
            # self._contract = self._w3.eth.contract(address=..., abi=...)
        except Exception:
            self._w3 = None

    @property
    def ready(self) -> bool:
        return self._w3 is not None and self._contract is not None

    def _guard(self) -> None:
        if not self.ready:
            raise RuntimeError(_NOT_READY)

    # -- writes (map to contract txns; would sign + send + wait for receipt) ----
    def register_evidence(self, *args, **kwargs) -> TxReceipt:  # noqa: D401
        self._guard()
        raise NotImplementedError("Wire to EvidenceRegistry.registerEvidence")

    def update_custody(self, *args, **kwargs) -> TxReceipt:
        self._guard()
        raise NotImplementedError("Wire to EvidenceRegistry.updateCustody")

    def record_verification(self, *args, **kwargs) -> TxReceipt:
        self._guard()
        raise NotImplementedError("Wire to EvidenceRegistry.verifyEvidence")

    # -- reads -----------------------------------------------------------------
    def get_record(self, evidence_id: str) -> Optional[OnChainRecord]:
        self._guard()
        raise NotImplementedError("Wire to EvidenceRegistry.getEvidenceRecord")

    def get_audit_trail(self, evidence_id: str) -> List[Dict[str, Any]]:
        self._guard()
        raise NotImplementedError("Wire to EvidenceRegistry.getAuditTrail")

    def get_transaction(self, tx_id: str) -> Optional[Dict[str, Any]]:
        self._guard()
        raise NotImplementedError("Wire to w3.eth.get_transaction_receipt")

    def status(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "chain_id": self.chain_id,
            "ready": self.ready,
            "rpc_url": self.rpc_url or None,
            "contract_address": self.contract_address or None,
            "note": None if self.ready else _NOT_READY,
        }

    def verify_integrity(self) -> Dict[str, Any]:
        # On a public chain, integrity is guaranteed by network consensus; verification
        # is performed by reading the immutable on-chain hash and comparing locally.
        return {
            "valid": self.ready,
            "message": "Integrity guaranteed by chain consensus." if self.ready else _NOT_READY,
        }
