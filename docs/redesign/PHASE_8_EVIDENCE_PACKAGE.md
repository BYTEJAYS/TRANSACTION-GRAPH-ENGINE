# Phase 8 — Evidence Package Generation (DESIGN DOC, for approval)

> Status: **APPROVED · Wave 1 BUILT & VERIFIED.** New: `evidence/packager.py` (15-section bundle from case enrich payload, canonical SHA-256, deterministic reportlab PDF), `evidence/fiu.py` (regulatory_summary + FIU-IND STR demo), `evidence/anchor.py` (BELS register/verify, graceful), `api/v1/evidence.py` (build/download.json/download.pdf/fiu/verify, auth + read-audit). Verified on seed case TGIE-2026-0001: 15 sections; **identical SHA-256 + stable package_id on rebuild** (deterministic); JSON 20KB + PDF 18KB rendered; verify=VERIFIED_LOCAL; FIU STR generated; BELS down → graceful `unanchored`; app boots with all 5 routes + legacy `/api/evidence/generate` preserved. Wave 2 (BELS custody lifecycle + on-chain verify round-trip + certificate + screenshots) pending `:8200` live.
> Sign-off: hash canonical JSON ✅ · FIU-IND STR demo ✅ · BELS graceful-optional ✅
> Builds on: case_management enrich payload (recovery/DNA/roles/graph_snapshot/timeline/raw-JSON already baked per case), `risk_engine`, Phase 4 detector evidence, Phase 5 ML `Explanation`, BELS service (`:8200`), Phase 7 Evidence Builder UI.
> Iron rule: **ONLY ADD / reuse.** Reuses `evidence/generator.py` (EvidenceGenerator), `evidence/pdf_builder.py` (reportlab), `case_management/bels_client.py`, and the BELS API — resurrecting the dormant `bling/evidence_packager` design. The existing `/api/evidence/generate` stays.

## 1. Goals
1. Produce a **server-side, regulator-grade evidence package** (not client screenshots) for any case — deterministic, complete, and **hash-anchored** with **chain-of-custody**.
2. Cover every Part 7 element + an **FIU/STR** templated output.
3. Anchor each package in **BELS** and record custody; make verification one call.
4. Degrade gracefully: works on the JSON case store + reportlab **without Docker**; BELS anchoring is best-effort (marked "unanchored" if `:8200` is down).

## 2. Why (Phase 1 finding)
Today evidence = client-side jsPDF/html2canvas screenshots — non-deterministic, unsigned, not court-grade. The robust `bling/evidence_packager.build_evidence_package()` + `trail_builder.reconstruct_fund_trail()` are unused, and BELS already does register/verify/certificate/custody. Phase 8 connects these into one server pipeline.

## 3. Bundle contents (Part 7, complete)
A package is a deterministic JSON document + a rendered PDF, sections:
1. **Case Summary** (id, title, status, priority, disposition, investigator)
2. **Timeline** (case `timeline` + event-store replay when available)
3. **Graph Snapshot** (verbatim `graph_snapshot` from the case — the rule per memory)
4. **Suspicious Accounts** (flagged nodes + roles from `account_roles`)
5. **Transactions** (from `raw_transaction_json`)
6. **Risk Score** (risk_engine assessment + factor breakdown)
7. **Fraud Pattern(s)** + **Reason** + **Confidence** (detector evidence)
8. **Supporting Rules** (which detectors fired, versions)
9. **ML Explanation** (Phase 5 `Explanation` — reason codes / SHAP)
10. **Graph Metrics** (centralities, component stats)
11. **Path Analysis** (fund trail via `trail_builder` design)
12. **Investigator Notes / Comments** (case `notes`/`comments`)
13. **Screenshots** (optional, uploaded from the Phase 7 Evidence Builder)
14. **Regulatory Summary** + **FIU/STR format**
15. **Integrity block**: canonical SHA-256, BELS anchor ref, custody chain, generated_by, generated_at

## 4. Architecture
```
backend/evidence/
  generator.py        # EXISTING — reused for narrative/reason/path
  pdf_builder.py      # EXISTING — reused (made deterministic: stable order, no volatile content in hash)
  packager.py         # NEW — EvidencePackager.build(case_id) -> bundle dict (assembles §3 from case store + risk + findings + ML)
  fiu.py              # NEW — render FIU-IND STR (demo) + generic regulatory JSON from the bundle
  anchor.py           # NEW — canonical JSON -> SHA-256 -> BELS register + custody (reuses case_management/bels_client)
backend/api/v1/
  evidence.py         # NEW — POST /build/{case_id}, GET /download/{pkg_id}.{pdf|json}, GET /fiu/{case_id}, GET /verify/{pkg_id}
backend/evidence_storage/   # EXISTING dir — rendered PDFs + JSON packages on disk (object store later)
```

### Determinism & integrity
- The **canonical JSON** (sorted keys, fixed separators, stable section order) is hashed → SHA-256. This hash is what BELS anchors — **the PDF is a rendering of it**, so rendering variance never affects integrity.
- Re-building the same case yields the **same hash** (a Wave-1 test asserts this), proving reproducibility for audit.

### BELS anchoring + custody (reuse)
- `anchor.py` calls `case_management/bels_client` → BELS `POST /evidence/register` (SHA-256, metadata), then `POST /evidence/custody/{id}` for create/access events; `GET /evidence/{id}/certificate` for the certificate embedded in the bundle.
- If BELS unreachable: bundle marked `"anchor": {"status": "unanchored", reason}` — still produced, clearly flagged.

### Security / audit
- `/api/v1/evidence/*` requires auth; every build/download writes an `AuditEntry` (Phase 3) and a BELS custody event → full chain-of-custody (who generated/downloaded what, when).

## 5. API
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/evidence/build/{case_id}` | assemble + render + anchor → returns `{pkg_id, sha256, anchor, sections}` |
| GET | `/api/v1/evidence/download/{pkg_id}.json` | canonical JSON package |
| GET | `/api/v1/evidence/download/{pkg_id}.pdf` | rendered PDF |
| GET | `/api/v1/evidence/fiu/{case_id}` | FIU-IND STR document (JSON; PDF optional) |
| GET | `/api/v1/evidence/verify/{pkg_id}` | re-hash + BELS verify → tamper check |
Legacy `/api/evidence/generate` stays mounted.

## 6. Build order (waves)
- **Wave 1 (now, no Docker — JSON case store + reportlab; BELS graceful):** `packager.build()` assembling all §3 sections from the seed cases, deterministic canonical JSON + SHA-256, PDF via existing builder, `fiu.py` STR template, `/api/v1/evidence/*` endpoints, BELS anchor best-effort. **Verify:** build for a seed case → all 15 sections present; identical hash on rebuild; PDF + JSON written; FIU doc validates; unit tests.
- **Wave 2 (with BELS `:8200` live):** full custody lifecycle, certificate embedding, `verify` round-trip against the chain, screenshot ingestion from the Phase 7 Evidence Builder, FIU PDF rendering.

## 7. Risks & mitigations
| Risk | Mitigation |
|---|---|
| Non-determinism breaks the hash | hash canonical JSON (not PDF); stable ordering; exclude volatile fields from the hashed core (generated_at kept outside the hashed section) |
| BELS offline (no Docker) | graceful "unanchored" status; anchor later via a re-anchor endpoint |
| Regulator format fidelity | FIU-IND STR template marked DEMO; structured for real mapping later |
| Large packages | stream PDF; store on disk (object store in Phase 9) |
| PII in evidence | respect `pii` masking from the graph; raw values only via the audited PII vault |

## 8. Testing
- Bundle completeness: all 15 sections present for a seed case.
- **Determinism**: `build()` twice → identical canonical SHA-256.
- PDF/JSON written and non-empty; JSON re-parses.
- FIU document has required STR fields.
- Anchor graceful: BELS down → `unanchored`, no crash; BELS up (when available) → register + verify round-trip.
- Audit: build/download writes an AuditEntry.
- No-regression: legacy `/api/evidence/generate` unchanged.

## 9. Expected output
- `evidence/packager.py`, `fiu.py`, `anchor.py`; `api/v1/evidence.py`; deterministic, hash-anchored packages with FIU/STR output; chain-of-custody via BELS + audit.
- Phase 7 Evidence Builder upgraded to call `/api/v1/evidence/build`.

## 10. Open questions for sign-off
1. Anchor the **canonical JSON hash** (deterministic) rather than the PDF. **Recommended: yes.**
2. FIU format = **FIU-IND STR (demo template)** + generic regulatory JSON. **Recommended: yes.**
3. BELS **graceful-optional for Wave 1** (anchor when `:8200` up, else flagged unanchored). **Recommended: yes.**
