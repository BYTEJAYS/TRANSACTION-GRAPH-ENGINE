// ──────────────────────────────────────────────────────────────────────────────
// graphAnalysis — TGIE topology intelligence engine.
//
// Pure, dependency-free functions that compute REAL graph topology metrics
// from live transaction data and turn them into investigation-grade narration.
//
// Nothing here is hardcoded or random — every sentence UB speaks is derived
// from the actual structure of the graph in front of the analyst.
// ──────────────────────────────────────────────────────────────────────────────
import type { GraphData, GraphNode, GraphLink } from '../types'
import { explainNodeRisk } from './riskModel'
import { exposureNarration, type NodeIntel } from './riskPropagation'

// ── Adjacency helpers ──────────────────────────────────────────────────────────
function idOf(x: string | GraphNode): string {
  return typeof x === 'string' ? x : x.id
}

interface Adjacency {
  nodes:    GraphNode[]
  byId:     Map<string, GraphNode>
  out:      Map<string, string[]>   // node → downstream targets
  in:       Map<string, string[]>   // node → upstream sources
  amountOut: Map<string, number>    // total value leaving a node (edge sum)
  amountIn:  Map<string, number>    // total value entering a node
  links:    GraphLink[]
}

function buildAdjacency(data: GraphData): Adjacency {
  const byId = new Map<string, GraphNode>()
  for (const n of data.nodes) byId.set(n.id, n)

  const out = new Map<string, string[]>()
  const inn = new Map<string, string[]>()
  const amountOut = new Map<string, number>()
  const amountIn  = new Map<string, number>()

  for (const l of data.links) {
    const s = idOf(l.source)
    const t = idOf(l.target)
    if (!byId.has(s) || !byId.has(t)) continue
    ;(out.get(s) ?? out.set(s, []).get(s)!).push(t)
    ;(inn.get(t) ?? inn.set(t, []).get(t)!).push(s)
    amountOut.set(s, (amountOut.get(s) ?? 0) + (l.amount ?? 0))
    amountIn.set(t,  (amountIn.get(t)  ?? 0) + (l.amount ?? 0))
  }

  return { nodes: data.nodes, byId, out, in: inn, amountOut, amountIn, links: data.links }
}

// ── Money formatting (mirrors App.fmt) ──────────────────────────────────────────
function money(v: number): string {
  if (v >= 1e7) return `${(v / 1e7).toFixed(1)} crore`
  if (v >= 1e5) return `${(v / 1e5).toFixed(1)} lakh`
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)} thousand`
  return `${Math.round(v)}`
}

function shortId(id: string): string {
  // Account ids are read aloud; trim long prefixes for speech.
  return id.length > 14 ? `…${id.slice(-8)}` : id
}

// ── Result shape ────────────────────────────────────────────────────────────────
export interface AnalysisResult {
  /** Spoken narration — concise, analytical, investigation-oriented. */
  narration: string
  /** Node ids to highlight / focus the camera on, if any. */
  focusNodes: string[]
  /** True when the metric surfaced something genuinely suspicious. */
  flagged: boolean
}

const EMPTY = (msg: string): AnalysisResult => ({ narration: msg, focusNodes: [], flagged: false })

// ── 1. Topology summary ─────────────────────────────────────────────────────────
export function summarizeTopology(data: GraphData): AnalysisResult {
  if (data.nodes.length === 0) return EMPTY('The graph is empty. Submit transactions to begin analysis.')
  const a = buildAdjacency(data)
  const n = a.nodes.length
  const e = a.links.length

  const degrees = a.nodes.map(node =>
    (a.out.get(node.id)?.length ?? 0) + (a.in.get(node.id)?.length ?? 0))
  const avgDeg = degrees.reduce((s, d) => s + d, 0) / Math.max(1, n)
  const maxDeg = Math.max(0, ...degrees)
  const components = countComponents(a)
  const density = n > 1 ? e / (n * (n - 1)) : 0
  const shape =
    density > 0.25 ? 'densely interconnected — consistent with a coordinated network'
    : maxDeg > avgDeg * 3 ? 'hub-and-spoke — funds concentrate through a small number of central accounts'
    : 'distributed — no single dominant routing point'

  return {
    narration:
      `Topology scan complete. ${n} accounts, ${e} transaction edges across ${components} ` +
      `cluster${components !== 1 ? 's' : ''}. Average connectivity ${avgDeg.toFixed(1)} links per account. ` +
      `Structure reads ${shape}.`,
    focusNodes: [],
    flagged: false,
  }
}

function countComponents(a: Adjacency): number {
  const seen = new Set<string>()
  let count = 0
  for (const node of a.nodes) {
    if (seen.has(node.id)) continue
    count++
    const stack = [node.id]
    while (stack.length) {
      const cur = stack.pop()!
      if (seen.has(cur)) continue
      seen.add(cur)
      for (const nb of a.out.get(cur) ?? []) if (!seen.has(nb)) stack.push(nb)
      for (const nb of a.in.get(cur)  ?? []) if (!seen.has(nb)) stack.push(nb)
    }
  }
  return count
}

// ── 2. Fan-out detection ────────────────────────────────────────────────────────
// A fan-out hub sprays funds to many recipients in a short window — a hallmark
// of mule coordination and rapid distribution.
export function analyzeFanOut(data: GraphData): AnalysisResult {
  if (data.nodes.length === 0) return EMPTY('No graph loaded. Nothing to analyze.')
  const a = buildAdjacency(data)

  let best: GraphNode | null = null
  let bestOut = 0
  for (const node of a.nodes) {
    const o = a.out.get(node.id)?.length ?? node.outgoing_count ?? 0
    if (o > bestOut) { bestOut = o; best = node }
  }

  if (!best || bestOut < 3) {
    return EMPTY('No significant fan-out behavior detected. Outbound distribution is within normal bounds.')
  }

  const inDeg = a.in.get(best.id)?.length ?? best.incoming_count ?? 0
  const ratio = bestOut / Math.max(1, inDeg)
  const value = a.amountOut.get(best.id) ?? best.total_sent ?? 0
  const targets = a.out.get(best.id) ?? []

  return {
    narration:
      `High fan-out behavior detected at account ${shortId(best.id)}. ` +
      `It distributes funds across ${bestOut} downstream endpoints` +
      (inDeg > 0 ? `, against just ${inDeg} inbound source${inDeg !== 1 ? 's' : ''} — a ${ratio.toFixed(1)} to one spread ratio.` : '.') +
      ` Approximately ${money(value)} routed outward. ` +
      `This pattern is consistent with mule coordination and rapid fund dispersal.`,
    focusNodes: [best.id, ...targets],
    flagged: ratio >= 2 || bestOut >= 5,
  }
}

// ── 3. Central account (degree centrality) ──────────────────────────────────────
export function findCentralAccount(data: GraphData): AnalysisResult {
  if (data.nodes.length === 0) return EMPTY('No graph loaded.')
  const a = buildAdjacency(data)

  let best: GraphNode | null = null
  let bestDeg = -1
  for (const node of a.nodes) {
    const deg = (a.out.get(node.id)?.length ?? 0) + (a.in.get(node.id)?.length ?? 0)
    if (deg > bestDeg) { bestDeg = deg; best = node }
  }
  if (!best) return EMPTY('Centrality could not be resolved.')

  const through = (a.amountIn.get(best.id) ?? 0) + (a.amountOut.get(best.id) ?? 0)
  return {
    narration:
      `Central account identified: ${shortId(best.id)} with ${bestDeg} total connections — ` +
      `the highest-centrality node in the network. ` +
      `Roughly ${money(through)} in value transits this account. ` +
      `It is the structural keystone; isolating it would fragment the cluster.`,
    focusNodes: [best.id, ...(a.out.get(best.id) ?? []), ...(a.in.get(best.id) ?? [])],
    flagged: best.is_flagged || best.risk_score > 0.6,
  }
}

// ── 4. Circular movement / cycle detection (directed) ───────────────────────────
export function findCircularMovement(data: GraphData): AnalysisResult {
  if (data.nodes.length === 0) return EMPTY('No graph loaded.')
  const a = buildAdjacency(data)
  const cycle = detectCycle(a)

  if (!cycle) {
    return EMPTY('No circular transaction flow detected. Fund movement is acyclic — value does not return to origin.')
  }
  return {
    narration:
      `Circular transaction behavior detected. Funds recycle through a closed loop of ${cycle.length} accounts: ` +
      `${cycle.map(shortId).join(' → ')} → back to origin. ` +
      `Value appears to cycle with minimal decay — a strong indicator of layering or wash activity designed to obscure the source.`,
    focusNodes: cycle,
    flagged: true,
  }
}

// Iterative DFS that returns the first directed cycle found (node-id list).
function detectCycle(a: Adjacency): string[] | null {
  const WHITE = 0, GRAY = 1, BLACK = 2
  const color = new Map<string, number>()
  const parent = new Map<string, string>()
  for (const n of a.nodes) color.set(n.id, WHITE)

  for (const start of a.nodes) {
    if (color.get(start.id) !== WHITE) continue
    const stack: Array<{ id: string; iter: number }> = [{ id: start.id, iter: 0 }]
    color.set(start.id, GRAY)
    while (stack.length) {
      const frame = stack[stack.length - 1]
      const neighbors = a.out.get(frame.id) ?? []
      if (frame.iter < neighbors.length) {
        const next = neighbors[frame.iter++]
        const c = color.get(next)
        if (c === WHITE) {
          color.set(next, GRAY)
          parent.set(next, frame.id)
          stack.push({ id: next, iter: 0 })
        } else if (c === GRAY) {
          // Found a back-edge → reconstruct the cycle.
          const cycle: string[] = [next]
          let cur = frame.id
          while (cur !== next && cur !== undefined) {
            cycle.push(cur)
            cur = parent.get(cur)!
            if (cycle.length > a.nodes.length) break
          }
          return cycle.reverse()
        }
      } else {
        color.set(frame.id, BLACK)
        stack.pop()
      }
    }
  }
  return null
}

// ── 5. Layering chain (longest directed pass-through path) ──────────────────────
export function detectLayering(data: GraphData): AnalysisResult {
  if (data.nodes.length === 0) return EMPTY('No graph loaded.')
  const a = buildAdjacency(data)
  const chain = longestChain(a)

  if (chain.length < 4) {
    return EMPTY('No multi-hop layering chain detected. Transaction depth is shallow — funds reach their destination in few hops.')
  }
  return {
    narration:
      `Multi-hop layering pattern identified. Funds traverse a ${chain.length}-account chain: ` +
      `${chain.map(shortId).join(' → ')}. ` +
      `Each hop adds a layer of separation between source and destination. ` +
      `Transaction depth at this level strongly suggests deliberate laundering behavior.`,
    focusNodes: chain,
    flagged: true,
  }
}

// Longest simple downstream path via memoized DFS (graphs are small, ≤150 nodes).
function longestChain(a: Adjacency): string[] {
  const memo = new Map<string, string[]>()
  const visiting = new Set<string>()

  function dfs(id: string): string[] {
    if (memo.has(id)) return memo.get(id)!
    if (visiting.has(id)) return [id]   // cycle guard
    visiting.add(id)
    let best: string[] = []
    for (const nb of a.out.get(id) ?? []) {
      const sub = dfs(nb)
      if (sub.length > best.length) best = sub
    }
    visiting.delete(id)
    const path = [id, ...best]
    memo.set(id, path)
    return path
  }

  let longest: string[] = []
  for (const n of a.nodes) {
    const p = dfs(n.id)
    if (p.length > longest.length) longest = p
  }
  return longest
}

// ── 6. Mule account detection ────────────────────────────────────────────────────
// Mules are pass-through accounts: they receive funds and forward a similar
// amount almost immediately, retaining little. We score balance symmetry.
export function findMuleAccounts(data: GraphData): AnalysisResult {
  if (data.nodes.length === 0) return EMPTY('No graph loaded.')
  const a = buildAdjacency(data)

  const mules: Array<{ node: GraphNode; score: number }> = []
  for (const node of a.nodes) {
    const inn = a.amountIn.get(node.id) ?? node.total_received ?? 0
    const out = a.amountOut.get(node.id) ?? node.total_sent ?? 0
    const inDeg  = a.in.get(node.id)?.length  ?? node.incoming_count ?? 0
    const outDeg = a.out.get(node.id)?.length ?? node.outgoing_count ?? 0
    if (inn <= 0 || out <= 0 || inDeg === 0 || outDeg === 0) continue
    // Pass-through symmetry: how close out is to in (1 = perfect pass-through).
    const symmetry = 1 - Math.abs(inn - out) / Math.max(inn, out)
    const retention = Math.abs(inn - out) / Math.max(inn, out)
    if (symmetry > 0.78 && retention < 0.22) {
      mules.push({ node, score: symmetry })
    }
  }
  mules.sort((x, y) => y.score - x.score)

  if (mules.length === 0) {
    return EMPTY('No mule accounts detected. No accounts show the rapid pass-through signature of a relay.')
  }
  const top = mules.slice(0, 5).map(m => m.node.id)
  return {
    narration:
      `${mules.length} potential mule account${mules.length !== 1 ? 's' : ''} detected. ` +
      `These accounts receive and forward near-identical amounts with minimal retention — ` +
      `classic relay behavior. Highest-confidence relay: ${shortId(mules[0].node.id)} at ` +
      `${Math.round(mules[0].score * 100)} percent pass-through symmetry.`,
    focusNodes: top,
    flagged: true,
  }
}

// ── 7. Hidden loops (all small directed cycles up to length 4) ──────────────────
export function findHiddenLoops(data: GraphData): AnalysisResult {
  if (data.nodes.length === 0) return EMPTY('No graph loaded.')
  const a = buildAdjacency(data)
  const loops = findShortCycles(a, 4)

  if (loops.length === 0) {
    return EMPTY('No hidden loops found. No short circular routes exist between the monitored accounts.')
  }
  const involved = Array.from(new Set(loops.flat()))
  return {
    narration:
      `${loops.length} hidden loop${loops.length !== 1 ? 's' : ''} surfaced. ` +
      `Short circular routes connect ${involved.length} accounts that, on the surface, appear unrelated. ` +
      `Tightest loop spans ${Math.min(...loops.map(l => l.length))} accounts. ` +
      `These closed routes are frequently used to disguise the true direction of fund flow.`,
    focusNodes: involved,
    flagged: true,
  }
}

// Enumerate distinct simple directed cycles up to maxLen (small graphs only).
function findShortCycles(a: Adjacency, maxLen: number): string[][] {
  const cycles: string[][] = []
  const seen = new Set<string>()

  for (const start of a.nodes) {
    const path: string[] = [start.id]
    const onPath = new Set([start.id])

    const walk = (cur: string) => {
      if (path.length > maxLen) return
      for (const nb of a.out.get(cur) ?? []) {
        if (nb === start.id && path.length >= 2) {
          const key = [...path].sort().join('|')
          if (!seen.has(key)) { seen.add(key); cycles.push([...path]) }
          continue
        }
        if (onPath.has(nb) || nb < start.id) continue   // canonical: start is min id
        path.push(nb); onPath.add(nb)
        walk(nb)
        path.pop(); onPath.delete(nb)
      }
    }
    walk(start.id)
  }
  return cycles
}

// ── 8. Per-node contextual analysis (fires on selection) ────────────────────────
export function analyzeNode(node: GraphNode, data: GraphData, intel?: NodeIntel | null): AnalysisResult {
  const a = buildAdjacency(data)
  const outDeg = a.out.get(node.id)?.length ?? node.outgoing_count ?? 0
  const inDeg  = a.in.get(node.id)?.length  ?? node.incoming_count ?? 0
  const sent   = a.amountOut.get(node.id) ?? node.total_sent ?? 0
  const recv   = a.amountIn.get(node.id)  ?? node.total_received ?? 0
  const risk   = Math.round((node.risk_score ?? 0) * 100)

  const fragments: string[] = []

  // Behavioral signature — pick the dominant role.
  if (outDeg >= 4 && outDeg > inDeg * 2) {
    fragments.push(
      `High fan-out behavior. This account distributes funds across ${outDeg} endpoints in a short interval — possible mule coordination pattern.`)
  } else if (inDeg >= 4 && inDeg > outDeg * 2) {
    fragments.push(
      `High fan-in behavior. ${inDeg} accounts converge funds here — consistent with a collection or aggregation point.`)
  } else if (inDeg > 0 && outDeg > 0 && Math.abs(sent - recv) / Math.max(sent, recv, 1) < 0.25) {
    fragments.push(
      `Pass-through signature. This account forwards nearly everything it receives — a likely relay in the laundering chain.`)
  } else {
    fragments.push(
      `Account ${shortId(node.id)}: ${inDeg} inbound, ${outDeg} outbound connection${outDeg !== 1 ? 's' : ''}.`)
  }

  if (node.detected_patterns && node.detected_patterns.length > 0) {
    fragments.push(`Flagged patterns: ${node.detected_patterns.join(', ').replace(/_/g, ' ')}.`)
  }

  // Inherited fraud context — the node's exposure to its cluster's verdict.
  const exposure = intel ? exposureNarration(intel) : null
  if (exposure) fragments.push(exposure)

  // Explainable ML risk — names the behavioral signals driving the score.
  fragments.push(explainNodeRisk(node, data))

  const propagated = intel ? Math.round(intel.propagatedRisk * 100) : risk
  return {
    narration: fragments.join(' '),
    focusNodes: [node.id],
    flagged: (intel?.clusterFlagged ?? false) || node.is_flagged || propagated >= 60,
  }
}

// ── 9. Risky-accounts roundup ────────────────────────────────────────────────────
export function findRiskyAccounts(data: GraphData, fraudNodeIds?: ReadonlySet<string>): AnalysisResult {
  if (data.nodes.length === 0) return EMPTY('No graph loaded.')
  const risky = data.nodes
    .filter(n => n.is_flagged || (fraudNodeIds?.has(n.id)) || n.risk_score >= 0.6)
    .sort((x, y) => y.risk_score - x.risk_score)

  if (risky.length === 0) {
    return EMPTY('No high-risk accounts. Every account scores within acceptable behavioral bounds.')
  }
  const top = risky.slice(0, 8).map(n => n.id)
  const worst = risky[0]
  return {
    narration:
      `${risky.length} high-risk account${risky.length !== 1 ? 's' : ''} flagged. ` +
      `Highest exposure: ${shortId(worst.id)} at ${Math.round(worst.risk_score * 100)} percent. ` +
      `Highlighting the top ${top.length} for review.`,
    focusNodes: top,
    flagged: true,
  }
}
