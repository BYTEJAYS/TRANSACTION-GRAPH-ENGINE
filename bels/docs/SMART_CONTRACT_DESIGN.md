# BELS — Smart Contract Design

The reference contract is `bels/smart_contracts/EvidenceRegistry.sol` (Solidity
^0.8.20). The Python mirror is `bels/smart_contracts/contract_interface.py`, which exposes
the identical function names over whichever `BlockchainProvider` is active. This 1:1
mirroring is what makes the demo→bank migration a configuration change.

## On-chain data model
```solidity
struct Evidence {
    bytes32 fileHash;        // SHA-256 of the file (NEVER the file itself)
    bytes32 metadataHash;    // digest of the off-chain metadata manifest
    string  caseId;
    string  evidenceId;
    address owner;
    Status  status;          // None|Registered|Verified|Tampered|Archived
    uint256 timestamp;
    uint256 verificationCount;
    bool    exists;
}
struct CustodyEvent { string action; address actor; string detail; uint256 timestamp; }
```

## Functions
| Function | Purpose | Mirror (Python) |
|----------|---------|-----------------|
| `registerEvidence(evidenceId, caseId, fileHash, metadataHash)` | Anchor new evidence; reverts on duplicate ID | `EvidenceRegistry.registerEvidence(...)` |
| `verifyEvidence(evidenceId, candidateHash) → bool` | Compare a hash to the anchor; records the attempt; flips status to Verified/Tampered | `verifyEvidence(...)` |
| `updateCustody(evidenceId, action, detail)` | Append an immutable custody event | `updateCustody(...)` |
| `getEvidenceRecord(evidenceId)` | Read the full record | `getEvidenceRecord(...)` |
| `getAuditTrail(evidenceId)` | Read the ordered custody/audit trail | `getAuditTrail(...)` |

## Events
`EvidenceRegistered`, `EvidenceVerified`, `CustodyUpdated` — these are what an indexer or
the bank's SIEM subscribes to.

## Security properties
- **Immutability**: records are append-only; there is no update/delete of a `fileHash`.
- **Idempotent registration**: duplicate `evidenceId` reverts, preventing overwrite.
- **Tamper status is sticky**: once `verifyEvidence` sees a mismatch, status → `Tampered`.
- **Provenance**: `msg.sender` (the registrant/verifier) is recorded per event. In the
  internal provider this is captured as the signed `actor` + Ed25519 signature.

## Gas / cost note
Only fixed-size fields (two `bytes32`, small strings, counters) are written, so per-anchor
cost is bounded and predictable — critical for a bank operating at scale. Bulk anchoring
can batch multiple evidence hashes under one Merkle root if cost optimisation is required.

## Compiling & deploying (production)
```bash
solc --abi --bin bels/smart_contracts/EvidenceRegistry.sol -o build/
# deploy build/EvidenceRegistry.bin to the target EVM network, then set:
#   BELS_PROVIDER=ethereum
#   BELS_ETH_RPC_URL / BELS_ETH_CONTRACT / BELS_ETH_PRIVATE_KEY
```
`EthereumProvider._connect()` is the single integration point to wire the ABI.
