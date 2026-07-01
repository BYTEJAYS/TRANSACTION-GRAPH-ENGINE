# ⛓ BELS — TGIE Blockchain Evidence Ledger System

An immutable, blockchain-anchored fraud-evidence registry, verification and
chain-of-custody platform for the TGIE ecosystem.

It proves, for any piece of evidence, that it **existed at a time**, **has not been
altered**, **is traceable**, and **can be independently verified** — without ever
storing the file on-chain. Only the SHA-256 hash, identifiers, metadata digest,
signatures and custody events are anchored.

## Quick start
```bash
cd ~/Desktop/TGIE
python3 -m bels.main          # → http://localhost:8200  (dashboard at /)
# then click "▶ Bank Demo" in the dashboard, or:
curl -X POST localhost:8200/demo/run
```
No external services required — the default provider is a self-contained, tamper-evident
hash-linked proof-of-work ledger.

## What you get
| Module | Path | Role |
|--------|------|------|
| Blockchain layer | `blockchain_ledger/` | `BlockchainProvider` + internal ledger + EVM adapter |
| Smart contract | `smart_contracts/` | `EvidenceRegistry.sol` + Python mirror |
| Off-chain storage | `evidence_storage/` | content-addressed file store |
| Chain of custody | `chain_of_custody/` | immutable handling trail |
| Verification | `verification_engine/` | VERIFIED/TAMPERED/MISSING/CORRUPTED |
| API | `api.py` / `main.py` | FastAPI service |
| Dashboard | `dashboard/index.html` | matte-black banking UI |
| Reporting | `reporting/` | PDF · JSON · CSV forensic reports |
| UB layer | `ub_integration.py` | natural-language forensic Q&A |
| Demo | `demo.py` | live bank demonstration workflow |
| Docs | `docs/` | architecture, contract, custody, lifecycle, bank guide, API |

## Proven by the bundled demo
fraud complaint → evidence uploaded → registered & anchored → verified (proof) →
chain of custody tracked → **tamper simulated and detected** → audit report generated.

## Configuration (env)
| var | default | meaning |
|-----|---------|---------|
| `BELS_PROVIDER` | `internal` | `internal` or `ethereum` |
| `BELS_PORT` | `8200` | API port |
| `BELS_POW_DIFFICULTY` | `3` | internal-ledger proof-of-work strength |
| `BELS_EVIDENCE_DIR` | `../evidence_storage` | off-chain file store |
| `BELS_ETH_RPC_URL` / `BELS_ETH_CONTRACT` / `BELS_ETH_PRIVATE_KEY` | – | EVM migration |

## Migrating to a bank / RBI chain
Deploy `EvidenceRegistry.sol`, set `BELS_PROVIDER=ethereum` + the RPC/contract/key vars.
No application code changes — see `docs/BANK_INTEGRATION_GUIDE.md`.

## Integrate into the TGIE backend
```python
from bels.api import router as bels_router
app.include_router(bels_router, prefix="/bels")
```
