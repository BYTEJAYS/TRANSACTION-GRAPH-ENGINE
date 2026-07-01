# TGIE Frontend Review

> Target: `frontend/` — Vite + React 18 + TypeScript SPA. Primary surface is the
> live 3D transaction graph (`react-force-graph-3d` / three.js) with the UB
> (Universal Brain) voice assistant. Design intent: **matte-black institutional
> trading terminal, minimal clutter, graph-first.**

---

## 1. Design-Intent Conformance

| Requirement | State | Notes |
|---|:--:|---|
| Matte black theme | ✅ | `#000000` background (token `C.bg`); renderer clear color `0x000000`. |
| Professional / institutional | ✅ | Monospace labels, restrained accent palette (green/amber/red verdict). |
| Minimal clutter | ✅ | Header removed; RightPanel removed; intel panels gated off by default. |
| Graph-first focus | ✅ | Graph fills viewport (`position:absolute; inset:0`); orb is call-driven. |
| No unnecessary panels | ✅ | Scenario buttons replaced by a single unified sim feed (`data/sampleDataset.ts`). |
| Responsive | ⚠️ | Functional, but the resize path is fragile — see graph_validation.md. |
| Mac optimized | ⚠️ | devicePixelRatio not explicitly managed → soft text on Retina. |

---

## 2. Current Issues

- **`GraphScene.tsx` is a 1,287-line monolith** mixing: force config (`FORCE`), camera control, renderer setup, the d3 cluster force, intel overlays, cluster labels, hover path-highlight, and event handling. Hard to test or reason about.
- **Resize handling is window-derived, not container-derived** — `dims` reads `window.innerWidth/innerHeight` and updates only on the `resize` event. This is the source of the rhombus/aspect distortion (full root-cause in `graph_validation.md`).
- **No device-pixel-ratio management** → blurry nodes/labels on Retina/4K Macs.
- **Dead JSX** — the old header is wrapped in `{false && (…)}` in `App.tsx` rather than deleted.
- **Orphaned `RightPanel.tsx`** kept on disk but imported nowhere.
- **No frontend tests** — no vitest/playwright; correctness is verified manually via puppeteer screenshots.
- **First-mic-grant UX** depends on a capture-phase gesture listener; brittle on non-Chromium and LAN-IP/HTTP origins (mediaDevices undefined).
- **TTS autoplay** may need one user gesture on a fresh Vercel load.

---

## 3. UI Inconsistencies

- Verdict colors are defined inline in multiple places (cluster labels, links, nodes) rather than from one token map.
- Font sizing in cluster-label overlays uses ad-hoc tiny sizes (7–8px) — legibility risk on high-DPI but small absolute size.
- Two app shells exist: default `App` (GraphScene) and a `?v=2` `CinematicApp` (worker-based layout) — divergent code paths to maintain.

---

## 4. Graph Rendering Issues

(Full analysis in `graph_validation.md`.) Summary:
- **Aspect distortion / rhombus** when the WebGL drawing buffer dimensions (`innerWidth × innerHeight`) diverge from the CSS-displayed canvas box (orientation change, URL-bar resize, scrollbar gutter from `100vw`, zoom, devtools).
- **Heartbeat reheat** — the backend re-broadcasts `graph_update` ~1s; mitigated by memoizing `mergedData` on a content signature (`graphSig`) so identical frames reuse the object reference and the sim cools. Do not regress this.
- **Blank-canvas crash** — never call `d3ReheatSimulation()` before the first graphData is processed (library `layoutTick` crash). Known and avoided.

---

## 5. Performance Concerns

- Single 1,287-line component re-renders on every WS frame; mitigated by `memo` + `graphSig` memoization but still heavy.
- Directional particles on links + per-frame hover dimming loop add GPU/CPU cost on large graphs.
- No `setPixelRatio` clamp → on Retina the renderer may render at 2× resolution unnecessarily.
- `GRAPH_MAX_NODES=150 / GRAPH_MAX_EDGES=600` on the deployed backend caps client load (a deploy constraint, not a frontend one).

---

## 6. Improvement Roadmap

**P0 — correctness**
1. Replace window-derived sizing with a **ResizeObserver on the graph container** + `orientationchange`/`visualViewport` listeners, reading dims on the next animation frame. (Fixes the rhombus — see graph_validation.md.)
2. Clamp and apply `devicePixelRatio` (`renderer.setPixelRatio(Math.min(2, dpr))`).

**P1 — maintainability**
3. Decompose `GraphScene.tsx` into: `useForceConfig`, `useCameraControls`, `useResizeDims`, `ClusterLabels`, `IntelOverlay`.
4. Delete dead JSX (header) and orphaned `RightPanel.tsx` (or document why kept).
5. Centralize verdict color/size tokens.

**P2 — quality**
6. Add vitest unit tests for the risk-intel layer (`ai/riskPropagation.ts`) and a playwright smoke test that asserts the canvas aspect == container aspect after a simulated rotation.
7. Consolidate or retire the `?v=2` CinematicApp path.
8. Harden mic/TTS UX with explicit insecure-context and non-Chromium messaging (already partly present).
