# Graph Validation — Distortion / Rhombus Root-Cause Analysis

> Observed symptoms (reported): the graph appears distorted; sometimes looks like a
> **rhombus**; the shape **changes when the screen is rotated**; visual proportions
> seem inconsistent.
>
> Subject: `frontend/src/components/GraphScene.tsx` (1,287 lines) using
> `react-force-graph-3d` over three.js, mounted full-viewport in `frontend/src/App.tsx`.

---

## 1. Root Cause Analysis

**The distortion is a WebGL drawing-buffer ↔ CSS-display aspect-ratio mismatch.**

The relevant code:

```tsx
// GraphScene.tsx
const [dims, setDims] = useState({ w: window.innerWidth, h: window.innerHeight })   // L186
// ...
useEffect(() => {                                                                    // L368–372
  const onResize = () => setDims({ w: window.innerWidth, h: window.innerHeight })
  window.addEventListener('resize', onResize)
  return () => window.removeEventListener('resize', onResize)
}, [])
// ...
<div style={{ position: 'absolute', inset: 0, zIndex: 1 }}>                           // L1194
  <ForceGraph3D width={dims.w} height={dims.h} ... />                                 // L1198–1202
</div>
```

`react-force-graph-3d` uses the `width`/`height` props as the **WebGL drawing buffer
size** — it calls `renderer.setSize(width, height)` and sets
`camera.aspect = width / height`. Meanwhile the canvas *element* is laid out by CSS:
the wrapper is `position:absolute; inset:0` inside an `App` container of
`width:100vw; height:100vh`, so the canvas is **stretched by CSS to fill the real box.**

A scene is rendered into the NDC cube, mapped to the drawing buffer, then the browser
**stretches that buffer to the CSS box.** If

```
drawingBufferAspect (= dims.w / dims.h)   ≠   cssBoxAspect (actual canvas client size)
```

the stretch is **non-uniform** → every circle becomes an ellipse and the (roughly
spherical) cluster layout reads as a **rhombus / diamond**. The two aspects diverge
whenever `dims` is stale or `100vw/100vh` ≠ `innerWidth/innerHeight`.

### Why it specifically distorts *on rotation*
On orientation change (tablet/phone, or a Mac display rotate / Sidecar / Stage Manager
resize), iOS/Safari and some Chromium paths fire `resize` **before layout settles**, and
`window.innerWidth/innerHeight` are read transposed or pre-rotation. The CSS box updates
immediately (it's `inset:0`), but `dims` lags by a frame (or never fires a clean
`resize`), so the drawing buffer keeps the **old/transposed aspect** while the box has the
new one → maximal shear right after rotation. This is exactly the reported symptom.

### Secondary contributors
1. **`100vw` includes the scrollbar gutter**, while `window.innerWidth` may not (platform-dependent) → a few-px aspect mismatch even at rest.
2. **No `orientationchange` / `visualViewport.resize` listener** — mobile URL-bar show/hide and split-view resizes don't reliably fire `resize`.
3. **No `ResizeObserver`** on the actual container — any layout-driven size change (devtools dock, panel open) that doesn't bubble a window `resize` is missed.
4. **No `devicePixelRatio` management** — causes blur on Retina (not rhombus), but compounds the "proportions look off" impression.

---

## 2. Screenspace Analysis

| Quantity | Source | Correct? |
|---|---|---|
| Drawing buffer W×H | `dims.w × dims.h` (= `innerWidth × innerHeight` at last `resize`) | Stale between/around resizes |
| Canvas CSS box | `inset:0` of a `100vw × 100vh` parent | Always current |
| `camera.aspect` | set by library from `width/height` props | Inherits staleness of `dims` |
| Pixel ratio | unmanaged (browser default) | Blur on HiDPI |

The invariant that must hold every frame — `camera.aspect === cssBox.width / cssBox.height`
**and** `drawingBuffer == cssBox (× dpr)` — is only *coincidentally* satisfied (when the
window is the source of truth and no rotation/resize is mid-flight).

---

## 3. Coordinate Transform Analysis

- **Model → world:** d3-force-3d positions (the multi-scale cluster forces) are correct and uniform; the layout itself is not distorted.
- **World → view:** `camera.cameraPosition(...)` / `zoomToFit(...)` are uniform; fine.
- **View → clip:** `projectionMatrix` derived from `camera.aspect`. **This is where the error enters** — a wrong `aspect` makes the projection anisotropic.
- **Clip → screen (viewport transform):** correct relative to the drawing buffer.
- **Drawing buffer → CSS pixels (browser stretch):** **second error source** — non-uniform when buffer aspect ≠ box aspect.

So the geometry is right; the **projection aspect** and the **final CSS stretch** are the two places the rhombus is introduced, both fed by the same stale `dims`.

---

## 4. Rendering Pipeline Analysis

1. WS `graph_update` → `mergedData` memoized on `graphSig` (prevents heartbeat reheat — keep).
2. d3 sim warms (`warmupTicks=40`) and cools (`cooldownTicks=340`, `d3AlphaDecay=0.0165`).
3. Library `renderer.setSize(dims.w, dims.h)` + `camera.aspect = dims.w/dims.h` on prop change.
4. three.js renders into the buffer; browser composites/stretches the canvas element to the `inset:0` box.

The pipeline is sound; only step 3's inputs (and the step-4 stretch) are wrong when `dims` is stale.

---

## 5. Recommended Fixes

**Fix 1 (primary) — measure the container, not the window.** Replace the window-derived
`dims` with a `ResizeObserver` on the graph wrapper, reading the box on the next frame:

```tsx
const wrapRef = useRef<HTMLDivElement>(null)
const [dims, setDims] = useState({ w: 0, h: 0 })
useLayoutEffect(() => {
  const el = wrapRef.current!
  let raf = 0
  const measure = () => {
    cancelAnimationFrame(raf)
    raf = requestAnimationFrame(() => {
      const r = el.getBoundingClientRect()
      setDims({ w: Math.round(r.width), h: Math.round(r.height) })
    })
  }
  const ro = new ResizeObserver(measure)
  ro.observe(el)
  measure()
  window.addEventListener('orientationchange', measure)
  window.visualViewport?.addEventListener('resize', measure)
  return () => { ro.disconnect(); cancelAnimationFrame(raf)
    window.removeEventListener('orientationchange', measure)
    window.visualViewport?.removeEventListener('resize', measure) }
}, [])
// <div ref={wrapRef} style={{ position:'absolute', inset:0 }}>
//   <ForceGraph3D width={dims.w} height={dims.h} ... />
```

This guarantees `drawingBuffer == cssBox` at all times, so `camera.aspect` is always
correct and the CSS stretch is always uniform → **no rhombus, rotation-safe.**

**Fix 2 — clamp device pixel ratio** for crisp HiDPI without over-rendering:

```tsx
useEffect(() => {
  const r = fgRef.current?.renderer?.()
  r?.setPixelRatio(Math.min(2, window.devicePixelRatio || 1))
}, [dims])
```

**Fix 3 — belt-and-braces** on every `dims` change, force the library to re-derive:

```tsx
useEffect(() => {
  const cam = fgRef.current?.camera?.() as THREE.PerspectiveCamera | undefined
  if (cam) { cam.aspect = dims.w / dims.h; cam.updateProjectionMatrix() }
  fgRef.current?.renderer?.()?.setSize(dims.w, dims.h, false)
}, [dims])
```

**Fix 4 — CSS hygiene:** ensure no global rule forces `canvas { width:100%!important;
height:100%!important }` (today only `.cy-container canvas` is styled, for cytoscape — OK).
Prefer `width:100%; height:100%` on the wrapper over `100vw/100vh` on the ancestor to avoid
the scrollbar-gutter mismatch.

**Verification:** add a playwright/puppeteer check that, after a simulated viewport
rotation, `canvas.width / canvas.height` (drawing buffer) equals
`canvas.clientWidth / canvas.clientHeight` (CSS box) within 1px — the rhombus is
*defined* by that ratio diverging.

---

## 6. Verdict

The graph **geometry and force layout are correct**; the distortion is purely a
**viewport/aspect plumbing bug** — drawing-buffer dimensions sourced from
`window.innerWidth/innerHeight` and updated only on `resize`, while the canvas is
CSS-stretched to a `100vw/100vh inset:0` box. Switching to a container `ResizeObserver`
(+ orientation/visualViewport listeners + DPR clamp) resolves all four reported symptoms.
