# Phase 7 — Investigation Panel Suite (DESIGN DOC, for approval)

> Status: **APPROVED · Wave 1 BUILT & COMPILES (0 TS errors project-wide).** New in `frontend/src/workstation/`: `panelRegistry.tsx`, tab-switchable right dock + `filters/GraphFilters.tsx` (risk/amount/rail/flagged, wired to GraphCanvas), `bookmarks.ts`, `exporters.ts` (JSON/CSV), panels `FraudScorePanel` · `ExplainabilityPanel` · `PatternExplorerPanel` · `AuditTrailPanel` · `CaseWorkflowBar` · `EvidenceBuilderPanel` (+ reused `EntityInspectorPanel`/`CasesPanel`); `services/resources/index.ts` (alerts/risk/audit/evidence/replay, v1-first). Workstation toolbar gains ⚲ Filters; right dock tabs Inspector/Score/Explain/Patterns/Audit/Workflow/Evidence. `npm run build` OK; bundles still split. Wave 2 (replay/geo/snapshot/customer-inspector/FIU) pending event store + Phase 8. Browser screenshot pending dev-server run.
> Sign-off: Wave-1-first ✅ · replay via event_repo+fallback ✅ · reuse existing panels ✅
> Builds on: Phase 6 Wave 2 workstation shell (dock host + command palette + `SelectedEntityContext`), Phase 3 repos (`graph_repo.neighbourhood`, `event_repo.replay`, `/api/v1`), Phase 4 detectors, Phase 5 ML explain.
> Iron rule: **ONLY ADD / reuse.** Every Part 6 surface either reuses an existing component (NodeInspector, AlertPanel, EvidenceModal, MetricsPanel, TransactionFeed/Ticker, GraphIntelHUD, RedTeamPanel, PinToCaseControl, recovery/risk pages) *wrapped as a dock panel*, or is a thin new panel. Nothing is rebuilt from scratch or removed.

---

## 1. Goals
Turn the shell into a full investigator workstation by delivering every Part 6 surface as a **dockable panel or graph interaction**, each driven by the shared `SelectedEntityContext`, each reading through the typed API client (v1-first), each degrading gracefully when a backend feature isn't live.

## 2. Surface → panel mapping (Part 6, complete)
Legend — **Reuse** = existing component wrapped; **New** = new thin panel; **Src** = data source; **Wave**.

### A. Search & navigation
| Surface | Plan | Src | Wave |
|---|---|---|---|
| Global / Customer / Account / Transaction search | command palette (built) + `SearchResults` page (reuse) | `/api/accounts/search`, `/api/v1` search | 1 |
| One-click Expand / Collapse | graph node dbl-click → `graph_repo.neighbourhood` lazy expand; collapse leaves | `/api/v1/graph/neighbourhood` (fallback: current `/api/graph/node/{id}/edges`) | 1 |

### B. Inspectors (right dock, react to selection)
| Surface | Plan | Src | Wave |
|---|---|---|---|
| Entity / Account Inspector | extend `EntityInspectorPanel` (built) + reuse `NodeInspector` facts | live store + `/api/accounts/{id}` | 1 |
| Transaction Inspector | New panel — amount/rail/ts/path/counterparties | edge data + `/api/v1` txn | 1 |
| Customer Inspector | New panel (KYC/income/segment) — entity-graph backed | Neo4j via `/api/v1` (graceful) | 2 |
| Fraud Score Panel | New — cumulative risk breakdown (factors) | `risk_engine` `/api/risk` | 1 |
| Explainability Panel | New — renders Phase 5 `Explanation` (reason codes + SHAP) + detector evidence | ML explain + detector evidence | 1 |

### C. Explorers (center/overlay)
| Surface | Plan | Src | Wave |
|---|---|---|---|
| Graph / Relationship / Neighbour Explorer | GraphCanvas expand-on-demand + relationship filter (shared-identity edges) | `graph_repo` | 1 (topology) / 2 (identity edges) |
| Path Explorer | select two nodes → shortest/fund path overlay | `/api/graph/path/{a}/{b}` (exists) | 1 |
| Pattern Explorer | list detector findings for the component, click → highlight nodes | detector evidence | 1 |
| Timeline Replay / Transaction Playback | bottom dock scrubber; replays edges by ts | `event_repo.replay` (db) → fallback `/api/replay/recent` (exists) | 2 |
| Fund Journey Replay | animate value flow along a path over time | same as timeline + path | 2 |
| Heatmaps / Geo View (demo) | risk heat over graph; geo map (demo coords) | node risk + `geo_locations` | 2 |
| Snapshot Comparison | diff two graph snapshots (before/after) | client snapshots + case `graph_snapshot` | 2 |

### D. Dashboards (left dock / routes)
| Surface | Plan | Src | Wave |
|---|---|---|---|
| Case Dashboard | `CasesPanel` (built) + `InvestigationsPage` (reuse) | casesApi v1-first | 1 |
| Alert Dashboard | reuse `AlertPanel` as dock | `/api/alerts` (exists) | 1 |
| Risk Dashboard | reuse `MetricsPanel`/`LiveStats` + `RiskPolicyPage` | `/api/risk`, `/api/stats` | 1 |
| Evidence Dashboard | reuse `EvidenceBlockchainPanel` + BELS | BELS `:8200` | 1 |

### E. Case workflow & collaboration
| Surface | Plan | Src | Wave |
|---|---|---|---|
| Case Notes / Investigator Comments | reuse case `notes`/`comments` (enrich payload) | casesApi | 1 |
| Alert Status / Case Status / Assign / Close / Reopen | New action bar in case panel → case mutations | `/api/cases/*` (exists) + `/api/v1` later | 1 |
| Bookmarks / Tags / Pinned Entities | client store (localStorage) + `PinToCaseControl` (reuse) | local + case | 1 |
| Audit Trail / Evidence Timeline | New panel rendering `/api/v1/audit/recent` (built) + case `timeline` | `/api/v1/audit`, case payload | 1 |

### F. Evidence & export
| Surface | Plan | Src | Wave |
|---|---|---|---|
| Evidence Builder | reuse `EvidenceModal` + select graph/nodes/findings | client + `/api/evidence/generate` (exists) | 1 |
| PDF / JSON / CSV Export | reuse jsPDF/`ai/evidence`; add JSON/CSV client exporters | client | 1 |
| FIU Report Generator | New (UI here, server packaging in Phase 8) | Phase 8 packager | 2 |

## 3. Architecture (extends the shell, no churn)
```
workstation/
  panels/
    TransactionInspectorPanel.tsx   FraudScorePanel.tsx   ExplainabilityPanel.tsx
    PatternExplorerPanel.tsx        AlertsPanel.tsx        AuditTrailPanel.tsx
    CaseWorkflowBar.tsx             EvidenceBuilderPanel.tsx
    TimelinePanel.tsx (Wave 2)      GeoHeatPanel.tsx (Wave 2)  SnapshotDiffPanel.tsx (Wave 2)
  panelRegistry.ts                  # id → {title, component, default dock, shortcut}
  filters/GraphFilters.tsx          # branch/product/date/amount/risk/channel (drives GraphCanvas filters)
  bookmarks.ts                      # localStorage bookmarks/tags/pins store
services/resources/
  graphApi.ts  alertsApi.ts  riskApi.ts  searchApi.ts  evidenceApi.ts   # v1-first, fallback to legacy
```
- **Panel registry**: panels are registered with a dock position + optional shortcut; the dock host renders from the registry and the command palette can open any panel. This makes the workstation extensible (Part 9 "dockable panels").
- **Graph filters** feed the existing `GraphCanvas` `filters` prop (already supports risk/rail/flagged); we extend with branch/product/date/amount/channel (client-side now; server-side query in Phase 9).
- All new data access goes through new `services/resources/*` modules using the `api.v1First` helper — consistent with Phase 6.

## 4. Reuse-first inventory (preserve)
`NodeInspector`, `AlertPanel`, `MetricsPanel`, `LiveStats`, `TransactionFeed`, `TransactionTicker`, `EvidenceModal`, `GraphIntelHUD`, `EvidenceBlockchainPanel`, `RedTeamPanel`, `TrainingReviewPanel`, `PinToCaseControl`, `InvestigationsPage`, `CaseDetailPage`, `RiskPolicyPage`, `RecoveryDashboardPage`, `ai/evidence` (PDF). These are wrapped as dock panels or linked from the palette — not rewritten.

## 5. Build order (waves)
- **Wave 1 (now, build/compile-verifiable on existing endpoints):** GraphFilters, expand/collapse, Transaction Inspector, Fraud Score Panel, Explainability Panel, Pattern Explorer, Path Explorer, Alerts/Risk/Evidence dock panels (wrap existing), Case Workflow bar (status/assign/notes), Bookmarks/Tags/Pins, Audit Trail panel, Evidence Builder + JSON/CSV/PDF export, panel registry.
- **Wave 2 (needs live data / Phase 8):** Timeline & Fund-Journey replay (event store), Geo/Heatmap (demo), Snapshot comparison, Customer Inspector (entity graph), FIU report generator.

## 6. Risks & mitigations
| Risk | Mitigation |
|---|---|
| Panel sprawl / dock complexity | panel registry + reuse existing components; lazy-mount panels |
| Endpoints not yet on v1 | `api.v1First` fallback to legacy per resource |
| Replay needs event store (not live without Docker) | fallback to existing `/api/replay/recent` + client reconstruction from edge timestamps |
| Performance with many panels | virtualized lists (built), lazy panel mount, memoized selectors |
| Evidence/FIU overlaps Phase 8 | Phase 7 = UI/builder; Phase 8 = server-side packaging + chain-of-custody |

## 7. Testing / verification
- Build/tsc gate on every new panel; panel registry renders all panels without error.
- Selection propagation: selecting a node updates inspector + fraud-score + explainability panels (context test).
- Filters: applying a risk/rail filter changes the rendered element count in GraphCanvas.
- Workflow: case status change calls the right endpoint (mock) and updates the list.
- Export: JSON/CSV produce valid files from a sample case; PDF path reuses existing generator.
- Live (dev server): open workstation → expand a node, open Cmd-K, dock/undock a panel, change a filter, build evidence.

## 8. Expected output
- ~12 new dock panels + GraphFilters + bookmarks store + panel registry + 5 resource API modules.
- Every Part 6 surface present (Wave 2 ones gated/graceful until their backend lands).
- Zero existing components removed; the heavy ones reused as docks.

## 9. Open questions for sign-off
1. **Build order Wave 1 → Wave 2** (explorers/inspectors/filters/score/explainability/workflow/export now; replay/geo/snapshot/FIU after event store + Phase 8). **Recommended: yes.**
2. Replay data source: **event_repo.replay with fallback to existing `/api/replay/recent`** + client reconstruction. **Recommended: yes.**
3. Reuse `NodeInspector`/`AlertPanel`/`EvidenceModal` wrapped as docks vs fresh builds. **Recommended: reuse/wrap.**
