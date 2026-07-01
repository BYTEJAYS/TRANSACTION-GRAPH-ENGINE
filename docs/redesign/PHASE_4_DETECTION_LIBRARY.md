# Phase 4 — Fraud Pattern Library (DESIGN DOC, for approval)

> Status: **APPROVED · Wave 1 BUILT & VERIFIED.** 11 new topology detectors (diamond, nested_layering, round_tripping, hub_network, scatter_gather, structuring, cash_laundering, night_activity, weekend_activity, temporal_spike, uniform_amount) registered in the orchestrator → registry 11→22. `core/context/entity_context.py` bridges the entity graph (no-ops in json mode). Golden fixtures + fire/no-fire precision test added; **full suite 41 passed**, zero regression. See `detectors/CALIBRATION.md`. Wave 2 (identity rings/profile/geo) pending Neo4j; Wave 3 (ML-structural) pending Phase 5.
> Sign-off: meta-extension contract ✅ · Wave-1-first ✅ · configurable thresholds ✅
> Builds on: Phase 2 entity graph, Phase 3 repositories (`graph_repo` projects Neo4j → NetworkX).
> Iron rule: **ONLY ADD.** The 11 shipped detectors + `PatternEngine` + `risk_engine` are untouched; we extend the registry and the detector contract *backward-compatibly*.

---

## 1. Goals
1. Grow from **11 → ~60 detectors** covering every pattern in the brief, organised into families.
2. Keep the **exact detector contract** (`NAME` + `detect(tg, metrics, meta) -> list[Evidence]`) so the orchestrator, adapter, risk engine, and Red-Team self-play loop need no changes.
3. Make **identity/ring detectors** possible by feeding entity context through `meta` — and **degrade gracefully** when the entity graph isn't populated (json mode / no Neo4j), so nothing breaks today.
4. Every detector emits **explainable Evidence** (nodes, severity, confidence, investigator-readable description, structured `data`) — the risk engine remains the single place that turns evidence into a case (no single detector trips a case alone).

## 2. The contract extension (backward-compatible)
Current detectors read `tg` (transaction graph) + `metrics` (18-factor NodeMetrics) + `meta` (origins/chain/cycle_nodes/traits). Identity & profile detectors need more. We **add optional keys to `meta`** — never new positional args:

```
meta["entity_ctx"]  # EntityContext | None  — shared-identity adjacency from graph_repo
meta["profiles"]    # {account_id: AccountProfile} | None — KYC/income/occupation/open_date
meta["temporal"]    # {account_id: [ (ts, amount, rail, channel, geo) ]} | None
```

A detector that needs entity context starts with `ctx = meta.get("entity_ctx")` and **returns `[]` if it's None** — so on today's data (no Neo4j) the new detectors are silent no-ops, and the 11 existing ones are unaffected. `EntityContext` is built by `graph_repo` from the `SHARES_*`/`SAME_*` derived edges (Phase 2 §5).

## 3. Detector taxonomy (~60 patterns → families)
Legend — **Source**: `TG` transaction graph (works today) · `ENT` entity graph (needs Neo4j) · `PROF` account/customer profile · `TMP` temporal log · `ML` model-backed (Phase 5 hook). **Wave**: 1 = ships on current data, 2 = needs entity/profile data, 3 = ML-backed.

### Family L1 — Layering & chains  (Source TG · Wave 1)
| Pattern | Algorithm sketch | Severity driver | Evidence |
|---|---|---|---|
| Rapid layering | existing layering + inter-hop Δt < τ | depth × speed | chain, hop times |
| Double / nested layering | ≥2 disjoint layering chains sharing interior nodes | overlap count | chains, shared relays |
| Diamond | split→parallel paths→re-merge (1→k→1); detect via dominator/merge node | path count k | split/merge nodes |
| Double / triple diamond | sequential diamonds (merge node feeds next split) | diamond depth | diamond sequence |
| Multi-hop laundering | generalised layering depth ≥ N, low retention per hop | depth, retention | chain, retained % |

### Family L2 — Cyclic flow  (TG · Wave 1)
Circular (exists), Round-tripping (funds return to origin within window, possibly via merchant), Circular merchant payments (cycle through `:Merchant`). Algorithm: cycle enumeration (bounded `CYCLE_DETECTION_DEPTH`) + value-conservation + time-ordering check. Severity = cycle value retained ÷ injected.

### Family L3 — Mule & topology roles  (TG/ENT · Wave 1–2)
Money-mule networks (exists), Bridge accounts (exists, betweenness/articulation), Hub networks (high-degree central node + spokes), Synthetic accounts (exists), Scatter-gather (fan-in → relay → fan-out signature across one cluster). Reuse `ClusterIntelligence` roles already computed.

### Family L4 — Fan structures  (TG · Wave 1)
Fan-in (exists), Fan-out (exists), Beneficiary explosion (`ADDED_BENEFICIARY` rate spike — ENT/PROF), Burst transactions (TMP burstiness factor already in NodeMetrics).

### Family L5 — Structuring & cash  (TG/TMP · Wave 1)
Threshold structuring (amounts clustered just under reporting limit ₹X), Smurfing (exists; many sub-threshold deposits across accounts), Rapid cash withdrawal (CASH_OUT velocity), Cash-deposit laundering (CASH_IN bursts → immediate transfer). Algorithm: amount-histogram proximity to threshold + actor count.

### Family L6 — Velocity & temporal  (TMP · Wave 1, some Wave 3)
Velocity fraud (exists), Burst (exists), Weekend fraud, Night activity, Seasonal behaviour change, Dormant-account activation (exists; `dormancy_reactivation` factor). Algorithm: time-of-day / day-of-week distributions vs the account's own baseline; seasonal = STL/EWMA deviation (ML hook).

### Family L7 — Behavioural drift & profile mismatch  (PROF/TMP · Wave 2)
Behavioural drift, Salary mismatch, Occupation mismatch, Income mismatch, KYC mismatch. Algorithm: compare observed throughput/turnover to `declared_income`/`occupation`/`segment` from `AccountProfile`; drift = divergence of current window stats from the account's rolling baseline. Severity = z-score of mismatch.

### Family L8 — Channel / product / geo routing  (PROF/TMP/ENT · Wave 2)
Branch hopping (`FROM_BRANCH` diversity), Product hopping (`USES_PRODUCT` churn), Channel switching (`USED_CHANNEL` entropy spike), Cross-border routing (`Location.country` ∈ high-risk / `HighRiskCountry`). Algorithm: entropy / distinct-count over a window vs baseline.

### Family L9 — Identity-collision rings  (ENT · Wave 2)  ← the big unlock
Device sharing, Shared phone, Shared address, Shared PAN, Shared Aadhaar (demo), Shared IP, Same employer. Algorithm: read `SHARES_DEVICE/SHARES_IP/SAME_PAN/...` derived edges from `entity_ctx`; a connected component over these edges spanning ≥k distinct customers = a ring. Severity weighted by edge basis (PAN/phone strong, IP weak — per Phase 2 weights). **These are impossible in today's account-only model** and are the headline new capability.

### Family L10 — Geo / device risk  (PROF/TMP/ENT · Wave 2)
Geo velocity, Impossible travel (two txns whose geodistance ÷ Δt exceeds feasible speed), Multiple login locations, New-device risk (`Device.first_seen` ≈ txn time + high value). Algorithm: haversine(geohash) ÷ Δt threshold.

### Family L11 — Shell & business  (ENT/PROF · Wave 2)
Shell companies (`Business.is_shell_suspect`: high passthrough, no payroll/utility pattern, recent incorporation, common control). Algorithm: business turnover with ~0 retention + `CONTROLLED_BY` fan-in.

### Family L12 — Graph-structural & ML-backed  (ML · Wave 3)
Community detection, Clique detection, Hidden rings, Hidden bridges, Anomalous central nodes, Unexpected graph expansion, Suspicious connected components, Subgraph matching, Motif detection, Graph embeddings, Temporal graph fraud. These are **detector hooks** in Phase 4 that call into the Phase 5 ML engine (Louvain/Leiden, Bron–Kerbosch cliques, node2vec/GraphSAGE embeddings, temporal-GNN). In Phase 4 they ship as interfaces with NetworkX-only fallbacks (e.g. community via greedy modularity, cliques via NetworkX) so they produce evidence even before the ML models land.

## 4. Per-detector evidence & explainability contract
Every new detector returns `Evidence` with, at minimum:
- `pattern` (canonical code), `title`, plain-language `description` naming the implicated nodes and *why*,
- `nodes`, `severity` (0–1, calibrated per family), `confidence` (0–1),
- `data` = the structured facts an investigator/regulator needs (chain, amounts, timestamps, shared-identity basis, baseline-vs-observed).
The **PatternEngine** already aggregates co-occurring families into a `hybrid_network` finding — new families plug into that automatically (more families → stronger hybrid signal).

## 5. Calibration & false-positive control
- Severity bands per family, documented in `detectors/CALIBRATION.md`; conservative defaults.
- The **risk engine remains the gate** — detectors never auto-create cases; cumulative score crosses threshold (unchanged philosophy).
- Each Wave-2/3 detector has a `MIN_*` gate (min cluster size, min shared customers, min value) to suppress noise.
- **Red-Team self-play** (`adversarial_governance` learning gate) measures benign FP cost when thresholds tighten — new detectors register with the same harness so hardening stays honest.

## 6. Folder layout (extends, never moves)
```
blue_team_v2/detectors/
  base.py                      # unchanged
  <existing 11>/               # unchanged
  diamond/ round_tripping/ scatter_gather/ hub_network/ nested_layering/   # L1–L3 new (TG, Wave 1)
  structuring/ cash_laundering/ night_weekend/ seasonal/                   # L5–L6 new
  behavioural_drift/ profile_mismatch/                                     # L7 (Wave 2)
  channel_geo/ impossible_travel/ new_device/                             # L8/L10 (Wave 2)
  identity_rings/                                                          # L9 (Wave 2) — reads entity_ctx
  shell_company/                                                          # L11 (Wave 2)
  structural_ml/                                                          # L12 (Wave 3) — ML hooks + nx fallback
  CALIBRATION.md
core/pattern_engine/orchestrator.py   # registry list extended (the only edit to existing code)
core/context/entity_context.py        # NEW — builds EntityContext/profiles from graph_repo
```

## 7. Build order (waves)
- **Wave 1 (now, verifiable on current data):** L1 diamond/nested, L2 round-tripping, L3 hub/scatter-gather, L5 structuring/cash, L6 night/weekend/seasonal. ~15 new topology detectors on the existing `TransactionGraph` + synthetic generators.
- **Wave 2 (after Neo4j populated):** L7–L11 entity/profile/geo/identity-ring detectors (the headline rings). Verified against the live entity graph.
- **Wave 3 (with Phase 5):** L12 ML-backed structural detectors; ship now with NetworkX fallbacks, upgrade to GNN/embeddings in Phase 5.

## 8. Risks & mitigations
| Risk | Mitigation |
|---|---|
| Detector explosion → false positives | family severity calibration + risk-engine gate + MIN_* thresholds + Red-Team FP measurement |
| Entity detectors silently no-op without Neo4j | explicit: documented, logged once, covered by a "skipped: no entity_ctx" test |
| Performance (60 detectors per component) | detectors are O(component); heavy ones (cliques/community) move to precompute in Phase 9; per-detector try/except already isolates failures |
| Calibration drift vs V1 shadow | thresholds stay data; shadow comparison harness (`blue_team_v2/shadow.py`) unchanged |

## 9. Testing strategy (gate to Phase 5)
- **Golden synthetic fixtures**: extend `blue_team_v2/simulation/generators.py` with one labelled generator per new pattern; assert the matching detector fires and **non-matching detectors stay silent** (precision guard).
- **Contract test**: every detector module exposes `NAME` + `detect`, returns `list[Evidence]`, never raises (wrapped by orchestrator but tested directly too).
- **Graceful-degradation test**: Wave-2 detectors return `[]` when `meta["entity_ctx"] is None`.
- **Regression**: existing 11 detectors' outputs unchanged on the current sample dataset (snapshot test).
- **Hybrid test**: ≥3 families co-occurring → `hybrid_network` evidence emitted.

## 10. Expected output
- ~50 new detector modules across L1–L12, registered in the orchestrator, each with calibrated severity + explainable evidence.
- `core/context/entity_context.py` bridging the entity graph into the detector contract.
- Synthetic golden fixtures + tests proving fire/no-fire precision.
- Zero change to risk-engine gating, adapter, or the shipped 11 detectors.

## 11. Open questions for sign-off
1. Confirm the **`meta`-extension** approach (vs a new detector signature) for entity/profile context. **Recommended: meta-extension** (backward-compatible, no orchestrator change).
2. Confirm **Wave 1 first** (ship the ~15 topology detectors verifiable on current data now; entity/ML detectors after Docker/Neo4j). **Recommended: yes.**
3. Reporting thresholds: confirm structuring/CTR threshold band (e.g. ₹10,00,000 RTGS / ₹50,000 cash) for the structuring & cash families, or use configurable defaults. **Recommended: configurable in `risk_engine/config.py`.**
