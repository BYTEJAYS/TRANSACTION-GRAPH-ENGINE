# BELS — Blockchain Architecture

## Purpose
The Blockchain Evidence Ledger System (BELS) cryptographically anchors fraud evidence so
that four properties can be proven to a court, auditor or regulator:

1. **Existence** — the evidence existed at a specific time.
2. **Integrity** — the evidence has not been altered since.
3. **Traceability** — every access/handling event is recorded.
4. **Independent verification** — any party can re-check the proof.

## Core principle — never store files on-chain
```
Evidence File ──► SHA-256 Hash ──► Blockchain Transaction ──► Immutable Ledger Record
```
On-chain we store only: file hash, timestamp, case ID, evidence ID, metadata digest,
digital signature, and chain-of-custody events. The **file itself** lives in the
off-chain `evidence_storage/` content-addressed layer (IPFS/S3-swappable).

## Layered design
```
┌──────────────────────────────────────────────────────────────┐
│ blockchain_dashboard (matte-black UI)  ·  UB forensic layer   │
├──────────────────────────────────────────────────────────────┤
│ blockchain_api (FastAPI)  ·  reporting  ·  verification_engine │
├──────────────────────────────────────────────────────────────┤
│ service.py orchestrator  ·  chain_of_custody  ·  smart_contracts│
├──────────────────────────────────────────────────────────────┤
│            BlockchainProvider  (the migration seam)            │
│   ┌────────────────────┐         ┌──────────────────────────┐ │
│   │ InternalChainProvider│  OR    │ EthereumProvider (EVM)   │ │
│   │  (default, no deps)  │        │ Polygon/Hyperledger/bank │ │
│   └────────────────────┘         └──────────────────────────┘ │
├──────────────────────────────────────────────────────────────┤
│ evidence_storage (off-chain, content-addressed)               │
└──────────────────────────────────────────────────────────────┘
```

## The internal ledger (default provider)
A real, self-contained, tamper-evident chain — chosen so the demo runs with **zero
external dependencies, zero gas, and no network**, while still demonstrating every
cryptographic property a public chain would.

- **Blocks** are hash-linked via `prev_hash`.
- Each block carries a **Merkle root** over its transactions.
- Blocks are **sealed with proof-of-work** (configurable leading-zero difficulty,
  `BELS_POW_DIFFICULTY`).
- The ledger is persisted as append-only JSONL (`bels/data/ledger.jsonl`).
- `verify_integrity()` re-derives every block hash, Merkle root, PoW target and link.
  **Altering any record changes its hash, which breaks every subsequent block** — this is
  what makes tampering detectable.

### Transaction types
| type     | emitted by            | anchors                                  |
|----------|-----------------------|------------------------------------------|
| REGISTER | evidence registration | file hash, case/evidence id, metadata, signature |
| CUSTODY  | chain-of-custody      | action, actor, detail, signature         |
| VERIFY   | verification engine   | outcome, actor, recomputed hash          |

The materialised evidence record (status, verification count, custody count) is rebuilt
deterministically from this event history (event sourcing), exactly as the Solidity
contract would maintain it in storage.

## Migration path
The entire platform talks only to `BlockchainProvider`. Swapping the demo ledger for a
bank-owned / RBI-approved EVM network means: deploy `EvidenceRegistry.sol`, set
`BELS_PROVIDER=ethereum` + RPC/contract/key env vars. No application code changes.
See `BANK_INTEGRATION_GUIDE.md`.
