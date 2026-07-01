/// <reference lib="webworker" />
/**
 * GRAPH WORLD WORKER — True multi-simulation spatial layout
 *
 * Key insight: two simulations with sectorD = 800 and distanceMax = 150
 * have zero charge interaction (150 << 800). Combined with no cross-cluster
 * link springs, the two systems are mathematically independent.
 * World position is a simple translation: P_world = P_local + S_offset.
 * The cluster center force is replaced by the natural forceCenter(0,0,0)
 * in each local simulation — which is correct because each simulation lives
 * in its own coordinate frame.
 *
 * Architecture:
 *   detectComponents(allNodes, allLinks)
 *   → compA → independentSimA(localCenter=0,0,0) + sectorOffsetA=[  0,  0, 0]
 *   → compB → independentSimB(localCenter=0,0,0) + sectorOffsetB=[800,  0, 0]
 *   → compC → independentSimC(localCenter=0,0,0) + sectorOffsetC=[-800, 0, 0]
 *
 *   worldPos(node) = sectorOffset(comp) + localSimPos(node)
 *
 * Cross-component links are EXCLUDED from all simulations — no inter-cluster
 * forces exist at any level. Each simulation is fully independent.
 */

import { forceSimulation, forceCenter, forceLink, forceManyBody } from 'd3-force-3d'

// ── Types ──────────────────────────────────────────────────────────────────────
type SimNode = {
  id: string
  x: number; y: number; z: number
  vx: number; vy: number; vz: number
}

type WorkerNode = { id: string }
type WorkerLink = { source: string; target: string }

type InMsg =
  | { type: 'update'; nodes: WorkerNode[]; links: WorkerLink[]; nodeGroupIds?: Record<string, string> }
  | { type: 'heat'; value: number }

type CompWorld = {
  compId: string
  sectorOffset: [number, number, number]
  sim: ReturnType<typeof forceSimulation>
  simNodes: SimNode[]
}

// ── BFS connected-component detection ─────────────────────────────────────────
// Returns nodeId → compId where compId is the lexicographically smallest
// nodeId in the component — stable, collision-resistant identity that survives
// incremental graph updates.
function detectComponents(
  nodeIds: string[],
  links: WorkerLink[],
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
    const stack: string[] = [startId]
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
    for (let i = 1; i < members.length; i++) {
      if (members[i] < minId) minId = members[i]
    }
    for (const m of members) compOf.set(m, minId)
  }

  return compOf
}

// ── Sector layout ──────────────────────────────────────────────────────────────
// 800 >> distanceMax(150) → inter-cluster charge interaction is identically zero.
const SECTOR_D = 800

const PRESET_SECTORS: ReadonlyArray<[number, number, number]> = [
  [           0,           0,   0],  // primary cluster
  [  SECTOR_D,            0,   0],  // right
  [ -SECTOR_D,            0,   0],  // left
  [          0,   SECTOR_D,   0],  // top
  [          0,  -SECTOR_D,   0],  // bottom
  [  SECTOR_D,    SECTOR_D,  40],  // upper-right (slight Z for depth)
  [ -SECTOR_D,    SECTOR_D, -40],  // upper-left
  [  SECTOR_D,   -SECTOR_D, -40],  // lower-right
  [ -SECTOR_D,   -SECTOR_D,  40],  // lower-left
]

// compId → sector index — persists across updates; grows monotonically
const sectorAssignment = new Map<string, number>()
let sectorIdx = 0

function getOrAssignSectorIndex(compId: string): number {
  if (sectorAssignment.has(compId)) return sectorAssignment.get(compId)!
  const i = sectorIdx++
  sectorAssignment.set(compId, i)
  return i
}

function sectorOffset(i: number): [number, number, number] {
  if (i < PRESET_SECTORS.length) return [...PRESET_SECTORS[i]] as [number, number, number]
  // Golden-angle spiral for overflow components — XY-dominant
  const ga = 2.399911  // golden angle ≈ 137.5° in radians
  const t  = ga * (i - PRESET_SECTORS.length)
  const r  = SECTOR_D * (1.6 + (i - PRESET_SECTORS.length) * 0.3)
  return [r * Math.cos(t), r * Math.sin(t), 0]
}

// ── Worker-level state ─────────────────────────────────────────────────────────
// One CompWorld per connected component. Key = compId.
const worlds = new Map<string, CompWorld>()

// Flat ordered list matching the main thread's nodes array.
// positions[i*3..] corresponds to allNodes[i].
let allNodes: WorkerNode[] = []

// Fast lookup: nodeId → { node: SimNode, world: CompWorld }
// Rebuilt on every update so tick never needs a Map lookup per node.
let nodeWorldIndex = new Map<string, { node: SimNode; world: CompWorld }>()

// Tracks whether previous update used group-based assignment
let hadGroupsLastUpdate = false

// Output buffer — transferred via postMessage; reset after transfer
let positions = new Float32Array(0)

// Manual tick interval handle
let tickInterval: ReturnType<typeof setInterval> | null = null

// Debug — remembers last logged sector signature so the log fires only on change
let lastLoggedSig: string = ''

// ── Build a single simulation for one component ────────────────────────────────
function buildSim(simNodes: SimNode[], simLinks: WorkerLink[]): ReturnType<typeof forceSimulation> {
  // Rewrite links to reference SimNode objects by id — d3 needs this
  const d3Links = simLinks.map(l => ({ source: l.source, target: l.target }))

  const sim = forceSimulation(simNodes, 3)
    // Stop immediately — we drive the tick loop manually via setInterval
    .stop()
    .force('center', forceCenter(0, 0, 0))
    .force('charge', forceManyBody().strength(-90).distanceMax(150))
    .force('link',   forceLink(d3Links).id((d: any) => d.id).distance(28).strength(0.45))
    .alpha(0.8)
    .alphaDecay(0.018)
    .velocityDecay(0.32)

  return sim
}

// ── Emit tick positions to main thread ────────────────────────────────────────
// World position = sectorOffset + localSimPos.
// Buffer is transferred (zero-copy); reset immediately after.
function emitTick(): void {
  if (allNodes.length === 0) return

  const n = allNodes.length
  if (positions.length !== n * 3) positions = new Float32Array(n * 3)

  for (let i = 0; i < n; i++) {
    const entry = nodeWorldIndex.get(allNodes[i].id)
    if (!entry) {
      positions[i * 3]     = 0
      positions[i * 3 + 1] = 0
      positions[i * 3 + 2] = 0
      continue
    }
    const { node, world } = entry
    const [ox, oy, oz] = world.sectorOffset
    positions[i * 3]     = node.x + ox
    positions[i * 3 + 1] = node.y + oy
    positions[i * 3 + 2] = node.z + oz
  }

  const buf = positions.buffer
  ;(self as any).postMessage(
    { type: 'tick', positions, count: n },
    [buf],
  )
  // Reset after transfer — ArrayBuffer is detached; re-allocate next frame
  positions = new Float32Array(0)
}

// ── Emit cluster sector centers to main thread ─────────────────────────────────
function emitClusters(): void {
  const sectors: Array<{ compId: string; cx: number; cy: number; cz: number }> = []
  for (const [compId, world] of worlds) {
    const [cx, cy, cz] = world.sectorOffset
    sectors.push({ compId, cx, cy, cz })
  }
  ;(self as any).postMessage({ type: 'clusters', sectors })
}

// ── Manual tick loop ──────────────────────────────────────────────────────────
// 16 ms ≈ 60 fps. Each frame we advance every active sim by one tick,
// then emit a combined positions frame.
function startTickLoop(): void {
  if (tickInterval !== null) return
  tickInterval = setInterval(() => {
    let anyActive = false
    for (const world of worlds.values()) {
      const { sim } = world
      if (sim.alpha() > sim.alphaMin()) {
        sim.tick()
        anyActive = true
      }
    }
    // Always emit — even when cooling — so the scene stays up to date
    if (allNodes.length > 0) emitTick()
    // Once fully settled, stop polling (saves CPU)
    if (!anyActive) {
      clearInterval(tickInterval!)
      tickInterval = null
    }
  }, 16)
}

// ── Full reset ─────────────────────────────────────────────────────────────────
function resetWorld(): void {
  if (tickInterval !== null) { clearInterval(tickInterval); tickInterval = null }
  for (const w of worlds.values()) w.sim.stop()
  worlds.clear()
  allNodes = []
  nodeWorldIndex = new Map()
  sectorAssignment.clear()
  sectorIdx = 0
  positions = new Float32Array(0)
  hadGroupsLastUpdate = false
  lastLoggedSig = ''
}

// ── Message handler ────────────────────────────────────────────────────────────
self.addEventListener('message', (e: MessageEvent<InMsg>) => {
  const msg = e.data

  if (msg.type === 'update') {
    const inNodes      = msg.nodes
    const inLinks      = msg.links
    const nodeGroupIds = msg.nodeGroupIds

    if (inNodes.length === 0) {
      resetWorld()
      return
    }

    const hasGroups = !!nodeGroupIds && Object.keys(nodeGroupIds).length > 0

    // ── Determine component assignment ────────────────────────────────────────
    // When Blue Team provides explicit group ids, use those as compIds so
    // logically separate fraud graphs land in different world sectors even if
    // topologically connected in the raw transaction graph.
    let compOf: Map<string, string>
    if (hasGroups) {
      compOf = new Map(inNodes.map(n => [n.id, nodeGroupIds![n.id] ?? n.id]))
    } else {
      compOf = detectComponents(inNodes.map(n => n.id), inLinks)
    }

    // Cross-component links are entirely excluded — no inter-cluster spring forces
    const intraLinks = inLinks.filter(l => compOf.get(l.source) === compOf.get(l.target))

    // Detect group→BFS transition: must rebuild from scratch to re-seed positions
    const groupsJustArrived = hasGroups && !hadGroupsLastUpdate
    hadGroupsLastUpdate = hasGroups

    if (groupsJustArrived) {
      // Tear down all existing worlds; re-create with new sector assignments
      if (tickInterval !== null) { clearInterval(tickInterval); tickInterval = null }
      for (const w of worlds.values()) w.sim.stop()
      worlds.clear()
      sectorAssignment.clear()
      sectorIdx = 0
    }

    // ── Snapshot existing sim-node positions ──────────────────────────────────
    // Used to carry settled positions across incremental updates
    const prevPos = new Map<string, [number, number, number]>()
    for (const [, w] of worlds) {
      for (const sn of w.simNodes) {
        prevPos.set(sn.id, [sn.x, sn.y, sn.z])
      }
    }

    // ── Rebuild per-component worlds ──────────────────────────────────────────
    // Group inNodes by compId
    const compNodeIds = new Map<string, string[]>()
    for (const n of inNodes) {
      const cid = compOf.get(n.id)!
      let arr = compNodeIds.get(cid)
      if (!arr) { arr = []; compNodeIds.set(cid, arr) }
      arr.push(n.id)
    }

    const newWorlds = new Map<string, CompWorld>()
    const newIndex  = new Map<string, { node: SimNode; world: CompWorld }>()

    for (const [compId, nodeIds] of compNodeIds) {
      const secIdx = getOrAssignSectorIndex(compId)
      const offset = sectorOffset(secIdx)

      // Build local-frame simNodes
      const simNodes: SimNode[] = nodeIds.map(id => {
        const prev = prevPos.get(id)
        if (prev && !groupsJustArrived) {
          // Carry settled local position (world coords → subtract offset for local)
          return { id, x: prev[0], y: prev[1], z: prev[2], vx: 0, vy: 0, vz: 0 }
        }
        // New node or group transition: seed near origin of local frame
        const r     = 30 + Math.random() * 25
        const phi   = Math.acos(2 * Math.random() - 1)
        const theta = Math.random() * Math.PI * 2
        return {
          id,
          x: r * Math.sin(phi) * Math.cos(theta),
          y: r * Math.sin(phi) * Math.sin(theta),
          z: r * Math.cos(phi),
          vx: 0, vy: 0, vz: 0,
        }
      })

      // Filter links to only those within this component
      const compLinkSet = new Set(nodeIds)
      const compLinks = intraLinks.filter(
        l => compLinkSet.has(l.source) && compLinkSet.has(l.target),
      )

      let world: CompWorld
      const existing = worlds.get(compId)

      if (existing && !groupsJustArrived) {
        // Update existing world in-place: mutate simNodes array, re-register with d3
        existing.simNodes.length = 0
        for (const sn of simNodes) existing.simNodes.push(sn)

        existing.sim.nodes(existing.simNodes)
        // Calling .nodes() resets d3's internal n count — must .stop() again
        existing.sim.stop()

        const lf = existing.sim.force('link') as any
        if (lf) {
          const d3Links = compLinks.map(l => ({ source: l.source, target: l.target }))
          lf.links(d3Links)
        }
        existing.sim.alpha(0.6)
        world = existing
      } else {
        // Create a fresh world for this component
        const sim = buildSim(simNodes, compLinks)
        world = { compId, sectorOffset: offset, sim, simNodes }
      }

      newWorlds.set(compId, world)

      // Register nodes in the new index
      for (const sn of world.simNodes) {
        newIndex.set(sn.id, { node: sn, world })
      }
    }

    // Stop sims for components that no longer exist
    for (const [oldId, oldWorld] of worlds) {
      if (!newWorlds.has(oldId)) oldWorld.sim.stop()
    }

    worlds.clear()
    for (const [k, v] of newWorlds) worlds.set(k, v)

    // Rebuild the flat ordered allNodes list (must match main-thread ordering)
    allNodes = inNodes
    nodeWorldIndex = newIndex

    // Reheat all active sims
    for (const w of worlds.values()) {
      if (w.sim.alpha() < 0.4) w.sim.alpha(groupsJustArrived ? 0.9 : 0.6)
    }

    // Start (or resume) the manual tick loop
    startTickLoop()

    // Emit updated cluster metadata for camera auto-framing
    emitClusters()

    // Debug: log sector assignments whenever the cluster set changes so the
    // user can verify in DevTools that the worker is producing distinct
    // sectors for each component. Keep noise low — only log on changes.
    const sig = [...worlds.entries()]
      .map(([cid, w]) => `${cid}@(${w.sectorOffset.join(',')})`)
      .sort()
      .join(' | ')
    if (sig !== lastLoggedSig) {
      lastLoggedSig = sig
      // eslint-disable-next-line no-console
      console.log(`[graphWorld] ${worlds.size} sector(s): ${sig}`)
    }

  } else if (msg.type === 'heat') {
    for (const w of worlds.values()) w.sim.alpha(msg.value)
    startTickLoop()
  }
})

export {}
