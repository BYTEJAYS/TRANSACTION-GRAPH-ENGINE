# Phase 10 — Testing & Readiness (DESIGN DOC, for approval)

> Status: **APPROVED · Wave 1 BUILT & VERIFIED.** Added `pytest.ini` + `conftest.py`, `tests/test_api_contract.py` (auth 401 + pagination + evidence build/verify via TestClient), `tests/test_evidence_determinism.py` (15 sections, stable hash, tamper detection, FIU), `tests/test_migration_roundtrip.py`, `scripts/readiness.py`, `docs/redesign/REDESIGN_SUMMARY.md`. Fixed `repositories/case_repo.py` json branch (`store.list_cases/get_case` → `.all()/.get()`) + clarified `user_repo` json branch. **81 tests pass** suite-wide; **readiness scorecard 80/80** (no-Docker), +20 reserved for live Docker. `live` tests defined-but-skipped. Wave 2 = run `pytest -m live` against the stack.
> Sign-off: Wave-1-now ✅ · repo fixes ✅ · readiness scorecard + summary ✅
> Final phase. Consolidates testing across the whole redesign and produces a readiness summary.
> Iron rule: **ONLY ADD.** New tests + config + a readiness script; no production code changes except **bug fixes surfaced by the new tests** (called out explicitly).

## 1. Goals
1. One coherent, runnable test strategy + a single `pytest` entrypoint (root config), green across the suite.
2. Fill the coverage gaps the redesign opened: **API contract/auth**, **evidence determinism**, **migration round-trip** (as pytest), plus the already-built detector/ML/cache suites.
3. Fix correctness issues the tests surface (see §4).
4. A **readiness scorecard** + a redesign-wide summary doc.

## 2. Current state (audited)
- 68 tests across `blue_team_v2/tests`, `ml/tests`, `tests/` — detector fire/no-fire (Phase 4), ML platform + metrics gate (Phase 5), perf/cache/tasks (Phase 9), cash/training-governance (pre-existing). `.github/workflows/ci.yml` exists.
- **Gaps**: no API contract/auth tests for `/api/v1`; no pytest config at backend root; evidence determinism only checked ad-hoc; migration round-trip only via `migrations.run --check` (not a pytest).

## 3. Test strategy (the pyramid)
| Layer | Coverage | Where |
|---|---|---|
| Unit | detectors (fire/no-fire), risk factors, ML estimators, cache/offload/tasks, transforms | existing + extend |
| Contract | `/api/v1` auth (401 no token), pagination shape, evidence build/verify, health | NEW `tests/test_api_contract.py` (TestClient + `dependency_overrides`) |
| Determinism | evidence package canonical hash stable on rebuild; 15 sections; FIU fields | NEW `tests/test_evidence_determinism.py` |
| Migration | `cases.json`/`users` round-trip exact (reversible) | NEW `tests/test_migration_roundtrip.py` (wraps `migrations.run.check_roundtrip`) |
| Metrics gate | ensemble ROC-AUC ≥ 0.85; drift trips on shift | existing (Phase 5) |
| Regression | shipped 11 detectors unchanged; legacy routes preserved | existing + assert |

## 4. Bug fixes surfaced (to apply in Wave 1)
- **`repositories/case_repo.py` json branch** calls `store.list_cases()`/`store.get_case()` — but the case-store singleton exposes `.all()`/`.list()`/`.get()`. In json mode (default) this returns empty/None. **Fix**: use `from case_management.store import store` and call `.all()`/`.get()`. (Caught by the new API contract test asserting the 9 seed cases list.)
- Audit any similar mismatch in `user_repo.py` json branch (`get_by_employee_id`/`get_user` vs the auth store's real method) and align.

## 5. Tooling
- `backend/pytest.ini` — `testpaths`, `filterwarnings` (silence the known `utcnow` deprecation), markers (`live` for Docker-only tests, skipped by default).
- `backend/conftest.py` — shared fixtures (a built FastAPI app with `current_user` overridden, a sample component, a tmp artifact dir).
- `scripts/readiness.py` — runs the key gates (round-trip, ensemble AUC, detector fire/no-fire count, evidence determinism, cache speedup, route inventory) and prints a **readiness scorecard** (replaces the stale 55/100 from memory with a measured number).
- Extend `ci.yml` to run the full suite (note; CI runner has sklearn but not xgboost/torch — fallbacks keep it green).

## 6. `live` (Docker-gated) tests — defined, skipped by default
Marked `@pytest.mark.live`, run only when the stack is up (Phase 2/3/8/9 Wave 2 live verification): Neo4j schema bootstrap, Postgres migrations + `dump_cases` round-trip, BELS anchor+verify round-trip, Redis cache backend == "redis", Celery enqueue. These document the live acceptance criteria without blocking the no-Docker suite.

## 7. Build order
- **Wave 1 (now):** pytest.ini + conftest, the 3 new test files, the case_repo (and user_repo) fixes, `scripts/readiness.py`, readiness summary. Target: **whole suite green**, readiness scorecard printed.
- **Wave 2 (Docker):** the `live` tests executed against the running stack.

## 8. Risks & mitigations
| Risk | Mitigation |
|---|---|
| TestClient triggers heavy app lifespan | mount only `api_v1` on a bare FastAPI app for contract tests; override `current_user` |
| Optional-lib variance (xgboost/torch absent) | tests assert via `available()` + fallbacks; metrics gate uses sklearn-only ensemble |
| Fixing case_repo changes behaviour | it currently returns empty in json mode → fix is strictly corrective; covered by a new test |
| Flaky timing (cache/offload) | generous thresholds (≥5× not ≥1233×; <0.18s overlap) |

## 9. Expected output
- Green consolidated suite (existing + new contract/determinism/migration tests).
- `pytest.ini`, `conftest.py`, `scripts/readiness.py`, `REDESIGN_SUMMARY.md`.
- `case_repo`/`user_repo` json-mode fixes.
- `live` acceptance tests defined (skipped without Docker).

## 10. Open questions for sign-off
1. **Wave 1 now** (config + contract/determinism/migration tests + repo fixes + readiness), `live` tests defined-but-skipped. **Recommended: yes.**
2. Apply the **`case_repo`/`user_repo` json-branch fixes** (corrective). **Recommended: yes.**
3. Produce a measured **readiness scorecard** + `REDESIGN_SUMMARY.md` closing the program. **Recommended: yes.**
