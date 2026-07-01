// ──────────────────────────────────────────────────────────────────────────────
// Topology-aware 3D layout seeding for the transaction graph.
//
// The force simulation is no longer allowed to DEFINE structure (random seeding
// + generic charge produced twisted / diamond / zig-zag shapes). Instead, for
// each connected component we analyse the directed transaction topology and emit
// an intelligent INITIAL placement in a LOCAL frame (centred on the origin). The
// force engine then only REFINES that placement.
//
// Coordinate convention (LOCAL, world-aligned — NOT rotated per cluster, so the
// flow direction is globally consistent across every cluster):
//   • +Y  = upstream / source     (money originates at the TOP)
//   • -Y  = downstream / sink      (money terminates at the BOTTOM)
//   • +X  = the VISIBLE lateral spread axis (left↔right on screen)
//   • +Z  = DEPTH (into the screen) — used only for shallow organic volume
//
// CRITICAL — camera geometry drives this: the scene is framed HEAD-ON along the
// Z axis (camera sits at +Z looking toward the graph). So the X/Y plane FACES the
// investigator and Z is into-the-screen depth. Every structurally meaningful
// shape — fan-out arcs, ring circles, branch fans — is therefore laid out in the
// camera-facing X/Y plane, with Z carrying only a small amount of depth jitter.
// (The previous version spread structure in the X/Z plane, which is edge-on to
// this camera: rings collapsed to flat lines, fan-outs stacked into a hidden-
// depth column, and the graph read as a tall skinny vertical sliver.)
//
// Depth layers are spaced on Y so "money travels source → destination" reads
// instantly; a chain becomes a gently curving descent (not a ruler column), a
// fan-out becomes a wide camera-facing fan, a fan-in converges, and a laundering
// loop becomes an actual visible circle.
// ──────────────────────────────────────────────────────────────────────────────

export type LayoutType =
  | 'single'
  | 'chain'
  | 'ring'
  | 'fan-out'
  | 'fan-in'
  | 'tree'
  | 'layered'
  | 'hybrid'

export interface ComponentLayout {
  /** nodeId → local [x, y, z] position, centred on the component's own origin. */
  positions: Map<string, [number, number, number]>
  /** Detected structural pattern — drives nothing visual yet; useful for debug. */
  type: LayoutType
  /** True when this component contains a circular laundering ring (a cycle laid
   *  out as an actual circle, with any branches fanned radially OUTWARD). The
   *  renderer treats such a layout as PROTECTED — it keeps this interior-safe seed
   *  rather than letting a server/force layout route an edge through the ring. */
  containsRing?: boolean
  /** True when this component is a wide rooted fan-out laid out as a radial fan
   *  (hub centre, children on a circle, sub-branches fanned outward). Like
   *  containsRing it is a PROTECTED motif — the renderer keeps this seed instead of
   *  letting a flat server/force layout fling the branch-bearing children sideways. */
  containsFan?: boolean
  /** Post-layout quality report (collision / edge-uniformity / symmetry / aspect /
   *  crossings). Computed AFTER the refinement pass so it reflects what renders. */
  quality?: LayoutQuality
}

/** Quantified layout-quality report — the basis of the validate→refine loop. */
export interface LayoutQuality {
  /** True when every HARD criterion (no overlaps, sane aspect, uniform edges) holds. */
  pass: boolean
  /** Names of the hard criteria that failed (empty when pass === true). */
  failed: string[]
  metrics: {
    /** Closest centre-to-centre distance in the camera-facing X/Y plane. */
    minSep: number
    /** Coefficient of variation of edge lengths (0 = perfectly uniform). */
    edgeCV: number
    /** Mean residual when the layout is mirrored about its vertical axis. */
    symmetry: number
    /** Bounding-box width / height (≈1 = balanced; huge / tiny = sliver). */
    aspect: number
    /** Count of edge–edge intersections in the X/Y projection. */
    crossings: number
    /** Distance from the node centroid to the bounding-box centre (≈0 = centred). */
    centerOffset: number
  }
}

export interface DirectedEdge {
  source: string
  target: string
}

// ── Spacing constants ─────────────────────────────────────────────────────────
const LAYER_GAP            = 96   // fallback vertical distance when depth < 2
const RING_RADIUS_BASE     = 44   // circular (fraud-ring) layout base radius
const RING_RADIUS_PER_NODE = 13

// ── Chain meander (pure path) ────────────────────────────────────────────────
// A pure chain descends top→bottom while meandering left↔right on a low-frequency
// sine so it reads as a gentle curve filling width, not a ruler-straight column.
const CHAIN_PITCH      = 46   // vertical advance per node down a chain
const CHAIN_AMP        = 74   // lateral (visible X) meander amplitude — fills width
const CHAIN_WAVE       = 0.62 // radians of X-meander per node (~10 nodes/wave → gentle)
const CHAIN_Z          = 16   // shallow depth so the chain has 3D body, not flow-hiding

// ── Layered (Sugiyama) horizontal-coordinate constants ───────────────────────
// Symmetric even spacing + barycenter X-relaxation: forks stay symmetric, merge
// nodes sit between their parents, edges run vertical. Vertical gap auto-balances
// so the graph fills BOTH axes (no tall sliver, no flat pancake).
const SIB_GAP          = 76   // minimum horizontal gap between siblings in a layer
const X_SWEEPS         = 7    // barycenter X-relaxation passes (alternating direction)
const LAYER_ASPECT     = 0.82 // target stack height ≈ LAYER_ASPECT × in-plane width
const DENSE_LAYER      = 14   // above this many nodes a layer tightens its sibling step
const LAYER_JITTER     = 4    // deterministic micro-jitter → organic, non-grid feel
const LAYER_Z_DEPTH    = 16   // shallow per-node depth → 3D body, no tunnels
const GAP_MIN          = 50   // floor on vertical layer spacing (no layer merge)
const GAP_MAX          = 104  // cap on vertical layer spacing (no over-stretch)

// ── Radial fan (pure fan-out / fan-in) ───────────────────────────────────────
// A single hub splitting into k leaves (or k sources merging into one sink) is
// laid out on a circular ARC of constant radius instead of a flat horizontal row.
// Why: on a row the centre child sits directly under the hub (short edge) while
// the outer children are far diagonally (long edge) — edge lengths diverge wildly
// (a 12-way fan measured edgeCV 0.43, aspect 7.8 — a flat sliver). On an arc EVERY
// leaf is the same distance from the hub → identical edge lengths (req: equal edge
// lengths), identical angular spacing (req: even branch distribution), and a single
// merge point receives equal-length incoming edges (req: merge optimisation).
const ARC_STEP      = 0.42  // preferred angular gap between adjacent leaves (~24°)
const ARC_SPAN_MAX  = 2.70  // max total arc sweep (~155°) — keeps leaves clearly on
                            // the downstream side of the hub (flow stays readable)
const ARC_CHORD_MIN = 62    // min centre-to-centre between adjacent leaves
const ARC_R_BASE    = 116   // base fan radius (= every fan edge's length)

// ── Radial fan-out WITH downstream tails (wide rooted arborescence) ───────────
// A single source hub with a HIGH out-degree whose children carry their OWN
// outgoing branches (e.g. SOURCE → 6 smurfs, two of which → a cash-out). The pure
// 2-layer fan above is an arc; the moment a child has a tail the structure is 3+
// layers and falls into generic Sugiyama, which barycenter-pushes the branch-
// bearing children to the extremes (they "shoot sideways") and the fan stops
// reading as a fan. Instead we lay the direct children on a FULL circle (each gets
// its own outward angular corridor) and fan every child's subtree radially OUTWARD
// inside that corridor → equal hub→child radius, no branch crosses the fan or
// another branch, cash-out tails clearly exit outward.
const FAN_MIN           = 4    // hub out-degree at/above which the fan-out motif applies
const RADIAL_FAN_R      = 130  // radius of the direct-children ring (every hub edge's length)
const RADIAL_BRANCH_GAP = 96   // radial advance per downstream hop along a corridor
const RADIAL_SIB_SPREAD = 0.34 // tangential radians between sibling spurs in one corridor

// ── Validate → refine loop ───────────────────────────────────────────────────
// After the topology layout we measure quality and, where a HARD criterion fails,
// run a deterministic corrective pass before the result is ever returned (so the
// physics engine refines an already-validated seed). Deterministic = no Math.random
// anywhere, so the same dataset always yields the identical, validated layout.
const REFINE_SEP    = 46    // collision pass separates nodes to ≥ this (glows clear)
const REFINE_ITERS  = 24    // max relaxation sweeps in the collision pass
const REFINE_MAX_N  = 400   // skip the O(n²) seed-refine above this (physics handles it)
const VAL_OVERLAP   = 34    // hard fail: any node pair closer than this (glows merge)
const VAL_EDGE_CV   = 0.62  // hard fail: edge lengths too non-uniform within a graph
const VAL_ASPECT_LO = 0.16  // hard fail below — a vertical sliver
const VAL_ASPECT_HI = 6.2   // hard fail above — a flat horizontal sliver

// Deterministic [0,1) hash of a string (FNV-1a) → stable jitter, so the same
// dataset always lays out the same way (investigators build spatial memory).
function hashUnit(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) }
  return ((h >>> 0) % 100003) / 100003
}

// Tarjan's strongly-connected-components (iterative, stack-safe). A non-trivial
// SCC (size ≥ 2) is a laundering loop — money that can return to an earlier
// account. We use this to draw embedded rings as actual circles, not zig-zags.
function stronglyConnectedComponents(nodeIds: string[], out: Map<string, string[]>): string[][] {
  const idx = new Map<string, number>(), low = new Map<string, number>()
  const onStack = new Set<string>(), S: string[] = []
  const sccs: string[][] = []
  let counter = 0
  for (const start of nodeIds) {
    if (idx.has(start)) continue
    const work: Array<{ v: string; i: number }> = [{ v: start, i: 0 }]
    while (work.length) {
      const f = work[work.length - 1]
      const v = f.v
      if (f.i === 0) { idx.set(v, counter); low.set(v, counter); counter++; S.push(v); onStack.add(v) }
      const succ = out.get(v) ?? []
      if (f.i < succ.length) {
        const w = succ[f.i++]
        if (!idx.has(w)) work.push({ v: w, i: 0 })
        else if (onStack.has(w)) low.set(v, Math.min(low.get(v)!, idx.get(w)!))
      } else {
        if (low.get(v) === idx.get(v)) {
          const comp: string[] = []
          for (;;) { const w = S.pop()!; onStack.delete(w); comp.push(w); if (w === v) break }
          sccs.push(comp)
        }
        work.pop()
        if (work.length) { const p = work[work.length - 1].v; low.set(p, Math.min(low.get(p)!, low.get(v)!)) }
      }
    }
  }
  return sccs
}

// Order an SCC's nodes into cyclic sequence by following intra-SCC out-edges, so
// they sit on the circle in money-flow order (clean ring, minimal edge crossing).
function orderCycle(scc: string[], out: Map<string, string[]>): string[] {
  const inScc = new Set(scc)
  const visited = new Set<string>()
  const order: string[] = []
  let cur: string | undefined = scc[0]
  while (cur && !visited.has(cur)) {
    visited.add(cur); order.push(cur)
    cur = (out.get(cur) ?? []).find(w => inScc.has(w) && !visited.has(w))
  }
  for (const id of scc) if (!visited.has(id)) order.push(id)   // any not reached
  return order
}

// Barycenter of a node's neighbours by their current within-layer order index.
// Used to order nodes inside a layer so connected nodes sit near each other →
// fewer crossing edges.
function barycenter(
  id: string,
  adj: Map<string, string[]>,
  orderIndex: Map<string, number>,
): number {
  const nb = adj.get(id)
  if (!nb || nb.length === 0) return orderIndex.get(id) ?? 0
  let sum = 0, cnt = 0
  for (const m of nb) {
    const oi = orderIndex.get(m)
    if (oi != null) { sum += oi; cnt++ }
  }
  return cnt > 0 ? sum / cnt : (orderIndex.get(id) ?? 0)
}

// Place a hub + its leaves on a constant-radius circular arc so every hub→leaf
// edge is the SAME length and the leaves are evenly spaced by angle. `dir` = -1
// fans the leaves DOWNSTREAM (below the hub, for a fan-out); +1 fans them UPSTREAM
// (above the sink, for a fan-in). The result is vertically centred on its own
// bounding box (matching the layered branch's Y convention) and is perfectly
// symmetric — no X/Y jitter, only a shallow deterministic Z wobble for 3D body.
function placeFan(
  hub: string,
  leaves: string[],
  positions: Map<string, [number, number, number]>,
  dir: -1 | 1,
): void {
  const k = leaves.length
  const ordered = [...leaves].sort()                       // deterministic order
  const step = Math.min(ARC_STEP, ARC_SPAN_MAX / Math.max(1, k - 1))
  // Radius satisfies BOTH a comfortable base size and the min adjacent chord, so
  // wide fans grow DEEPER (bigger radius) rather than wrapping past the hub.
  const chordR = ARC_CHORD_MIN / (2 * Math.sin(step / 2) || 1)
  const R = Math.max(ARC_R_BASE, chordR)
  const centre = dir < 0 ? -Math.PI / 2 : Math.PI / 2      // straight down / up
  positions.set(hub, [0, 0, 0])
  ordered.forEach((id, i) => {
    const a = centre + (i - (k - 1) / 2) * step
    positions.set(id, [
      Math.cos(a) * R,
      Math.sin(a) * R,
      (hashUnit(id + 'z') - 0.5) * 2 * LAYER_Z_DEPTH,
    ])
  })
  // Centre on the vertical mid of the bbox (hub at one extreme, leaves at the other).
  let yMin = Infinity, yMax = -Infinity
  for (const id of [hub, ...ordered]) {
    const p = positions.get(id)!; if (p[1] < yMin) yMin = p[1]; if (p[1] > yMax) yMax = p[1]
  }
  const shift = (yMin + yMax) / 2
  for (const id of [hub, ...ordered]) { positions.get(id)![1] -= shift }
}

// Radial fan-out for a WIDE rooted arborescence (one source hub, every other node
// indeg 1, hub out-degree ≥ FAN_MIN, WITH downstream tails). Hub at centre; direct
// children on a full circle at even angular spacing (each gets its own outward
// corridor); each child's subtree fanned radially OUTWARD inside that corridor by
// BFS hop, with sibling tangential spread — so the fan reads as a fan, every hub
// edge is the same length, and no tail crosses the fan or another tail. Mirrors the
// embedded-ring branch's radial-outward strategy for geometric consistency.
function placeRadialFan(
  hub: string,
  out: Map<string, string[]>,
  nodeIds: string[],
  positions: Map<string, [number, number, number]>,
): void {
  const zj = (id: string) => (hashUnit(id + 'z') - 0.5) * 2 * LAYER_Z_DEPTH
  const children = [...(out.get(hub) ?? [])].sort()
  const k = children.length
  positions.set(hub, [0, 0, 0])
  // Direct children evenly spaced on a full circle (start at "down" = -90° so the
  // first child reads downstream), each anchoring its own outward corridor.
  const childAngle = new Map<string, number>()
  children.forEach((c, i) => {
    const a = -Math.PI / 2 + (i / k) * Math.PI * 2
    childAngle.set(c, a)
    positions.set(c, [Math.cos(a) * RADIAL_FAN_R, Math.sin(a) * RADIAL_FAN_R, zj(c)])
  })
  // BFS downstream → each descendant's hop distance + which direct-child corridor
  // it belongs to (so a whole subtree stays inside its child's angular sector).
  const hop = new Map<string, number>([[hub, 0]])
  const corridor = new Map<string, string>()
  for (const c of children) { hop.set(c, 1); corridor.set(c, c) }
  const q = [...children]
  for (let h = 0; h < q.length; h++) {
    for (const v of out.get(q[h]) ?? []) {
      if (!hop.has(v)) { hop.set(v, hop.get(q[h])! + 1); corridor.set(v, corridor.get(q[h])!); q.push(v) }
    }
  }
  // Group descendants by (corridor, hop) so siblings fan tangentially, not on top.
  const groups = new Map<string, string[]>()
  for (const id of nodeIds) {
    if (id === hub || (hop.get(id) ?? 0) <= 1) continue
    const key = `${corridor.get(id) ?? '?'}|${hop.get(id)}`
    ;(groups.get(key) ?? groups.set(key, []).get(key)!).push(id)
  }
  for (const [key, members] of groups) {
    const base = childAngle.get(key.split('|')[0]) ?? 0
    members.sort()
    members.forEach((id, i) => {
      const a = base + (i - (members.length - 1) / 2) * RADIAL_SIB_SPREAD
      const rr = RADIAL_FAN_R + ((hop.get(id) ?? 1) - 1) * RADIAL_BRANCH_GAP
      positions.set(id, [Math.cos(a) * rr, Math.sin(a) * rr, zj(id)])
    })
  }
  for (const id of nodeIds) if (!positions.has(id)) positions.set(id, [0, 0, 0])
}

// Deterministic, overlap-ONLY collision relaxation in the camera-facing X/Y plane.
// Only pairs closer than `minSep` move, and only by the amount needed to clear —
// so it NEVER disturbs already-well-spaced layouts (rings, fans, diamonds) and
// only rescues genuinely cramped nodes (e.g. branch spurs that landed on top of
// each other). `lockY` keeps hierarchical layers intact (push apart horizontally
// only); radial layouts (rings + spurs) unlock Y so spurs can splay outward.
// `fixed` nodes are anchors that never move (e.g. ring-core nodes — preserves the
// circle). O(n²·iters); the caller gates it by component size.
function resolveCollisions(
  positions: Map<string, [number, number, number]>,
  ids: string[],
  minSep: number,
  iters: number,
  lockY: boolean,
  fixed?: Set<string>,
): void {
  for (let it = 0; it < iters; it++) {
    let moved = false
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const A = ids[i], B = ids[j]
        const a = positions.get(A)!, b = positions.get(B)!
        let dx = b[0] - a[0], dy = b[1] - a[1]
        let d = Math.hypot(dx, dy)
        if (d >= minSep) continue
        if (d < 1e-6) {                                    // coincident → deterministic nudge
          dx = hashUnit(A + B + 'x') - 0.5; dy = hashUnit(A + B + 'y') - 0.5
          d = Math.hypot(dx, dy) || 1
        }
        const aFixed = fixed?.has(A) ?? false, bFixed = fixed?.has(B) ?? false
        if (aFixed && bFixed) continue
        // Split the correction by which endpoints can move.
        const wa = aFixed ? 0 : bFixed ? 1 : 0.5
        const wb = bFixed ? 0 : aFixed ? 1 : 0.5
        const push = (minSep - d) / d
        const ox = dx * push, oy = dy * push
        a[0] -= ox * wa; b[0] += ox * wb
        if (!lockY) { a[1] -= oy * wa; b[1] += oy * wb }
        moved = true
      }
    }
    if (!moved) break
  }
}

/**
 * Measure layout quality and decide pass/fail against the hard criteria. This is
 * the "validation" stage: overlaps, edge-length uniformity, bounding-box aspect,
 * symmetry, edge crossings and centring are all quantified so a layout can be
 * objectively checked (and re-refined) before it is shown to an investigator.
 *
 * Hard fails (drive the refine loop / warning): node overlap, extreme aspect,
 * non-uniform edges. Symmetry / crossings / centring are REPORTED — many genuine
 * fraud graphs are legitimately asymmetric, so they must not be forced symmetric.
 */
export function validateComponentLayout(
  nodeIds: string[],
  edges: DirectedEdge[],
  positions: Map<string, [number, number, number]>,
  thresholds?: Partial<{ overlap: number; aspectLo: number; aspectHi: number; edgeCV: number }>,
): LayoutQuality {
  const TH = {
    overlap:  thresholds?.overlap  ?? VAL_OVERLAP,
    aspectLo: thresholds?.aspectLo ?? VAL_ASPECT_LO,
    aspectHi: thresholds?.aspectHi ?? VAL_ASPECT_HI,
    edgeCV:   thresholds?.edgeCV   ?? VAL_EDGE_CV,
  }
  const P = nodeIds.map(id => positions.get(id) ?? [0, 0, 0])
  const n = P.length

  // minSep (closest pair, XY)
  let minSep = Infinity
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
    const d = Math.hypot(P[i][0] - P[j][0], P[i][1] - P[j][1])
    if (d < minSep) minSep = d
  }
  if (!Number.isFinite(minSep)) minSep = Infinity

  // edge-length uniformity (coefficient of variation, XY)
  const lens: number[] = []
  for (const e of edges) {
    const a = positions.get(e.source), b = positions.get(e.target)
    if (a && b) lens.push(Math.hypot(a[0] - b[0], a[1] - b[1]))
  }
  const eMean = lens.reduce((s, x) => s + x, 0) / (lens.length || 1)
  const eSd = Math.sqrt(lens.reduce((s, x) => s + (x - eMean) * (x - eMean), 0) / (lens.length || 1))
  const edgeCV = eMean > 1e-6 ? eSd / eMean : 0

  // bounding box → aspect + centring
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  let cxs = 0, cys = 0
  for (const p of P) {
    if (p[0] < minX) minX = p[0]; if (p[0] > maxX) maxX = p[0]
    if (p[1] < minY) minY = p[1]; if (p[1] > maxY) maxY = p[1]
    cxs += p[0]; cys += p[1]
  }
  const w = maxX - minX, h = maxY - minY
  const aspect = h > 1e-6 ? w / h : (w > 1e-6 ? VAL_ASPECT_HI + 1 : 1)
  const bboxCx = (minX + maxX) / 2, bboxCy = (minY + maxY) / 2
  const centerOffset = Math.hypot(cxs / (n || 1) - bboxCx, cys / (n || 1) - bboxCy)

  // mirror symmetry about the vertical axis through the centroid (nearest-match)
  const cx = cxs / (n || 1)
  let sym = 0
  for (const p of P) {
    const rx = 2 * cx - p[0], ry = p[1]
    let best = Infinity
    for (const q of P) { const d = Math.hypot(q[0] - rx, q[1] - ry); if (d < best) best = d }
    sym += best
  }
  sym = n ? sym / n : 0

  // edge crossings in the XY projection (skip edges sharing an endpoint).
  // O(E²) — report-only, so on very dense graphs we skip it (crossings = -1)
  // rather than spend tens of ms per structural update (req: performance).
  let crossings = edges.length > 800 ? -1 : 0
  const ccw = (a: number[], b: number[], c: number[]) =>
    (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c[0] - a[0])
  for (let i = 0; crossings >= 0 && i < edges.length; i++) {
    for (let j = i + 1; j < edges.length; j++) {
      const e1 = edges[i], e2 = edges[j]
      if (e1.source === e2.source || e1.source === e2.target ||
          e1.target === e2.source || e1.target === e2.target) continue
      const a1 = positions.get(e1.source), a2 = positions.get(e1.target)
      const b1 = positions.get(e2.source), b2 = positions.get(e2.target)
      if (!a1 || !a2 || !b1 || !b2) continue
      if ((ccw(a1, b1, b2) > 0) !== (ccw(a2, b1, b2) > 0) &&
          (ccw(a1, a2, b1) > 0) !== (ccw(a1, a2, b2) > 0)) crossings++
    }
  }

  const failed: string[] = []
  if (n > 1 && minSep < TH.overlap) failed.push('overlap')
  if (n > 2 && (aspect < TH.aspectLo || aspect > TH.aspectHi)) failed.push('aspect')
  if (lens.length > 1 && edgeCV > TH.edgeCV) failed.push('edgeCV')

  return {
    pass: failed.length === 0,
    failed,
    metrics: { minSep, edgeCV, symmetry: sym, aspect, crossings, centerOffset },
  }
}

/**
 * Compute an intelligent local 3D layout for ONE connected component, then
 * VALIDATE and (where needed) REFINE it before returning, so the force engine
 * always refines an already-clean, quality-checked seed.
 *
 * @param nodeIds  all node ids in the component
 * @param edges    directed edges (source → target) restricted to this component
 */
export function computeComponentLayout(
  nodeIds: string[],
  edges: DirectedEdge[],
): ComponentLayout {
  const base = computeBaseLayout(nodeIds, edges)
  const { positions, type } = base
  const n = nodeIds.length
  if (n <= 2) return base

  // ── Refinement pass (deterministic) ──────────────────────────────────────────
  // Resolve any residual node overlaps so glows never merge (req: collision). The
  // arc-fan / ring / Sugiyama branches are already well spaced, so this is a no-op
  // for them and only rescues cramped cases (e.g. branch spurs on an embedded ring).
  if (n <= REFINE_MAX_N) {
    // Hierarchical layouts push apart horizontally (keep layers intact); radial
    // layouts (rings, radial fans) unlock Y so spurs/branches splay outward.
    const radial = type === 'ring' || type === 'hybrid' || base.containsFan === true
    let fixed: Set<string> | undefined
    if (type === 'hybrid') {
      // Pin nodes that sit on the cycle (their radius ≈ the ring radius) so the
      // collision pass only splays the attached spurs, never deforms the loop.
      const rs = nodeIds.map(id => { const p = positions.get(id)!; return Math.hypot(p[0], p[1]) })
      const maxR = Math.max(...rs)
      fixed = new Set(nodeIds.filter((_, i) => rs[i] >= maxR * 0.72))
    }
    resolveCollisions(positions, nodeIds, REFINE_SEP, REFINE_ITERS, !radial, fixed)
  }

  // ── Validation pass ──────────────────────────────────────────────────────────
  const quality = validateComponentLayout(nodeIds, edges, positions)
  return { positions, type, containsRing: base.containsRing, containsFan: base.containsFan, quality }
}

/**
 * Raw topology layout (no validation / refinement) — the original, unit-tested
 * engine. Kept intact and wrapped by computeComponentLayout above.
 *
 * @param nodeIds  all node ids in the component
 * @param edges    directed edges (source → target) restricted to this component
 */
function computeBaseLayout(
  nodeIds: string[],
  edges: DirectedEdge[],
): ComponentLayout {
  const n = nodeIds.length
  const positions = new Map<string, [number, number, number]>()
  if (n === 0) return { positions, type: 'single' }
  if (n === 1) { positions.set(nodeIds[0], [0, 0, 0]); return { positions, type: 'single' } }

  // ── Directed adjacency + degrees (deduped, self-loops dropped) ───────────────
  const out    = new Map<string, string[]>()
  const inn    = new Map<string, string[]>()
  const indeg  = new Map<string, number>()
  const outdeg = new Map<string, number>()
  for (const id of nodeIds) { out.set(id, []); inn.set(id, []); indeg.set(id, 0); outdeg.set(id, 0) }

  const seen = new Set<string>()
  for (const e of edges) {
    if (e.source === e.target) continue
    if (!out.has(e.source) || !inn.has(e.target)) continue
    const key = `${e.source}>${e.target}`
    if (seen.has(key)) continue
    seen.add(key)
    out.get(e.source)!.push(e.target)
    inn.get(e.target)!.push(e.source)
    outdeg.set(e.source, outdeg.get(e.source)! + 1)
    indeg.set(e.target,  indeg.get(e.target)!  + 1)
  }

  // ── Pure cycle (fraud ring): every node has in==1 and out==1 and the single
  //    successor walk visits all nodes → lay them on a circle in cycle order. ──
  const allUnit = nodeIds.every(id => indeg.get(id) === 1 && outdeg.get(id) === 1)
  if (allUnit) {
    const order: string[] = []
    const visited = new Set<string>()
    let cur: string | undefined = nodeIds[0]
    while (cur && !visited.has(cur)) {
      visited.add(cur); order.push(cur)
      cur = out.get(cur)![0]
    }
    if (order.length === n) {
      const R = RING_RADIUS_BASE + n * RING_RADIUS_PER_NODE
      order.forEach((id, i) => {
        const a = (i / n) * Math.PI * 2
        // Circle lies in the camera-facing X/Y plane so a laundering loop reads as
        // an ACTUAL visible circle (head-on), not an edge-on flat line. A small Z
        // ripple gives it organic 3D body without hiding the ring shape.
        positions.set(id, [Math.cos(a) * R, Math.sin(a) * R, Math.sin(a * 3) * 9])
      })
      return { positions, type: 'ring', containsRing: true }
    }
  }

  // ── Embedded ring (a laundering cycle WITH attached branches / tails) ─────────
  // The pure-cycle case above handles a bare ring. Here a non-trivial strongly-
  // connected component (size ≥ 3) is a laundering LOOP that also has spurs or
  // tails hanging off it. Flattening it through the layered DAG (below) hides the
  // loop. Instead we keep the loop CIRCULAR — so the cycle reads instantly — and
  // fan the attached accounts radially OUTWARD from their ring anchor.
  const sccs = stronglyConnectedComponents(nodeIds, out)
  const bigScc = sccs.filter(s => s.length >= 3).sort((a, b) => b.length - a.length)[0]
  if (bigScc && bigScc.length < n) {
    const jitU = (id: string, axis: string) => (hashUnit(id + axis) - 0.5) * 2 * LAYER_JITTER
    const ringOrder = orderCycle(bigScc, out)
    const L = ringOrder.length
    const R = RING_RADIUS_BASE + L * RING_RADIUS_PER_NODE
    const ringPos = new Map<string, [number, number]>()
    const inRing = new Set(bigScc)
    ringOrder.forEach((id, i) => {
      const a = (i / L) * Math.PI * 2
      const x = Math.cos(a) * R, y = Math.sin(a) * R
      positions.set(id, [x, y, Math.sin(a * 3) * 9])
      ringPos.set(id, [x, y])
    })
    // undirected adjacency → BFS out from the ring for hop distance + anchor node
    const adj = new Map<string, string[]>()
    for (const id of nodeIds) adj.set(id, [])
    for (const e of edges) {
      if (e.source === e.target) continue
      adj.get(e.source)?.push(e.target)
      adj.get(e.target)?.push(e.source)
    }
    const hop = new Map<string, number>(), anchor = new Map<string, string>()
    const q: string[] = [...bigScc]
    for (const id of bigScc) { hop.set(id, 0); anchor.set(id, id) }
    for (let h = 0; h < q.length; h++) {
      const u = q[h]
      for (const v of adj.get(u) ?? []) {
        if (!hop.has(v)) { hop.set(v, hop.get(u)! + 1); anchor.set(v, anchor.get(u)!); q.push(v) }
      }
    }
    // group spurs by (anchor, hop) so siblings fan tangentially without overlap
    const groups = new Map<string, string[]>()
    for (const id of nodeIds) {
      if (inRing.has(id)) continue
      const key = `${anchor.get(id) ?? '?'}|${hop.get(id) ?? 1}`
      ;(groups.get(key) ?? groups.set(key, []).get(key)!).push(id)
    }
    const BRANCH_GAP = 42
    for (const [key, members] of groups) {
      const ap = ringPos.get(key.split('|')[0]) ?? [0, 0]
      const baseA = Math.atan2(ap[1], ap[0])            // outward (away from centre)
      members.sort()                                     // deterministic order
      members.forEach((id, i) => {
        const a = baseA + (i - (members.length - 1) / 2) * 0.5   // tangential spread
        const rr = R + (hop.get(id) ?? 1) * BRANCH_GAP
        positions.set(id, [
          Math.cos(a) * rr + jitU(id, 'x'),
          Math.sin(a) * rr + jitU(id, 'y'),
          (hashUnit(id + 'z') - 0.5) * 2 * LAYER_Z_DEPTH,
        ])
      })
    }
    for (const id of nodeIds) if (!positions.has(id)) positions.set(id, [jitU(id, 'x'), jitU(id, 'y'), 0])
    return { positions, type: 'hybrid', containsRing: true }
  }

  // ── Wide rooted fan-out WITH tails (arborescence, high-degree root) ───────────
  // A single source hub (indeg 0) that is the widest node (out-degree ≥ FAN_MIN),
  // every other node indeg 1, edge count = n-1 (a rooted out-tree), AND at least one
  // child carries a downstream tail (n > hub-out + 1, so it's NOT the pure 2-layer
  // fan handled below). Generic Sugiyama flings the branch-bearing children sideways
  // here; a radial fan keeps it reading as a fan. Runs BEFORE the layered fallback.
  const roots = nodeIds.filter(id => indeg.get(id) === 0)
  if (roots.length === 1) {
    const hub = roots[0]
    const hubOut = outdeg.get(hub) ?? 0
    const maxOut = Math.max(...nodeIds.map(id => outdeg.get(id) ?? 0))
    const isTree = seen.size === n - 1 && nodeIds.every(id => id === hub || indeg.get(id) === 1)
    if (hubOut === maxOut && hubOut >= FAN_MIN && isTree && n > hubOut + 1) {
      placeRadialFan(hub, out, nodeIds, positions)
      return { positions, type: 'fan-out', containsFan: true }
    }
  }

  // ── Layered (Sugiyama-style) for everything else ─────────────────────────────
  // Longest-path layering on a DAG. A naive relaxation over a CYCLIC component
  // re-relaxes through the cycle and inflates depths without bound (a 4-cycle +
  // tail produced depths like 29,30,31,32 instead of 0,1,2,3) — which flings the
  // downstream nodes many layers away from the rest and stretches the whole graph
  // into a thin line. So we first BREAK CYCLES: an iterative DFS drops every
  // back-edge (an edge to a node still on the DFS stack), yielding a DAG; then a
  // Kahn topological order + single relaxation gives correct, bounded depths.
  const color = new Map<string, number>()              // 0=unvisited 1=on-stack 2=done
  for (const id of nodeIds) color.set(id, 0)
  const acyclicOut = new Map<string, string[]>()
  for (const id of nodeIds) acyclicOut.set(id, [])
  for (const start of nodeIds) {
    if (color.get(start) !== 0) continue
    const stack: Array<{ id: string; i: number }> = [{ id: start, i: 0 }]
    color.set(start, 1)
    while (stack.length) {
      const top = stack[stack.length - 1]
      const succ = out.get(top.id)!
      if (top.i < succ.length) {
        const v = succ[top.i++]
        if (color.get(v) === 1) continue              // back-edge → drop (breaks cycle)
        acyclicOut.get(top.id)!.push(v)
        if (color.get(v) === 0) { color.set(v, 1); stack.push({ id: v, i: 0 }) }
      } else {
        color.set(top.id, 2)
        stack.pop()
      }
    }
  }

  // Kahn topological sort of the DAG, then longest-path relaxation in that order.
  const dagIn = new Map<string, number>()
  for (const id of nodeIds) dagIn.set(id, 0)
  for (const id of nodeIds) for (const v of acyclicOut.get(id)!) dagIn.set(v, dagIn.get(v)! + 1)
  const topo: string[] = []
  const ready: string[] = nodeIds.filter(id => dagIn.get(id) === 0)
  while (ready.length) {
    const u = ready.shift()!
    topo.push(u)
    for (const v of acyclicOut.get(u)!) {
      dagIn.set(v, dagIn.get(v)! - 1)
      if (dagIn.get(v) === 0) ready.push(v)
    }
  }
  const depth = new Map<string, number>()
  for (const id of nodeIds) depth.set(id, 0)
  for (const u of topo) {
    const du = depth.get(u)!
    for (const v of acyclicOut.get(u)!) {
      if (depth.get(v)! < du + 1) depth.set(v, du + 1)
    }
  }

  let maxDepth = 0
  for (const d of depth.values()) if (d > maxDepth) maxDepth = d
  const layers: string[][] = Array.from({ length: maxDepth + 1 }, () => [])
  for (const id of nodeIds) layers[depth.get(id)!].push(id)

  // ── Crossing reduction: alternate down/up barycenter sweeps ──────────────────
  const orderIndex = new Map<string, number>()
  layers.forEach(layer => layer.forEach((id, i) => orderIndex.set(id, i)))
  const SWEEPS = 4
  for (let s = 0; s < SWEEPS; s++) {
    if (s % 2 === 0) {
      // downward: order each layer by the barycenter of its PARENTS
      for (let d = 1; d < layers.length; d++) {
        layers[d].sort((a, b) => barycenter(a, inn, orderIndex) - barycenter(b, inn, orderIndex))
        layers[d].forEach((id, i) => orderIndex.set(id, i))
      }
    } else {
      // upward: order each layer by the barycenter of its CHILDREN
      for (let d = layers.length - 2; d >= 0; d--) {
        layers[d].sort((a, b) => barycenter(a, out, orderIndex) - barycenter(b, out, orderIndex))
        layers[d].forEach((id, i) => orderIndex.set(id, i))
      }
    }
  }

  // ── Assign 3D positions ──────────────────────────────────────────────────────
  // Deterministic micro-jitter keeps the layout organic (no robotic perfect grid)
  // while staying stable across reloads.
  const jit = (id: string, axis: string) => (hashUnit(id + axis) - 0.5) * 2 * LAYER_JITTER

  const D = layers.length
  let maxLayerSize = 0
  for (const layer of layers) if (layer.length > maxLayerSize) maxLayerSize = layer.length

  if (maxLayerSize === 1) {
    // ── PURE CHAIN / PATH → gentle camera-facing curve ─────────────────────────
    // One node per layer. A straight vertical line is the "tall skinny column"
    // problem. Instead the chain DESCENDS (money flow reads top→bottom) while
    // meandering left↔right in the VISIBLE x axis — a low-frequency sine so it's a
    // gentle curve, not a tight zig-zag. A shallow z wobble gives it 3D body
    // without hiding the flow. Long chains still read as long readable paths; they
    // just curve naturally instead of forming a ruler-straight sliver.
    const spine = layers.map(l => l[0])
    const m = spine.length
    spine.forEach((id, i) => {
      const y = ((m - 1) / 2 - i) * CHAIN_PITCH
      const x = Math.sin(i * CHAIN_WAVE) * CHAIN_AMP
      const z = Math.cos(i * CHAIN_WAVE * 0.5) * CHAIN_Z
      positions.set(id, [x + jit(id, 'x'), y + jit(id, 'y'), z + jit(id, 'z')])
    })
  } else if (D === 2 && (layers[0].length === 1 || layers[1].length === 1)) {
    // ── PURE FAN-OUT / FAN-IN → constant-radius arc ────────────────────────────
    // One hub → many leaves (or many sources → one sink). A flat row makes the
    // centre edge short and the outer edges long (edgeCV ↑, a wide sliver); an arc
    // makes EVERY hub edge identical in length and spaces the leaves evenly by
    // angle, with the single merge/split point centred on its group.
    const fanOut = layers[0].length === 1
    placeFan(
      fanOut ? layers[0][0] : layers[1][0],
      fanOut ? layers[1] : layers[0],
      positions,
      fanOut ? -1 : 1,
    )
  } else {
    // ── LAYERED (fan-out / fan-in / tree / diamond / hybrid) ───────────────────
    // Sugiyama horizontal coordinate assignment. Each layer's nodes start evenly
    // spaced and SYMMETRIC about the spine (in the crossing-reduced order), then a
    // few barycenter X-relaxation sweeps pull every node toward the mean X of its
    // neighbours. The effect:
    //   • FORKS stay symmetric — a hub sits centred above its children,
    //   • MERGE / diamond nodes sit centred BETWEEN their parents (a real diamond,
    //     not a skewed kite — the old sine-spine pushed merge points off-axis),
    //   • edges run as vertical as possible → far fewer crossings,
    //   • small fans spread evenly (the old golden-angle sunflower put 4 children
    //     at 0°/137°/274°/51° → "three left, one right", and leaf rings read as
    //     polygons).
    // Y encodes money-flow depth; Z is a shallow deterministic wobble (no tunnels).
    const xpos = new Map<string, number>()
    const stepOf = (cnt: number) => (cnt > DENSE_LAYER ? SIB_GAP * 0.66 : SIB_GAP)
    layers.forEach(layer => {
      const cnt = layer.length, s = stepOf(cnt)
      layer.forEach((id, i) => xpos.set(id, (i - (cnt - 1) / 2) * s))
    })
    // Enforce the minimum sibling gap inside one layer, preserving its centre.
    const resolveLayer = (layer: string[]) => {
      if (layer.length < 2) return
      const s = stepOf(layer.length)
      const sorted = [...layer].sort((p, q) => xpos.get(p)! - xpos.get(q)!)
      for (let i = 1; i < sorted.length; i++) {
        const need = xpos.get(sorted[i - 1])! + s
        if (xpos.get(sorted[i])! < need) xpos.set(sorted[i], need)
      }
      const mid = (xpos.get(sorted[0])! + xpos.get(sorted[sorted.length - 1])!) / 2
      for (const id of sorted) xpos.set(id, xpos.get(id)! - mid)
    }
    for (let s = 0; s < X_SWEEPS; s++) {
      const downward = s % 2 === 0
      for (let k = 0; k < layers.length; k++) {
        const d = downward ? k : layers.length - 1 - k
        for (const id of layers[d]) {
          const nb = [...(inn.get(id) ?? []), ...(out.get(id) ?? [])]
          if (!nb.length) continue
          let sum = 0, c = 0
          for (const m of nb) { const xm = xpos.get(m); if (xm != null) { sum += xm; c++ } }
          if (c) xpos.set(id, sum / c)
        }
        resolveLayer(layers[d])
      }
    }
    // Balanced vertical gap so the graph fills BOTH axes (height ≈ ASPECT × width)
    // — rounds out diamonds, prevents the tall-skinny sliver and the flat pancake.
    let minX = Infinity, maxX = -Infinity
    for (const v of xpos.values()) { if (v < minX) minX = v; if (v > maxX) maxX = v }
    const width = Math.max(SIB_GAP, maxX - minX)
    const gap = D > 1
      ? Math.min(GAP_MAX, Math.max(GAP_MIN, (width * LAYER_ASPECT) / (D - 1)))
      : LAYER_GAP
    layers.forEach((layer, d) => {
      const y = ((D - 1) / 2 - d) * gap
      for (const id of layer) {
        const z = (hashUnit(id + 'z') - 0.5) * 2 * LAYER_Z_DEPTH
        positions.set(id, [xpos.get(id)! + jit(id, 'x'), y + jit(id, 'y'), z])
      }
    })
  }

  // ── Classify (best-effort — for debug / future adaptive hooks) ───────────────
  let type: LayoutType
  const edgeCount = seen.size
  if (D === n) {
    type = 'chain'                                   // one node per layer, full depth
  } else if (D === 2 && layers[0].length === 1) {
    type = 'fan-out'                                 // single source → many sinks
  } else if (D === 2 && layers[1].length === 1) {
    type = 'fan-in'                                  // many sources → single sink
  } else if (edgeCount === n - 1 && nodeIds.every(id => indeg.get(id)! <= 1)) {
    type = 'tree'                                    // acyclic, single-parent
  } else if (edgeCount > n * 1.8) {
    type = 'hybrid'                                  // dense / heavily interconnected
  } else {
    type = 'layered'
  }

  return { positions, type }
}
