# BELS — Bank Integration Guide

This guide covers moving BELS from the bundled demonstration ledger to a bank-owned or
RBI-approved blockchain, and integrating it with existing bank systems.

## 1. The migration seam
All of BELS talks only to the `BlockchainProvider` interface
(`bels/blockchain_ledger/provider.py`). Two providers ship:

- `internal` — bundled hash-linked PoW ledger (default, demo).
- `ethereum` — adapter for any EVM chain (Ethereum, Polygon, Hyperledger Besu, or a
  consortium/bank chain).

Switching is configuration only:
```bash
export BELS_PROVIDER=ethereum
export BELS_ETH_RPC_URL="https://<bank-rpc-endpoint>"
export BELS_ETH_CONTRACT="0x<deployed EvidenceRegistry address>"
export BELS_ETH_PRIVATE_KEY="<service signer key, from HSM/KMS in prod>"
```

## 2. Deploy the smart contract
1. Compile `bels/smart_contracts/EvidenceRegistry.sol` (`solc ^0.8.20`).
2. Deploy to the target network (testnet first).
3. Wire the ABI in `EthereumProvider._connect()` and implement the write/read methods
   (`registerEvidence`, `updateCustody`, `verifyEvidence`, `getEvidenceRecord`,
   `getAuditTrail`) against `web3` — each maps 1:1 to a contract function.

## 3. Recommended production hardening
- **Keys**: replace the local Ed25519/HMAC signer with the bank HSM/KMS; never store
  private keys on disk.
- **Storage**: replace `evidence_storage/` with the bank's WORM object store or IPFS
  cluster; keep it content-addressed by SHA-256.
- **RBAC**: map `bels/security.py` roles (admin/investigator/auditor/compliance/viewer)
  onto the bank IAM/AD groups; enforce at the API gateway.
- **Network**: deploy behind the bank API gateway with mTLS; restrict `BELS_ALLOWED_ORIGINS`.
- **Audit**: ship `operational_audit.log.jsonl` to the SIEM.

## 4. TGIE integration
BELS exposes `bels.api.router`. To run in-process inside the main TGIE backend:
```python
from bels.api import router as bels_router
app.include_router(bels_router, prefix="/bels")
```
A TGIE fraud investigation can then: create a case, attach evidence (file or alert hash),
register/anchor it, verify it, and pull audit/timeline reports — all over the same API.

To anchor a fraud alert that has no file, use `POST /evidence/register` with the
artifact's SHA-256 (e.g. the hash of the serialised alert/graph snapshot).

## 5. UB (forensic intelligence) integration
`POST /ub/ask {"question": "..."}` answers: *show evidence for case …*, *verify evidence
…*, *explain chain of custody …*, *summarize investigation timeline …*, *generate audit
summary*, *blockchain verification result …*. It returns `{answer, data}` so UB can speak
the `answer` and render the structured `data`.

## 6. RBI / compliance alignment
- Immutable, timestamped, independently verifiable records support evidentiary integrity.
- Chain of custody supports investigative due-process requirements.
- Forensic reports (PDF/JSON/CSV) provide regulator-ready artifacts.
- A private/permissioned chain keeps data within the bank's regulatory boundary; no
  customer data or files ever leave to a public network (only hashes are anchored — and
  even those stay on the private chain in production).
