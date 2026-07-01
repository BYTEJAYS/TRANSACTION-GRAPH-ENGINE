// ──────────────────────────────────────────────────────────────────────────────
// riskPropagation — TGIE unified graph-intelligence state layer.
//
// THE single source of truth for per-node risk. Cluster risk and NODE risk are
// deliberately different quantities:
//   • clusterRisk    — overall severity of the whole fraud cluster (verdict).
//   • propagatedRisk  — this account's OWN exposure score, unique per node.
//
// Every node gets a genuinely computed score from:
//   1.  graph distance to the cluster's fraud origin   (decayed inheritance)
//   2.  transaction frequency / velocity
//   3.  fan-out behavior
//   4.  fan-in behavior
//   5.  circular-transaction (cycle) participation
//   6.  centrality (degree)
//   7.  amount / value anomaly  (population z-score)
//   8.  pass-through symmetry   (relay signature)
//   9.  payment-rail diversity  (mixed-rail laundering)
//  10.  multi-hop inherited exposure
//
// No random values, no flat copy of the cluster score.
// ──────────────────────────────────────────────────────────────────────────────
import type { GraphData, GraphNode, GraphLink, GraphComponentResult } from '../types'

// Flip to false to silence the per-node computation log.
const DEBUG_RISK = true

export type ExposureLevel = 'origin' | 'direct' | 'secondary' | 'peripheral' | 'none'
export type SuspicionDegree = 'CRITICAL' | 'HIGH' | 'MODERATE' | 'LOW' | 'MINIMAL'
// Semantic fraud role — what this account DOES in the network topology.
export type NodeRole =
  | 'origin'      // fraud hub / cluster anchor
  | 'hub'         // high-degree distributor
  | 'bridge'      // articulation point linking sub-structures (critical)
  | 'mule'        // pass-through relay (in ≈ out)
  | 'relay'       // chain link / loop participant
  | 'sink'        // terminal / cashout (in, no out)
  | 'source'      // funding source (out, no in)
  | 'peripheral'  // low-degree fringe of a fraud cluster
  | 'normal'      // unremarkable account

export interface NodeIntel {
  nodeId:            string
  clusterId:         string | null
  clusterFlagged:    boolean
  clusterRisk:       number          // 0..1 — cluster verdict severity
  localRisk:         number          // 0..1 — backend per-node score (may be 0)
  behaviorScore:     number          // 0..1 — topology/behavior model output
  propagatedRisk:    number          // 0..1 — FINAL node risk (what surfaces show)
  exposure:          ExposureLevel
  hop:               number          // hops to the cluster fraud origin (-1 if none)
  suspicion:         SuspicionDegree
  role:              NodeRole
  isBridge:          boolean
  transactionCount:  number
  degree:            number
  outDeg:            number
  inDeg:             number
}

export function roleLabel(r: NodeRole): string {
  switch (r) {
    case 'origin':     return 'Fraud Origin'
    case 'hub':        return 'Distribution Hub'
    case 'bridge':     return 'Bridge Account'
    case 'mule':       return 'Mule / Relay'
    case 'relay':      return 'Chain Relay'
    case 'sink':       return 'Sink / Cashout'
    case 'source':     return 'Funding Source'
    case 'peripheral': return 'Peripheral'
    default:           return 'Account'
  }
}

export interface RiskIntel {
  byNode:           Map<string, NodeIntel>
  flaggedCount:     number
  activeSuspicious: number
  meanRisk:         number
  maxRisk:          number
}

export const HIGH_THRESHOLD     = 0.6
export const MODERATE_THRESHOLD = 0.35
const DECAY = 0.62   // per-hop inheritance multiplier

function bandFor(hop: number): { min: number; max: number } {
  if (hop <= 0) return { min: 0.80, max: 0.97 }
  if (hop === 1) return { min: 0.45, max: 0.74 }
  if (hop === 2) return { min: 0.25, max: 0.52 }
  if (hop === 3) return { min: 0.14, max: 0.34 }
  return { min: 0.08, max: 0.22 }
}
function exposureFor(hop: number): ExposureLevel {
  if (hop < 0) return 'none'
  if (hop === 0) return 'origin'
  if (hop === 1) return 'direct'
  if (hop === 2) return 'secondary'
  return 'peripheral'
}
function suspicionFor(r: number): SuspicionDegree {
  if (r >= 0.8)  return 'CRITICAL'
  if (r >= 0.6)  return 'HIGH'
  if (r >= 0.35) return 'MODERATE'
  if (r >= 0.15) return 'LOW'
  return 'MINIMAL'
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))
const sigmoid = (z: number) => 1 / (1 + Math.exp(-z))
const idOf = (x: string | GraphNode) => (typeof x === 'string' ? x : x.id)

// ── Behavioral feature model ─────────────────────────────────────────────────────
interface FeatureSpec { key: string; weight: number; get: (id: string, F: Features) => number }
interface Features {
  outDeg: Map<string, number>; inDeg: Map<string, number>
  amtOut: Map<string, number>; amtIn: Map<string, number>
  txns:   Map<string, number>; rails: Map<string, Set<string>>
  cycle:  Set<string>
}

const FEATURES: FeatureSpec[] = [
  { key: 'spread',      weight: 0.95, get: (id, F) => (F.outDeg.get(id) ?? 0) / ((F.inDeg.get(id) ?? 0) + 1) },
  { key: 'fanOut',      weight: 0.45, get: (id, F) => F.outDeg.get(id) ?? 0 },
  { key: 'fanIn',       weight: 0.40, get: (id, F) => F.inDeg.get(id) ?? 0 },
  { key: 'degree',      weight: 0.55, get: (id, F) => (F.outDeg.get(id) ?? 0) + (F.inDeg.get(id) ?? 0) },
  { key: 'velocity',    weight: 0.60, get: (id, F) => ((F.amtIn.get(id) ?? 0) + (F.amtOut.get(id) ?? 0)) / ((F.txns.get(id) ?? 0) + 1) },
  { key: 'volume',      weight: 0.40, get: (id, F) => (F.amtIn.get(id) ?? 0) + (F.amtOut.get(id) ?? 0) },
  { key: 'passthrough', weight: 0.80, get: (id, F) => passThrough(F.amtIn.get(id) ?? 0, F.amtOut.get(id) ?? 0) },
  { key: 'railMix',     weight: 0.50, get: (id, F) => F.rails.get(id)?.size ?? 0 },
]
const CYCLE_WEIGHT = 0.75
const BIAS = -0.55

function passThrough(inAmt: number, outAmt: number): number {
  if (inAmt <= 0 || outAmt <= 0) return 0
  return 1 - Math.abs(inAmt - outAmt) / Math.max(inAmt, outAmt)
}

// ── Engine ───────────────────────────────────────────────────────────────────────
export function computeRiskIntel(
  data: GraphData,
  components: GraphComponentResult[],
  fraudNodeIds?: ReadonlySet<string>,
): RiskIntel {
  const byNode = new Map<string, NodeIntel>()
  if (data.nodes.length === 0) {
    return { byNode, flaggedCount: 0, activeSuspicious: 0, meanRisk: 0, maxRisk: 0 }
  }

  // Directed + undirected structure, amounts, rails.
  const ids = data.nodes.map(n => n.id)
  const byId = new Map<string, GraphNode>(data.nodes.map(n => [n.id, n]))
  const undirected = new Map<string, Set<string>>()
  const outAdj = new Map<string, Set<string>>()
  const F: Features = {
    outDeg: new Map(), inDeg: new Map(), amtOut: new Map(), amtIn: new Map(),
    txns: new Map(), rails: new Map(), cycle: new Set(),
  }
  for (const id of ids) { undirected.set(id, new Set()); outAdj.set(id, new Set()) }
  for (const n of data.nodes) F.txns.set(n.id, n.transaction_count ?? 0)

  for (const l of data.links as GraphLink[]) {
    const s = idOf(l.source), t = idOf(l.target)
    if (!byId.has(s) || !byId.has(t)) continue
    undirected.get(s)!.add(t); undirected.get(t)!.add(s)
    outAdj.get(s)!.add(t)
    F.outDeg.set(s, (F.outDeg.get(s) ?? 0) + 1)
    F.inDeg.set(t, (F.inDeg.get(t) ?? 0) + 1)
    F.amtOut.set(s, (F.amtOut.get(s) ?? 0) + (l.amount ?? 0))
    F.amtIn.set(t, (F.amtIn.get(t) ?? 0) + (l.amount ?? 0))
    if (l.payment_rail) {
      ;(F.rails.get(s) ?? F.rails.set(s, new Set()).get(s)!).add(l.payment_rail)
      ;(F.rails.get(t) ?? F.rails.set(t, new Set()).get(t)!).add(l.payment_rail)
    }
  }
  // Fallback to intrinsic node fields when no edges carry the data.
  for (const n of data.nodes) {
    if (!F.outDeg.has(n.id) && n.outgoing_count) F.outDeg.set(n.id, n.outgoing_count)
    if (!F.inDeg.has(n.id)  && n.incoming_count) F.inDeg.set(n.id, n.incoming_count)
    if (!F.amtOut.has(n.id) && n.total_sent)     F.amtOut.set(n.id, n.total_sent)
    if (!F.amtIn.has(n.id)  && n.total_received)  F.amtIn.set(n.id, n.total_received)
  }
  F.cycle = findCycleMembers(outAdj, ids, 5)

  const degreeOf = (id: string) => undirected.get(id)?.size ?? 0

  // Standardize features → per-node behavioral score (logistic).
  const stats: Record<string, { mean: number; std: number }> = {}
  for (const f of FEATURES) {
    const vals = ids.map(id => f.get(id, F))
    const mean = vals.reduce((a, b) => a + b, 0) / vals.length
    const variance = vals.reduce((a, b) => a + (b - mean) ** 2, 0) / vals.length
    stats[f.key] = { mean, std: Math.sqrt(variance) || 1 }
  }
  const behaviorOf = new Map<string, number>()
  for (const id of ids) {
    let logit = BIAS
    for (const f of FEATURES) {
      const z = (f.get(id, F) - stats[f.key].mean) / stats[f.key].std
      logit += f.weight * z
    }
    if (F.cycle.has(id)) logit += CYCLE_WEIGHT
    behaviorOf.set(id, sigmoid(logit))
  }

  // Cluster lookups.
  const clusterOf = new Map<string, string>()
  const clusterMeta = new Map<string, { risk: number; flagged: boolean; nodes: string[] }>()
  for (const c of components) {
    clusterMeta.set(c.graph_id, { risk: c.risk_score ?? 0, flagged: c.flagged, nodes: c.nodes })
    for (const nid of c.nodes) clusterOf.set(nid, c.graph_id)
  }

  // ── ONE topological fraud origin per flagged cluster ──────────────────────────
  // (Seeding from EVERY flagged node is what flattened all scores to the cluster
  // value. The origin is the single most central / behaviorally suspicious node;
  // distance from it produces a real gradient.)
  const seeds = new Set<string>()
  for (const c of components) {
    if (!c.flagged || !c.nodes.length) continue
    const rank = (nid: string) => degreeOf(nid) * 1.0 + (behaviorOf.get(nid) ?? 0) * 2.0
                                  + ((fraudNodeIds?.has(nid) || (c.flagged_nodes ?? []).includes(nid)) ? 0.5 : 0)
    let origin = c.nodes[0]
    for (const nid of c.nodes) if (rank(nid) > rank(origin)) origin = nid
    seeds.add(origin)
  }

  // Multi-source BFS — hop distance from the nearest cluster origin.
  const hop = new Map<string, number>()
  const queue: string[] = []
  for (const s of seeds) { hop.set(s, 0); queue.push(s) }
  let head = 0
  while (head < queue.length) {
    const cur = queue[head++]
    const d = hop.get(cur)!
    for (const nb of undirected.get(cur) ?? []) {
      if (!hop.has(nb)) { hop.set(nb, d + 1); queue.push(nb) }
    }
  }

  const bridges = findArticulationPoints(undirected, ids)

  // ── Compose final per-node risk ────────────────────────────────────────────────
  let sum = 0, max = 0, flaggedCount = 0, activeSuspicious = 0
  for (const node of data.nodes) {
    const cid = clusterOf.get(node.id) ?? null
    const meta = cid ? clusterMeta.get(cid) : undefined
    const clusterFlagged = meta?.flagged ?? false
    const clusterRisk = meta?.risk ?? 0
    const localRisk = clamp(node.risk_score ?? 0, 0, 1)
    const behavior = behaviorOf.get(node.id) ?? 0
    const degree = degreeOf(node.id)
    // Inside a flagged cluster every node is reachable from its origin; guard anyway.
    const h = clusterFlagged ? (hop.has(node.id) ? hop.get(node.id)! : 4) : (hop.get(node.id) ?? -1)

    let propagated: number
    let exposure: ExposureLevel
    if (clusterFlagged) {
      const band = bandFor(h)
      const inherited = clamp(clusterRisk * Math.pow(DECAY, h), band.min, band.max)
      const cycleBoost = F.cycle.has(node.id) ? 0.05 : 0
      // Weighted blend: proximity + own behavior + backend signal. Unique per node.
      propagated = clamp(0.50 * inherited + 0.35 * behavior + 0.15 * localRisk + cycleBoost, 0, 0.99)
      exposure = exposureFor(h)
    } else {
      // Not in a fraud cluster — risk is the node's own. Behavior only lifts a
      // genuine outlier above its backend score; clean nodes stay near zero.
      propagated = clamp(localRisk + Math.max(0, behavior - 0.55) * 0.5, 0, 0.99)
      exposure = 'none'
    }

    if (propagated >= HIGH_THRESHOLD) flaggedCount++
    if (propagated >= MODERATE_THRESHOLD) activeSuspicious++
    sum += propagated
    if (propagated > max) max = propagated

    // ── Semantic role — what this account does in the topology ──────────────────
    const outDeg = F.outDeg.get(node.id) ?? 0
    const inDeg  = F.inDeg.get(node.id) ?? 0
    // A node counts as a true bridge only if it's an articulation point AND a
    // genuine multi-way connector (degree ≥ 3) — otherwise every internal node
    // of a relay chain (also an articulation point) would falsely read "bridge".
    const isBridge = bridges.has(node.id) && degree >= 3
    const pt = passThrough(F.amtIn.get(node.id) ?? 0, F.amtOut.get(node.id) ?? 0)
    let role: NodeRole
    if (seeds.has(node.id))                              role = 'origin'
    else if (inDeg > 0 && outDeg === 0)                  role = 'sink'
    else if (outDeg > 0 && inDeg === 0)                  role = 'source'
    else if (degree >= 5)                                role = 'hub'
    else if (isBridge)                                   role = 'bridge'
    else if (F.cycle.has(node.id))                       role = 'relay'   // loop link
    else if (inDeg === 1 && outDeg === 1)                role = 'relay'   // chain link
    else if (inDeg >= 1 && outDeg >= 1 && pt > 0.6)      role = 'mule'    // branching pass-through
    else if (clusterFlagged && (exposure === 'peripheral' || exposure === 'secondary')) role = 'peripheral'
    else                                                 role = 'normal'

    byNode.set(node.id, {
      nodeId: node.id, clusterId: cid, clusterFlagged, clusterRisk,
      localRisk, behaviorScore: behavior, propagatedRisk: propagated,
      exposure, hop: h, suspicion: suspicionFor(propagated),
      role, isBridge,
      transactionCount: node.transaction_count ?? 0, degree, outDeg, inDeg,
    })
  }

  if (DEBUG_RISK) logRiskTable(byNode, seeds)

  return { byNode, flaggedCount, activeSuspicious, meanRisk: sum / data.nodes.length, maxRisk: max }
}

// ── Bridge detection — articulation points (iterative Tarjan, undirected) ─────────
// A bridge account is one whose removal would split its sub-network: the critical
// connector between laundering layers. These vanish in a plain force layout, so
// we surface them explicitly.
function findArticulationPoints(adj: Map<string, Set<string>>, ids: string[]): Set<string> {
  const ap = new Set<string>()
  const disc = new Map<string, number>()
  const low = new Map<string, number>()
  let timer = 0
  for (const start of ids) {
    if (disc.has(start)) continue
    const stack: Array<{ u: string; parent: string | null; it: Iterator<string>; children: number }> = []
    disc.set(start, timer); low.set(start, timer); timer++
    stack.push({ u: start, parent: null, it: (adj.get(start) ?? new Set()).values(), children: 0 })
    while (stack.length) {
      const top = stack[stack.length - 1]
      const nx = top.it.next()
      if (!nx.done) {
        const v = nx.value
        if (!disc.has(v)) {
          top.children++
          disc.set(v, timer); low.set(v, timer); timer++
          stack.push({ u: v, parent: top.u, it: (adj.get(v) ?? new Set()).values(), children: 0 })
        } else if (v !== top.parent) {
          low.set(top.u, Math.min(low.get(top.u)!, disc.get(v)!))
        }
      } else {
        stack.pop()
        const parent = stack[stack.length - 1]
        if (parent) {
          low.set(parent.u, Math.min(low.get(parent.u)!, low.get(top.u)!))
          if (parent.parent !== null && low.get(top.u)! >= disc.get(parent.u)!) ap.add(parent.u)
        }
        if (top.parent === null && top.children > 1) ap.add(top.u)
      }
    }
  }
  return ap
}

// ── Cycle detection — nodes participating in any directed cycle up to maxLen ──────
function findCycleMembers(outAdj: Map<string, Set<string>>, ids: string[], maxLen: number): Set<string> {
  const members = new Set<string>()
  for (const start of ids) {
    const path: string[] = [start]
    const onPath = new Set([start])
    const walk = (cur: string) => {
      if (path.length > maxLen) return
      for (const nb of outAdj.get(cur) ?? []) {
        if (nb === start && path.length >= 2) { for (const p of path) members.add(p); continue }
        if (onPath.has(nb) || nb < start) continue   // canonical: start is min id
        path.push(nb); onPath.add(nb); walk(nb); path.pop(); onPath.delete(nb)
      }
    }
    walk(start)
  }
  return members
}

// ── Temporary debug logging (set DEBUG_RISK=false to silence) ─────────────────────
let _lastSig = ''
function logRiskTable(byNode: Map<string, NodeIntel>, seeds: Set<string>) {
  const sig = [...byNode.keys()].join(',') + '|' + [...seeds].join(',')
  if (sig === _lastSig) return
  _lastSig = sig
  const rows = [...byNode.values()].map(i => ({
    node: i.nodeId,
    'node risk %': Math.round(i.propagatedRisk * 100),
    'cluster risk %': Math.round(i.clusterRisk * 100),
    role: i.role, bridge: i.isBridge ? 'YES' : '',
    behavior: Math.round(i.behaviorScore * 100),
    hop: i.hop, exposure: i.exposure, suspicion: i.suspicion,
    cluster: i.clusterId ?? '—', origin: seeds.has(i.nodeId) ? '★' : '',
  }))
  console.groupCollapsed(`%c[TGIE risk engine] ${rows.length} nodes · origins: ${[...seeds].join(', ') || 'none'}`, 'color:#4493f8;font-weight:600')
  console.table(rows)
  console.groupEnd()
}

// ── UI / narration helpers ────────────────────────────────────────────────────────
export function exposureLabel(e: ExposureLevel): string {
  switch (e) {
    case 'origin':     return 'Fraud Origin'
    case 'direct':     return 'Direct Exposure'
    case 'secondary':  return 'Secondary Exposure'
    case 'peripheral': return 'Peripheral'
    default:           return 'None'
  }
}

export function exposureNarration(intel: NodeIntel): string | null {
  if (!intel.clusterFlagged || intel.exposure === 'none') return null
  const node = Math.round(intel.propagatedRisk * 100)
  const cluster = Math.round(intel.clusterRisk * 100)
  switch (intel.exposure) {
    case 'origin':
      return `This account is the fraud origin of cluster ${intel.clusterId}, scoring ${node} percent against a ${cluster} percent cluster severity.`
    case 'direct':
      return `This node carries ${node} percent risk — direct inherited exposure from the fraud hub in cluster ${intel.clusterId}, which scores ${cluster} percent overall.`
    case 'secondary':
      return `This node has moderate inherited exposure, ${node} percent, sitting two hops from the origin of high-risk cluster ${intel.clusterId}.`
    default:
      return `This node has low residual exposure, ${node} percent, on the periphery of fraud cluster ${intel.clusterId}.`
  }
}
