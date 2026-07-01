import type { GraphData, GraphNode, GraphLink, RiskLevel, PaymentRail } from '../types'

// ─────────────────────────────────────────────────────────────────────────────
// SYNTHETIC OFFLINE-DEMO DATA — NOT A REAL ASSESSMENT.
// This module is the OFFLINE FALLBACK used ONLY when the backend is unreachable
// (App.tsx `generateSample` catch → useGraphSocket `loadDemo`). Whenever the
// backend is up, every risk_score / is_flagged shown in the UI comes from the
// backend Risk Engine (see backend/risk_engine) — never from here.
//
// AUDIT NOTE: it previously used Math.random() for risk_score/is_flagged, which
// produced non-reproducible fabricated fraud numbers indistinguishable from real
// ones. That is now DETERMINISTIC and SEEDED: every value is derived from the
// designed per-cluster `riskBase` via a fixed-seed PRNG, so demo runs are
// reproducible and no fraud field is random. Colours/levels are pure threshold
// maps. Visual-only randomness (node positions, orb, particles) lives elsewhere
// and never touches a fraud number.
// ─────────────────────────────────────────────────────────────────────────────

// mulberry32 — tiny deterministic PRNG. Seeded per generate() call so the demo
// graph is identical on every run (no Math.random anywhere in fraud fields).
function makeRng(seed: number) {
  let s = seed >>> 0
  return () => {
    s |= 0; s = (s + 0x6D2B79F5) | 0
    let t = Math.imul(s ^ (s >>> 15), 1 | s)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const DEMO_SEED = 0x7601   // fixed → the offline demo is byte-for-byte reproducible
let _rng = makeRng(DEMO_SEED)
const R  = (min: number, max: number) => _rng() * (max - min) + min
const RI = (min: number, max: number) => Math.floor(R(min, max + 1))
const P  = <T>(a: readonly T[]): T => a[RI(0, a.length - 1)]

const RAILS: PaymentRail[]   = ['UPI', 'IMPS', 'RTGS', 'NEFT']
const PATTERNS               = ['circular_transfer', 'fan_out', 'layering', 'mule_chain', 'structuring'] as const
const GEOS                   = ['Mumbai', 'Delhi', 'Bangalore', 'Chennai', 'Kolkata', 'Hyderabad', 'Pune', 'Ahmedabad'] as const
const ACCOUNT_TYPES          = ['normal', 'mule', 'high_value', 'merchant'] as const

export function nodeColorFromRisk(score: number, flagged: boolean): string {
  if (flagged || score > 0.85) return '#ff3366'
  if (score > 0.65)            return '#a855f7'
  if (score > 0.45)            return '#f59e0b'
  return '#00f5ff'
}

export function riskLevelFromScore(score: number): RiskLevel {
  if (score > 0.85) return 'critical'
  if (score > 0.65) return 'high'
  if (score > 0.45) return 'moderate'
  return 'safe'
}

export function linkColorFromRisk(score: number, flagged: boolean): string {
  if (flagged || score > 0.7) return 'rgba(255,51,102,0.35)'
  if (score > 0.5)            return 'rgba(168,85,247,0.25)'
  if (score > 0.35)           return 'rgba(245,158,11,0.2)'
  return 'rgba(100,180,255,0.12)'
}

// ── 30 sub-clusters matching the reference's ~188-group multi-color look ────
// riskBase drives the dominant color per cluster; spread adds variety within each
const CLUSTER_DEFS: Array<{ count: number; riskBase: number; type: string }> = [
  // Critical / red (3 clusters)
  { count: 42, riskBase: 0.88, type: 'mule'       },
  { count: 38, riskBase: 0.85, type: 'mule'       },
  { count: 40, riskBase: 0.82, type: 'mule'       },
  // High-risk / purple (5 clusters)
  { count: 36, riskBase: 0.72, type: 'normal'     },
  { count: 34, riskBase: 0.70, type: 'high_value' },
  { count: 30, riskBase: 0.68, type: 'normal'     },
  { count: 38, riskBase: 0.66, type: 'mule'       },
  { count: 32, riskBase: 0.74, type: 'high_value' },
  // Moderate / amber (5 clusters)
  { count: 44, riskBase: 0.58, type: 'high_value' },
  { count: 40, riskBase: 0.52, type: 'normal'     },
  { count: 38, riskBase: 0.48, type: 'high_value' },
  { count: 36, riskBase: 0.55, type: 'normal'     },
  { count: 42, riskBase: 0.50, type: 'high_value' },
  // Safe / cyan (17 clusters — majority, matching reference's dense safe zone)
  { count: 46, riskBase: 0.28, type: 'merchant'   },
  { count: 44, riskBase: 0.22, type: 'normal'     },
  { count: 48, riskBase: 0.18, type: 'merchant'   },
  { count: 40, riskBase: 0.15, type: 'normal'     },
  { count: 46, riskBase: 0.12, type: 'merchant'   },
  { count: 42, riskBase: 0.10, type: 'normal'     },
  { count: 44, riskBase: 0.08, type: 'merchant'   },
  { count: 38, riskBase: 0.25, type: 'normal'     },
  { count: 46, riskBase: 0.32, type: 'merchant'   },
  { count: 40, riskBase: 0.20, type: 'normal'     },
  { count: 44, riskBase: 0.14, type: 'merchant'   },
  { count: 42, riskBase: 0.35, type: 'normal'     },
  { count: 38, riskBase: 0.16, type: 'merchant'   },
  { count: 46, riskBase: 0.09, type: 'normal'     },
  { count: 44, riskBase: 0.30, type: 'merchant'   },
  { count: 40, riskBase: 0.11, type: 'normal'     },
  { count: 42, riskBase: 0.19, type: 'merchant'   },
]

export function generateMockGraph(): GraphData {
  _rng = makeRng(DEMO_SEED)   // reset → deterministic, reproducible offline demo
  const nodes: GraphNode[] = []
  const links: GraphLink[] = []
  const clusterRanges: Array<[number, number]> = []
  let idx = 0

  CLUSTER_DEFS.forEach(({ count, riskBase, type }) => {
    const start = idx
    for (let i = 0; i < count; i++) {
      const id      = `ACC${String(idx + 1000).padStart(6, '0')}`
      const risk    = Math.min(0.99, Math.max(0.01, riskBase + R(-0.15, 0.18)))
      // Deterministic: a node is flagged iff its (designed) risk clears the
      // high-risk threshold. No random gate — the demo is fully reproducible.
      const flagged = risk > 0.78
      nodes.push({
        id,
        transaction_count: RI(5, 250),
        total_sent:        R(2000, 8_000_000),
        total_received:    R(2000, 8_000_000),
        risk_level:        riskLevelFromScore(risk),
        risk_score:        risk,
        account_type:      type,
        detected_patterns: flagged ? [P(PATTERNS)] : ['normal'],
        geo_locations:     Array.from(new Set([P(GEOS), P(GEOS)])),
        is_flagged:        flagged,
        incoming_count:    RI(1, 80),
        outgoing_count:    RI(1, 80),
        connected_accounts: [],
        last_activity:     new Date(Date.now() - R(0, 86400000 * 14)).toISOString(),
        nodeColor:         nodeColorFromRisk(risk, flagged),
        nodeSize:          1,   // uniform — exactly like the reference
      })
      idx++
    }
    clusterRanges.push([start, idx - 1])
  })

  // ── Intra-cluster edges: target ~2.1 links-per-node ratio overall ─────────
  // Each cluster of N nodes gets ~N*1.1 edges  (gives ~2.2 total per node)
  clusterRanges.forEach(([start, end]) => {
    const clusterSize = end - start + 1
    const edgeCount   = Math.round(clusterSize * 1.1)
    for (let i = 0; i < edgeCount; i++) {
      const si = RI(start, end)
      let   ti = RI(start, end)
      if (ti === si) ti = si === end ? start : si + 1
      const s    = nodes[si], t = nodes[ti]
      const risk = (s.risk_score + t.risk_score) / 2
      links.push({
        id: `TXN${String(links.length + 60000).padStart(8, '0')}`,
        source:       s.id,
        target:       t.id,
        amount:       R(300, 800_000),
        payment_rail: P(RAILS),
        timestamp:    new Date(Date.now() - R(0, 86400000 * 6)).toISOString(),
        risk_score:   risk,
        is_flagged:   risk > 0.65,
        linkColor:    linkColorFromRisk(risk, risk > 0.65),
      })
    }
  })

  // ── Sparse inter-cluster bridges (like the reference's cross-user links) ──
  const bridgeCount = Math.round(nodes.length * 0.12) // ~12% of nodes get a bridge
  for (let i = 0; i < bridgeCount; i++) {
    const c1 = RI(0, clusterRanges.length - 1)
    let   c2 = RI(0, clusterRanges.length - 1)
    while (c2 === c1) c2 = RI(0, clusterRanges.length - 1)
    const [s1, e1] = clusterRanges[c1]
    const [s2, e2] = clusterRanges[c2]
    const s    = nodes[RI(s1, e1)]
    const t    = nodes[RI(s2, e2)]
    const risk = (s.risk_score + t.risk_score) / 2
    links.push({
      id: `TXN${String(links.length + 60000).padStart(8, '0')}`,
      source:       s.id,
      target:       t.id,
      amount:       R(10_000, 5_000_000),
      payment_rail: P(RAILS),
      timestamp:    new Date(Date.now() - R(0, 86400000 * 2)).toISOString(),
      risk_score:   risk,
      is_flagged:   risk > 0.72,
      linkColor:    'rgba(100,180,255,0.08)',
    })
  }

  // Build connected_accounts map
  const connMap = new Map<string, Set<string>>()
  links.forEach(l => {
    const s = l.source as string, t = l.target as string
    if (!connMap.has(s)) connMap.set(s, new Set())
    if (!connMap.has(t)) connMap.set(t, new Set())
    connMap.get(s)!.add(t)
    connMap.get(t)!.add(s)
  })
  nodes.forEach(n => { n.connected_accounts = Array.from(connMap.get(n.id) ?? []) })

  return { nodes, links }
}

export function generateMockTransactions(count = 20) {
  // Deterministic synthetic stream for the offline demo. risk_score is derived
  // from the transaction's own amount (higher value → higher demo risk) rather
  // than Math.random(), so it is reproducible and at least explainable AS DEMO
  // DATA. Never used when the backend is reachable.
  _rng = makeRng(DEMO_SEED ^ (count * 0x9E37))
  return Array.from({ length: count }, (_, i) => {
    const amount = R(500, 500_000)
    const risk   = Math.min(0.99, 0.05 + (amount / 500_000) * 0.9)   // amount-driven, deterministic
    return {
      id:           `TXN-LIVE-${String(i).padStart(5, '0')}`,
      from_account: `ACC${String(RI(1000, 1240)).padStart(6, '0')}`,
      to_account:   `ACC${String(RI(1000, 1240)).padStart(6, '0')}`,
      amount,
      payment_rail: P(RAILS),
      timestamp:    new Date(Date.now() - R(0, 3600000)).toISOString(),
      risk_score:   risk,
      is_flagged:   risk > 0.78,
      fraud_pattern: risk > 0.78 ? P(['circular_transfer', 'fan_out', 'layering']) as string : undefined,
    }
  })
}
