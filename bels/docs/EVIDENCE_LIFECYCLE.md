# BELS — Evidence Lifecycle

## Upload flow (9 steps)
Implemented in `bels/service.py → BELSService.upload_evidence()`.

1. **Upload** — investigator submits a file (`POST /evidence/upload`).
2. **Evidence ID** — `EV-YYYYMMDD-XXXXXXXX` generated.
3. **SHA-256** — computed over the raw bytes.
4. **Metadata** — size, MIME type, evidence type (auto-classified by extension),
   uploader and any user metadata are captured; a metadata digest is taken.
5. **Timestamp** — UTC ISO-8601 at registration.
6. **Blockchain transaction** — `EvidenceRegistry.registerEvidence()` anchors the hash.
7. **Transaction hash stored** — receipt (`tx_id`, `block_index`, `block_hash`) retained.
8. **Secure storage** — file written to `evidence_storage/<id>/` with a manifest sidecar.
9. **Certificate** — a verification certificate JSON is generated.

Result: the evidence is **tamper-evident**.

## Supported evidence types
PDF · Images · Screenshots · Audio · Video · Logs · CSV · JSON · Transaction records ·
Investigation reports · Other. (Auto-classified; override with the `evidence_type` field.)

## Status model
```
REGISTERED ──verify(match)──► VERIFIED
     │                            │
     └──────verify(mismatch)──────┴──► TAMPERED   (sticky)
                                  │
                              archive ──► ARCHIVED
```

## Verification flow
Implemented in `bels/verification_engine/verifier.py`.
1. Obtain a hash to check — a re-uploaded file, a supplied hash, or the stored file.
2. Retrieve the anchored record from the chain.
3. Compare on-chain hash vs computed hash.
4. Re-validate the **whole ledger's** integrity (so a forged record can't pass).
5. Anchor the verification result back on-chain.

Outcomes: **VERIFIED · TAMPERED · MISSING · CORRUPTED**.

- `VERIFIED` — hash matches and ledger is intact.
- `TAMPERED` — hash mismatch (file altered) or ledger integrity broken.
- `MISSING` — no on-chain record for that evidence ID.
- `CORRUPTED` — record exists on-chain but the off-chain file is unreadable/gone.

## Retrieval
- `GET /evidence` — list all records (newest first).
- `GET /evidence/{id}` — single record + block coordinates.
- `GET /evidence/{id}/certificate` — verification certificate.

## Off-chain storage layout
```
evidence_storage/
└── EV-YYYYMMDD-XXXXXXXX/
    ├── <original_filename>        ← the artifact
    └── manifest.json              ← size, sha256, mime, type, metadata_hash, stored_at
```
This layer is content-addressed and can be replaced by IPFS or an S3 object store behind
the same `EvidenceStore` interface without touching the chain logic.
