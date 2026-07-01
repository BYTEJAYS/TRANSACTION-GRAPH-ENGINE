# BELS — API Reference

Base URL (standalone): `http://localhost:8200`
When mounted in the TGIE backend, prefix every path with `/bels`.

All privileged actions take an `actor` and `role`; RBAC roles are
`admin · investigator · auditor · compliance · viewer`.

## Evidence
### `POST /evidence/upload` — multipart/form-data
Upload, hash, anchor and open chain of custody in one call.
| field | type | notes |
|-------|------|-------|
| `file` | file | the evidence artifact (required) |
| `case_id` | str | required |
| `owner` | str | default `system` |
| `role` | str | default `investigator` |
| `evidence_type` | str | optional; auto-classified otherwise |
| `metadata` | str | optional JSON string |

Returns the full evidence record (id, hash, status, block coordinates).

### `POST /evidence/register` — application/json
Anchor an already-hashed artifact (no file). Body: `RegisterRequest`
`{file_hash, case_id, filename, evidence_type, owner, role, metadata}`.

### `POST /evidence/verify` — multipart/form-data
`{evidence_id, file?, actor, role}`. Omit `file` to verify the stored copy.
Returns `{outcome, on_chain_hash, computed_hash, chain_integrity_ok, message, verification_tx_id}`.
Outcomes: `VERIFIED · TAMPERED · MISSING · CORRUPTED`.

### `POST /evidence/verify-hash` — application/json
`{evidence_id, file_hash, actor, role}` — verify by supplying a hash directly.

### `GET /evidence` — list all records (newest first)
### `GET /evidence/{id}` — single record
### `GET /evidence/{id}/certificate` — verification certificate (JSON)
### `GET /evidence/audit/{id}` — raw on-chain trail
### `GET /evidence/custody/{id}` — rendered custody timeline
### `POST /evidence/custody/{id}` — append custody event `{action, actor, role, detail}`

## Blockchain
### `GET /blockchain/status` — provider, height, blocks, head hash + integrity
### `GET /blockchain/transaction/{txid}` — tx + block + confirmations
### `GET /blockchain/integrity` — full ledger re-validation

## Cases
### `POST /cases` — `{title, description, owner, role}`
### `GET /cases` — list with evidence counts
### `GET /cases/{case_id}` — case + nested evidence

## Reports
### `GET /reports/{report_type}?fmt=json|csv|pdf&evidence_id=&case_id=`
`report_type` ∈ `evidence_verification · chain_of_custody · case_timeline ·
blockchain_audit · integrity_verification`.
PDF/CSV download; JSON inline.

## UB forensic intelligence
### `POST /ub/ask` — `{question}` → `{answer, data}`

## Ops
### `GET /audit-log?limit=` — operational audit (SOC)
### `POST /demo/run` — run the full bank demonstration workflow
### `GET /health` — liveness

## Example
```bash
CID=$(curl -s -X POST localhost:8200/cases -H 'Content-Type: application/json' \
  -d '{"title":"FIR-2271","owner":"rao"}' | jq -r .case_id)
EID=$(curl -s -X POST localhost:8200/evidence/upload \
  -F file=@statement.pdf -F case_id=$CID -F owner=rao | jq -r .evidence_id)
curl -s -X POST localhost:8200/evidence/verify -F evidence_id=$EID | jq .outcome   # VERIFIED
curl -s "localhost:8200/reports/chain_of_custody?evidence_id=$EID&fmt=pdf" -o custody.pdf
```
