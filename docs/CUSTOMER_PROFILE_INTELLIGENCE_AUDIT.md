# Customer Profile Intelligence — Phase 1 Audit

**Verdict: NOT implemented in the live detection path.** The *concept* exists in the
offline adversarial research plane and is documented as a known gap; the live Blue Team
and risk engine use static, one-size-fits-all thresholds. No UI support.

Date: 2026-06-30. Scope audited: `backend/`, `red_team/adversarial/`, `frontend/`.

## What exists today (and why it is not enough)

| Component | What it is | Profile-aware? |
|---|---|---|
| `risk_engine/engine.py` | The live multi-factor 0–100 risk engine called on every component (`routes.py`). | **No.** `_amount_intensity()` uses absolute ₹ bands (10k / 50k / 2L / 5L / 10L) for *all* accounts — the exact one-size-fits-all weakness this feature targets. |
| `red_team/adversarial/common/behavioral.py` | A real "compare each account to *its own* baseline" model: `AccountProfile` (establishment, segment, baseline_throughput, baseline_txn), `_SEGMENTS` (household/retail/corporate/sme), `BehavioralRegistry`, `BehavioralScorer`. | **Concept yes, live no.** Synthetic random profiles, only 4 coarse segments, and it runs **only** inside `HardenedBlueTeam` in the offline adversarial integration — never wired into the live risk engine or the demo path. |
| `blue_team_v2/core/context/entity_context.py` | `EntityContext.profiles` field typed `{customer_id, kyc_level, declared_income, occupation}`. | **Placeholder.** `build_entity_context()` never populates `profiles`, and returns `None` unless Neo4j is up — a no-op on the live JSON demo. |
| `knowledge/customer_risk.py`, `entities.py`, `investigation.py` | Cross-product **entity/identity/product** risk propagation and an entity taxonomy (`EntityType`: savings/current/salary/corporate/…). `investigation.py` has a `profile` block = entity_type + product/device counts. | **No.** This is identity/product risk, not behavioural customer profiling. `EntityType` distinguishes *account products*, not customer occupations (Salaried/Farmer/Student…). |
| `auth/accounts_db.py` | Synthetic search registry (name, risk_band). | **No** occupation/segment/baseline fields. |
| `blue_team_v2/docs/AUDIT_2026-06-29.md` | Internal audit. | Explicitly lists the gap: *"no historical baseline, no entity resolution"*, *"make velocity relative to baseline"*, *"needs entity store"* — i.e. this feature is **acknowledged future work**. |
| Frontend | `NodeInspector.tsx` shows risk/role/exposure. | **No** profile UI. |

## Conclusion

- **Implemented?** No — not in the live path.
- **Partially?** Only conceptually: a synthetic, offline behavioural-baseline model and an
  unpopulated `profiles` placeholder.
- **Unused / placeholder code?** Yes — `EntityContext.profiles` (never filled);
  `behavioral.py` (offline only).
- **UI support?** None.
- **Blue Team using profile info?** No — static absolute thresholds.

## Design decision (reuse, don't duplicate)

- The live demo transactions carry only `{from, to, amount, rail, timestamp}` (+ optional
  `account_type`). There is no occupation field, so profiles are **inferred** from observable
  behaviour (with an optional explicit override path for future KYC data).
- We **reuse the proven concept** from `behavioral.py` — *compare each account to its own
  profile baseline* — but implement a **live, deterministic, explainable** engine with a
  richer, extensible taxonomy, and **integrate it into the existing `risk_engine`** as a new
  signal rather than building a parallel scorer. One scoring authority; no duplicated logic.
- The engine makes the **amount factor profile-relative** (₹25L is normal for a Business
  Owner, abnormal for a Salaried Employee) and adds a **profile-deviation factor** — directly
  reducing false positives for legitimate high-volume customers.

Implementation follows in `backend/profile_intelligence/` + a `risk_engine` integration + a
compact NodeInspector card.

---

# Implementation & Phase 12 Validation (complete)

**New module `backend/profile_intelligence/`** (deterministic, explainable, no duplicate logic):
- `profiles.py` — 15 extensible customer profiles (Salaried, Business Owner, MSME, Large
  Corporate, Farmer, Student, Pensioner, Freelancer, Govt Employee, NGO/Trust, Retail
  Merchant, E-commerce, HNI, Cash-Intensive, Exporter/Importer) + `unknown`, each with a
  behavioural envelope (baseline txn ceiling, throughput, fan-out, cash intensity, expected
  rails & products) and human-readable expected/abnormal behaviour. Add a profile = add one entry.
- `engine.py` — extracts each account's behaviour, **infers** its profile (explicit KYC →
  account-type prior → behaviour), and **evaluates behaviour relative to that profile**:
  `deviation` (abnormal-for-this-customer) and `mitigation` (a large amount that is routine
  for this customer kind). Reuses the proven "compare to own baseline" idea from the offline
  `behavioral.py`, now live.

**Integrated into the existing `risk_engine`** (one scoring authority, not a parallel system):
- The `amount` factor is now **profile-relative** — dampened by `0.85 × amount_mitigation`, so
  ₹25L from a Business Owner no longer drives risk.
- New `profile_deviation` factor (weight 24 — among the strongest) for abnormal-for-profile
  behaviour.
- `assess()` returns `profile_intelligence` (per-account profiles + reasons); `routes.py`
  attaches it to the broadcast verdict.
- Recovery (`recovery/engine.py`) adds a **profile-aware containment action** (corporate →
  freeze settlement account + trace shell chain; retail → freeze receiving mule; sme →
  investigate vendor chain).

**Frontend (minimal):** one compact **Customer Profile card** in `NodeInspector` — profile,
expected vs current behaviour, signed risk adjustment, and the reasons. No new page/dashboard.

**Validation (all green):**
| Check | Result |
|---|---|
| Profile Intelligence exists & Blue Team uses it | ✓ `profile_deviation` factor + profile-relative amount in live `risk_engine` |
| Behaviour evaluated relative to customer type | ✓ same ₹25L fan-out scores **49 (Salaried) vs 18 (Business Owner)** |
| Static thresholds minimised | ✓ amount factor is now profile-relative |
| Risk explainable | ✓ per-account reasons + `explanation` ("17× the routine ceiling for a Salaried Employee") |
| Recovery is profile-aware | ✓ corporate→settlement-first, retail→freeze-receiving |
| Graph importance relative to profile | ✓ fan-out/aggregation judged vs the profile's expected envelope |
| FPs for legit high-volume customers reduced | ✓ Business ₹25L mitigated (−40% adjustment) |
| Frontend almost unchanged | ✓ one card only |
| No duplicate logic | ✓ integrated into `risk_engine`; reuses entity/edge data |
| Tests | ✓ `tests/test_profile_intelligence.py` (11) + existing `test_risk_engine.py` (32) + recovery/case/cross-product all pass (91 total); `tsc` clean |

**Honest limitation:** the live demo transactions carry no occupation field, so without explicit
KYC the profile is *inferred* from behaviour (coarse). The full value — and the headline FP
reduction — is realised when a profile is supplied (via `component["customer_profiles"]` or a
future KYC feed); the engine is built for that and degrades gracefully otherwise.
