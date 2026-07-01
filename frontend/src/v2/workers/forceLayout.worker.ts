/// <reference lib="webworker" />
/**
 * FORCE LAYOUT WORKER (v2) — Delegates to the shared multi-simulation architecture.
 *
 * This file is intentionally a thin re-export of the graphWorld.worker logic,
 * rewritten inline so Vite can tree-shake and inline it independently.
 * The message protocol is identical to graphWorld.worker.ts:
 *
 *   Inputs:  { type: 'update', nodes, links, nodeGroupIds? }
 *            { type: 'heat', value }
 *   Outputs: { type: 'tick', positions: Float32Array, count }
 *            { type: 'clusters', sectors: [{compId, cx, cy, cz}] }
 *
 * See graphWorld.worker.ts for the architectural rationale.
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
const SECTOR_D = 800

const PRESET_SECTORS: ReadonlyArray<[number, number, number]> = [
  [          0,          0,   0],
  [  SECTOR_D,          0,   0],
  [ -SECTOR_D,          0,   0],
  [          0,  SECTOR_D,   0],
  [          0, -SECTOR_D,   0],
  [  SECTOR_D,  SECTOR_D,  40],
  [ -SECTOR_D,  SECTOR_D, -40],
  [  SECTOR_D, -SECTOR_D, -40],
  [ -SECTOR_D, -SECTOR_D,  40],
]

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
  const ga = 2.399911
  const t  = ga * (i - PRESET_SECTORS.length)
  const r  = SECTOR_D * (1.6 + (i - PRESET_SECTORS.length) * 0.3)
  return [r * Math.cos(t), r * Math.sin(t), 0]
}

// ── Worker state ───────────────────────────────────────────────────────────────
const worlds = new Map<string, CompWorld>()
let allNodes: WorkerNode[] = []
let nodeWorldIndex = new Map<string, { node: SimNode; world: CompWorld }>()
let hadGroupsLastUpdate = false
let positions = new Float32Array(0)
let tickInterval: ReturnType<typeof setInterval> | null = null

// ── Build simulation ──────────────────────────────────────────────────────────
function buildSim(simNodes: SimNode[], simLinks: WorkerLink[]): ReturnType<typeof forceSimulation> {
  const d3Links = simLinks.map(l => ({ source: l.source, target: l.target }))
  return forceSimulation(simNodes, 3)
    .stop()
    .force('center', forceCenter(0, 0, 0))
    .force('charge', forceManyBody().strength(-90).distanceMax(150))
    .force('link',   forceLink(d3Links).id((d: any) => d.id).distance(28).strength(0.45))
    .alpha(0.8)
    .alphaDecay(0.018)
    .velocityDecay(0.32)
}

// ── Emit helpers ───────────────────────────────────────────────────────────────
function emitTick(): void {
  if (allNodes.length === 0) return
  const n = allNodes.length
  if (positions.length !== n * 3) positions = new Float32Array(n * 3)

  for (let i = 0; i < n; i++) {
    const entry = nodeWorldIndex.get(allNodes[i].id)
    if (!entry) {
      positions[i * 3] = positions[i * 3 + 1] = positions[i * 3 + 2] = 0
      continue
    }
    const { node, world } = entry
    const [ox, oy, oz] = world.sectorOffset
    positions[i * 3]     = node.x + ox
    positions[i * 3 + 1] = node.y + oy
    positions[i * 3 + 2] = node.z + oz
  }

  const buf = positions.buffer
  ;(self as any).postMessage({ type: 'tick', positions, count: n }, [buf])
  positions = new Float32Array(0)
}

function emitClusters(): void {
  const sectors: Array<{ compId: string; cx: number; cy: number; cz: number }> = []
  for (const [compId, world] of worlds) {
    const [cx, cy, cz] = world.sectorOffset
    sectors.push({ compId, cx, cy, cz })
  }
  ;(self as any).postMessage({ type: 'clusters', sectors })
}

// ── Manual tick loop ──────────────────────────────────────────────────────────
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
    if (allNodes.length > 0) emitTick()
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

    let compOf: Map<string, string>
    if (hasGroups) {
      compOf = new Map(inNodes.map(n => [n.id, nodeGroupIds![n.id] ?? n.id]))
    } else {
      compOf = detectComponents(inNodes.map(n => n.id), inLinks)
    }

    // Exclude cross-component links entirely
    const intraLinks = inLinks.filter(l => compOf.get(l.source) === compOf.get(l.target))

    const groupsJustArrived = hasGroups && !hadGroupsLastUpdate
    hadGroupsLastUpdate = hasGroups

    if (groupsJustArrived) {
      if (tickInterval !== null) { clearInterval(tickInterval); tickInterval = null }
      for (const w of worlds.values()) w.sim.stop()
      worlds.clear()
      sectorAssignment.clear()
      sectorIdx = 0
    }

    const prevPos = new Map<string, [number, number, number]>()
    for (const w of worlds.values()) {
      for (const sn of w.simNodes) prevPos.set(sn.id, [sn.x, sn.y, sn.z])
    }

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

      const simNodes: SimNode[] = nodeIds.map(id => {
        const prev = prevPos.get(id)
        if (prev && !groupsJustArrived) {
          return { id, x: prev[0], y: prev[1], z: prev[2], vx: 0, vy: 0, vz: 0 }
        }
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

      const compLinkSet = new Set(nodeIds)
      const compLinks = intraLinks.filter(
        l => compLinkSet.has(l.source) && compLinkSet.has(l.target),
      )

      let world: CompWorld
      const existing = worlds.get(compId)

      if (existing && !groupsJustArrived) {
        existing.simNodes.length = 0
        for (const sn of simNodes) existing.simNodes.push(sn)
        existing.sim.nodes(existing.simNodes)
        existing.sim.stop()
        const lf = existing.sim.force('link') as any
        if (lf) lf.links(compLinks.map(l => ({ source: l.source, target: l.target })))
        existing.sim.alpha(0.6)
        world = existing
      } else {
        const sim = buildSim(simNodes, compLinks)
        world = { compId, sectorOffset: offset, sim, simNodes }
      }

      newWorlds.set(compId, world)
      for (const sn of world.simNodes) newIndex.set(sn.id, { node: sn, world })
    }

    for (const [oldId, oldWorld] of worlds) {
      if (!newWorlds.has(oldId)) oldWorld.sim.stop()
    }

    worlds.clear()
    for (const [k, v] of newWorlds) worlds.set(k, v)

    allNodes = inNodes
    nodeWorldIndex = newIndex

    for (const w of worlds.values()) {
      if (w.sim.alpha() < 0.4) w.sim.alpha(groupsJustArrived ? 0.9 : 0.6)
    }

    startTickLoop()
    emitClusters()

  } else if (msg.type === 'heat') {
    for (const w of worlds.values()) w.sim.alpha(msg.value)
    startTickLoop()
  }
})

export {}
