// ──────────────────────────────────────────────────────────────────────────────
// riskModel — TGIE behavioral risk model (frontend, explainable).
//
// A transparent feature-based ensemble scorer. For every account we extract
// behavioral features, standardize them across the live population (z-scores),
// run them through a weighted logistic model, and surface the top contributing
// signals — a SHAP-style explanation of *why* an account scored the way it did.
//
// This runs alongside the backend's IsolationForest / Blue-Team anomaly score.
// We blend the two so UB speaks from an actual model output, not a template.
// ──────────────────────────────────────────────────────────────────────────────
import type { GraphData, GraphNode } from '../types'

// ── Feature definitions ─────────────────────────────────────────────────────────
interface FeatureSpec {
  key:    string
  label:  string        // human-readable, spoken by UB
  weight: number        // logistic coefficient
  /** Extract the raw feature value from a node. */
  extract: (n: GraphNode) => number
}

const FEATURES: FeatureSpec[] = [
  { key: 'spread',      label: 'fan-out ratio',        weight: 1.05, extract: n => (n.outgoing_count ?? 0) / ((n.incoming_count ?? 0) + 1) },
  { key: 'fanout',      label: 'outbound degree',      weight: 0.65, extract: n => n.outgoing_count ?? 0 },
  { key: 'velocity',    label: 'transaction velocity', weight: 0.70, extract: n => ((n.total_sent ?? 0) + (n.total_received ?? 0)) / ((n.transaction_count ?? 0) + 1) },
  { key: 'passthrough', label: 'pass-through symmetry',weight: 1.00, extract: n => passThrough(n) },
  { key: 'volume',      label: 'value throughput',     weight: 0.50, extract: n => (n.total_sent ?? 0) + (n.total_received ?? 0) },
  { key: 'connectivity',label: 'network connectivity', weight: 0.45, extract: n => n.connected_accounts?.length ?? 0 },
  { key: 'fanin',       label: 'inbound concentration',weight: 0.35, extract: n => n.incoming_count ?? 0 },
]
const BIAS = -0.55

function passThrough(n: GraphNode): number {
  const s = n.total_sent ?? 0, r = n.total_received ?? 0
  if (s <= 0 || r <= 0) return 0
  return 1 - Math.abs(s - r) / Math.max(s, r)
}

const sigmoid = (z: number) => 1 / (1 + Math.exp(-z))

// ── Population statistics (mean / std per feature) ──────────────────────────────
interface Stats { mean: number; std: number }

function computeStats(nodes: GraphNode[]): Record<string, Stats> {
  const out: Record<string, Stats> = {}
  for (const f of FEATURES) {
    const vals = nodes.map(f.extract)
    const mean = vals.reduce((a, b) => a + b, 0) / Math.max(1, vals.length)
    const variance = vals.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, vals.length)
    out[f.key] = { mean, std: Math.sqrt(variance) || 1 }
  }
  return out
}

// ── Scored output ────────────────────────────────────────────────────────────────
export interface Contribution {
  key:    string
  label:  string
  z:      number   // standardized feature value
  impact: number   // signed contribution to the logit (weight * z)
}

export interface NodeRiskScore {
  id:            string
  /** Model probability ∈ [0,1]. */
  modelScore:    number
  /** Blended with the backend anomaly score when available. */
  blendedScore:  number
  contributions: Contribution[]   // sorted by |impact| desc
}

function scoreOne(node: GraphNode, stats: Record<string, Stats>): NodeRiskScore {
  let logit = BIAS
  const contributions: Contribution[] = []
  for (const f of FEATURES) {
    const raw = f.extract(node)
    const { mean, std } = stats[f.key]
    const z = (raw - mean) / std
    const impact = f.weight * z
    logit += impact
    contributions.push({ key: f.key, label: f.label, z, impact })
  }
  contributions.sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact))
  const modelScore = sigmoid(logit)
  // Blend 60/40 with the backend anomaly score (real IsolationForest output)
  // when the node carries one, so UB speaks from a true two-model ensemble.
  const backend = node.risk_score ?? 0
  const blendedScore = backend > 0 ? 0.6 * modelScore + 0.4 * backend : modelScore
  return { id: node.id, modelScore, blendedScore, contributions }
}

// ── Public API ───────────────────────────────────────────────────────────────────
export interface NetworkScoring {
  scores:       NodeRiskScore[]      // every node, sorted by blendedScore desc
  meanScore:    number
  highRiskCount: number              // nodes ≥ 0.6
  topAnomalies: NodeRiskScore[]      // top 5
}

export function scoreNetwork(data: GraphData): NetworkScoring {
  if (data.nodes.length === 0) {
    return { scores: [], meanScore: 0, highRiskCount: 0, topAnomalies: [] }
  }
  const stats  = computeStats(data.nodes)
  const scores = data.nodes.map(n => scoreOne(n, stats)).sort((a, b) => b.blendedScore - a.blendedScore)
  const meanScore = scores.reduce((s, x) => s + x.blendedScore, 0) / scores.length
  const highRiskCount = scores.filter(s => s.blendedScore >= 0.6).length
  return { scores, meanScore, highRiskCount, topAnomalies: scores.slice(0, 5) }
}

/** Score a single node against the current population. */
export function scoreNode(node: GraphNode, data: GraphData): NodeRiskScore {
  const stats = computeStats(data.nodes.length ? data.nodes : [node])
  return scoreOne(node, stats)
}

/** Spoken explanation of a node's model risk — names the driving signals. */
export function explainNodeRisk(node: GraphNode, data: GraphData): string {
  const r = scoreNode(node, data)
  const pct = Math.round(r.blendedScore * 100)
  const drivers = r.contributions
    .filter(c => c.impact > 0.15)
    .slice(0, 3)
    .map(c => `${c.label} (z ${c.z >= 0 ? '+' : ''}${c.z.toFixed(1)})`)
  const driverText = drivers.length
    ? `Top contributing signals: ${drivers.join(', ')}.`
    : 'No single dominant risk signal — score reflects baseline behavior.'
  return `Ensemble risk model scores this account at ${pct} percent. ${driverText}`
}

/** Spoken network-wide model summary, used by the "run anomaly detection" intent. */
export function explainNetworkScoring(data: GraphData): { narration: string; focusNodes: string[]; flagged: boolean } {
  if (data.nodes.length === 0) {
    return { narration: 'No graph loaded. Submit transactions before running the model.', focusNodes: [], flagged: false }
  }
  const s = scoreNetwork(data)
  const top = s.topAnomalies[0]
  const topDrivers = top
    ? top.contributions.filter(c => c.impact > 0.15).slice(0, 2).map(c => c.label)
    : []
  return {
    narration:
      `Anomaly model run complete across ${s.scores.length} accounts. ` +
      `Mean risk ${Math.round(s.meanScore * 100)} percent. ` +
      `${s.highRiskCount} account${s.highRiskCount !== 1 ? 's' : ''} above the high-risk threshold. ` +
      (top
        ? `Top anomaly: ${shortId(top.id)} at ${Math.round(top.blendedScore * 100)} percent` +
          (topDrivers.length ? `, driven by ${topDrivers.join(' and ')}.` : '.')
        : ''),
    focusNodes: s.topAnomalies.map(a => a.id),
    flagged: s.highRiskCount > 0,
  }
}

function shortId(id: string): string {
  return id.length > 14 ? `…${id.slice(-8)}` : id
}
