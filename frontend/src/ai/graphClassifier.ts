// ──────────────────────────────────────────────────────────────────────────────
// graphClassifier — TGIE fraud-pattern classification engine.
//
// Turns a flagged cluster's RAW topology into a named laundering pattern, a
// confidence, the investigation facts (source / sink / volume / duration), a
// human-readable narrative, and a reconstructed fraud timeline.
//
// This is the single backbone the rest of the copilot reads from:
//   • the Graph Intelligence HUD (prominent GRAPH TYPE display)
//   • UB's fraud auto-activation narration
//   • the "investigate this graph" command
//   • the evidence package
//
// Everything below is DERIVED from the live graph — no hardcoded labels, no
// random numbers. The classifier scores every candidate pattern from real
// structural signals and the strongest one wins.
// ──────────────────────────────────────────────────────────────────────────────
import type { GraphData, GraphNode, GraphLink, GraphComponentResult } from '../types'
import type { NodeIntel, NodeRole } from './riskPropagation'
import { roleLabel } from './riskPropagation'

// ── The pattern taxonomy ──────────────────────────────────────────────────────
export type FraudPatternType =
  | 'circular_laundering'
  | 'fan_out'
  | 'fan_in'
  | 'layering_chain'
  | 'mule_network'
  | 'smurfing'
  | 'shell_network'
  | 'cross_rail'
  | 'multi_hop'
  | 'hybrid'
  | 'dormant_activation'
  | 'burst'
  | 'unclassified'

const PATTERN_LABEL: Record<FraudPatternType, string> = {
  circular_laundering: 'Circular Laundering',
  fan_out:             'Fan-Out Network',
  fan_in:              'Fan-In Aggregation',
  layering_chain:      'Layering Chain',
  mule_network:        'Mule Network',
  smurfing:            'Smurfing Pattern',
  shell_network:       'Shell Account Network',
  cross_rail:          'Cross-Rail Laundering',
  multi_hop:           'Multi-Hop Laundering',
  hybrid:              'Hybrid Laundering Structure',
  dormant_activation:  'Dormant Account Activation',
  burst:               'Burst Transaction Pattern',
  unclassified:        'Unclassified Structure',
}

export function patternLabel(t: FraudPatternType): string {
  return PATTERN_LABEL[t]
}

// Behavioral families — used to decide what counts as a genuine "hybrid".
type PatternFamily = 'distribution' | 'consolidation' | 'chaining' | 'cycling'
  | 'relay' | 'structuring' | 'temporal' | 'dormancy' | 'other'
function patternFamily(t: FraudPatternType): PatternFamily {
  switch (t) {
    case 'fan_out':             return 'distribution'
    case 'fan_in':              return 'consolidation'
    case 'layering_chain':
    case 'multi_hop':
    case 'cross_rail':
    case 'shell_network':       return 'chaining'
    case 'circular_laundering': return 'cycling'
    case 'mule_network':        return 'relay'
    case 'smurfing':            return 'structuring'
    case 'burst':               return 'temporal'
    case 'dormant_activation':  return 'dormancy'
    default:                    return 'other'
  }
}

export type Severity = 'CRITICAL' | 'HIGH' | 'MODERATE' | 'LOW'
export type RecommendedAction = 'Monitor' | 'Review' | 'Escalate' | 'Freeze' | 'SAR Filing'

export interface TimelineEvent {
  /** HH:MM clock label (or relative T+Xm when timestamps are absent). */
  at:      string
  /** Short phase title. */
  title:   string
  /** One-line description. */
  detail:  string
}

/** A structural detection signal that fired, with its measured strength. */
export interface SignalIndicator {
  key:      string
  label:    string
  strength: number   // 0..1 — how strongly this signal is present
  detail:  string    // the concrete measurement (e.g. "6-way fan-out")
}

/** A candidate pattern and the score it earned during classification. */
export interface PatternScore {
  type:  FraudPatternType
  label: string
  score: number      // 0..1
}

/** A notable account within the cluster, with its inferred role + risk. */
export interface KeyAccount {
  id:        string
  role:      NodeRole
  roleLabel: string
  risk:      number  // 0..1
  netFlow:   number  // signed ₹ (out − in): positive = net sender
  txCount:   number  // in-cluster degree
}

/** Quantitative network metrics beyond the headline facts. */
export interface ClusterMetrics {
  density:           number   // 0..1 — directed edge density
  velocityTxPerMin:  number   // transactions per minute (0 if no clock)
  avgTx:             number   // mean transaction amount (₹)
  largestTx:         number   // single largest transaction (₹)
  concentration:     number   // 0..1 — share of volume through the busiest account
  retention:         number   // 0..1 — mean fraction of inflow NOT forwarded onward
  rails:             string[] // distinct payment rails observed
}

export interface ClusterIntel {
  graphId:        string
  type:           FraudPatternType
  typeLabel:      string
  confidence:     number          // 0..1
  /** Secondary patterns that also scored (for hybrid structures). */
  alsoMatched:    FraudPatternType[]
  severity:       Severity
  recommendation: RecommendedAction
  actionRationale: string         // why this action is recommended
  // ── Network facts ──
  accounts:       number
  transactions:   number
  volume:         number          // total ₹ moved within the cluster
  durationMin:    number          // span between first and last transaction
  primarySource:  string | null   // origin / funding account
  primarySink:    string | null   // terminal / cashout account
  riskScore:      number          // cluster verdict severity 0..1
  // ── Derived intelligence ──
  indicators:     SignalIndicator[]   // the detection signals that fired
  patternScores:  PatternScore[]      // ranked candidate-pattern breakdown
  keyAccounts:    KeyAccount[]        // notable accounts by role / risk
  metrics:        ClusterMetrics      // quantitative network metrics
  riskFactors:    string[]            // human-readable "why flagged" bullets
  confidenceBreakdown: { structural: number; verdict: number } // 0..1 each
  // ── Narrative ──
  summary:        string          // human-readable explanation
  timeline:       TimelineEvent[]
}

// ── Adjacency restricted to a cluster ─────────────────────────────────────────
const idOf = (x: string | GraphNode): string => (typeof x === 'string' ? x : x.id)

interface ClusterAdj {
  nodes:     GraphNode[]
  links:     GraphLink[]          // links with BOTH ends inside the cluster
  out:       Map<string, string[]>
  in:        Map<string, string[]>
  amtOut:    Map<string, number>
  amtIn:     Map<string, number>
  rails:     Set<string>
  amounts:   number[]
  timestamps: number[]
}

function buildClusterAdj(cluster: GraphComponentResult, data: GraphData): ClusterAdj {
  const set = new Set(cluster.nodes)
  const nodes = data.nodes.filter(n => set.has(n.id))
  const out = new Map<string, string[]>()
  const inn = new Map<string, string[]>()
  const amtOut = new Map<string, number>()
  const amtIn = new Map<string, number>()
  const rails = new Set<string>()
  const amounts: number[] = []
  const timestamps: number[] = []
  const links: GraphLink[] = []

  for (const l of data.links as GraphLink[]) {
    const s = idOf(l.source), t = idOf(l.target)
    if (!set.has(s) || !set.has(t)) continue
    links.push(l)
    ;(out.get(s) ?? out.set(s, []).get(s)!).push(t)
    ;(inn.get(t) ?? inn.set(t, []).get(t)!).push(s)
    amtOut.set(s, (amtOut.get(s) ?? 0) + (l.amount ?? 0))
    amtIn.set(t, (amtIn.get(t) ?? 0) + (l.amount ?? 0))
    if (l.payment_rail) rails.add(l.payment_rail)
    if (l.amount) amounts.push(l.amount)
    const ts = l.timestamp ? Date.parse(l.timestamp) : NaN
    if (!Number.isNaN(ts)) timestamps.push(ts)
  }
  return { nodes, links, out, in: inn, amtOut, amtIn, rails, amounts, timestamps }
}

// ── Structural signal extraction ──────────────────────────────────────────────
interface Signals {
  n:            number
  e:            number
  maxOut:       number   // largest fan-out degree
  maxIn:        number   // largest fan-in degree
  cycleLen:     number   // longest cycle found (0 = none)
  chainLen:     number   // longest directed simple path
  muleCount:    number   // pass-through relays
  railCount:    number
  shellCount:   number   // strict 1-in-1-out low-activity nodes
  burstScore:   number   // 0..1, transactions packed into a short window
  smurfScore:   number   // 0..1, many similar near-threshold amounts
  dormantScore: number   // 0..1, long-dormant accounts that just activated
}

function passThrough(a: number, b: number): number {
  if (a <= 0 || b <= 0) return 0
  return 1 - Math.abs(a - b) / Math.max(a, b)
}

function extractSignals(adj: ClusterAdj): Signals {
  const ids = adj.nodes.map(n => n.id)
  let maxOut = 0, maxIn = 0, muleCount = 0, shellCount = 0
  for (const n of adj.nodes) {
    const o = adj.out.get(n.id)?.length ?? 0
    const i = adj.in.get(n.id)?.length ?? 0
    if (o > maxOut) maxOut = o
    if (i > maxIn) maxIn = i
    const pt = passThrough(adj.amtIn.get(n.id) ?? 0, adj.amtOut.get(n.id) ?? 0)
    // A defining mule is a BRANCHING pass-through (fans in or out) — a plain
    // 1-in-1-out node is a chain/ring relay, not a mule-network signature.
    if ((i >= 2 || o >= 2) && i >= 1 && o >= 1 && pt > 0.78) muleCount++
    // Shell: strict relay with a single hop in and out and almost no retention.
    if (i === 1 && o === 1 && pt > 0.9) shellCount++
  }

  const cycleLen = longestCycle(adj.out, ids)
  const chainLen = longestChain(adj.out, ids)

  // Burst: how tightly packed the transactions are in time.
  let burstScore = 0
  if (adj.timestamps.length >= 3) {
    const sorted = [...adj.timestamps].sort((a, b) => a - b)
    const span = (sorted[sorted.length - 1] - sorted[0]) / 60000 // minutes
    const txPerMin = adj.timestamps.length / Math.max(1, span)
    burstScore = clamp01((txPerMin - 1) / 5) // >6 tx/min → saturates
  }

  // Smurf: cluster of similar amounts sitting just below round reporting bands.
  // Near-threshold structuring is the defining signal — uniform amounts alone
  // (common in any synthetic flow) must NOT register as smurfing.
  let smurfScore = 0
  if (adj.amounts.length >= 4) {
    const mean = adj.amounts.reduce((a, b) => a + b, 0) / adj.amounts.length
    const cv = stddev(adj.amounts) / (mean || 1) // low variance = structured
    const nearBand = adj.amounts.filter(a => isNearThreshold(a)).length / adj.amounts.length
    smurfScore = nearBand > 0 ? clamp01(nearBand * 0.85 + (1 - cv) * 0.25) : 0
  }

  // Dormant activation: accounts whose last_activity predates the cluster window
  // by a wide margin yet are suddenly transacting.
  let dormantScore = 0
  const now = Date.now()
  const dormant = adj.nodes.filter(n => {
    const la = n.last_activity ? Date.parse(n.last_activity) : NaN
    if (Number.isNaN(la)) return false
    return now - la > 30 * 24 * 3600 * 1000 && (n.transaction_count ?? 0) > 0
  }).length
  if (adj.nodes.length) dormantScore = clamp01(dormant / adj.nodes.length * 1.5)

  return {
    n: adj.nodes.length,
    e: adj.links.length,
    maxOut, maxIn, cycleLen, chainLen, muleCount,
    railCount: adj.rails.size, shellCount,
    burstScore, smurfScore, dormantScore,
  }
}

function isNearThreshold(amount: number): boolean {
  // Common structuring bands (₹): just under 50k / 1L / 2L / 10L.
  const bands = [50000, 100000, 200000, 1000000]
  return bands.some(b => amount >= b * 0.82 && amount < b)
}

// ── Pattern scoring ───────────────────────────────────────────────────────────
function scorePatterns(s: Signals): Array<{ type: FraudPatternType; score: number }> {
  const scores: Array<{ type: FraudPatternType; score: number }> = []
  const push = (type: FraudPatternType, score: number) => scores.push({ type, score: clamp01(score) })

  // Circular laundering — a directed cycle is the strongest single signal.
  push('circular_laundering', s.cycleLen >= 3 ? 0.7 + Math.min(0.25, (s.cycleLen - 3) * 0.06) : s.cycleLen === 2 ? 0.4 : 0)
  // Fan-out — one source sprays to many.
  push('fan_out', s.maxOut >= 3 ? 0.45 + Math.min(0.45, (s.maxOut - 3) * 0.09) : 0)
  // Fan-in — many converge to one.
  push('fan_in', s.maxIn >= 3 ? 0.45 + Math.min(0.45, (s.maxIn - 3) * 0.09) : 0)
  // Layering — a long pass-through chain.
  push('layering_chain', s.chainLen >= 4 ? 0.5 + Math.min(0.4, (s.chainLen - 4) * 0.1) : 0)
  // Multi-hop — depth without a clean single chain (distinct from layering).
  push('multi_hop', s.chainLen >= 5 ? 0.4 + Math.min(0.3, (s.chainLen - 5) * 0.08) : 0)
  // Mule network — several pass-through relays.
  push('mule_network', s.muleCount >= 2 ? 0.4 + Math.min(0.45, (s.muleCount - 2) * 0.12) : s.muleCount === 1 ? 0.3 : 0)
  // Shell network — many strict 1-in-1-out conduits.
  push('shell_network', s.shellCount >= 3 ? 0.45 + Math.min(0.4, (s.shellCount - 3) * 0.1) : 0)
  // Cross-rail — funds hop across ≥3 payment rails.
  push('cross_rail', s.railCount >= 3 ? 0.5 + Math.min(0.35, (s.railCount - 3) * 0.12) : 0)
  // Smurfing — structured near-threshold amounts.
  push('smurfing', s.smurfScore * 0.85)
  // Burst — temporal packing.
  push('burst', s.burstScore * 0.8)
  // Dormant activation.
  push('dormant_activation', s.dormantScore * 0.8)

  // When a strong directed cycle exists, the chain / shell / mule signals are
  // largely the SAME ring counted a second time. Dampen them so circular
  // laundering reads as the primary pattern rather than a false hybrid.
  if (s.cycleLen >= 3) {
    const damp: Partial<Record<FraudPatternType, number>> = {
      shell_network: 0.5, layering_chain: 0.5, multi_hop: 0.5, mule_network: 0.6,
    }
    for (const item of scores) if (damp[item.type] != null) item.score *= damp[item.type]!
  }

  return scores.sort((a, b) => b.score - a.score)
}

// ── Main entry ────────────────────────────────────────────────────────────────
export function classifyCluster(
  cluster: GraphComponentResult,
  data: GraphData,
  riskByNode?: Map<string, NodeIntel>,
): ClusterIntel {
  const adj = buildClusterAdj(cluster, data)
  const sig = extractSignals(adj)
  const ranked = scorePatterns(sig)

  const best = ranked[0]
  const second = ranked[1]
  // Hybrid only when two strong signals from DIFFERENT behavioral families
  // coexist (e.g. distribution + consolidation). Two close same-family signals
  // — a chain that is also cross-rail — are not a hybrid; the stronger wins.
  const isHybrid = !!best && !!second &&
    best.score >= 0.5 && second.score >= 0.5 &&
    best.score - second.score < 0.18 &&
    patternFamily(best.type) !== patternFamily(second.type)
  const type: FraudPatternType = !best || best.score < 0.25
    ? 'unclassified'
    : isHybrid ? 'hybrid' : best.type

  const alsoMatched = ranked.filter(r => r.score >= 0.4).slice(0, 3).map(r => r.type)

  // Confidence blends structural signal strength with the backend verdict so a
  // weak structure can't masquerade as high-confidence — and vice-versa.
  const structural = best?.score ?? 0
  const verdict = clamp01(cluster.risk_score ?? 0)
  const confidence = type === 'unclassified'
    ? Math.max(0.35, verdict * 0.8)
    : clamp01(0.55 * structural + 0.45 * verdict)

  // ── Network facts ──
  const volume = adj.amounts.reduce((a, b) => a + b, 0)
  const durationMin = adj.timestamps.length >= 2
    ? (Math.max(...adj.timestamps) - Math.min(...adj.timestamps)) / 60000
    : 0
  const { source, sink } = resolveSourceSink(adj, riskByNode)
  const severity = severityFor(verdict)
  const recommendation = recommend(severity, type)

  const metrics = buildMetrics(adj, volume, durationMin)
  const indicators = buildIndicators(sig, metrics)
  const patternScores = ranked
    .filter(r => r.score > 0.04)
    .slice(0, 5)
    .map(r => ({ type: r.type, label: patternLabel(r.type), score: r.score }))
  const keyAccounts = buildKeyAccounts(adj, riskByNode, source, sink)
  const riskFactors = buildRiskFactors(sig, metrics, severity, indicators)

  return {
    graphId:        cluster.graph_id,
    type,
    typeLabel:      patternLabel(type),
    confidence,
    alsoMatched:    alsoMatched.filter(t => t !== best?.type),
    severity,
    recommendation,
    actionRationale: actionRationale(severity, type, recommendation),
    accounts:       adj.nodes.length,
    transactions:   adj.links.length,
    volume,
    durationMin,
    primarySource:  source,
    primarySink:    sink,
    riskScore:      verdict,
    indicators,
    patternScores,
    keyAccounts,
    metrics,
    riskFactors,
    confidenceBreakdown: { structural, verdict },
    summary:        buildSummary(type, sig, { volume, durationMin, source, sink, accounts: adj.nodes.length, transactions: adj.links.length }),
    timeline:       buildTimeline(adj, sig, type),
  }
}

// ── Detection-signal extraction (the "why" behind the classification) ──────────
// Surfaces every structural signal that actually fired, with its measured
// strength, so the analyst sees the evidence — not just the verdict.
function buildIndicators(s: Signals, m: ClusterMetrics): SignalIndicator[] {
  const out: SignalIndicator[] = []
  const add = (key: string, label: string, strength: number, detail: string) => {
    if (strength > 0.04) out.push({ key, label, strength: clamp01(strength), detail })
  }

  if (s.cycleLen >= 2)
    add('cycle', 'Circular flow', s.cycleLen >= 3 ? clamp01(0.6 + (s.cycleLen - 3) * 0.1) : 0.4,
      `${s.cycleLen}-account directed loop`)
  if (s.maxOut >= 3)
    add('fanout', 'Fan-out spray', clamp01((s.maxOut - 2) / 8), `${s.maxOut}-way distribution`)
  if (s.maxIn >= 3)
    add('fanin', 'Fan-in funnel', clamp01((s.maxIn - 2) / 8), `${s.maxIn} sources converge`)
  if (s.chainLen >= 4)
    add('chain', 'Layering depth', clamp01((s.chainLen - 3) / 7), `${s.chainLen}-hop pass-through path`)
  if (s.muleCount >= 1)
    add('mule', 'Pass-through relays', clamp01(s.muleCount / 5), `${s.muleCount} mule relay${s.muleCount !== 1 ? 's' : ''}`)
  if (s.shellCount >= 2)
    add('shell', 'Shell conduits', clamp01(s.shellCount / 6), `${s.shellCount} strict 1-in-1-out nodes`)
  if (s.railCount >= 3)
    add('rail', 'Cross-rail hops', clamp01((s.railCount - 2) / 3), `${s.railCount} payment rails used`)
  add('burst', 'Burst velocity', s.burstScore, m.velocityTxPerMin >= 1 ? `${m.velocityTxPerMin.toFixed(1)} tx/min` : 'tightly time-packed')
  add('smurf', 'Near-threshold structuring', s.smurfScore, 'amounts engineered below reporting bands')
  add('dormant', 'Dormant reactivation', s.dormantScore, 'aged accounts suddenly active')
  if (m.concentration >= 0.5)
    add('concentration', 'Value concentration', clamp01((m.concentration - 0.4) / 0.6), `${Math.round(m.concentration * 100)}% routes via one account`)

  return out.sort((a, b) => b.strength - a.strength)
}

// ── Quantitative network metrics ──────────────────────────────────────────────
function buildMetrics(adj: ClusterAdj, volume: number, durationMin: number): ClusterMetrics {
  const n = adj.nodes.length
  const e = adj.links.length
  const possible = n > 1 ? n * (n - 1) : 1
  const density = clamp01(e / possible)
  const velocityTxPerMin = durationMin > 0 ? e / durationMin : 0
  const avgTx = adj.amounts.length ? volume / adj.amounts.length : 0
  const largestTx = adj.amounts.length ? Math.max(...adj.amounts) : 0

  // Concentration: the busiest account's throughput (in+out) as a share of 2×volume.
  let busiest = 0
  for (const node of adj.nodes) {
    const thru = (adj.amtIn.get(node.id) ?? 0) + (adj.amtOut.get(node.id) ?? 0)
    if (thru > busiest) busiest = thru
  }
  const concentration = volume > 0 ? clamp01(busiest / (2 * volume)) : 0

  // Retention: across accounts that received funds, the mean fraction kept (not forwarded).
  let retSum = 0, retCount = 0
  for (const node of adj.nodes) {
    const inn = adj.amtIn.get(node.id) ?? 0
    if (inn <= 0) continue
    const fwd = adj.amtOut.get(node.id) ?? 0
    retSum += clamp01(1 - fwd / inn)
    retCount++
  }
  const retention = retCount ? retSum / retCount : 0

  return { density, velocityTxPerMin, avgTx, largestTx, concentration, retention, rails: [...adj.rails] }
}

// ── Key-account ranking (who matters in this cluster) ──────────────────────────
function buildKeyAccounts(
  adj: ClusterAdj,
  riskByNode: Map<string, NodeIntel> | undefined,
  source: string | null,
  sink: string | null,
): KeyAccount[] {
  const accounts: KeyAccount[] = adj.nodes.map(node => {
    const intel = riskByNode?.get(node.id)
    const topoRole: NodeRole = node.id === source ? 'source' : node.id === sink ? 'sink' : 'relay'
    const role = intel?.role && intel.role !== 'normal' ? intel.role : topoRole
    const risk = intel?.propagatedRisk ?? node.risk_score ?? 0
    const netFlow = (adj.amtOut.get(node.id) ?? 0) - (adj.amtIn.get(node.id) ?? 0)
    const txCount = (adj.out.get(node.id)?.length ?? 0) + (adj.in.get(node.id)?.length ?? 0)
    return { id: node.id, role, roleLabel: roleLabel(role), risk: clamp01(risk), netFlow, txCount }
  })

  // Rank: pinned source/sink first, then by risk, then by absolute throughput.
  const rank = (a: KeyAccount) =>
    (a.id === source ? 100 : 0) + (a.id === sink ? 90 : 0) + a.risk * 10 + Math.min(1, a.txCount / 10)
  return accounts.sort((a, b) => rank(b) - rank(a)).slice(0, 5)
}

// ── Human-readable "why flagged" factors ──────────────────────────────────────
function buildRiskFactors(
  s: Signals,
  m: ClusterMetrics,
  severity: Severity,
  indicators: SignalIndicator[],
): string[] {
  const factors: string[] = []
  // Lead with the two strongest structural signals, phrased as findings.
  for (const ind of indicators.slice(0, 2)) {
    factors.push(`${ind.label} detected — ${ind.detail}.`)
  }
  if (m.retention <= 0.15 && m.avgTx > 0)
    factors.push('Near-zero retention — funds are forwarded almost immediately, typical of conduit accounts.')
  if (m.concentration >= 0.6)
    factors.push(`Flow is highly concentrated (${Math.round(m.concentration * 100)}%) through a single account.`)
  if (m.velocityTxPerMin >= 2)
    factors.push(`Elevated velocity at ${m.velocityTxPerMin.toFixed(1)} transactions per minute.`)
  if (s.railCount >= 3)
    factors.push(`Funds switch across ${s.railCount} payment rails, fragmenting the audit trail.`)
  if (severity === 'CRITICAL' || severity === 'HIGH')
    factors.push(`Backend verdict places this cluster at ${severity.toLowerCase()} severity.`)
  // De-duplicate while preserving order.
  const seen = new Set<string>()
  return factors.filter(f => (seen.has(f) ? false : (seen.add(f), true))).slice(0, 5)
}

function actionRationale(sev: Severity, type: FraudPatternType, action: RecommendedAction): string {
  const pat = type === 'unclassified' ? 'the anomalous structure' : `a ${patternLabel(type).toLowerCase()} pattern`
  switch (action) {
    case 'Freeze':
      return `Critical-severity ${pat} warrants an immediate hold on the involved accounts pending investigation.`
    case 'SAR Filing':
      return `The strength and structure of ${pat} meets the bar for a Suspicious Activity Report.`
    case 'Escalate':
      return `${cap(sev.toLowerCase())}-severity ${pat} should be escalated to a human analyst for review.`
    case 'Review':
      return `Moderate signals from ${pat} merit manual review before any action.`
    default:
      return `Low-severity ${pat} — keep under automated monitoring for escalation.`
  }
}

// ── Source / sink resolution ──────────────────────────────────────────────────
function resolveSourceSink(
  adj: ClusterAdj,
  riskByNode?: Map<string, NodeIntel>,
): { source: string | null; sink: string | null } {
  let source: string | null = null
  let sink: string | null = null

  // Prefer the risk engine's semantic roles when available.
  if (riskByNode) {
    for (const n of adj.nodes) {
      const role = riskByNode.get(n.id)?.role
      if (!source && (role === 'origin' || role === 'source')) source = n.id
      if (!sink && role === 'sink') sink = n.id
    }
  }
  // Fall back to pure topology: max net-outflow → source, max net-inflow → sink.
  if (!source) {
    let bestNet = -Infinity
    for (const n of adj.nodes) {
      const net = (adj.amtOut.get(n.id) ?? 0) - (adj.amtIn.get(n.id) ?? 0)
      const outDeg = adj.out.get(n.id)?.length ?? 0
      if (outDeg > 0 && net > bestNet) { bestNet = net; source = n.id }
    }
  }
  if (!sink) {
    let bestNet = -Infinity
    for (const n of adj.nodes) {
      if (n.id === source) continue   // sink must differ from the source
      const net = (adj.amtIn.get(n.id) ?? 0) - (adj.amtOut.get(n.id) ?? 0)
      const inDeg = adj.in.get(n.id)?.length ?? 0
      if (inDeg > 0 && net > bestNet) { bestNet = net; sink = n.id }
    }
  }
  // In a closed ring every node nets ~zero, so fall back to the account that
  // closes the loop back onto the source (the last hop before origin).
  if ((!sink || sink === source) && source) {
    const closer = (adj.in.get(source) ?? []).find(p => p !== source)
    if (closer) sink = closer
  }
  return { source, sink }
}

// ── Human-readable summary ────────────────────────────────────────────────────
interface SummaryFacts {
  volume: number; durationMin: number
  source: string | null; sink: string | null
  accounts: number; transactions: number
}

function buildSummary(type: FraudPatternType, s: Signals, f: SummaryFacts): string {
  const src = f.source ? `account ${f.source}` : 'a single source account'
  const dst = f.sink ? `account ${f.sink}` : 'a terminal account'
  const inter = Math.max(0, f.accounts - 2)
  const vol = money(f.volume)

  switch (type) {
    case 'circular_laundering':
      return `This cluster exhibits characteristics of circular laundering. Funds originated from ${src} and were ` +
        `distributed across ${inter} intermediary account${inter !== 1 ? 's' : ''}. The funds then returned toward the ` +
        `originating cluster through one or more closed loops spanning ${s.cycleLen} accounts. ` +
        `Recycling value through a ring like this is commonly used to obscure the true origin of funds. ` +
        `Approximately ${vol} moved through the structure.`
    case 'fan_out':
      return `This cluster shows a fan-out distribution. ${cap(src)} pushed funds outward to ${s.maxOut} downstream ` +
        `recipients in rapid succession. Spraying value across many fresh accounts at once is a hallmark of mule ` +
        `coordination and is designed to fragment a single sum beyond easy tracing. Total dispersed: ${vol}.`
    case 'fan_in':
      return `This cluster shows fan-in aggregation. ${s.maxIn} separate accounts converged funds into ${dst}, ` +
        `consolidating value that had previously been dispersed. Aggregation points like this are typically the ` +
        `collection stage that precedes a cash-out. Roughly ${vol} was funnelled together.`
    case 'layering_chain':
      return `This cluster is a layering chain. Funds traverse a ${s.chainLen}-account path from ${src} toward ${dst}, ` +
        `with each hop adding a layer of separation between the source and the eventual destination. ` +
        `Chained pass-through of this depth is a deliberate laundering technique. Value in motion: ${vol}.`
    case 'multi_hop':
      return `This cluster is a multi-hop laundering structure. Value moves ${s.chainLen} hops deep across ${f.accounts} ` +
        `accounts before settling, with no direct path from source to destination. The added depth is consistent with ` +
        `intentional obfuscation. Approximately ${vol} routed through the network.`
    case 'mule_network':
      return `This cluster is a mule network. ${s.muleCount} account${s.muleCount !== 1 ? 's' : ''} act as pass-through ` +
        `relays, receiving and forwarding near-identical amounts with minimal retention. Relays like these are typically ` +
        `recruited intermediaries used to move ${vol} while distancing it from the original holder.`
    case 'smurfing':
      return `This cluster matches a smurfing / structuring pattern. Multiple transactions cluster just below common ` +
        `reporting thresholds, fragmenting a larger sum into amounts engineered to avoid scrutiny. ` +
        `${f.transactions} transactions totalling ${vol} were structured across ${f.accounts} accounts.`
    case 'shell_network':
      return `This cluster resembles a shell-account network. ${s.shellCount} accounts operate as strict single-in, ` +
        `single-out conduits with no genuine economic activity, serving only to relay ${vol} along a controlled path ` +
        `between ${src} and ${dst}.`
    case 'cross_rail':
      return `This cluster shows cross-rail laundering. Funds hop across ${s.railCount} distinct payment rails as they ` +
        `move from ${src} toward ${dst}. Switching rails mid-flow breaks the audit trail between systems and is a known ` +
        `evasion tactic. Total value moved: ${vol}.`
    case 'dormant_activation':
      return `This cluster shows dormant-account activation. Previously inactive accounts have suddenly begun transacting ` +
        `as part of a coordinated movement of ${vol}. Reactivation of aged accounts in concert is frequently associated ` +
        `with compromised or purpose-bought identities.`
    case 'burst':
      return `This cluster shows a burst transaction pattern. ${f.transactions} transactions fired within a ${fmtDur(f.durationMin)} ` +
        `window across ${f.accounts} accounts — a velocity far above normal account behavior, consistent with automated ` +
        `or scripted movement of ${vol}.`
    case 'hybrid':
      return `This cluster is a hybrid laundering structure: it combines more than one technique simultaneously, blending ` +
        `distribution, layering and consolidation behaviours across ${f.accounts} accounts. Mixed structures like this are ` +
        `built to defeat single-signature detection. Approximately ${vol} moved through the network from ${src} toward ${dst}.`
    default:
      return `This cluster was flagged on anomalous behaviour but does not match a single canonical laundering template. ` +
        `${f.accounts} accounts moved ${vol} across ${f.transactions} transactions in a structure that warrants manual review.`
  }
}

// ── Timeline reconstruction ───────────────────────────────────────────────────
function buildTimeline(adj: ClusterAdj, s: Signals, type: FraudPatternType): TimelineEvent[] {
  const events: TimelineEvent[] = []
  const hasClock = adj.timestamps.length >= 2
  const sorted = [...adj.timestamps].sort((a, b) => a - b)
  const t0 = sorted[0] ?? Date.now()
  const tEnd = sorted[sorted.length - 1] ?? t0
  const span = Math.max(1, tEnd - t0)

  // Map a 0..1 progress fraction to a clock label.
  const at = (frac: number): string => {
    if (hasClock) {
      const d = new Date(t0 + span * frac)
      return `${pad(d.getHours())}:${pad(d.getMinutes())}`
    }
    const mins = Math.round((span / 60000) * frac)
    return `T+${mins}m`
  }

  events.push({ at: at(0), title: 'Source funded', detail: 'Initial value enters the cluster from the origin account.' })

  if (s.maxOut >= 3) {
    events.push({ at: at(0.2), title: 'Fan-out initiated', detail: `Funds dispersed to ${s.maxOut} downstream recipients.` })
  }
  if (s.chainLen >= 4 || type === 'layering_chain' || type === 'multi_hop') {
    events.push({ at: at(0.4), title: 'Layering began', detail: `Pass-through transfers extend the chain ${s.chainLen} hops deep.` })
  }
  if (s.railCount >= 3) {
    events.push({ at: at(0.5), title: 'Rail switch', detail: `Flow crosses ${s.railCount} payment rails to break the trail.` })
  }
  if (s.cycleLen >= 3) {
    events.push({ at: at(0.6), title: 'Circular transfers observed', detail: `Value loops back through a ${s.cycleLen}-account ring.` })
  }
  if (s.maxIn >= 3) {
    events.push({ at: at(0.8), title: 'Aggregation detected', detail: `${s.maxIn} accounts converge funds toward a collection point.` })
  }
  events.push({ at: at(1), title: 'Funds exited network', detail: 'Value reaches the terminal / cash-out account.' })

  // Keep chronological and de-duplicated by title.
  const seen = new Set<string>()
  return events.filter(e => (seen.has(e.title) ? false : (seen.add(e.title), true)))
}

// ── Severity + recommendation ─────────────────────────────────────────────────
function severityFor(risk: number): Severity {
  if (risk >= 0.85) return 'CRITICAL'
  if (risk >= 0.70) return 'HIGH'
  if (risk >= 0.50) return 'MODERATE'
  return 'LOW'
}

function recommend(sev: Severity, type: FraudPatternType): RecommendedAction {
  // Structuring / smurfing is the textbook trigger for a Suspicious Activity Report.
  if ((sev === 'CRITICAL' || sev === 'HIGH') && type === 'smurfing') return 'SAR Filing'
  if (sev === 'CRITICAL') return type === 'unclassified' ? 'Escalate' : 'Freeze'
  if (sev === 'HIGH')     return 'Escalate'
  if (sev === 'MODERATE') return 'Review'
  return 'Monitor'
}

// ── Topology helpers ──────────────────────────────────────────────────────────
// Longest directed cycle length within a cap (small clusters only).
function longestCycle(out: Map<string, string[]>, ids: string[]): number {
  let best = 0
  const CAP = 8
  for (const start of ids) {
    const path: string[] = [start]
    const onPath = new Set([start])
    const walk = (cur: string) => {
      if (path.length > CAP) return
      for (const nb of out.get(cur) ?? []) {
        if (nb === start && path.length >= 2) { best = Math.max(best, path.length); continue }
        if (onPath.has(nb) || nb < start) continue // canonical: start = min id
        path.push(nb); onPath.add(nb); walk(nb); path.pop(); onPath.delete(nb)
      }
    }
    walk(start)
    if (best >= CAP) break
  }
  return best
}

// Longest directed simple path (memoized DFS, cycle-guarded).
function longestChain(out: Map<string, string[]>, ids: string[]): number {
  const memo = new Map<string, number>()
  const visiting = new Set<string>()
  const dfs = (id: string): number => {
    if (memo.has(id)) return memo.get(id)!
    if (visiting.has(id)) return 1
    visiting.add(id)
    let best = 0
    for (const nb of out.get(id) ?? []) best = Math.max(best, dfs(nb))
    visiting.delete(id)
    const len = 1 + best
    memo.set(id, len)
    return len
  }
  let longest = 0
  for (const id of ids) longest = Math.max(longest, dfs(id))
  return longest
}

// ── Misc utilities ────────────────────────────────────────────────────────────
function clamp01(v: number): number { return Math.min(1, Math.max(0, v)) }
function pad(n: number): string { return `${n}`.padStart(2, '0') }
function cap(s: string): string { return s.charAt(0).toUpperCase() + s.slice(1) }

function stddev(xs: number[]): number {
  if (xs.length < 2) return 0
  const m = xs.reduce((a, b) => a + b, 0) / xs.length
  return Math.sqrt(xs.reduce((a, b) => a + (b - m) ** 2, 0) / xs.length)
}

function money(v: number): string {
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(1)}Cr`
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)}L`
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(0)}K`
  return `₹${Math.round(v)}`
}

export function fmtDur(min: number): string {
  if (min <= 0) return 'under a minute'
  if (min < 1) return 'under a minute'
  if (min < 60) return `${Math.round(min)} minute${Math.round(min) !== 1 ? 's' : ''}`
  const h = Math.floor(min / 60), m = Math.round(min % 60)
  return m ? `${h}h ${m}m` : `${h} hour${h !== 1 ? 's' : ''}`
}

// ── Spoken narration for UB (auto-activation + investigate) ────────────────────
export function spokenAlert(intel: ClusterIntel, clusterCount = 1): string {
  const pct = Math.round(intel.confidence * 100)
  const parts = [
    'Attention.',
    'Potential fraud cluster detected.',
    `${intel.accounts} accounts involved.`,
    `Estimated risk score ${Math.round(intel.riskScore * 100)} percent.`,
    `Pattern resembles ${intel.typeLabel.toLowerCase()}, confidence ${pct} percent.`,
  ]
  if (clusterCount > 1) parts.push(`${clusterCount} clusters are flagged in total.`)
  parts.push('Would you like a detailed analysis?')
  return parts.join(' ')
}

export function spokenInvestigation(intel: ClusterIntel): string {
  const parts = [
    `Investigation complete. This is a ${intel.typeLabel.toLowerCase()} pattern at ${Math.round(intel.confidence * 100)} percent confidence.`,
    `${intel.accounts} accounts, ${intel.transactions} transactions, ${money(intel.volume)} in total volume over ${fmtDur(intel.durationMin)}.`,
  ]
  if (intel.primarySource) parts.push(`Primary source is ${intel.primarySource}.`)
  if (intel.primarySink) parts.push(`Funds terminate at ${intel.primarySink}.`)
  parts.push(`Severity ${intel.severity.toLowerCase()}. Recommended action: ${intel.recommendation}.`)
  return parts.join(' ')
}
