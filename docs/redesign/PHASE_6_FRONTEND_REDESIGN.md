# Phase 6 — Frontend Redesign (DESIGN DOC, for approval)

> Status: **APPROVED · Wave 1 BUILT & COMPILES.** New: `services/api.ts` (typed client reusing auth `apiRequest` + `sessionHeaders`, cursor pagination, v1-first fallback), `services/resources/casesApi.ts` (cases v1-first→legacy), `components/graph/GraphRenderer.ts` (renderer interface), `components/graph/GraphCanvas.tsx` (Cytoscape 2D, reuses `cytoscapeStylesheet`, enterprise theme, expand-on-dblclick), `pages/WorkstationGraphPage.tsx` mounted at **/workstation** (non-destructive; `/graph` cinematic stays default until Wave-2 parity). Verified: `tsc --noEmit` clean on new files; `npm run build` succeeds (3399 modules). Finding: a 3.5 MB JS chunk = the R3F/three path → lazy-split `/cinematic` in Wave 2. Browser screenshot pending dev-server run.
> Sign-off: Cytoscape single renderer (cinematic preserved) ✅ · Wave-1-first ✅ · per-resource v1 fallback ✅
>
> **Wave 2 BUILT & COMPILES.** `workstation/`: `Workstation.tsx` (dock host — resizable/collapsible left+right panels, toolbar), `CommandPalette.tsx` (Cmd-K — account search via auth API + actions + nav), `keymap.ts`, `VirtualList.tsx` (dependency-free windowing), `context/SelectedEntityContext.tsx` (one selection drives all panels), `panels/CasesPanel.tsx` (virtualized, v1-first casesApi) + `panels/EntityInspectorPanel.tsx` (reads selection + live store). `/workstation` now renders the shell and is the **default route** (`/`,`*` → /workstation); `/graph` (cinematic + 3D App) preserved and **lazy-split**. Result: main chunk 3,531→2,927 kB; App (225 kB) + CinematicApp (384 kB) deferred to separate chunks. tsc clean on new files; `npm run build` OK. Browser screenshot still pending dev-server run.
> Builds on: Phase 3 `/api/v1` (auth + cursor pagination), Phase 4/5 outputs surfaced in the UI.
> **This is the one phase verifiable live without Docker** — the Vite dev server runs against the existing backend on `:3000`.
> Iron rule: **ONLY ADD / preserve.** No page or feature is deleted. The 3D/cinematic renderers are *demoted to an opt-in route*, not removed.

---

## 1. Goals
1. Consolidate **three graph renderers → one** enterprise 2D renderer; make the investigation graph obey the existing "Less UI, More Intelligence" theme (no neon/glow/3D by default).
2. Build a true **investigator workstation shell**: command palette, dockable/resizable panels, keyboard shortcuts, high-density layout, and a single **selected-entity context** that drives every panel.
3. **Virtualized / progressive** graph + lists so it stays fast at scale (expand-on-demand, lazy neighbour loading, LOD).
4. Introduce a **typed central API client** and cut over to `/api/v1` (auth + cursor pagination), with legacy fallback per-resource.

## 2. Current state (audited)
- **3 renderers**: Cytoscape (`graph/cytoscapeConfig.ts`, 2 files), react-force-graph-3d (2), and **R3F/three+postprocessing (10 files)** — `components/GraphScene.tsx`, `v2/CinematicApp.tsx`, `v2/scene`, `v2/shaders`. The R3F path is the shader-heavy "cyberpunk" look that fights the UI bar; `App.tsx` renders the live graph via `GraphScene` (3D).
- **Theme is already correct**: `theme.ts` = deep matte black + restrained gold + muted status — explicitly "NOT cyberpunk/neon." It only wraps the shell, not the graph.
- **No central API layer**: `fetch()` scattered across 9 files using `apiUrl()` + `sessionHeaders()` from `config.ts`. Session = `X-Session-Id` header + `?session=` on WS.
- 11 pages (Investigations, Cases, CaseGraph, Recovery×2, Risk, Account, Search, Login, Register, Graph) + rich panels (NodeInspector, AlertPanel, Evidence, RedTeam, Training). All preserved.

## 3. Renderer decision — **Cytoscape.js as the single investigation renderer**
| Option | Verdict |
|---|---|
| **Cytoscape.js (canvas 2D)** | **Chosen.** Deterministic layouts, compound nodes, high node density, fast, already partly used (`cytoscapeConfig.ts`), matches enterprise tools (i2, Linkurious). |
| react-force-graph-3d | Retire from investigation — 3D depth hurts legibility for forensics. |
| R3F/three + postprocessing (`GraphScene`/`CinematicApp`) | **Demote to an opt-in `/cinematic` route** (kept, not deleted) — it's an existing feature and a nice demo, but never the investigator default. |
| sigma.js (WebGL) | Noted as the **future** swap if components exceed ~5k visible nodes; same renderer interface so it's a drop-in later. |

A new `components/graph/GraphCanvas.tsx` wraps Cytoscape behind a small `GraphRenderer` interface (`setData / expandNode / focus / onSelect / applyFilters`) so the renderer is swappable (sigma later) without touching the workstation.

## 4. Target architecture
```
frontend/src/
  services/
    api.ts            # NEW typed client: baseUrl, auth token, sessionHeaders, cursor pagination,
                      #   v1-first with legacy fallback per resource; one fetch wrapper for all 9 callers
    resources/        # casesApi, graphApi, alertsApi, searchApi, riskApi, evidenceApi, redteamApi
  workstation/        # NEW shell
    Workstation.tsx   # dock layout host (resizable/closable panels)
    CommandPalette.tsx# Cmd/Ctrl-K — search entities, run actions, jump panels
    keymap.ts         # global keyboard shortcuts
    panels/           # registry of dockable panels (wraps EXISTING panels)
    context/SelectedEntityContext.tsx   # one selection drives every panel
  components/graph/
    GraphCanvas.tsx   # NEW Cytoscape renderer (enterprise theme tokens)
    GraphRenderer.ts  # interface (Cytoscape now, sigma later)
  components/...      # EXISTING panels reused as dock panels (NodeInspector, AlertPanel, …)
  cinematic/          # MOVED v2/CinematicApp + GraphScene behind opt-in /cinematic route (preserved)
  theme.ts            # reused as the single design system (extract a few shared primitives)
```

## 5. Design language ("Less UI, More Intelligence")
- All surfaces use `theme.ts` tokens (matte black, gold accent only for active/primary, muted status).
- No glow, no postprocessing, motion limited to functional transitions (panel open/close, focus). Density over decoration.
- Information-dense tables (virtualized), monospace for ids/amounts, consistent risk-band coloring from the muted status palette.
- The graph: flat 2D, clear edge direction + amount labels on demand, risk-banded node fill, selection halo (not neon).

## 6. Workstation shell
- **Dock layout**: resizable, collapsible, rearrangeable panels (graph center; inspector right; alerts/cases left; timeline bottom). Layout persisted per investigator (localStorage now, server later).
- **Command palette (Cmd/Ctrl-K)**: global entity search (hits `/api/v1` search), quick actions (open case, generate evidence, expand node, run detector), panel navigation.
- **Selected-entity context**: selecting a node/row sets one context; NodeInspector, risk panel, ML explanation, evidence, and neighbours all react to it — the "investigator OS" feel.
- **Keyboard shortcuts**: expand/collapse, focus, pin-to-case, next-alert, toggle panels (documented in `keymap.ts`, discoverable in the palette).

## 7. Performance (Part 10)
- **Progressive graph**: load a bounded neighbourhood (graph_repo `neighbourhood` endpoint), expand-on-demand per node, cap visible nodes with LOD (collapse low-degree leaves).
- **Virtualized lists** (react-window or lightweight custom) for alerts/cases/transactions/search — render only visible rows.
- **Cursor pagination** end-to-end via the new API client.
- Debounced layout, web-worker layout for large components (Cytoscape supports it), memoized selectors in the Zustand stores (`graphStore`, `session`).

## 8. API cutover
- `services/api.ts` central client: attaches JWT (from auth store) + `sessionHeaders()`, parses `{items,next_cursor}`, and resolves base path **v1-first with legacy fallback** per resource (cases → `/api/v1/cases`; others stay legacy until their v1 router lands). Migrates the 9 scattered `fetch()` callers behind typed resource modules.
- WS (`useGraphSocket`/`useWebSocket`) unchanged (still `?session=`), now reading through the client's auth where applicable.

## 9. Migration strategy (frontend strangler)
1. Land `theme.ts` primitives + `services/api.ts` (no visual change).
2. Build `GraphCanvas` (Cytoscape) behind `GraphRenderer`; add a feature flag `VITE_GRAPH=cytoscape|cinematic` defaulting to cytoscape; move `GraphScene`/`CinematicApp` to `/cinematic`.
3. Build `Workstation` shell hosting the EXISTING panels as docks; switch the default route to it; keep all current pages reachable.
4. Cut list views to virtualized + cursor pagination via the client.
Each step is independently shippable and live-verifiable on `:3000`.

## 10. Risks & mitigations
| Risk | Mitigation |
|---|---|
| Retiring R3F breaks the current main view | keep it behind `/cinematic` + feature flag; default flips only after GraphCanvas reaches parity |
| Cytoscape perf on big graphs | progressive expand + LOD + worker layout; sigma.js swap path reserved behind the same interface |
| API cutover regressions | v1-first **with legacy fallback**; per-resource, not big-bang; legacy routes still mounted (Phase 3) |
| Losing rich existing panels | panels are reused as-is inside the dock; not rewritten |
| Scope (79 tsx files) | waves; shell wraps existing components rather than replacing them |

## 11. Testing / verification (live, no Docker)
- `npm run dev` on `:3000` against the running backend; verify: graph renders in Cytoscape, expand-on-demand works, command palette opens (Cmd-K), panels dock/resize, cases list paginates via `/api/v1/cases`, `/cinematic` still loads the old view.
- Visual check against the UI bar: no neon/glow, dense layout, gold used sparingly (matches `feedback_tgie_premium_ui`).
- Build check: `npm run build` succeeds; no R3F imports on the default path (tree-shaken).
- Screenshot the workstation for the record.

## 12. Expected output
- One renderer (Cytoscape) on the default path; 3D/cinematic preserved behind `/cinematic`.
- `services/api.ts` + resource modules; cases on `/api/v1`.
- `Workstation` shell with command palette, dockable panels, keyboard shortcuts, selected-entity context.
- Virtualized lists + progressive graph.
- Zero pages/features removed.

## 13. Open questions for sign-off
1. **Single renderer = Cytoscape**, with R3F/force-graph-3d demoted to an opt-in `/cinematic` route (preserved, not deleted)? **Recommended: yes.**
2. **Build order**: Wave 1 = API client + GraphCanvas + theme primitives (verifiable live), Wave 2 = Workstation shell + command palette + virtualization. **Recommended: yes.**
3. API cutover: **v1-first with legacy fallback per resource** (start with cases) vs wait for full v1 parity. **Recommended: per-resource fallback.**
