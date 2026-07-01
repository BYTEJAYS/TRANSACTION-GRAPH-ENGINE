// ── GRAPH ENGINE STORE — application-wide singleton ───────────────────────────
// Previously this was a per-component hook (useState), so the entire graph —
// nodes, links, live transactions, Blue Team verdict, cash animations — was
// destroyed the moment the investigator navigated away from /graph and recreated
// from scratch on return. It now lives in a module-level singleton OUTSIDE the
// React tree, exposed via useSyncExternalStore, so the graph survives navigation
// exactly like the rest of the investigation session. The exported hook keeps the
// same return shape, so App.tsx / CinematicApp.tsx need no changes.
import { useSyncExternalStore } from 'react'
import type {
  GraphNode,
  GraphLink,
  GraphData,
  GraphStats,
  LiveTransaction,
  FraudAlert,
  ClassificationStatus,
  WSGraphUpdate,
  PaymentRail,
  BlueTeamMultiResult,
  GraphComponentResult,
  CashNode,
} from '../types'
import {
  nodeColorFromRisk,
  riskLevelFromScore,
  linkColorFromRisk,
} from '../data/mockGraph'
import { layoutCache } from './layoutCache'

const MAX_TRANSACTIONS = 60
const MAX_ALERTS = 20

function mapNode(n: any, suspicious: Set<string>): GraphNode {
  const risk: number = n.risk_score ?? 0
  const flagged: boolean = n.is_flagged ?? suspicious.has(n.id)
  return {
    id: n.id,
    transaction_count: n.transaction_count ?? 0,
    total_sent: n.total_sent ?? 0,
    total_received: n.total_received ?? 0,
    risk_level: riskLevelFromScore(risk),
    risk_score: risk,
    account_type: n.account_type ?? 'normal',
    detected_patterns: n.detected_patterns ?? [],
    geo_locations: n.geo_locations ?? [],
    is_flagged: flagged,
    incoming_count: n.incoming_count ?? 0,
    outgoing_count: n.outgoing_count ?? 0,
    connected_accounts: n.connected_accounts ?? [],
    last_activity: n.last_activity ?? new Date().toISOString(),
    cash_inflows: n.cash_inflows ?? 0,
    cash_outflows: n.cash_outflows ?? 0,
    cash_inflow_count: n.cash_inflow_count ?? 0,
    cash_outflow_count: n.cash_outflow_count ?? 0,
    // Virtual cash endpoints carry a PERMANENT semantic identity colour that fraud
    // must never override (fraud is shown as a separate red halo overlay, not by
    // recolouring the fill — see GraphScene). Emerald = CASH_SOURCE (cash ENTERED
    // the banking network); Gold = CASH_EXIT (cash LEFT it). Direction is inferred
    // from flow: a source mostly SENDS, a sink mostly RECEIVES. Note: NO `!flagged`
    // guard — identity outranks fraud status by design.
    nodeColor: n.account_type === 'cash'
      ? ((n.total_sent ?? 0) >= (n.total_received ?? 0) ? '#00E676' : '#FFC400')
      : nodeColorFromRisk(risk, flagged),
    nodeSize: 1,
  }
}

function mapLink(e: any): GraphLink {
  const risk: number = e.risk_score ?? 0
  const flagged: boolean = e.is_flagged ?? false
  return {
    id: e.id ?? `${e.source}-${e.target}-${e.timestamp ?? ''}`,
    source: e.source,
    target: e.target,
    amount: e.amount ?? 0,
    payment_rail: (e.payment_rail ?? 'UPI') as PaymentRail,
    timestamp: e.timestamp ?? new Date().toISOString(),
    risk_score: risk,
    is_flagged: flagged,
    linkColor: linkColorFromRisk(risk, flagged),
  }
}

// ── singleton reactive state ──────────────────────────────────────────────────
interface GState {
  graphData: GraphData
  classification: ClassificationStatus
  stats: GraphStats
  recentTransactions: LiveTransaction[]
  alerts: FraudAlert[]
  cashNodes: CashNode[]
  cashAnimIds: ReadonlySet<string>
  blueTeamMultiResult: BlueTeamMultiResult
}

function emptyStats(): GraphStats {
  return { nodeCount: 0, linkCount: 0, flaggedNodes: 0, alertCount: 0, totalVolume: 0, fraudRate: 0 }
}

let g: GState = {
  graphData: { nodes: [], links: [] },
  classification: 'normal',
  stats: emptyStats(),
  recentTransactions: [],
  alerts: [],
  cashNodes: [],
  cashAnimIds: new Set<string>(),
  blueTeamMultiResult: { status: 'idle', graphs: [] },
}

// non-reactive companions (persist across navigation, not part of the snapshot)
const knownNodes = new Set<string>()
const knownLinks = new Set<string>()
let nodeToGraphId = new Map<string, string>()
const cashTimers = new Map<string, ReturnType<typeof setTimeout>>()
// Signature of the last current_transaction we pushed to the ticker. The backend
// re-broadcasts graph_update on a ~1s heartbeat carrying the SAME current
// transaction, so without this guard each heartbeat re-added a duplicate row
// (with a fresh id) — the "same transaction shown multiple times" bug.
let lastTxnSig: string | null = null

const listeners = new Set<() => void>()
function subscribe(cb: () => void) { listeners.add(cb); return () => { listeners.delete(cb) } }
function emit() { listeners.forEach(l => l()) }
function set(patch: Partial<GState>) { g = { ...g, ...patch }; emit() }

// ── actions (stable module-level functions) ───────────────────────────────────
function mergeGraphUpdate(data: WSGraphUpdate) {
  // Backend reset signal (start of a new run): wipe everything so the new
  // scenario never merges into the previous graph.
  if (data.reset) {
    knownNodes.clear()
    knownLinks.clear()
    nodeToGraphId.clear()
    cashTimers.forEach(t => clearTimeout(t))
    cashTimers.clear()
    lastTxnSig = null
    layoutCache.clear()   // new run → discard the persisted layout so it can't restore onto a different graph
    set({
      graphData: { nodes: [], links: [] },
      classification: 'normal',
      stats: emptyStats(),
      recentTransactions: [],
      cashNodes: [],
      cashAnimIds: new Set(),
    })
    return
  }

  const inNodes: any[] = data.nodes ?? []
  const inEdges: any[] = data.edges ?? []
  const suspicious = new Set<string>(data.suspicious_nodes ?? [])

  inNodes.forEach(n => knownNodes.add(n.id))
  inEdges.forEach(e => { knownLinks.add(e.id ?? `${e.source}-${e.target}-${e.timestamp ?? ''}`) })

  const nodeMap = new Map<string, GraphNode>(g.graphData.nodes.map(n => [n.id, n]))
  const linkMap = new Map<string, GraphLink>(g.graphData.links.map(l => [(l as any).id, l]))

  inNodes.forEach(n => {
    const mapped = mapNode(n, suspicious)
    const existing = nodeMap.get(n.id)
    nodeMap.set(n.id, existing ? { ...mapped, x: existing.x, y: existing.y, z: existing.z } : mapped)
  })
  inEdges.forEach(e => {
    const mapped = mapLink(e)
    linkMap.set(mapped.id as string, mapped)
  })

  const nodes = Array.from(nodeMap.values())
  const links = Array.from(linkMap.values())
  const flagged = nodes.filter(n => n.is_flagged).length
  const totalVol = links.reduce((s, l) => s + l.amount, 0)
  const fraudLinks = links.filter(l => l.is_flagged).length

  const patch: Partial<GState> = {
    graphData: { nodes, links },
    stats: {
      nodeCount: nodes.length,
      linkCount: links.length,
      flaggedNodes: flagged,
      alertCount: 0,
      totalVolume: totalVol,
      fraudRate: links.length ? fraudLinks / links.length : 0,
    },
  }
  if (data.status) patch.classification = data.status

  // Cash event: floating cash node + temporary edge animation
  if (data.cash_event) {
    const evt = data.cash_event
    const cashNode: CashNode = {
      id: evt.id,
      cashType: evt.type,
      parentAccount: evt.parent_account,
      amount: evt.amount,
      timestamp: evt.timestamp,
    }
    patch.cashNodes = [...g.cashNodes, cashNode]
    patch.cashAnimIds = new Set([...g.cashAnimIds, evt.id])
    const timer = setTimeout(() => {
      const next = new Set(g.cashAnimIds)
      next.delete(evt.id)
      set({ cashAnimIds: next })
      cashTimers.delete(evt.id)
    }, 2500)
    cashTimers.set(evt.id, timer)
  }

  if (data.current_transaction) {
    const ct = data.current_transaction
    // Dedup: the ~1s heartbeat re-sends the SAME current_transaction, so only add
    // it once. `step` uniquely identifies a transaction within a simulation run;
    // include the endpoints/amount so back-to-back identical-step replays are caught.
    const sig = `${ct.step}|${ct.from_account}|${ct.to_account}|${ct.amount}`
    if (sig !== lastTxnSig) {
      lastTxnSig = sig
      // Recover the REAL payment rail + timestamp from the matching edge in this
      // update (current_transaction itself doesn't carry them) so the ticker shows
      // IMPS/RTGS/NEFT correctly instead of a hardcoded "UPI".
      const edge = inEdges.find(
        (e: any) => String(e.source) === ct.from_account && String(e.target) === ct.to_account
          && Number(e.amount) === ct.amount,
      ) ?? inEdges.find(
        (e: any) => String(e.source) === ct.from_account && String(e.target) === ct.to_account,
      )
      const txn: LiveTransaction = {
        id: `live-${ct.step}-${ct.from_account}-${ct.to_account}`,
        from_account: ct.from_account,
        to_account: ct.to_account,
        amount: ct.amount,
        payment_rail: edge?.payment_rail ?? 'UPI',
        timestamp: edge?.timestamp ?? new Date().toISOString(),
        risk_score: typeof edge?.risk_score === 'number' ? edge.risk_score : 0.5,
        is_flagged: edge?.is_flagged ?? data.status === 'fraud',
      }
      patch.recentTransactions = [txn, ...g.recentTransactions].slice(0, MAX_TRANSACTIONS)
    }
  }

  set(patch)
}

function addAlert(alert: FraudAlert) {
  set({
    alerts: [alert, ...g.alerts].slice(0, MAX_ALERTS),
    stats: { ...g.stats, alertCount: g.stats.alertCount + 1 },
  })
}

function addTransaction(txn: LiveTransaction) {
  set({ recentTransactions: [txn, ...g.recentTransactions].slice(0, MAX_TRANSACTIONS) })
}

function loadMockData(data: GraphData) {
  data.nodes.forEach(n => knownNodes.add(n.id))
  data.links.forEach(l => knownLinks.add(l.id as string))

  const flagged = data.nodes.filter(n => n.is_flagged).length
  const totalVol = data.links.reduce((s, l) => s + l.amount, 0)
  const fraudLinks = data.links.filter(l => l.is_flagged).length

  set({
    graphData: data,
    stats: {
      nodeCount: data.nodes.length,
      linkCount: data.links.length,
      flaggedNodes: flagged,
      alertCount: 0,
      totalVolume: totalVol,
      fraudRate: data.links.length ? fraudLinks / data.links.length : 0,
    },
  })
}

function clearGraph() {
  knownNodes.clear()
  knownLinks.clear()
  nodeToGraphId.clear()
  cashTimers.forEach(t => clearTimeout(t))
  cashTimers.clear()
  layoutCache.clear()   // explicit clear → drop the persisted layout too
  set({
    graphData: { nodes: [], links: [] },
    classification: 'normal',
    stats: emptyStats(),
    recentTransactions: [],
    alerts: [],
    cashNodes: [],
    cashAnimIds: new Set(),
    blueTeamMultiResult: { status: 'idle', graphs: [] },
  })
}

// ── Blue Team multi-graph integration ─────────────────────────────────────────
function setBlueTeamAnalyzing() {
  set({ blueTeamMultiResult: { status: 'analyzing', graphs: [] } })
}

function setBlueTeamMultiVerdict(data: { graphs: GraphComponentResult[] }) {
  const graphs = data.graphs ?? []

  // Build node→graphId lookup
  const newNodeMap = new Map<string, string>()
  graphs.forEach(gr => { gr.nodes.forEach(nid => newNodeMap.set(nid, gr.graph_id)) })
  nodeToGraphId = newNodeMap

  // Color all nodes/links in fraud components red
  const fraudComponentNodeIds = new Set<string>()
  graphs.forEach(gr => {
    if (gr.flagged) {
      gr.nodes.forEach(n => fraudComponentNodeIds.add(n))
      gr.flagged_nodes.forEach(n => fraudComponentNodeIds.add(n))
    }
  })

  if (fraudComponentNodeIds.size === 0) {
    set({ blueTeamMultiResult: { status: 'analyzed', graphs } })
    return
  }

  // Blue Team verdict is the authority on flagged count + fraud rate
  const fraudGraphs = graphs.filter(gr => gr.flagged)
  const blueTeamFraudRate = graphs.length > 0 ? fraudGraphs.length / graphs.length : 0
  const avgRiskScore = fraudGraphs.length > 0
    ? fraudGraphs.reduce((sum, gr) => sum + gr.risk_score, 0) / fraudGraphs.length
    : 0

  set({
    blueTeamMultiResult: { status: 'analyzed', graphs },
    stats: {
      ...g.stats,
      flaggedNodes: Math.max(g.stats.flaggedNodes, fraudComponentNodeIds.size),
      fraudRate: Math.max(g.stats.fraudRate, Math.max(blueTeamFraudRate, avgRiskScore)),
    },
    graphData: {
      nodes: g.graphData.nodes,
      links: g.graphData.links.map(l => {
        const src = typeof l.source === 'string' ? l.source : (l.source as GraphNode).id
        const tgt = typeof l.target === 'string' ? l.target : (l.target as GraphNode).id
        if (fraudComponentNodeIds.has(src) || fraudComponentNodeIds.has(tgt)) {
          return { ...l, linkColor: 'rgba(255,51,102,0.70)', is_flagged: true }
        }
        return l
      }),
    },
  })
}

// ── React binding — same return shape as the original hook ────────────────────
export function useGraphStore() {
  const snap = useSyncExternalStore(subscribe, () => g, () => g)

  // All nodes belonging to fraud-flagged components (drives red coloring)
  const fraudNodeIds = (() => {
    const ids = new Set<string>()
    snap.blueTeamMultiResult.graphs.forEach(gr => {
      if (gr.flagged) {
        gr.nodes.forEach(n => ids.add(n))
        gr.flagged_nodes.forEach(n => ids.add(n))
      }
    })
    return ids
  })()

  // Unified fraud signal — Blue Team verdict is authority; classification is fallback
  const isFraudDetected =
    snap.classification === 'fraud' ||
    snap.blueTeamMultiResult.graphs.some(gr => gr.flagged)

  return {
    graphData: snap.graphData,
    classification: snap.classification,
    stats: snap.stats,
    recentTransactions: snap.recentTransactions,
    alerts: snap.alerts,
    blueTeamMultiResult: snap.blueTeamMultiResult,
    fraudNodeIds,
    isFraudDetected,
    nodeToGraphId,
    cashNodes: snap.cashNodes,
    cashAnimIds: snap.cashAnimIds,
    mergeGraphUpdate,
    addAlert,
    addTransaction,
    loadMockData,
    clearGraph,
    setBlueTeamAnalyzing,
    setBlueTeamMultiVerdict,
  }
}

export type GraphStoreReturn = ReturnType<typeof useGraphStore>
