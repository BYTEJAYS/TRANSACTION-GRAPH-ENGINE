import { useRef, useCallback, useEffect, useLayoutEffect, useState, useMemo, memo, forwardRef, useImperativeHandle } from 'react'
import ForceGraph3D from 'react-force-graph-3d'
import * as THREE from 'three'
import type { ForceGraphMethods } from 'react-force-graph-3d'
import { forceCollide } from 'd3-force-3d'
import type { GraphData, GraphNode, CashNode, CashNodeType } from '../types'
import type { GraphComponentResult } from '../types'
import type { NodeIntel } from '../ai/riskPropagation'
import { computeComponentLayout, validateComponentLayout } from './graphLayout'
import { layoutCache } from '../store/layoutCache'

// ── Spatial cluster helpers (module-level) ─────────────────────────────────────
// BFS connected-component detection. Returns nodeId → compId where compId is
// the lex-min nodeId in the component (stable across incremental updates).
function detectComponentsFromGraph(
  nodeIds: string[],
  links: Array<{ source: string; target: string }>,
): Map<string, string> {
  const adj = new Map<string, string[]>()
  for (const id of nodeIds) adj.set(id, [])
  for (const l of links) {
    adj.get(l.source)?.push(l.target)
    adj.get(l.target)?.push(l.source)
  }
  const compOf = new Map<string, string>()
  for (const startId of nodeIds) {
    if (compOf.has(startId)) continue
    const members: string[] = []
    const stack = [startId]
    while (stack.length) {
      const cur = stack.pop()!
      if (compOf.has(cur)) continue
      compOf.set(cur, '?')
      members.push(cur)
      for (const nbr of (adj.get(cur) ?? [])) {
        if (!compOf.has(nbr)) stack.push(nbr)
      }
    }
    let minId = members[0]
    for (let i = 1; i < members.length; i++) { if (members[i] < minId) minId = members[i] }
    for (const m of members) compOf.set(m, minId)
  }
  return compOf
}

// ── Force tuning — EQUAL, decentralized cluster distribution ────────────────
// CRITICAL: there is NO global center force and NO origin gravity. A shared
// origin attractor would make the heaviest cluster park at the center and every
// other cluster orbit it (a hierarchy / solar-system layout). Instead EVERY
// connected component is an equal citizen: each is assigned its own independent
// "home" position spread evenly across world space, and its nodes spring gently
// toward THAT home — never toward a shared center. Cluster-repulsion keeps them
// from overlapping; local charge + links keep each one cohesive and readable.
// The result is a balanced galaxy of independent islands, no privileged center.
const FORCE = {
  // The intelligent Sugiyama SEED already spaces layers, splays fans symmetrically
  // and centres merges (see graphLayout.ts), so charge no longer has to do that
  // work — it is now only a GENTLE local de-clumper. Softening it (was -135 with a
  // up-to-3× hub multiplier) stops leaf nodes flinging far from their parent and
  // keeps edge lengths uniform; the structFloor anchor + collision do the rest.
  charge:       -108,    // LOCAL many-body repulsion — gentle; seed handles macro spacing
  chargeMaxDist:  170,   // bounded: charge is intra-cluster only; global layout is the home springs' job
  linkDistance:    46,   // BASE edge length; getLinkDistance() adapts in a NARROW band
  linkStrength:  0.55,   // a touch stiffer → direct transactions sit at a consistent length
  linkIterations:   2,   // stiffer links → chains read as chains, not springs
  velocityDecay: 0.45,   // a little more damping → calmer settle, less oscillation
  homeStrength:  0.050,  // (legacy fallback) per-node spring toward its cluster home
  structStrength: 0.130, // per-node spring toward its TOPOLOGY slot (home + local layout
                         // position). This is what makes physics REFINE the intelligent
                         // initial layout instead of scrambling it — layers stay separated,
                         // flow direction is preserved, chains stay straight.
  // CRITICAL — the structural spring must NOT fade to zero as the sim cools, or
  // charge/collision win the FINAL settled shape and fan-outs / diamonds / rings
  // relax back into blobs and lines (the reported "collapse" symptoms). We floor
  // the spring's effective alpha so the deterministic hierarchy keeps dominating
  // all the way to equilibrium, while charge/collide still do LOCAL spacing. At
  // rest pos≈target so the spring adds ~no velocity → the sim still settles.
  // FLOORED LOW (was 0.34). A high permanent floor kept the anchor spring pulling
  // toward target while charge/collide pushed the other way → a forced LIMIT CYCLE
  // that never reaches static equilibrium (the reported "vibration tail"). With the
  // convergence-freeze below, motifs are LOCKED by pinning at settle time, so the
  // spring no longer has to fight cooling forever — it may relax to ~0 and let the
  // system reach true rest (zero kinetic energy). Active-phase dominance is intact:
  // while alpha is high, anchorAlpha = alpha and the spring still governs the seed.
  structFloor:   0.06,   // effective alpha = max(alpha, structFloor) for the anchor springs
  homeRadiusK:   110,    // world radius ≈ homeRadiusK·√(clusterCount) — grows so clusters always fit
  clusterGap:     64,    // guaranteed empty space between two components' surfaces (overlap safety)
  clusterRepel:  0.90,   // how firmly overlapping components push apart (soft, overlap-only)
  collideStrength: 0.85, // hard node-overlap prevention → dense regions auto-expand
  collideIter:      2,
  maxRadius:    4000,    // hard cap on |position| — pure safety net
  // ── Convergence / freeze (professional "settle then stop") ────────────────
  // The sim is declared SETTLED when mean per-node kinetic energy (Σv²/n) stays
  // below freezeEnergy for freezeTicks consecutive ticks; every node is then
  // pinned (fx/fy/fz) so the layout becomes completely still and stays still
  // across later re-energizing (only NEW nodes move). Adaptive damping ramps the
  // velocity decay from velocityDecay (free movement) toward dampMax (near rest)
  // so the approach to equilibrium is critically damped — no overshoot, no ring.
  freezeEnergy:  0.05,   // mean per-node KE threshold for "settled"
  freezeTicks:     20,   // consecutive settled ticks required before locking
  dampMax:       0.86,   // velocity decay ceiling applied near equilibrium
} as const

// ── SINGLE SOURCE OF TRUTH FOR THE LIVE LAYOUT ───────────────────────────────
// The deterministic, motif-aware seed in `graphLayout.ts` (chain / fan / radial
// fan-out / ring / diamond / Sugiyama) is the ONE authority for every component's
// structure; the force sim only polishes + freezes it (collision, spacing). The
// backend `/api/graph/layout` engine is kept for evidence/SSR/the API but is NOT
// injected into the live 3D scene — running TWO motif layout engines reconciled by
// a per-component override is exactly what let a flat backend layout stab a ring
// interior and flatten 3D motifs. Flip to true ONLY to A/B the backend layout in
// the live view (the override then applies to non-protected components).
const LIVE_USES_BACKEND_LAYOUT = false

// Visual + collision radius for a node, by its fraud/risk role. Drives both the
// nodeVal (render size) and the collision force, so bigger/important nodes claim
// more space and never sit on top of one another.
function nodeRadius(n: { isCashNode?: boolean; is_flagged?: boolean; risk_score?: number }): number {
  if (n.isCashNode)            return 9
  if (n.is_flagged)            return 14
  if ((n.risk_score ?? 0) > 0.6) return 11
  if ((n.risk_score ?? 0) > 0.35) return 9
  return 7
}


// Prefix-stable low-discrepancy DIRECTION for a cluster, keyed only by its
// appearance index. Van der Corput (base 2) on the polar axis + golden-angle
// azimuth gives a set of directions that stays evenly spread over the sphere
// for ANY number of clusters — and each index keeps its direction forever, so
// adding clusters never reshuffles existing ones (they just push outward as the
// world radius grows). This is what guarantees an equal, non-hierarchical
// distribution with no cluster ever favored toward the center.
function radicalInverse2(i: number): number {
  let f = 1, r = 0
  while (i > 0) { f /= 2; r += f * (i % 2); i = Math.floor(i / 2) }
  return r
}
function clusterUnitDir(idx: number): [number, number, number] {
  const z = 1 - 2 * radicalInverse2(idx + 1)        // prefix-uniform in [-1, 1]
  const theta = 2 * Math.PI * ((idx + 1) * 0.6180339887498949) // golden-angle azimuth
  const r = Math.sqrt(Math.max(0, 1 - z * z))
  return [r * Math.cos(theta), r * Math.sin(theta), z]
}
// Deterministic [0,1) hash of a string (FNV-1a) — same node id always hashes the
// same, so the rare seed fallbacks below are reproducible across reloads. This is
// what makes the layout STABLE: investigators keep their spatial mental map.
function hashUnit(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) }
  return ((h >>> 0) % 100003) / 100003
}

// Initial seed for a freshly-seen node: near its cluster's home (so it doesn't
// spawn at the origin and tear across the world). DETERMINISTIC — placement is a
// function of the node id only (no Math.random), so the same dataset always lays
// out the same way. `home` is the cluster's distributed home; `spread` widens with
// cluster size to keep density low. Only used as a fallback when a node has no
// computed topology slot (the slot is the normal, fully-deterministic seed).
function seedNear(home: [number, number, number], spread: number, id = ''): [number, number, number] {
  const r = spread * Math.cbrt(hashUnit(id + ':r'))
  const phi = Math.acos(2 * hashUnit(id + ':p') - 1)
  const theta = hashUnit(id + ':t') * Math.PI * 2
  return [
    home[0] + r * Math.sin(phi) * Math.cos(theta),
    home[1] + r * Math.sin(phi) * Math.sin(theta),
    home[2] + r * Math.cos(phi),
  ]
}

// ── Verbatim snapshot ───────────────────────────────────────────────────────
// A frozen capture of the live graph: every node's EXACT 3D position plus the
// camera. Restoring it pins fx/fy/fz and applies the camera so a case reopens to
// precisely what the investigator saw — no force simulation runs again.
export interface CapturedSnapshot {
  nodes: Array<Record<string, any> & { id: string; x: number; y: number; z: number }>
  edges: Array<{ source: string; target: string } & Record<string, any>>
  camera: { position: { x: number; y: number; z: number }; target: { x: number; y: number; z: number } } | null
  captured_at?: number
}

export interface GraphSceneHandle {
  /** Immediately clears the Three.js scene via the library's own API. */
  nuke: () => void
  /** Camera control — driven by UB voice/UI commands. */
  zoomIn: () => void
  zoomOut: () => void
  resetCamera: () => void
  showAll: () => void
  focusCenter: () => void
  /** Read the live node positions + camera into a verbatim snapshot (read-only). */
  captureSnapshot: () => CapturedSnapshot | null
}

interface Props {
  graphData: GraphData
  selectedNodeId: string | null
  selectedClusterNodeIds?: ReadonlySet<string> | null
  onNodeClick: (node: GraphNode | null) => void
  onHoverChange?: (node: GraphNode | null) => void
  fraudNodeIds?: ReadonlySet<string>
  graphComponents?: GraphComponentResult[]
  focusRef?: React.MutableRefObject<((nodeIds: string[]) => void) | null>
  cashNodes?: CashNode[]
  cashAnimIds?: ReadonlySet<string>
  /** Unified propagated-risk map — drives glow intensity so visuals match metadata. */
  riskIntel?: ReadonlyMap<string, NodeIntel>
  /** When set, the scene RESTORES this verbatim snapshot: positions pinned
   *  (fx/fy/fz), no force layout, camera applied exactly. Read-only view. */
  restoreSnapshot?: CapturedSnapshot | null
  /** Server-computed investigation layout (GET /api/graph/layout?mode=auto).
   *  When present, each covered node's structural target comes from the backend's
   *  motif-preserving layout (diamonds, fan-out/in, rings, separated components,
   *  L→R flow) instead of the local force layout. The force step only refines. */
  backendLayout?: BackendLayout | null
}

/** Server-computed layout payload from GET /api/graph/layout. */
export interface BackendLayout {
  mode: string
  positions: Record<string, { x: number; y: number }>
  bounds?: { minX: number; maxX: number; minY: number; maxY: number }
}

interface ClusterLabel {
  graphId: string
  verdict: string
  score:   number
  flagged: boolean
  x:       number
  y:       number
}

function makeGlowTexture(size = 192): THREE.Texture {
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const ctx = canvas.getContext('2d')!
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  g.addColorStop(0,    'rgba(255,255,255,1)')
  g.addColorStop(0.08, 'rgba(255,255,255,0.97)')
  g.addColorStop(0.25, 'rgba(255,255,255,0.65)')
  g.addColorStop(0.55, 'rgba(255,255,255,0.18)')
  g.addColorStop(0.8,  'rgba(255,255,255,0.04)')
  g.addColorStop(1,    'rgba(255,255,255,0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, size, size)
  const tex = new THREE.CanvasTexture(canvas)
  tex.needsUpdate = true
  return tex
}

// Deterministic offset angle per cash-node id (golden angle distribution)
function cashAngleFromId(id: string): number {
  const hash = id.split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  return (hash * 2.399963) % (Math.PI * 2)
}

const GraphSceneInner = forwardRef<GraphSceneHandle, Props>(function GraphScene({
  graphData,
  selectedNodeId,
  selectedClusterNodeIds,
  onNodeClick,
  onHoverChange,
  fraudNodeIds,
  graphComponents,
  riskIntel,
  focusRef,
  cashNodes = [],
  cashAnimIds = new Set(),
  restoreSnapshot = null,
  backendLayout = null,
}: Props, ref) {
  const restore = !!restoreSnapshot
  const fgRef        = useRef<ForceGraphMethods | undefined>()
  // The graph canvas is sized from the actual CONTAINER box (measured via
  // ResizeObserver), never from window.innerWidth/innerHeight. This keeps the
  // WebGL drawing buffer aspect == the displayed CSS box aspect at all times, so
  // the scene is never non-uniformly stretched (the "rhombus on rotate" bug).
  const wrapRef      = useRef<HTMLDivElement>(null)
  const [dims, setDims] = useState({ w: 0, h: 0 })
  const animFrameRef = useRef<number>(0)
  const labelTickRef = useRef<number>(0)

  // ── Refs accessible from animation loop / callbacks without stale closures ──
  const nodeObjectMapRef     = useRef<Map<string, THREE.Group>>(new Map())
  const fraudNodeIdsRef      = useRef<ReadonlySet<string>>(new Set())
  const riskIntelRef         = useRef<ReadonlyMap<string, NodeIntel> | undefined>(undefined)
  // Degree map + reciprocal-edge set — drive adaptive link distance & curvature
  // so hubs keep tight readable spokes while relay chains stretch out straight.
  const degreeRef            = useRef<Map<string, number>>(new Map())
  const reverseEdgeRef       = useRef<Set<string>>(new Set())
  // Undirected neighbor map + currently-hovered id — drive hover path highlight.
  const neighborRef          = useRef<Map<string, Set<string>>>(new Map())
  const hoveredIdRef         = useRef<string | null>(null)
  const selectedNodeIdRef    = useRef<string | null>(null)
  const selectedClusterRef   = useRef<ReadonlySet<string> | null>(null)
  const cashAnimIdsRef       = useRef<ReadonlySet<string>>(new Set())
  const graphDataRef         = useRef(graphData)

  // Stable position cache for cash nodes — written once, never overwritten
  const cashPositionsRef = useRef<Map<string, { fx: number; fy: number; fz: number }>>(new Map())

  // ── Spatial cluster refs ─────────────────────────────────────────────────────
  // compId → stable appearance index (assigned once; drives the cluster's fixed
  // distributed DIRECTION via clusterUnitDir). Adding clusters never changes an
  // existing cluster's index, so no reshuffle.
  const clusterIndexRef = useRef<Map<string, number>>(new Map())
  const clusterIdxRef   = useRef(0)
  // compId → current HOME position in world space (dir × world radius). Rebuilt
  // every render (radius grows with cluster count). Read by the layout force as
  // each cluster's INDEPENDENT spring target — there is no shared origin anchor.
  const clusterHomeRef  = useRef<Map<string, [number, number, number]>>(new Map())
  // nodeId → compId. Rebuilt every render from compOf; used for new-node seed
  // placement, the home spring, and to position the per-component cluster labels.
  const nodeToCompRef  = useRef<Map<string, string>>(new Map())
  // Tracks which nodes we've already seeded with an initial position so we
  // don't re-randomize them on every render.
  const initialPositionRef = useRef<Map<string, [number, number, number]>>(new Map())
  // nodeId → its TOPOLOGY slot in world space (cluster home + local layout pos
  // from computeComponentLayout). The layout force springs each free node toward
  // THIS, so the physics polishes the intelligent layout rather than defining it.
  // Recomputed on every structural change (smoothly re-targets existing nodes).
  const structTargetRef = useRef<Map<string, [number, number, number]>>(new Map())

  // ── Convergence / freeze refs ────────────────────────────────────────────────
  // liveNodesRef  → the ACTUAL d3 node array (objects d3 mutates with x/y/z +
  //                 vx/vy/vz), captured in the layout force's initialize(). This
  //                 is what we read to measure kinetic energy each engine tick.
  // frozenPosRef  → durable id → settled [x,y,z]. A node here is re-emitted PINNED
  //                 (fx/fy/fz) by mergedData, so it never moves again across
  //                 re-energizing until the layout mode changes or the graph resets
  //                 — this is the stable investigator mental map.
  // settledTicksRef → consecutive low-energy tick counter driving the freeze gate.
  // isFrozenRef   → latch: true once locked, so we don't re-pin every tick.
  const liveNodesRef    = useRef<any[]>([])
  const frozenPosRef    = useRef<Map<string, [number, number, number]>>(new Map())
  const settledTicksRef = useRef(0)
  const isFrozenRef     = useRef(false)
  // ── Layout persistence across navigation / reload (fixes "graph distorts after
  // leaving and returning") ─────────────────────────────────────────────────────
  // Rehydrate the settled positions from the durable module-level cache ONCE, on
  // first render — synchronously, BEFORE the mergedData memo below reads
  // frozenPosRef. On a remount (route change / tab switch / reload) this restores
  // every previously-frozen node so mergedData re-emits it PINNED (fx/fy/fz) and
  // the force sim reproduces the exact layout instead of re-solving it. A genuine
  // relayout (reset / clear / mode change) clears the cache first, so this is
  // empty on those paths and the graph solves fresh — see layoutCache.ts.
  const layoutRehydratedRef = useRef(false)
  if (!layoutRehydratedRef.current) {
    layoutRehydratedRef.current = true
    const persisted = layoutCache.load()
    if (persisted.size > 0) frozenPosRef.current = persisted
  }
  // Last resolved backend layout mode — a CHANGE is a sanctioned full-relayout
  // trigger (req 5): we clear the frozen mental map so every node re-solves.
  const lastLayoutModeRef = useRef<string | null>(null)

  // Track cluster count to trigger zoom when new clusters appear
  const [clusterCount, setClusterCount] = useState(0)

  // ── Robust auto-fit ──────────────────────────────────────────────────────
  // Frame the graph so it fills the viewport, WITHOUT being thrown off by a few
  // far-flung stragglers (the bug behind "graph is a tiny sliver"). The library's
  // zoomToFit fits the FARTHEST node, so one outlier zooms everything out. Instead
  // we center on the per-axis MEDIAN (outlier-proof) and size the camera from a
  // radius found by iterative 3σ trimming: nodes beyond mean+3·stddev of the
  // distance distribution are dropped and the stats recomputed (up to 3×, never
  // dropping more than half). A CONTIGUOUS chain tail has a gradual distance
  // gradient → nothing is beyond 3σ → it stays fully framed; a DISCONNECTED
  // straggler sits far past 3σ → it's excluded so the dense core fills the screen.
  // Distance is solved from the camera's smaller (vertical vs. horizontal) half-
  // FOV so it fits on any aspect ratio and never clips when orbited. `fill` is the
  // fraction of the limiting viewport dimension the graph should occupy.
  const frameGraph = useCallback((durationMs = 700) => {
    const fg = fgRef.current as any
    const cam = fg?.camera?.() as THREE.PerspectiveCamera | undefined
    if (!fg || !cam) return
    // Read live positions from the rendered THREE node groups (the library
    // mutates these every frame). fg.graphData() does NOT reliably return the
    // live nodes here, so the node objects are the ground truth.
    const xs: number[] = [], ys: number[] = [], zs: number[] = []
    nodeObjectMapRef.current.forEach(group => {
      const p = group.position
      if (Number.isFinite(p.x) && Number.isFinite(p.y) && Number.isFinite(p.z)) {
        xs.push(p.x); ys.push(p.y); zs.push(p.z)
      }
    })
    if (xs.length === 0) return
    const median = (a: number[]) => {
      const s = [...a].sort((p, q) => p - q); const m = s.length >> 1
      return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
    }
    const mean = (a: number[]) => a.reduce((s, x) => s + x, 0) / a.length
    const cx = median(xs), cy = median(ys), cz = median(zs)

    const dists: number[] = []
    for (let i = 0; i < xs.length; i++) {
      const dx = xs[i] - cx, dy = ys[i] - cy, dz = zs[i] - cz
      dists.push(Math.sqrt(dx * dx + dy * dy + dz * dz))
    }
    // Iterative 3σ trim of the distance distribution (drops disconnected
    // stragglers, keeps contiguous tails; never trims away more than half).
    let active = dists.slice()
    for (let pass = 0; pass < 3; pass++) {
      const m = mean(active)
      const sd = Math.sqrt(mean(active.map(d => (d - m) * (d - m))))
      const cut = m + 3 * sd
      const next = active.filter(d => d <= cut)
      if (next.length === active.length || next.length < Math.max(3, dists.length * 0.5)) break
      active = next
    }
    const R = Math.max(Math.max(...active) + 22, 40)   // margin + floor (tiny graphs)

    const n = xs.length
    // Target 65–80% viewport occupancy (≈15–20% padding). Larger tiers can fill
    // MORE than before because the Sugiyama layout is flatter in Z (shallow depth),
    // so framing it no longer needs deep-sphere orbit margin → big graphs stop
    // looking tiny while still never clipping when rotated.
    const fill = n <= 20 ? 0.82 : n <= 60 ? 0.74 : n <= 200 ? 0.66 : 0.58
    const fovY = (cam.fov * Math.PI) / 180
    const fovX = 2 * Math.atan(Math.tan(fovY / 2) * (cam.aspect || 1))
    const half = Math.min(fovY, fovX) / 2
    let dist = (R / fill) / Math.max(1e-3, Math.sin(half))
    dist = Math.max(40, Math.min(9000, dist))

    // Head-on view (camera along +Z) keeps the top→bottom money flow vertical.
    fg.cameraPosition({ x: cx, y: cy, z: cz + dist }, { x: cx, y: cy, z: cz }, durationMs)
  }, [])

  // ── Imperative clear handle ───────────────────────────────────────────────
  useImperativeHandle(ref, () => ({
    nuke() {
      const fg = fgRef.current as any
      if (fg) {
        try {
          fg.pauseAnimation?.()

          const renderer = fg.renderer?.()
          if (renderer) {
            renderer.setClearColor(0x000000, 1)
            renderer.clear()
            renderer.renderLists?.dispose()
          }

          const scene = fg.scene?.()
          if (scene) {
            const toRemove: THREE.Object3D[] = []
            scene.traverse((obj: THREE.Object3D) => { if (obj !== scene) toRemove.push(obj) })
            toRemove.forEach(obj => {
              scene.remove(obj)
              const g = (obj as any).geometry
              if (g) g.dispose()
              const mat = (obj as any).material
              if (mat) {
                const mats: THREE.Material[] = Array.isArray(mat) ? mat : [mat]
                mats.forEach(m => m?.dispose?.())
              }
            })
          }

          fg.d3Force?.('link',    null)
          fg.d3Force?.('charge',  null)
          fg.d3Force?.('center',  null)
          fg.d3Force?.('gravity', null)
        } catch {
          // Non-fatal — scene may already be torn down
        }
      }
      nodeObjectMapRef.current.clear()
      cashPositionsRef.current.clear()
      clusterIndexRef.current.clear()
      clusterHomeRef.current.clear()
      clusterIdxRef.current = 0
      nodeToCompRef.current.clear()
      initialPositionRef.current.clear()
      structTargetRef.current.clear()
    },

    // ── Camera control — scales the current camera distance toward / away from
    // the orbit target (origin), or frames the whole graph. ────────────────────
    zoomIn() {
      const fg = fgRef.current as any
      const cam = fg?.camera?.()
      if (!cam) return
      const p = cam.position
      fg.cameraPosition({ x: p.x * 0.7, y: p.y * 0.7, z: p.z * 0.7 }, undefined, 500)
    },
    zoomOut() {
      const fg = fgRef.current as any
      const cam = fg?.camera?.()
      if (!cam) return
      const p = cam.position
      fg.cameraPosition({ x: p.x * 1.45, y: p.y * 1.45, z: p.z * 1.45 }, undefined, 500)
    },
    resetCamera() { frameGraph(800) },
    showAll()     { frameGraph(800) },
    focusCenter() { frameGraph(700) },

    // Read-only verbatim capture: live node positions + render fields + camera.
    captureSnapshot() {
      const fg = fgRef.current as any
      if (!fg?.graphData) return null
      const data = fg.graphData() as { nodes: any[]; links: any[] }
      const KEEP = [
        'risk_score', 'is_flagged', 'nodeColor', 'account_type', 'total_sent',
        'total_received', 'isCashNode', 'cashType', 'amount', 'parentAccount',
        'incoming_count', 'outgoing_count', 'detected_patterns',
      ]
      const id = (v: any) => (typeof v === 'string' ? v : v?.id)
      const nodes = (data?.nodes ?? [])
        .filter(n => Number.isFinite(n.x) && Number.isFinite(n.y) && Number.isFinite(n.z))
        .map(n => {
          const out: Record<string, any> = { id: n.id, x: n.x, y: n.y, z: n.z }
          for (const k of KEEP) if (n[k] !== undefined) out[k] = n[k]
          return out
        })
      const edges = (data?.links ?? []).map(l => {
        const e: Record<string, any> = { source: id(l.source), target: id(l.target) }
        for (const k of ['amount', 'payment_rail', 'is_flagged', 'isCashEdge', 'cashType', 'linkColor']) {
          if (l[k] !== undefined) e[k] = l[k]
        }
        return e
      })
      const cam = fg.camera?.() as THREE.PerspectiveCamera | undefined
      const ctrls = fg.controls?.() as { target?: THREE.Vector3 } | undefined
      const camera = cam ? {
        position: { x: cam.position.x, y: cam.position.y, z: cam.position.z },
        target: ctrls?.target
          ? { x: ctrls.target.x, y: ctrls.target.y, z: ctrls.target.z }
          : { x: 0, y: 0, z: 0 },
      } : null
      return { nodes, edges, camera, captured_at: Date.now() / 1000 } as CapturedSnapshot
    },
  }))

  const [clusterLabels, setClusterLabels] = useState<ClusterLabel[]>([])
  const glowTex = useMemo(() => makeGlowTexture(192), [])

  // TEMP DEBUG: expose live node positions for CDP layout-quality measurement.
  useEffect(() => {
    (window as any).__tgieDbg = () => {
      const out: any[] = []
      nodeObjectMapRef.current.forEach((g, id) => {
        out.push({ id, comp: nodeToCompRef.current.get(id), p: [Math.round(g.position.x), Math.round(g.position.y), Math.round(g.position.z)] })
      })
      return out
    }
  })

  // Keep refs in sync with latest values
  useEffect(() => { fraudNodeIdsRef.current  = fraudNodeIds ?? new Set() })
  useEffect(() => { riskIntelRef.current     = riskIntel })

  // Recompute degree + reciprocal-edge structure whenever the graph changes.
  useEffect(() => {
    const deg = new Map<string, number>()
    const dir = new Set<string>()
    const rev = new Set<string>()
    const nbr = new Map<string, Set<string>>()
    for (const l of graphData.links) {
      const s = typeof l.source === 'string' ? l.source : (l.source as any).id
      const t = typeof l.target === 'string' ? l.target : (l.target as any).id
      deg.set(s, (deg.get(s) ?? 0) + 1)
      deg.set(t, (deg.get(t) ?? 0) + 1)
      dir.add(`${s}>${t}`)
      if (dir.has(`${t}>${s}`)) { rev.add(`${s}>${t}`); rev.add(`${t}>${s}`) }
      ;(nbr.get(s) ?? nbr.set(s, new Set()).get(s)!).add(t)
      ;(nbr.get(t) ?? nbr.set(t, new Set()).get(t)!).add(s)
    }
    degreeRef.current = deg
    reverseEdgeRef.current = rev
    neighborRef.current = nbr

    // Temporary topology debug — verify the layout reflects real structure.
    if (graphData.nodes.length > 0) {
      const hubs = [...deg.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5)
        .map(([id, d]) => `${id}(${d})`)
      console.log(
        `%c[TGIE topology] ${graphData.nodes.length} nodes · ${graphData.links.length} edges · ` +
        `${rev.size / 2} reciprocal pairs · top hubs: ${hubs.join(', ')}`,
        'color:#79c0ff',
      )
    }
  }, [graphData])
  useEffect(() => { selectedNodeIdRef.current = selectedNodeId },         [selectedNodeId])
  useEffect(() => { selectedClusterRef.current = selectedClusterNodeIds ?? null }, [selectedClusterNodeIds])
  useEffect(() => { cashAnimIdsRef.current   = cashAnimIds },   [cashAnimIds])
  useEffect(() => { graphDataRef.current     = graphData },     [graphData])

  // Clear caches when the graph is fully reset
  useEffect(() => {
    if (graphData.nodes.length === 0) {
      cashPositionsRef.current.clear()
      clusterIndexRef.current.clear()
      clusterHomeRef.current.clear()
      clusterIdxRef.current = 0
      nodeToCompRef.current.clear()
      initialPositionRef.current.clear()
      structTargetRef.current.clear()
    }
  }, [graphData.nodes.length])

  useEffect(() => {
    if (cashNodes.length === 0) cashPositionsRef.current.clear()
  }, [cashNodes.length])

  // ── Container resize (rotation-safe) ─────────────────────────────────────────
  // Measure the real container box (not the window) on a rAF so iOS/Safari layout
  // has settled after an orientation change before we read it. ResizeObserver also
  // catches layout-driven size changes (devtools dock, panels) that never fire a
  // window 'resize'. orientationchange + visualViewport cover mobile URL-bar resizes.
  useLayoutEffect(() => {
    const el = wrapRef.current
    if (!el) return
    let raf = 0
    const measure = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        const r = el.getBoundingClientRect()
        const w = Math.round(r.width), h = Math.round(r.height)
        if (w > 0 && h > 0) setDims(prev => (prev.w === w && prev.h === h ? prev : { w, h }))
      })
    }
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    measure()
    window.addEventListener('orientationchange', measure)
    window.visualViewport?.addEventListener('resize', measure)
    return () => {
      ro.disconnect()
      cancelAnimationFrame(raf)
      window.removeEventListener('orientationchange', measure)
      window.visualViewport?.removeEventListener('resize', measure)
    }
  }, [])

  // ── Keep camera aspect + drawing buffer in lock-step with the box ────────────
  // Belt-and-braces: react-force-graph derives these from the width/height props,
  // but forcing them on every dims change guarantees no stale aspect survives a
  // rotation, and clamps devicePixelRatio so HiDPI Macs stay crisp without over-rendering.
  useEffect(() => {
    if (dims.w === 0 || dims.h === 0) return
    const fg = fgRef.current as any
    const cam = fg?.camera?.() as THREE.PerspectiveCamera | undefined
    if (cam) { cam.aspect = dims.w / dims.h; cam.updateProjectionMatrix() }
    const r = fg?.renderer?.()
    if (r) {
      r.setPixelRatio(Math.min(2, window.devicePixelRatio || 1))
      r.setSize(dims.w, dims.h, false)
    }
  }, [dims])

  // ── Force architecture (DECENTRALIZED: every cluster is an equal citizen) ────
  // Keep three-forcegraph's d3 simulation authoritative. There is deliberately
  // NO global center force and NO origin gravity — those make the heaviest
  // cluster sit at the center and everything else orbit it (a hierarchy). Each
  // connected component instead springs toward its OWN independent home (spread
  // evenly across world space, see clusterUnitDir), charge spaces nodes locally,
  // links hold each component together, and a soft overlap force keeps clusters
  // from intersecting. Result: a balanced galaxy of independent islands.
  useEffect(() => {
    const fg = fgRef.current as any
    if (!fg) return
    const t = setTimeout(() => {
      // ── ADAPTIVE force profile by graph size ─────────────────────────────────
      // One fixed configuration can't serve a 10-node star and a 300-node mule
      // network equally. Small graphs get STRONGER repulsion + more collision pad
      // so they read big and breathe; large graphs ease off (the per-component
      // home springs + cluster separation already organize them) to stay compact
      // and performant. Re-read live each time d3 re-initializes the forces.
      const profile = () => {
        const n = graphDataRef.current.nodes.length
        if (n <= 25)  return { chargeMul: 1.25, collidePad: 6 } // compact, strong
        if (n <= 80)  return { chargeMul: 1.08, collidePad: 5 } // balanced
        if (n <= 200) return { chargeMul: 0.94, collidePad: 4 } // community-aware
        return            { chargeMul: 0.82, collidePad: 3 }    // large / perf
      }

      // LOCAL charge only (bounded) — spaces nodes inside a component; it must
      // NOT span clusters, or it would fight the per-cluster home springs. The hub
      // multiplier is now GENTLE (cap ×1.8, was ×3) because the seed already splays
      // fans symmetrically — strong hub charge only flung leaves far and made edge
      // lengths uneven. The size multiplier keeps small graphs roomy, large compact.
      fg.d3Force('charge')
        ?.strength((n: any) => FORCE.charge * profile().chargeMul * (1 + Math.min(0.8, (degreeRef.current.get(n.id) ?? 0) * 0.08)))
        .distanceMax(FORCE.chargeMaxDist)

      // Link distance in a NARROW band → consistent edge lengths (the seed already
      // encodes topology spacing, so links no longer stretch chains 1.9×). Hub
      // spokes sit at the base length, chains/relays only slightly longer.
      const linkDist = (link: any) => {
        const s = typeof link.source === 'string' ? link.source : link.source?.id
        const t = typeof link.target === 'string' ? link.target : link.target?.id
        const maxDeg = Math.max(degreeRef.current.get(s) ?? 1, degreeRef.current.get(t) ?? 1)
        if (maxDeg >= 5) return FORCE.linkDistance * 1.0    // hub spoke
        if (maxDeg <= 2) return FORCE.linkDistance * 1.3    // chain/relay — slightly longer
        return FORCE.linkDistance * 1.15
      }
      const linkForce = fg.d3Force('link')
      linkForce?.distance(linkDist).strength(FORCE.linkStrength)
      linkForce?.iterations?.(FORCE.linkIterations)
      fg.d3Force('center', null)   // no shared center — that's the whole point

      // COLLISION — nodes must never overlap; dense regions auto-expand outward.
      // Radius scales with the node's fraud importance (hubs claim more space) and
      // with the size-adaptive pad so dense clusters BREATHE (glow halos stop
      // merging, hover stays precise) without inflating the whole graph.
      // (radius accepts a per-node accessor; strength is a constant in d3-force, so
      // the size-adaptive lever here is the collision PAD on the radius.)
      fg.d3Force('collide',
        forceCollide()
          .radius((n: any) => nodeRadius(n) + profile().collidePad)
          .strength(FORCE.collideStrength)
          .iterations(FORCE.collideIter),
      )

      // ── Layout force: per-cluster home spring + component-overlap separation ─
      //  (a) HOME SPRING — pull every node toward ITS OWN cluster's home (an
      //      evenly-distributed point in world space), NOT a shared origin. This
      //      is what makes all clusters equal: each settles in its own region;
      //      none is privileged at the center. Bounds the layout too (no drift).
      //  (b) SEPARATION — measure each component's ACTUAL radius and, when two
      //      overlap (+ gap), push them apart (overlap-only, lighter moves more)
      //      so cluster spheres never intersect, regardless of home spacing.
      let d3Nodes: any[] = []
      function layout(alpha: number) {
        const homes = clusterHomeRef.current
        const targets = structTargetRef.current
        const comp = nodeToCompRef.current
        // Floor the anchor alpha so the hierarchy keeps dominating through cooldown
        // (see FORCE.structFloor). Separation (b) stays pure-alpha so it fades out
        // once clusters are apart and the sim can reach equilibrium.
        const anchorAlpha = Math.max(alpha, FORCE.structFloor)
        const ks = FORCE.structStrength * anchorAlpha
        const kh = FORCE.homeStrength * anchorAlpha
        // (a) STRUCTURAL anchor spring + NaN safety net + hard bound.
        //     Each node is pulled toward its topology slot (home + local layout
        //     position from computeComponentLayout) so depth layers stay apart,
        //     flow direction holds, and chains stay straight — the force engine
        //     only refines. Nodes with no slot fall back to the cluster home.
        for (const n of d3Nodes) {
          if (n.fx != null) continue
          if (!Number.isFinite(n.x) || !Number.isFinite(n.y) || !Number.isFinite(n.z)) {
            const id = n.id as string
            n.x = (hashUnit(id + ':rx') - 0.5) * 60
            n.y = (hashUnit(id + ':ry') - 0.5) * 60
            n.z = (hashUnit(id + ':rz') - 0.5) * 60
            n.vx = 0; n.vy = 0; n.vz = 0
          }
          const target = targets.get(n.id as string)
          if (target) {
            n.vx = (n.vx ?? 0) + (target[0] - n.x) * ks
            n.vy = (n.vy ?? 0) + (target[1] - n.y) * ks
            n.vz = (n.vz ?? 0) + (target[2] - n.z) * ks
          } else {
            const home = homes.get(comp.get(n.id as string) ?? '')
            if (home) {
              n.vx = (n.vx ?? 0) + (home[0] - n.x) * kh
              n.vy = (n.vy ?? 0) + (home[1] - n.y) * kh
              n.vz = (n.vz ?? 0) + (home[2] - n.z) * kh
            }
          }
          // Hard bound: pure safety net against any pathological blow-up.
          const r2 = n.x * n.x + n.y * n.y + n.z * n.z
          if (r2 > FORCE.maxRadius * FORCE.maxRadius) {
            const f = FORCE.maxRadius / Math.sqrt(r2)
            n.x *= f; n.y *= f; n.z *= f
            n.vx *= 0.5; n.vy *= 0.5; n.vz *= 0.5
          }
        }

        // (b) component-overlap separation
        if (comp.size === 0) return

        // centroids + counts
        const sx = new Map<string, number>(), sy = new Map<string, number>(),
              sz = new Map<string, number>(), cnt = new Map<string, number>()
        for (const n of d3Nodes) {
          const c = comp.get(n.id as string); if (c === undefined) continue
          sx.set(c, (sx.get(c) ?? 0) + n.x); sy.set(c, (sy.get(c) ?? 0) + n.y)
          sz.set(c, (sz.get(c) ?? 0) + n.z); cnt.set(c, (cnt.get(c) ?? 0) + 1)
        }
        const ids = [...cnt.keys()]
        if (ids.length < 2) return
        const cx = new Map<string, number>(), cy = new Map<string, number>(), cz = new Map<string, number>()
        for (const c of ids) {
          const k = cnt.get(c)!
          cx.set(c, sx.get(c)! / k); cy.set(c, sy.get(c)! / k); cz.set(c, sz.get(c)! / k)
        }
        // ACTUAL radius = max node distance from its centroid (so separation
        // tracks however far charge has spread each component)
        const rad = new Map<string, number>()
        for (const n of d3Nodes) {
          const c = comp.get(n.id as string); if (c === undefined) continue
          const dx = n.x - cx.get(c)!, dy = n.y - cy.get(c)!, dz = n.z - cz.get(c)!
          const d = Math.sqrt(dx * dx + dy * dy + dz * dz)
          if (d > (rad.get(c) ?? 0)) rad.set(c, d)
        }

        const dvx = new Map<string, number>(), dvy = new Map<string, number>(), dvz = new Map<string, number>()
        for (const c of ids) { dvx.set(c, 0); dvy.set(c, 0); dvz.set(c, 0) }
        for (let i = 0; i < ids.length; i++) {
          for (let j = i + 1; j < ids.length; j++) {
            const a = ids[i], b = ids[j]
            let dx = cx.get(b)! - cx.get(a)!, dy = cy.get(b)! - cy.get(a)!, dz = cz.get(b)! - cz.get(a)!
            let dist = Math.sqrt(dx * dx + dy * dy + dz * dz)
            // Deterministic nudge when two centroids coincide (stable across reloads).
            if (dist < 1e-6) { dx = hashUnit(a + b + 'x') - 0.5; dy = hashUnit(a + b + 'y') - 0.5; dz = hashUnit(a + b + 'z') - 0.5; dist = Math.sqrt(dx*dx+dy*dy+dz*dz) || 1 }
            const minGap = (rad.get(a) ?? 0) + (rad.get(b) ?? 0) + FORCE.clusterGap
            if (dist >= minGap) continue            // already clearly apart — do nothing
            const push = ((minGap - dist) / dist) * alpha * FORCE.clusterRepel
            const ka = cnt.get(a)!, kb = cnt.get(b)!, tot = ka + kb
            const wa = kb / tot, wb = ka / tot       // lighter component moves more
            dvx.set(a, dvx.get(a)! - dx * push * wa); dvy.set(a, dvy.get(a)! - dy * push * wa); dvz.set(a, dvz.get(a)! - dz * push * wa)
            dvx.set(b, dvx.get(b)! + dx * push * wb); dvy.set(b, dvy.get(b)! + dy * push * wb); dvz.set(b, dvz.get(b)! + dz * push * wb)
          }
        }
        for (const n of d3Nodes) {
          if (n.fx != null) continue
          const c = comp.get(n.id as string); if (c === undefined) continue
          n.vx += dvx.get(c) ?? 0; n.vy += dvy.get(c) ?? 0; n.vz += dvz.get(c) ?? 0
        }
      }
      // d3 calls initialize() on registration and whenever simulation.nodes()
      // changes (every structural graphData update). Capture the live node
      // array and seed any brand-new node near its component's shell seed so it
      // doesn't spawn at the origin and tear across the world.
      ;(layout as any).initialize = (nodes: any[]) => {
        d3Nodes = nodes
        liveNodesRef.current = nodes   // for the convergence-energy probe (onEngineTick)
        for (const n of nodes) {
          const id = n.id as string
          if (initialPositionRef.current.has(id)) continue
          // Prefer the node's intelligent topology slot; fall back to a near-home
          // seed only if no slot was computed (e.g. transient state).
          let p = structTargetRef.current.get(id)
          if (!p) {
            const home = clusterHomeRef.current.get(nodeToCompRef.current.get(id) ?? '')
            if (!home) continue
            p = seedNear(home, 26, id)
          }
          n.x = p[0]; n.y = p[1]; n.z = p[2]
          n.vx = 0; n.vy = 0; n.vz = 0
          initialPositionRef.current.set(id, p)
        }
      }
      fg.d3Force('gravity', layout)
      fg.d3VelocityDecay?.(FORCE.velocityDecay)
      // NOTE: do NOT call d3ReheatSimulation() here. The library assigns its
      // internal `state.layout` only AFTER it first processes graphData; reheat
      // flips engineRunning=true without that guard, so the animation loop hits
      // `state.layout.tick()` on undefined, throws once, and the whole render
      // loop dies → permanently black canvas. The library already re-energizes
      // (alpha→1) on every structural graphData change, so no manual reheat is
      // needed for forces registered here to take effect.
    }, 0)
    return () => clearTimeout(t)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Tracks the distinct-cluster signature so the camera auto-frame fires once
  // per change in the SET of clusters.
  const lastSectorSigRef = useRef<string>('')

  // ── Simulation lifecycle ─────────────────────────────────────────────────────
  // We let the sim COOL and stabilize into a readable layout (vs. the old
  // cooldownTicks=0 churn). The library re-energizes (alpha→1 + warmup) on every
  // structural graphData change on its own, so we do NOT manually reheat —
  // manual d3ReheatSimulation() before the library's internal layout is ready
  // crashes the render loop (see force-setup effect). handleEngineStop just
  // records the settled node count.
  const settledCountRef = useRef(0)
  // Set when a STRUCTURAL change reheats the sim; consumed by the first engine
  // stop afterward to do ONE final auto-fit. This frames the fully-cooled layout
  // (the burst of timed fits below can't know exactly when the sim settles) while
  // NOT yanking the camera after a user drag (a drag reheats but leaves this false).
  const pendingFitRef = useRef(false)

  // ── Post-render validation (req: validate AFTER the graph is rendered) ───────
  // After the physics settles, read the LIVE node positions and re-run the quality
  // checks per cluster — so the RENDERED, physics-refined layout (not just the
  // deterministic seed) is objectively verified: no collapsed/overlapping cluster,
  // uniform-ish edges, sane aspect. Uses render-scale thresholds (the collision
  // force legitimately packs nodes tighter than the seed spacing). Logs a
  // consolidated pass/fail so any residual problem is visible, never silent.
  const validateLive = useCallback(() => {
    if (restore) return
    const objs = nodeObjectMapRef.current
    const comp = nodeToCompRef.current
    if (objs.size === 0 || comp.size === 0 || objs.size > 800) return  // keep O(n²)/cluster cheap
    const byComp = new Map<string, Map<string, [number, number, number]>>()
    objs.forEach((g, id) => {
      const c = comp.get(id); if (c === undefined) return        // skip cash nodes
      const p = g.position
      if (!Number.isFinite(p.x) || !Number.isFinite(p.y) || !Number.isFinite(p.z)) return
      ;(byComp.get(c) ?? byComp.set(c, new Map()).get(c)!).set(id, [p.x, p.y, p.z])
    })
    const edgesByComp = new Map<string, { source: string; target: string }[]>()
    for (const l of graphDataRef.current.links) {
      const s = typeof l.source === 'string' ? l.source : (l.source as any).id
      const t = typeof l.target === 'string' ? l.target : (l.target as any).id
      const c = comp.get(s); if (c === undefined || comp.get(t) !== c) continue
      ;(edgesByComp.get(c) ?? edgesByComp.set(c, []).get(c)!).push({ source: s, target: t })
    }
    const TH = { overlap: 14, aspectLo: 0.1, aspectHi: 7.5, edgeCV: 0.9 }  // render-scale gates
    let fails = 0
    const report: string[] = []
    for (const [c, pos] of byComp) {
      if (pos.size < 3) continue
      const q = validateComponentLayout([...pos.keys()], edgesByComp.get(c) ?? [], pos, TH)
      if (!q.pass) { fails++; report.push(`${c}:✗${q.failed.join('/')}`) }
    }
    if (byComp.size > 0) {
      console.log(
        `%c[TGIE validate] live layout — ${byComp.size - fails}/${byComp.size} cluster(s) pass` +
        (fails ? ` · ${report.join(', ')}` : ' ✓'),
        `color:${fails ? '#f0b86e' : '#7ee787'}`,
      )
    }
  }, [restore])

  // ── Freeze: lock the settled layout (req 1/2/3/7/9) ──────────────────────────
  // Pin every currently-FREE node at its live position (fx/fy/fz) and record it in
  // the durable frozenPosRef. Once pinned, d3 may keep ticking but overwrites
  // x←fx each tick, so the node is mathematically immovable → zero vibration,
  // zero drift, zero expansion. Cash nodes are already pinned and are skipped.
  // Motifs (diamond/fan/ring/chain/…) are locked exactly as drawn — physics can
  // never destroy them after this point.
  const freezeLayout = useCallback((reason: string) => {
    const nodes = liveNodesRef.current
    if (!nodes || nodes.length === 0) return
    let pinned = 0
    for (const n of nodes) {
      if (!Number.isFinite(n.x) || !Number.isFinite(n.y) || !Number.isFinite(n.z)) continue
      // Respect pre-existing pins (cash nodes / restore mode) — just record them.
      if (n.fx == null) { n.fx = n.x; n.fy = n.y; n.fz = n.z; pinned++ }
      n.vx = 0; n.vy = 0; n.vz = 0
      frozenPosRef.current.set(n.id as string, [n.x, n.y, n.z])
    }
    isFrozenRef.current = true
    settledTicksRef.current = 0
    // Persist the settled layout OUTSIDE the React tree so it survives navigation,
    // tab switches and reloads (the whole point of the freeze — a stable mental
    // map). Once per settle, not per tick, so it's cheap. On remount, frozenPosRef
    // is rehydrated from here and every node is re-emitted pinned → no re-solve.
    layoutCache.saveAll(frozenPosRef.current)
    if (pinned > 0) {
      console.log(
        `%c[TGIE freeze] layout settled (${reason}) → ${pinned} node(s) locked, ${frozenPosRef.current.size} held (persisted)`,
        'color:#7ee787',
      )
    }
  }, [])

  // (Thaw — releasing pins so the layout re-solves — is handled inline in
  //  mergedData on the two sanctioned triggers: a layout-mode change, and a graph
  //  reset, which remounts the scene and recreates these refs from scratch.)

  // ── Engine tick: kinetic-energy probe + adaptive damping + freeze gate ───────
  // Runs every simulation tick. Measures mean per-node kinetic energy over the
  // FREE (unpinned) nodes; ramps velocity decay toward dampMax as energy falls
  // (critical damping near rest → no overshoot/ring, req 4); and once energy has
  // stayed below freezeEnergy for freezeTicks consecutive ticks, freezes the
  // layout (req 1/2/3). Pinned nodes contribute no energy, so a graph that is
  // already mostly frozen (incremental update) settles its few new nodes fast.
  const handleEngineTick = useCallback(() => {
    if (restore || isFrozenRef.current) return
    const nodes = liveNodesRef.current
    if (!nodes || nodes.length === 0) return
    let energy = 0, free = 0
    for (const n of nodes) {
      if (n.fx != null) continue                   // pinned → immovable, no energy
      const vx = n.vx ?? 0, vy = n.vy ?? 0, vz = n.vz ?? 0
      energy += vx * vx + vy * vy + vz * vz
      free++
    }
    const fg = fgRef.current as any
    if (free === 0) {                              // everything pinned already → done
      freezeLayout('all-pinned')
      return
    }
    const meanKE = energy / free
    // Adaptive damping: 0 energy → dampMax, high energy → base velocityDecay.
    const t = Math.min(1, meanKE / (FORCE.freezeEnergy * 8))
    const decay = FORCE.dampMax - (FORCE.dampMax - FORCE.velocityDecay) * t
    fg?.d3VelocityDecay?.(decay)
    // Convergence gate.
    if (meanKE < FORCE.freezeEnergy) {
      if (++settledTicksRef.current >= FORCE.freezeTicks) freezeLayout(`KE=${meanKE.toExponential(1)}`)
    } else {
      settledTicksRef.current = 0
    }
  }, [restore, freezeLayout])

  const handleEngineStop = useCallback(() => {
    settledCountRef.current = graphDataRef.current.nodes.length
    // One-shot final fit after the layout cools from a structural change.
    if (pendingFitRef.current) {
      pendingFitRef.current = false
      frameGraph(700)
    }
    // The library hit its tick cap before the energy gate fired (very large graph
    // or an unlucky reheat). Lock whatever we have so the canvas still goes still.
    if (!isFrozenRef.current) freezeLayout('engine-stop')
    validateLive()
  }, [frameGraph, validateLive, freezeLayout])

  // ── Continuous camera auto-framing ───────────────────────────────────────────
  // The globe GROWS and SPREADS as nodes stream in, so a one-shot fit (the old
  // behavior) leaves most nodes outside the frustum → a black-looking canvas.
  // Instead we re-fit on every node-count change, debounced, plus a couple of
  // trailing fits so the view keeps pace as the layout cools and expands. This
  // is what guarantees the graph is always on screen regardless of globe size.
  const refitTimersRef = useRef<ReturnType<typeof setTimeout>[]>([])
  useEffect(() => {
    refitTimersRef.current.forEach(clearTimeout)
    refitTimersRef.current = []
    if (restore) return    // verbatim restore applies the captured camera instead
    if (graphData.nodes.length === 0) return
    pendingFitRef.current = true   // arm the one-shot final fit at engine stop
    // A burst of fits: snappy first frame, then catch the expanding/cooling globe.
    const schedule = [300, 900, 2000, 3500]
    refitTimersRef.current = schedule.map(ms =>
      setTimeout(() => frameGraph(650), ms),
    )
    return () => { refitTimersRef.current.forEach(clearTimeout); refitTimersRef.current = [] }
  }, [graphData.nodes.length, frameGraph, restore])

  // ── Verbatim camera restore ──────────────────────────────────────────────────
  // Apply the captured camera exactly (no animation), retrying until the library's
  // camera API is ready. Never auto-fits, so the saved viewpoint is preserved.
  useEffect(() => {
    const cam = restoreSnapshot?.camera
    if (!cam) return
    let tries = 0
    let timer: ReturnType<typeof setTimeout>
    const apply = () => {
      const fg = fgRef.current as any
      if (fg?.cameraPosition) {
        fg.cameraPosition(cam.position, cam.target, 0)
      } else if (tries++ < 40) {
        timer = setTimeout(apply, 80)
      }
    }
    timer = setTimeout(apply, 120)
    return () => clearTimeout(timer)
  }, [restoreSnapshot])

  // ── Focus API (called by BlueTeam panel) ────────────────────────────────────
  useEffect(() => {
    if (!focusRef) return
    focusRef.current = (nodeIds: string[]) => {
      if (!fgRef.current) return
      const nodeSet   = new Set(nodeIds)
      const fg        = fgRef.current as any
      const d3Data    = fg.graphData?.() as { nodes: any[] } | undefined
      const positions = (d3Data?.nodes ?? graphData.nodes)
        .filter((n: any) => nodeSet.has(n.id) && n.x !== undefined)
        .map((n: any) => ({ x: n.x!, y: n.y!, z: n.z! }))
      if (positions.length === 0) return
      const cx = positions.reduce((s: number, p: any) => s + p.x, 0) / positions.length
      const cy = positions.reduce((s: number, p: any) => s + p.y, 0) / positions.length
      const cz = positions.reduce((s: number, p: any) => s + p.z, 0) / positions.length
      fgRef.current.cameraPosition(
        { x: cx + 130, y: cy + 70, z: cz + 130 },
        { x: cx, y: cy, z: cz },
        1100,
      )
    }
  }, [graphData, focusRef])

  // ── Cluster label overlay positions (rAF loop) ───────────────────────────────
  useEffect(() => {
    if (!graphComponents || graphComponents.length === 0) {
      setClusterLabels([])
      return
    }
    const tick = () => {
      const fg = fgRef.current as any
      if (!fg?.graph2ScreenCoords) { labelTickRef.current = requestAnimationFrame(tick); return }

      const d3Data = fg.graphData?.() as { nodes: any[] } | undefined
      const d3ById = d3Data
        ? new Map<string, any>(d3Data.nodes.map((n: any) => [n.id, n]))
        : new Map<string, any>()

      const labels: ClusterLabel[] = []
      for (const comp of graphComponents) {
        if (comp.nodes.length === 0) continue

        const pts: Array<[number, number, number]> = []
        for (const nid of comp.nodes) {
          const n = d3ById.get(nid) ?? graphData.nodes.find(gn => gn.id === nid)
          if (n?.x != null) pts.push([n.x, n.y, n.z])
        }
        if (pts.length === 0) continue

        const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length
        const cy = pts.reduce((s, p) => s + p[1], 0) / pts.length
        const cz = pts.reduce((s, p) => s + p[2], 0) / pts.length
        const screen = fg.graph2ScreenCoords(cx, cy, cz)
        if (!screen) continue

        labels.push({
          graphId: comp.graph_id,
          verdict: comp.verdict ?? 'CLEAN',
          score:   comp.risk_score ?? 0,
          flagged: comp.flagged,
          x: screen.x,
          y: screen.y - 42,
        })
      }
      setClusterLabels(labels)
      labelTickRef.current = requestAnimationFrame(tick)
    }
    labelTickRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(labelTickRef.current)
  }, [graphComponents, graphData])

  // ── Animation loop: glow pulsing, fraud coloring, cash node effects ──────────
  useEffect(() => {
    const FRAUD_COLOR = new THREE.Color('#ff3366')

    const tick = () => {
      const t        = performance.now() / 1000
      const fraudSet = fraudNodeIdsRef.current
      const selId    = selectedNodeIdRef.current
      const cluster  = selectedClusterRef.current
      const hasCluster = cluster !== null && cluster.size > 0

      nodeObjectMapRef.current.forEach((group, id) => {
        const glowSprite = (group as any).__glowSprite as THREE.Sprite | undefined
        const ringMesh   = (group as any).__ringMesh   as THREE.Mesh | undefined
        const isCashNode = (group as any).__isCashNode as boolean | undefined

        // ── Cash node: pulsing glow + ghost line breathing ─────────────────────
        if (isCashNode) {
          const isCashIn = (group as any).__isCashIn as boolean
          const phaseOff = isCashIn ? 0 : Math.PI * 0.6

          if (glowSprite) {
            const pulse = isCashIn
              ? 0.42 + 0.30 * Math.abs(Math.sin(t * 2.1 + phaseOff))
              : 0.22 + 0.22 * Math.abs(Math.sin(t * 1.5 + phaseOff))
            glowSprite.material.opacity = pulse
          }
          if (ringMesh) {
            const mat = ringMesh.material as THREE.MeshBasicMaterial
            const s   = 1 + 0.22 * Math.abs(Math.sin(t * 1.9))
            mat.opacity = 0.12 + 0.18 * Math.abs(Math.sin(t * 2.2 + phaseOff))
            ringMesh.scale.set(s, s, s)
          }
          const ring2 = (group as any).__ring2Mesh as THREE.Mesh | undefined
          if (ring2) {
            const mat2 = ring2.material as THREE.MeshBasicMaterial
            mat2.opacity = 0.06 + 0.12 * Math.abs(Math.sin(t * 2.8 + 0.7))
            const s2 = 1 + 0.14 * Math.abs(Math.sin(t * 2.5 + 1.4))
            ring2.scale.set(s2, s2, s2)
          }
          const ghostLine = (group as any).__ghostLine as THREE.Line | undefined
          const arrowMesh = (group as any).__arrowMesh as THREE.Mesh | undefined
          if (ghostLine) {
            ;(ghostLine.material as THREE.LineBasicMaterial).opacity =
              0.18 + 0.10 * Math.abs(Math.sin(t * 1.1 + phaseOff))
          }
          if (arrowMesh) {
            ;(arrowMesh.material as THREE.MeshBasicMaterial).opacity =
              0.35 + 0.20 * Math.abs(Math.sin(t * 1.1 + phaseOff))
          }
          return
        }

        // ── Regular node animation ─────────────────────────────────────────────
        const isFlagged  = (group as any).__isFlagged as boolean
        const baseRisk   = (group as any).__riskScore as number
        const isFraud    = fraudSet.has(id)
        const isSelected = id === selId
        const isInCluster = !hasCluster || (cluster?.has(id) ?? true)

        // Propagated risk is the source of truth: a node in a fraud cluster
        // inherits exposure even if its own score is 0, so the glow always
        // agrees with the tooltip / inspector.
        const intel        = riskIntelRef.current?.get(id)
        const riskScore    = intel ? intel.propagatedRisk : baseRisk
        const inheritFraud = intel?.clusterFlagged ?? false

        // ── RENDERING PRIORITY: node type → fraud overlay → selection → hover ──
        // Cash endpoints keep their PERMANENT emerald/gold identity fill; fraud is
        // shown only as the red halo ring (below). Ordinary accounts colour by
        // risk: fraud/high-risk → red fill; cluster members redden proportionally.
        const isCashIdentity = (group as any).__isCashIdentity as boolean | undefined
        if (glowSprite) {
          if (isCashIdentity) {
            // Identity is non-negotiable — restore the base colour every frame so
            // nothing (fraud, cluster inheritance, hover) can override it.
            const baseCol = (group as any).__baseColor as THREE.Color | undefined
            if (baseCol) glowSprite.material.color.copy(baseCol)
          } else if (isFraud) {
            glowSprite.material.color.copy(FRAUD_COLOR)
            if (ringMesh) (ringMesh.material as THREE.MeshBasicMaterial).color.copy(FRAUD_COLOR)
          } else if (inheritFraud && riskScore > 0.12) {
            const baseCol = (group as any).__baseColor as THREE.Color | undefined
            if (baseCol) glowSprite.material.color.copy(baseCol).lerp(FRAUD_COLOR, Math.min(1, riskScore))
          }
        }

        // Hover path-highlight: spotlight the hovered node + its direct
        // neighbors, dim everything else — the connected money path lights up.
        const hov = hoveredIdRef.current
        const related = !hov || id === hov || (neighborRef.current.get(hov)?.has(id) ?? false)
        const hoverDim = hov && !related ? 0.12 : 1
        const isHovered = hov === id

        if (glowSprite) {
          const shouldPulse = isFlagged || isFraud || riskScore > 0.45
          let opacity: number
          if (isSelected || isHovered) {
            opacity = 0.9 + 0.1 * Math.sin(t * 4.5)
          } else if (shouldPulse) {
            const intense = isFlagged || isFraud || riskScore > 0.6
            const phase   = t * (intense ? 3.2 : 1.8) + id.charCodeAt(3) * 0.4
            const lo = 0.20 + riskScore * 0.30
            const hi = 0.16 + riskScore * 0.34
            opacity = lo + hi * Math.abs(Math.sin(phase))
          } else {
            opacity = 0.30 + riskScore * 0.18
          }
          glowSprite.material.opacity = opacity * (isInCluster ? 1.0 : 0.12) * hoverDim
        }

        // Size: hover spotlight + selection pulse + cluster-focus / hover dim.
        if (isHovered) {
          const pulse = 1.25 + 0.10 * Math.sin(t * 4.5)
          group.scale.set(pulse, pulse, pulse)
        } else if (isSelected) {
          const pulse = 1.1 + 0.10 * Math.sin(t * 3.5)
          group.scale.set(pulse, pulse, pulse)
        } else if (hov && !related) {
          group.scale.set(0.6, 0.6, 0.6)
        } else if (!isInCluster && hasCluster) {
          group.scale.set(0.75, 0.75, 0.75)
        } else {
          group.scale.set(1, 1, 1)
        }

        // Fraud halo (ring). For cash nodes this is the ONLY fraud indicator and
        // is forced RED; it pulses whenever the cash node is fraud-involved (direct
        // flag OR inherited cluster exposure). Ordinary flagged/fraud nodes keep the
        // existing behaviour. When a cash node is NOT fraud-involved, fade it out so
        // a clean green/gold endpoint shows no halo.
        const cashFraud = !!isCashIdentity && (isFraud || (inheritFraud && riskScore > 0.12))
        if (ringMesh && (isFlagged || isFraud || cashFraud)) {
          const mat = ringMesh.material as THREE.MeshBasicMaterial
          if (isCashIdentity) mat.color.copy(FRAUD_COLOR)   // cash halo is always red
          const phase = t * 2.6 + id.charCodeAt(3) * 0.5
          const base  = isCashIdentity ? 0.14 : 0.08
          const amp   = isCashIdentity ? 0.34 : 0.20
          mat.opacity = (base + amp * Math.abs(Math.sin(phase))) * (isInCluster ? 1 : 0.1) * hoverDim
          const s = 1 + 0.18 * Math.abs(Math.sin(phase * 1.2))
          ringMesh.scale.set(s, s, s)
        } else if (ringMesh && isCashIdentity) {
          // Clean cash endpoint — no fraud → hide the halo entirely.
          ;(ringMesh.material as THREE.MeshBasicMaterial).opacity = 0
        }
      })
      animFrameRef.current = requestAnimationFrame(tick)
    }
    animFrameRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(animFrameRef.current)
  }, [])

  // ── Structural signature ─────────────────────────────────────────────────────
  // The backend re-broadcasts graph_update on a ~1s heartbeat even when nothing
  // changed, handing us a fresh graphData object each time. If that flowed
  // straight into ForceGraph3D it would reset the d3 alpha to 1 every second and
  // the layout would NEVER cool — nodes jitter forever ("vibrating / under
  // construction"). We collapse the graph to a content signature so mergedData
  // keeps a STABLE identity across identical heartbeats; the library only
  // reheats when the node/link/cluster set genuinely changes.
  // Server investigation layout → normalized world-space targets. Centered and
  // scaled to a density comparable to the local layout; planar (z=0) so the
  // motif-preserving fund_flow/layered/community layout reads as an investigation
  // diagram. Empty when the backend layout is unavailable → local layout is used.
  const backendTargets = useMemo(() => {
    const out = new Map<string, [number, number, number]>()
    const pos = backendLayout?.positions
    if (!pos) return out
    const ids = Object.keys(pos)
    if (ids.length === 0) return out
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    for (const id of ids) {
      const p = pos[id]
      if (p.x < minX) minX = p.x
      if (p.x > maxX) maxX = p.x
      if (p.y < minY) minY = p.y
      if (p.y > maxY) maxY = p.y
    }
    const cx = (minX + maxX) / 2
    const cy = (minY + maxY) / 2
    const diag = Math.hypot(maxX - minX, maxY - minY) || 1
    const scale = (90 * Math.sqrt(ids.length)) / diag  // adaptive: even density vs node count
    for (const id of ids) {
      const p = pos[id]
      out.set(id, [(p.x - cx) * scale, -(p.y - cy) * scale, 0])  // negate y → top-down reads correctly
    }
    return out
  }, [backendLayout])

  // STRUCTURAL signature ONLY — the reheat trigger. It MUST change only when the
  // graph's TOPOLOGY changes (nodes, edges, cash endpoints, component grouping) or
  // the layout MODE changes. It must NOT change on re-scoring: a Blue-Team verdict
  // that flips a component's `flagged` flag, or a node's risk score, is a SEMANTIC
  // event handled by the (position-free) animation loop — folding it in here reset
  // d3 alpha to 1 on every re-score and was the dominant cause of the graph never
  // settling. `cashAnimIds` (a transient pulse set) is likewise visual-only and is
  // excluded. The backend `mode` stays in — a real layout change is a sanctioned
  // motion trigger — but its node COUNT does not (that rides on `nodes`).
  const graphSig = useMemo(() => {
    const nodes = graphData.nodes.map(n => n.id).join(',')
    const links = graphData.links.map(l =>
      `${typeof l.source === 'string' ? l.source : (l.source as any).id}>` +
      `${typeof l.target === 'string' ? l.target : (l.target as any).id}`,
    ).join(',')
    const cash  = cashNodes.map(c => c.id).join(',')
    // Component GROUPING affects clustering/home assignment, so membership is
    // structural — but the `flagged` boolean is NOT: exclude it so re-scoring a
    // known grouping does not relayout.
    const comps = (graphComponents ?? []).map(c => `${c.graph_id}:${c.nodes.length}`).join(',')
    const blay  = backendLayout ? backendLayout.mode : ''
    return `${nodes}||${links}||${cash}||${comps}||${blay}`
  }, [graphData, cashNodes, graphComponents, backendLayout])

  // ── Merged graph data — component detection + force-seed injection ───────────
  // Runs synchronously inside the render pass so nodeToCompRef is populated
  // BEFORE d3 fires force.initialize() after React commit. The cluster force
  // reads nodeToCompRef every tick to group nodes into soft-body clusters.
  // Keyed on graphSig (not graphData) so heartbeat re-broadcasts reuse the
  // cached object and don't reheat the simulation. See graphSig above.
  const mergedData = useMemo(() => {
    // RESTORE MODE: pin every node at its captured position (fx/fy/fz) so the d3
    // simulation cannot move it — the graph is reproduced EXACTLY, no re-layout.
    if (restoreSnapshot) {
      return {
        nodes: restoreSnapshot.nodes.map(n => ({
          ...n, x: n.x, y: n.y, z: n.z, fx: n.x, fy: n.y, fz: n.z,
        })) as any[],
        links: restoreSnapshot.edges.map(e => ({ ...e })) as any[],
      }
    }
    if (graphData.nodes.length === 0) {
      return { nodes: [] as any[], links: [] as any[] }
    }

    // LAYOUT-MODE CHANGE = sanctioned full re-layout (req 5): drop every frozen
    // pin so all nodes re-solve under the new mode. New transactions do NOT reach
    // here with a mode change, so the mental map is only ever discarded on a real
    // mode switch — never on streaming.
    const mode = backendLayout?.mode ?? null
    const prevMode = lastLayoutModeRef.current
    if (mode !== prevMode) {
      lastLayoutModeRef.current = mode
      // Only a GENUINE switch between two real modes (e.g. an investigator
      // "Recalculate Layout" that changes the backend mode) is a sanctioned full
      // relayout. The null→mode transition is just the backend layout arriving —
      // which ALSO happens on every remount, after the cache was rehydrated above.
      // Treating that as a relayout was part of the navigation bug: it wiped the
      // frozen map the instant the layout fetch resolved. So guard against it.
      if (prevMode !== null && mode !== null) {
        frozenPosRef.current.clear()
        layoutCache.clear()   // real relayout → discard persisted positions
        for (const n of liveNodesRef.current) {
          if ((n as any).isCashNode) continue
          n.fx = null; n.fy = null; n.fz = null
        }
      }
    }

    // RE-ARM the convergence gate: a structural change (this memo only recomputes
    // on graphSig) means there is work to settle, so unlatch the freeze. Already-
    // frozen nodes stay pinned (below); only the newcomers move and re-settle.
    isFrozenRef.current = false
    settledTicksRef.current = 0

    // 1. Build nodeId → compId.
    //    Blue Team's graphComponents (if present) OVERRIDES BFS — that's the
    //    only way separate fraud graphs land in separate clusters when the
    //    raw transaction graph happens to be connected via a shared hub.
    const nodeIdList = graphData.nodes.map(n => n.id)
    const linkPairs  = graphData.links.map(l => ({
      source: typeof l.source === 'string' ? l.source : (l.source as any).id,
      target: typeof l.target === 'string' ? l.target : (l.target as any).id,
    }))
    let compOf: Map<string, string>
    if (graphComponents && graphComponents.length > 0) {
      const groupMap = new Map<string, string>()
      for (const comp of graphComponents) {
        for (const nid of comp.nodes) groupMap.set(nid, comp.graph_id)
      }
      // Any node not covered by graphComponents falls back to BFS
      const bfs = detectComponentsFromGraph(nodeIdList, linkPairs)
      compOf = new Map(nodeIdList.map(id => [id, groupMap.get(id) ?? bfs.get(id) ?? id]))
    } else {
      compOf = detectComponentsFromGraph(nodeIdList, linkPairs)
    }
    nodeToCompRef.current = compOf

    // 2. Assign each freshly-seen component a stable appearance index, then
    //    compute every cluster's HOME = its fixed distributed direction × a
    //    world radius that grows with the cluster count (so N clusters always
    //    have room). NO cluster is placed at the origin → no central dominance.
    //    Recomputed each render: as clusters appear, radius grows and existing
    //    clusters glide outward along their fixed direction (no reshuffle).
    const clusterIds = [...new Set(compOf.values())]
    for (const cid of clusterIds) {
      if (clusterIndexRef.current.has(cid)) continue
      clusterIndexRef.current.set(cid, clusterIdxRef.current++)
    }
    const N = clusterIds.length
    const worldR = N <= 1 ? 0 : FORCE.homeRadiusK * Math.sqrt(N)
    for (const cid of clusterIds) {
      const dir = clusterUnitDir(clusterIndexRef.current.get(cid)!)
      clusterHomeRef.current.set(cid, [dir[0] * worldR, dir[1] * worldR, dir[2] * worldR])
    }

    // Component sizes — used to scale initial seed spread (below).
    const compSize = new Map<string, number>()
    for (const cid of compOf.values()) compSize.set(cid, (compSize.get(cid) ?? 0) + 1)

    // 2b. TOPOLOGY-AWARE LAYOUT — for each connected component, analyse its
    //     directed transaction structure and compute an intelligent local
    //     placement (chain → line, fan-out → cone, ring → circle, layered fraud →
    //     stacked layers …). The node's structural TARGET = its cluster home +
    //     this local position. The layout force springs toward this target so the
    //     physics only refines the intelligent layout. Recomputed every structural
    //     change; existing nodes keep their live x/y/z and merely re-target, so
    //     new transactions animate in smoothly instead of rebuilding the graph.
    const compNodeIds = new Map<string, string[]>()
    const compEdges   = new Map<string, { source: string; target: string }[]>()
    for (const id of nodeIdList) {
      const cid = compOf.get(id) ?? id
      ;(compNodeIds.get(cid) ?? compNodeIds.set(cid, []).get(cid)!).push(id)
    }
    for (const lp of linkPairs) {
      const cid = compOf.get(lp.source) ?? lp.source
      ;(compEdges.get(cid) ?? compEdges.set(cid, []).get(cid)!).push(lp)
    }
    const nextTargets = new Map<string, [number, number, number]>()
    const layoutTypes: string[] = []
    let seedFails = 0
    for (const [cid, ids] of compNodeIds) {
      const home = clusterHomeRef.current.get(cid) ?? [0, 0, 0]
      const { positions, type, containsRing, containsFan, quality } = computeComponentLayout(ids, compEdges.get(cid) ?? [])
      // Each cluster's seed is validated inside computeComponentLayout; surface a
      // ✗ marker (with the failed criteria) so a sub-par seed is visible, not silent.
      const tag = quality && !quality.pass ? `${type}(${ids.length})✗${quality.failed.join('/')}` : `${type}(${ids.length})`
      if (quality && !quality.pass) seedFails++
      const protectedMotif = containsRing || containsFan
      layoutTypes.push(protectedMotif ? `${tag}⊚` : tag)
      // The motif-aware seed is the SINGLE source of truth (see LIVE_USES_BACKEND_
      // LAYOUT). Every node's structural target = its cluster home + the seed's local
      // motif position; the force sim only polishes it. The backend override is OFF
      // by default (it ran a second, flat layout engine that fought the 3D motifs).
      for (const id of ids) {
        const bt = (LIVE_USES_BACKEND_LAYOUT && !protectedMotif)
          ? backendTargets.get(id)
          : undefined
        if (bt) {
          nextTargets.set(id, bt)
          continue
        }
        const lp = positions.get(id) ?? [0, 0, 0]
        nextTargets.set(id, [home[0] + lp[0], home[1] + lp[1], home[2] + lp[2]])
      }
    }
    structTargetRef.current = nextTargets
    if (layoutTypes.length > 0) {
      console.log(
        `%c[TGIE layout] ${compNodeIds.size} cluster(s) → ${layoutTypes.join(', ')}` +
        (seedFails ? ` · ${seedFails} seed(s) need refinement` : ' · all seeds validated ✓'),
        `color:${seedFails ? '#f0b86e' : '#7ee787'}`,
      )
    }

    // Drive camera auto-frame: bump clusterCount when the SET of clusters changes
    const clusterSig = clusterIds.slice().sort().join('|')
    if (clusterSig !== lastSectorSigRef.current) {
      lastSectorSigRef.current = clusterSig
      // Defer to avoid setState-during-render
      Promise.resolve().then(() => setClusterCount(new Set(nodeToCompRef.current.values()).size))
    }

    // 3. Inject a home-anchored x/y/z onto each input node so three-forcegraph's
    //    d3.nodes(newArray) call doesn't randomize fresh objects to the origin.
    //    Existing nodes keep their previously seeded position (no per-frame
    //    jump). Seed spread scales with √(component size) so a large component
    //    starts low-density (dense seeds + local charge would otherwise spike).
    const regularNodes = graphData.nodes.map(n => {
      const cid = compOf.get(n.id)
      const home = cid ? clusterHomeRef.current.get(cid) : undefined
      if (!home) return n
      let ip = initialPositionRef.current.get(n.id)
      if (!ip) {
        // Seed a brand-new node AT its intelligent topology slot (not a random
        // sphere) so the structure reads correctly from the very first frame and
        // the force engine only has to relax it. Falls back to a near-home seed.
        ip = structTargetRef.current.get(n.id)
          ?? seedNear(home, 22 + Math.sqrt(compSize.get(cid!) ?? 1) * 11, n.id)
        initialPositionRef.current.set(n.id, ip)
      }
      // INCREMENTAL STABILITY: a node that already settled in a prior convergence
      // is re-emitted PINNED at its frozen position (fx/fy/fz), so a new
      // transaction never disturbs the existing picture — only brand-new nodes are
      // free to find their slot. This is what gives the investigator a stable
      // mental map (req 8/13) and locks fraud motifs permanently (req 9).
      const frozen = frozenPosRef.current.get(n.id)
      if (frozen) {
        return { ...n, x: frozen[0], y: frozen[1], z: frozen[2], fx: frozen[0], fy: frozen[1], fz: frozen[2] }
      }
      // x/y/z only — NOT fx/fy/fz. The d3 sim refines layout for this NEW node; the
      // structural anchor + cluster separation place it; it freezes on next settle.
      return { ...n, x: ip[0], y: ip[1], z: ip[2] }
    })

    if (cashNodes.length === 0) {
      return { nodes: regularNodes as any[], links: graphData.links as any[] }
    }

    const parentPosMap = new Map(regularNodes.map(n => [n.id, n]))

    const cashNodeObjects = cashNodes.flatMap(cn => {
      let pos = cashPositionsRef.current.get(cn.id)

      if (!pos) {
        const parent = parentPosMap.get(cn.parentAccount)
        if (parent?.x === undefined || parent?.y === undefined || parent?.z === undefined) {
          return []
        }
        const angle = cashAngleFromId(cn.id)
        const dist  = 68
        pos = {
          fx: parent.x + Math.cos(angle) * dist,
          fy: parent.y + (cn.cashType === 'CASH_IN' ? 34 : -34),
          fz: parent.z + Math.sin(angle) * dist,
        }
        cashPositionsRef.current.set(cn.id, pos)
      }

      const parent = parentPosMap.get(cn.parentAccount)
      const dx = (parent?.x ?? pos.fx) - pos.fx
      const dy = (parent?.y ?? pos.fy) - pos.fy
      const dz = (parent?.z ?? pos.fz) - pos.fz
      const len = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1

      const isCashIn = cn.cashType === 'CASH_IN'
      return [{
        id: cn.id,
        fx: pos.fx, fy: pos.fy, fz: pos.fz,
        x:  pos.fx, y:  pos.fy, z:  pos.fz,
        isCashNode:     true,
        cashType:       cn.cashType as CashNodeType,
        amount:         cn.amount,
        parentAccount:  cn.parentAccount,
        dirToParent:    { x: dx / len, y: dy / len, z: dz / len },
        distToParent:   len,
        transaction_count: 0,
        total_sent:        isCashIn ? 0 : cn.amount,
        total_received:    isCashIn ? cn.amount : 0,
        risk_level:        'safe',
        risk_score:        0,
        account_type:      'cash',
        detected_patterns: [],
        geo_locations:     [],
        is_flagged:        false,
        incoming_count:    isCashIn ? 1 : 0,
        outgoing_count:    isCashIn ? 0 : 1,
        connected_accounts:[cn.parentAccount],
        last_activity:     cn.timestamp,
        nodeColor:         isCashIn ? '#22c98a' : '#e8b54a',
        nodeSize:          1,
      }]
    })

    // The edge from a cash event to its source/destination account is PERMANENT —
    // a cash node must never float orphaned once its 2.5s entry animation ends.
    const cashLinks = cashNodes
      .filter(cn => cashPositionsRef.current.has(cn.id))
      .map(cn => {
        const isCashIn = cn.cashType === 'CASH_IN'
        return {
          id:           `cash-edge-${cn.id}`,
          source:       isCashIn ? cn.id : cn.parentAccount,
          target:       isCashIn ? cn.parentAccount : cn.id,
          amount:       cn.amount,
          payment_rail: 'CASH',
          risk_score:   0,
          is_flagged:   false,
          timestamp:    cn.timestamp,
          isCashEdge:   true,
          cashType:     cn.cashType,
          linkColor:    isCashIn ? 'rgba(34,201,138,0.45)' : 'rgba(232,181,74,0.45)',
        }
      })

    return {
      nodes: [...regularNodes, ...cashNodeObjects] as any[],
      links: [...graphData.links, ...cashLinks] as any[],
    }
  // Recompute ONLY when the structural signature changes — heartbeat
  // re-broadcasts with identical content reuse the previous object reference,
  // which keeps ForceGraph3D from reheating and lets the layout cool.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphSig, restoreSnapshot])

  // ── Per-node THREE.js object factory ─────────────────────────────────────────
  const nodeThreeObject = useCallback((node: any) => {
    const n = node as GraphNode & {
      isCashNode?:   boolean
      cashType?:     CashNodeType
      amount?:       number
      parentAccount?:string
      dirToParent?:  { x: number; y: number; z: number }
      distToParent?: number
    }

    // ── Cash node ─────────────────────────────────────────────────────────────
    if (n.isCashNode) {
      const isCashIn  = n.cashType === 'CASH_IN'
      const cashColor = new THREE.Color(isCashIn ? '#22c98a' : '#e8b54a')
      const group     = new THREE.Group()

      const glowSprite = new THREE.Sprite(new THREE.SpriteMaterial({
        map: glowTex, color: cashColor,
        transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0.50,
      }))
      glowSprite.scale.set(34, 34, 1)
      group.add(glowSprite)

      const coreSprite = new THREE.Sprite(new THREE.SpriteMaterial({
        map: glowTex, color: new THREE.Color(isCashIn ? '#9affd0' : '#ffe6a8'),
        transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0.92,
      }))
      coreSprite.scale.set(5, 5, 1)
      group.add(coreSprite)

      const ring = new THREE.Mesh(
        new THREE.RingGeometry(6.8, 9.0, 32),
        new THREE.MeshBasicMaterial({
          color: cashColor, side: THREE.DoubleSide,
          transparent: true, opacity: 0.22,
          blending: THREE.AdditiveBlending, depthWrite: false,
        }),
      )
      group.add(ring)

      if (isCashIn) {
        const ring2 = new THREE.Mesh(
          new THREE.RingGeometry(4.2, 5.8, 32),
          new THREE.MeshBasicMaterial({
            color: cashColor, side: THREE.DoubleSide,
            transparent: true, opacity: 0.14,
            blending: THREE.AdditiveBlending, depthWrite: false,
          }),
        )
        group.add(ring2)
        ;(group as any).__ring2Mesh = ring2
      }

      const dir = n.dirToParent ?? { x: 0, y: 0, z: -1 }
      const ghostLen = Math.min((n.distToParent ?? 60) * 0.55, 38)
      const linePoints = [
        new THREE.Vector3(0, 0, 0),
        new THREE.Vector3(dir.x * ghostLen, dir.y * ghostLen, dir.z * ghostLen),
      ]
      const ghostLine = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(linePoints),
        new THREE.LineBasicMaterial({
          color: cashColor, transparent: true, opacity: 0.22,
          blending: THREE.AdditiveBlending, depthWrite: false,
        }),
      )
      group.add(ghostLine)

      const coneGeo  = new THREE.ConeGeometry(1.8, 5, 8)
      const coneMat  = new THREE.MeshBasicMaterial({
        color: cashColor, transparent: true, opacity: 0.45,
        blending: THREE.AdditiveBlending, depthWrite: false,
      })
      const arrow = new THREE.Mesh(coneGeo, coneMat)

      if (isCashIn) {
        arrow.position.set(dir.x * ghostLen, dir.y * ghostLen, dir.z * ghostLen)
        const up = new THREE.Vector3(0, 1, 0)
        const target = new THREE.Vector3(dir.x, dir.y, dir.z).normalize()
        arrow.quaternion.setFromUnitVectors(up, target)
      } else {
        arrow.position.set(dir.x * 6, dir.y * 6, dir.z * 6)
        const up = new THREE.Vector3(0, 1, 0)
        const awayDir = new THREE.Vector3(-dir.x, -dir.y, -dir.z).normalize()
        arrow.quaternion.setFromUnitVectors(up, awayDir)
      }
      group.add(arrow)

      ;(group as any).__glowSprite = glowSprite
      ;(group as any).__ringMesh   = ring
      ;(group as any).__isCashNode = true
      ;(group as any).__isCashIn   = isCashIn
      ;(group as any).__isFlagged  = false
      ;(group as any).__riskScore  = 0
      ;(group as any).__ghostLine  = ghostLine
      ;(group as any).__arrowMesh  = arrow

      nodeObjectMapRef.current.set(n.id, group)
      return group
    }

    // ── Regular account node ─────────────────────────────────────────────────
    // Cash endpoints (CASH_SOURCE/CASH_EXIT) are first-class VIRTUAL system nodes.
    // Their identity colour (emerald = cash in, gold = cash out) is PERMANENT;
    // fraud is shown as a red halo overlay (below + in the animation loop), never
    // by recolouring the fill. This is the rendering-priority rule:
    //   node type → fraud overlay → selection → hover.
    const isCashIdentity = (n.account_type as string) === 'cash'
    const cashIsIn = isCashIdentity && (n.total_sent ?? 0) >= (n.total_received ?? 0)
    const hex = (n.nodeColor ?? '#00f5ff') as string
    const col = new THREE.Color(hex)
    const group = new THREE.Group()

    const glowMat = new THREE.SpriteMaterial({
      map: glowTex, color: col,
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
      opacity: n.is_flagged ? 0.72 : n.risk_score > 0.65 ? 0.42 : 0.32,
    })
    const glowSprite = new THREE.Sprite(glowMat)
    const glowSize   = n.is_flagged ? 28 : n.risk_score > 0.65 ? 20 : n.risk_score > 0.45 ? 15 : 13
    glowSprite.scale.set(glowSize, glowSize, 1)
    group.add(glowSprite)

    const coreSprite = new THREE.Sprite(new THREE.SpriteMaterial({
      map: glowTex, color: new THREE.Color('#ffffff'),
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
      opacity: n.is_flagged ? 1.0 : 0.88,
    }))
    coreSprite.scale.set(
      n.is_flagged ? 5.5 : n.risk_score > 0.65 ? 4 : 2.8,
      n.is_flagged ? 5.5 : n.risk_score > 0.65 ? 4 : 2.8,
      1,
    )
    group.add(coreSprite)

    // Ring mesh doubles as the fraud halo. Normal flagged nodes get a subtle ring
    // in their own colour; cash nodes ALWAYS get a (larger, initially-hidden) RED
    // ring so fraud involvement can be shown as an overlay without ever touching
    // the emerald/gold identity fill.
    if (n.is_flagged || isCashIdentity) {
      const ring = new THREE.Mesh(
        isCashIdentity ? new THREE.RingGeometry(6, 8.6, 44) : new THREE.RingGeometry(5, 7, 36),
        new THREE.MeshBasicMaterial({
          color: isCashIdentity ? new THREE.Color('#ff3366') : col,
          side: THREE.DoubleSide,
          transparent: true, opacity: isCashIdentity ? 0 : 0.16,
          blending: THREE.AdditiveBlending, depthWrite: false,
        }),
      )
      group.add(ring)
      ;(group as any).__ringMesh = ring
    }

    ;(group as any).__glowSprite     = glowSprite
    ;(group as any).__isFlagged      = n.is_flagged
    ;(group as any).__riskScore      = n.risk_score
    ;(group as any).__baseColor      = col.clone()
    ;(group as any).__isCashIdentity = isCashIdentity
    ;(group as any).__cashRole       = isCashIdentity ? (cashIsIn ? 'in' : 'out') : undefined

    nodeObjectMapRef.current.set(n.id, group)
    return group
  }, [glowTex])

  // ── Interaction callbacks ────────────────────────────────────────────────────
  const handleNodeClick = useCallback((node: any) => {
    onNodeClick(node as GraphNode)
    if (!fgRef.current || !node) return
    const { x = 0, y = 0, z = 0 } = node
    const cam = fgRef.current.camera() as THREE.PerspectiveCamera
    const dir = new THREE.Vector3(
      cam.position.x - x, cam.position.y - y, cam.position.z - z,
    ).normalize().multiplyScalar(65)
    fgRef.current.cameraPosition(
      { x: x + dir.x, y: y + dir.y, z: z + dir.z },
      { x, y, z },
      950,
    )
  }, [onNodeClick])

  const handleNodeHover = useCallback((node: any) => {
    hoveredIdRef.current = node?.id ?? null
    onHoverChange?.(node ?? null)
    document.body.style.cursor = node ? 'pointer' : 'default'
  }, [onHoverChange])

  // ── Link appearance ──────────────────────────────────────────────────────────
  const getLinkWidth = useCallback((link: any) => {
    if (link.isCashEdge) return 1.5
    // Logarithmic magnitude encoding (req: log scaling). Thickness tracks the
    // ORDER of magnitude of the transfer, so each decade is visibly distinct and
    // no two collapse together — the old linear buckets rendered ₹1cr and ₹5L at
    // the SAME width (2.8). Now ₹10k→1.2, ₹1L→1.8, ₹10L→2.4, ₹1cr→3.0, ₹10cr→3.6.
    const amt    = Math.max(1, (link.amount ?? 0) as number)
    const decade = Math.log10(amt)        // ₹1k→3, ₹10k→4 … ₹10cr→8
    return Math.max(0.6, Math.min(3.6, 0.6 + 0.6 * (decade - 3)))
  }, [])

  const getLinkColor = useCallback((link: any) => {
    if (link.isCashEdge) {
      return link.cashType === 'CASH_IN'
        ? 'rgba(34,201,138,0.55)'
        : 'rgba(232,181,74,0.55)'
    }
    const fraudSet = fraudNodeIdsRef.current
    if (fraudSet.size > 0) {
      const src = typeof link.source === 'object' ? link.source?.id : link.source
      const tgt = typeof link.target === 'object' ? link.target?.id : link.target
      if (fraudSet.has(src) || fraudSet.has(tgt)) return 'rgba(255,51,102,0.65)'
    }
    return (link.linkColor as string) ?? 'rgba(120,190,255,0.22)'
  }, [])

  // NOTE: moving flow particles were removed intentionally. On an investigator-
  // grade case graph (mostly historical / completed fraud) continuous motion
  // reads as "live streaming", adds visual noise over nodes/arrowheads, and
  // costs CPU/GPU at scale. Fund DIRECTION is carried by static arrowheads;
  // MAGNITUDE by logarithmic edge width; RISK by edge colour. No moving objects.

  // Straight links by default (readability > decoration). Curve ONLY when a
  // reciprocal edge exists (A→B and B→A) so the two don't overlap into one line.
  const getLinkCurvature = useCallback((link: any) => {
    const s = typeof link.source === 'string' ? link.source : link.source?.id
    const t = typeof link.target === 'string' ? link.target : link.target?.id
    return reverseEdgeRef.current.has(`${s}>${t}`) ? 0.22 : 0
  }, [])

  // Render size mirrors fraud importance → visual hierarchy (hubs dominate).
  const getNodeVal = useCallback((n: any) => {
    const base = n.isCashNode ? 2.0 : n.is_flagged ? 3.6 : n.risk_score > 0.6 ? 2.4 : n.risk_score > 0.35 ? 1.6 : 1
    const deg  = degreeRef.current.get(n.id) ?? 0
    return base + Math.min(2.2, deg * 0.18)   // higher degree ⇒ larger node
  }, [])

  // ── Node tooltip ─────────────────────────────────────────────────────────────
  // The legacy built-in hover label was removed. The unified, fraud-aware
  // tooltip in App.tsx (driven by onHoverChange → propagated risk intel) is the
  // SINGLE source of truth for node hover rendering. Returning '' here ensures
  // react-force-graph never paints its own duplicate overlay.
  const getNodeLabel = useCallback(() => '', [])

  return (
    <div
      ref={wrapRef}
      style={{ position: 'absolute', inset: 0, zIndex: 1 }}
      onClick={e => { if ((e.target as HTMLElement).tagName === 'CANVAS') onNodeClick(null) }}
    >
      <ForceGraph3D
        ref={fgRef as any}
        graphData={mergedData as any}
        width={dims.w}
        height={dims.h}

        backgroundColor="#000000"

        nodeThreeObject={nodeThreeObject}
        nodeThreeObjectExtend={false}
        nodeLabel={getNodeLabel}

        nodeVal={getNodeVal}
        nodeRelSize={4}

        linkColor={getLinkColor}
        linkWidth={getLinkWidth}
        linkOpacity={0.40}
        linkCurvature={getLinkCurvature}

        // Arrowheads on EVERY edge → money direction is always explicit (req:
        // directionality), not just on the animated cash/fraud streams. Colour
        // matches the link so it never introduces a new palette element.
        linkDirectionalArrowLength={3.2}
        linkDirectionalArrowRelPos={0.92}
        linkDirectionalArrowColor={getLinkColor}

        onNodeClick={handleNodeClick}
        onNodeHover={handleNodeHover}
        enableNodeDrag={!restore}
        enableNavigationControls
        showNavInfo={false}

        // Let the d3 sim run and COOL into a stable, readable layout (the
        // multi-scale forces above organize the clusters during this window).
        // warmupTicks pre-settles a few ticks before first paint so clusters
        // don't visibly fly apart from origin; cooldownTicks caps the settle so
        // CPU drops to idle once organized. Reheated on data growth (see effect).
        warmupTicks={restore ? 0 : 40}
        cooldownTicks={restore ? 0 : 340}
        d3AlphaDecay={0.0165}
        d3VelocityDecay={FORCE.velocityDecay}
        onEngineTick={handleEngineTick}
        onEngineStop={handleEngineStop}
      />

      {/* Cluster label overlays */}
      {clusterLabels.map(label => {
        const borderC = label.flagged ? 'rgba(255,51,102,0.45)'
          : label.verdict === 'SUSPICIOUS' ? 'rgba(245,158,11,0.35)'
          : 'rgba(0,255,136,0.22)'
        const bg = label.flagged ? 'rgba(255,51,102,0.10)'
          : label.verdict === 'SUSPICIOUS' ? 'rgba(245,158,11,0.07)'
          : 'rgba(0,255,136,0.06)'
        const textC = label.flagged ? '#ff3366'
          : label.verdict === 'SUSPICIOUS' ? '#f59e0b'
          : '#00ff88'
        return (
          <div key={label.graphId} style={{
            position: 'absolute', left: label.x, top: label.y,
            transform: 'translateX(-50%)', pointerEvents: 'none', zIndex: 20,
            display: 'flex', alignItems: 'center', gap: 5,
            padding: '3px 10px', borderRadius: 20,
            background: bg, border: `1px solid ${borderC}`,
            backdropFilter: 'blur(8px)',
            boxShadow: label.flagged ? '0 0 16px rgba(255,51,102,0.22)'
              : label.verdict === 'SUSPICIOUS' ? '0 0 10px rgba(245,158,11,0.12)'
              : '0 0 8px rgba(0,255,136,0.08)',
            whiteSpace: 'nowrap',
          }}>
            <div style={{
              width: 4, height: 4, borderRadius: '50%',
              background: textC, boxShadow: `0 0 5px ${textC}`, flexShrink: 0,
            }} />
            <span style={{ fontSize: 8, fontFamily: 'monospace', fontWeight: 700, color: '#3a5060', letterSpacing: '.08em' }}>
              {label.graphId}
            </span>
            <span style={{ fontSize: 7, color: '#1e2d3a' }}>—</span>
            <span style={{ fontSize: 8, fontWeight: 700, letterSpacing: '.10em', color: textC }}>
              {label.verdict === 'FRAUD' ? 'FRAUD' : label.verdict === 'SUSPICIOUS' ? 'WARN' : 'SAFE'}
            </span>
            <span style={{ fontSize: 7, color: '#1e2d3a' }}>—</span>
            <span style={{ fontSize: 8, fontFamily: 'monospace', color: textC }}>
              {label.score.toFixed(2)}
            </span>
          </div>
        )
      })}
    </div>
  )
})

export const GraphScene = memo(GraphSceneInner)
