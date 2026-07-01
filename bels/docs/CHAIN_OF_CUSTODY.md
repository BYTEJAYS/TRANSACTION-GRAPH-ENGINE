# BELS — Chain of Custody

Chain of custody is the legally defensible record of **who handled evidence, when, and
what they did**. In BELS every custody action is anchored as an immutable `CUSTODY`
transaction on the ledger, so the trail cannot be edited or back-dated.

## Tracked actions
| Action | Meaning |
|--------|---------|
| `UPLOAD` | Evidence first ingested into the store |
| `REGISTER` | Hash anchored on the blockchain |
| `REVIEW` | An analyst inspected the evidence |
| `ACCESS` | Evidence was read/opened |
| `VERIFY` | Integrity check performed (auto-anchored by the verification engine) |
| `EXPORT` | Evidence exported (e.g. for SAR filing) |
| `TRANSFER` | Ownership/handling transferred to another party |
| `SHARE` | Shared with another team (e.g. compliance) |
| `ARCHIVE` | Moved to archival; sets record status `Archived` |

## How an event is recorded
```
action + actor + detail + timestamp
        │
        ▼  SHA-256 digest
   Ed25519 / HMAC signature
        │
        ▼
  provider.update_custody(...)  →  sealed CUSTODY block  →  receipt
```
Code: `bels/chain_of_custody/custody.py` → `CustodyEngine.record()`.

## Reconstructing the timeline
`CustodyEngine.timeline(evidence_id)` reads the evidence's full audit trail from the
ledger and renders an ordered, human-readable sequence — each entry carries its
`tx_id`, `block_index` and `block_hash` so it is independently verifiable.

Example (from the bank demo):
```
REGISTER  · investigator.rao  Evidence registered & anchored (case CASE-…)   block #2
UPLOAD    · investigator.rao  Uploaded transactions_FIR2271.csv (…bytes)     block #3
REVIEW    · auditor.menon     Reviewed transaction export against complaint  block #5
VERIFY    · auditor.menon     Integrity check → VERIFIED                     block #6
SHARE     · auditor.menon     Shared with compliance team                    block #7
EXPORT    · compliance.iyer   Exported for SAR filing                        block #8
```

## Why it is tamper-proof
Because each event lives in a hash-linked, proof-of-work-sealed block, deleting or
re-ordering an event would break the ledger's `verify_integrity()` check. The custody
trail is therefore as strong as the chain itself.

## API
- `GET  /evidence/custody/{id}` — rendered timeline
- `POST /evidence/custody/{id}` — append an event `{action, actor, role, detail}`
- `GET  /evidence/audit/{id}` — raw on-chain trail (all REGISTER/CUSTODY/VERIFY txs)
