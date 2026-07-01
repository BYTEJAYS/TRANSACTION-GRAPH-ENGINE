import { useState, useCallback, useRef, useMemo, useEffect } from 'react'
import { flushSync } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { GraphScene, type GraphSceneHandle, type BackendLayout } from './components/GraphScene'
import { NodeInspector } from './components/NodeInspector'
import { TransactionTicker } from './components/TransactionTicker'
import { UBOrb } from './components/ai/UBOrb'
import { useGraphSocket } from './hooks/useGraphSocket'
import { useGraphStore } from './store/graphStore'
import { useUB, type UBHandlers } from './hooks/useUB'
import { askUB } from './services/ubBrain'
import { buildGreeting, resolveNodeRef } from './ai/ub'
import {
  ABOUT_TGIE, CAPABILITIES, defineTerm, answerSmallTalk, answerConversational,
} from './ai/knowledge'
import { generateEvidencePDF } from './ai/evidence'
import { classifyCluster, spokenAlert, spokenInvestigation } from './ai/graphClassifier'
import { GraphIntelHUD } from './components/GraphIntelHUD'
import { EvidenceBlockchainPanel } from './components/panels/EvidenceBlockchainPanel'
import { LeftPanel } from './components/panels/LeftPanel'
import { RedTeamPanel } from './components/panels/RedTeamPanel'
import { TrainingReviewPanel } from './components/panels/TrainingReviewPanel'
import { EmptyState } from './components/EmptyState'
import { buildSampleTransactions } from './data/sampleDataset'
import { Swords, GraduationCap } from 'lucide-react'
import { useThoughtStream } from './hooks/useThoughtStream'
import * as VoiceService from './services/voiceService'
import VoiceDebugPanel from './components/ai/VoiceDebugPanel'
import {
  summarizeTopology, analyzeFanOut, findCentralAccount, findCircularMovement,
  detectLayering, findMuleAccounts, findHiddenLoops, analyzeNode, findRiskyAccounts,
  type AnalysisResult,
} from './ai/graphAnalysis'
import { explainNetworkScoring } from './ai/riskModel'
import {
  computeRiskIntel, exposureLabel, exposureNarration, roleLabel, type NodeIntel,
} from './ai/riskPropagation'
import { WS_URL, apiUrl, sessionHeaders } from './config'
import { riskValue } from './utils/percent'
import type { GraphNode, WSGraphUpdate, LiveTransaction, FraudAlert } from './types'
import type { GraphComponentResult } from './types'
import type { SimulationState } from './types/transaction'

// ── Design tokens ──────────────────────────────────────────────────────────
const C = {
  bg:      '#000000',
  surface: '#161b22',
  raised:  '#1c2128',
  border:  'rgba(255,255,255,0.08)',
  text1:   '#e6edf3',
  text2:   '#8b949e',
  text3:   '#484f58',
  accent:  '#4493f8',
  cyan:    '#79c0ff',
  warn:    '#d29922',
  danger:  '#f85149',
  success: '#3fb950',
} as const

// ── Small header stat pill ─────────────────────────────────────────────────
function StatChip({ label, value, color = C.text2 }: { label: string; value: string | number; color?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
      <span style={{ fontSize: 11, fontWeight: 600, color, fontVariantNumeric: 'tabular-nums' }}>
        {value}
      </span>
      <span style={{ fontSize: 10, color: C.text3, letterSpacing: '.02em' }}>
        {label}
      </span>
    </div>
  )
}

// ── Thin divider for header ────────────────────────────────────────────────
function Div() {
  return <div style={{ width: 1, height: 16, background: C.border, flexShrink: 0 }} />
}

function fmt(v: number): string {
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(1)}Cr`
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)}L`
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(0)}K`
  return `₹${Math.floor(v)}`
}

// Short wake acknowledgments — used on every wake after the first (full) greeting.
// Rotated randomly without immediate repeats.
const WAKE_ACKS = [
  'Yes.', 'Yes, sir.', 'Aye aye, sir.', 'Yup.', 'Go ahead.',
  'At your service.', 'Standing by.', 'Listening.', 'Ready when you are.',
  'Online.', 'Reporting in.', 'Right here.',
]

export default function App() {
  const {
    graphData,
    classification,
    stats,
    recentTransactions,
    blueTeamMultiResult,
    fraudNodeIds,
    isFraudDetected,
    nodeToGraphId,
    cashNodes,
    cashAnimIds,
    mergeGraphUpdate,
    addAlert,
    addTransaction,
    clearGraph,
    setBlueTeamAnalyzing,
    setBlueTeamMultiVerdict,
  } = useGraphStore()

  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [hoveredNode, setHoveredNode]   = useState<GraphNode | null>(null)

  const [leftOpen,  setLeftOpen]  = useState(false)
  const [isMuted,   setIsMuted]   = useState(false)
  const [monitoring, setMonitoring] = useState(true)

  const [simulationState, setSimulationState] = useState<SimulationState>('idle')
  const [currentStep,     setCurrentStep]     = useState(0)
  const [totalSteps,      setTotalSteps]       = useState(0)
  const [sceneKey, setSceneKey] = useState(0)

  const focusRef      = useRef<((nodeIds: string[]) => void) | null>(null)
  const graphSceneRef = useRef<GraphSceneHandle>(null)
  const isMutedRef = useRef(false)
  useEffect(() => { isMutedRef.current = isMuted }, [isMuted])
  // Latest graph snapshot for use inside WS callbacks (the store is a plain
  // useState hook with no getState()), so auto-activation can classify live data.
  const graphDataRef = useRef(graphData)
  useEffect(() => { graphDataRef.current = graphData }, [graphData])

  // ── Speech-synthesis user-activation unlock ───────────────────────────────
  // PRODUCTION FIX: browsers block audio until a user gesture. We arm a global
  // first-gesture listener that warms the synthesis engine, so narration fired
  // later from timers / WebSocket events is audible on Vercel (not just on
  // localhost, which Chrome treats leniently). See services/voiceService.ts.
  const [speechSupported] = useState(() => VoiceService.isSupported())
  const [voiceDebug] = useState(
    () => typeof window !== 'undefined' &&
      (window.location.search.includes('voicedebug') || localStorage.getItem('voicedebug') === '1'),
  )
  useEffect(() => {
    if (!speechSupported) return
    const teardown = VoiceService.installSpeechUnlock()
    return teardown
  }, [speechSupported])

  // Tracks the last node UB narrated, so auto-narration doesn't repeat itself.
  const lastNarratedNodeRef = useRef<string | null>(null)
  // Wake greeting state: first wake → full time-based greeting, then short acks.
  const wakeCountRef = useRef(0)
  const lastAckRef   = useRef(-1)

  // Blocks stale WS graph_update messages that arrive while a clear is in flight.
  // The backend broadcast loop fires every 500ms; without this gate the old graph
  // data arrives before the HTTP /graph/clear response, making the delete look broken.
  const isClearingRef = useRef(false)
  const [isClearing, setIsClearing] = useState(false)
  const [showClearAnim, setShowClearAnim] = useState(false)
  const clearAnimTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [graphComponents, setGraphComponents] = useState<GraphComponentResult[]>([])
  // Server-computed investigation layout (backend decides the topology via
  // mode=auto). Fed to GraphScene as node positioning targets — no UI/control.
  const [backendLayout, setBackendLayout] = useState<BackendLayout | null>(null)
  const [evidence, setEvidence] = useState<{ blobUrl: string; filename: string; caseRef: string } | null>(null)
  const [orbVisible, setOrbVisible] = useState(false)
  // Which flagged cluster the Graph Intelligence HUD currently displays.
  const [hudClusterIdx, setHudClusterIdx] = useState(0)
  // Intel HUD is hidden by default — surfaces only when UB is asked for it.
  const [intelVisible, setIntelVisible] = useState(false)
  // Red Team demo panel — LOCALHOST ONLY (never on the deployed/GitHub build).
  const [redTeamOpen, setRedTeamOpen] = useState(false)
  const [trainingOpen, setTrainingOpen] = useState(false)
  const isLocalhost = useMemo(
    () => typeof location !== 'undefined' && /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname),
    [],
  )

  // ── UB voice copilot ──────────────────────────────────────────────────────
  // Handlers are built below the store-dependent helpers; provided as a ref
  // so we don't churn the hook on every render.
  const handlersRef = useRef<UBHandlers>({})
  const ub = useUB({
    handlers: handlersRef.current,
    muted: isMuted,
    onWake: () => {
      // Ambient activation: just wake the orb + chime. NO panel auto-open.
      // Speak a SHORT, non-terminal acknowledgment — UB then keeps listening for
      // the actual command (see keepListeningRef in useUB).
      setOrbVisible(true)
      playChime()
      if (isMutedRef.current) return
      const n = wakeCountRef.current++
      if (n === 0) {
        ub.speak('UB online. Listening.')
      } else {
        let i = Math.floor(Math.random() * WAKE_ACKS.length)
        if (i === lastAckRef.current) i = (i + 1) % WAKE_ACKS.length
        lastAckRef.current = i
        ub.speak(WAKE_ACKS[i])
      }
    },
    onUnknown: (t) => {
      // If the utterance names a real account, just open it.
      const ref = resolveNodeRef(t, graphData.nodes.map(n => n.id))
      if (ref) { handlersRef.current.open_node?.(t); return }
      // Free-form question / conversation → ask the local UB brain (Ollama RAG).
      askBrainAndSpeak(t)
    },
  })

  // Ask the local UB brain and SPEAK the reply. `chat` mode auto-routes small talk
  // ("how are you", "what can you do") to UB's conversational persona and real
  // questions to RAG over the codebase. `fallback` runs if the brain is unreachable
  // (offline-safe). Spoken text is sanitized so citations/markdown sound natural aloud.
  const askBrainAndSpeak = useCallback((t: string, fallback?: () => void) => {
    const localFallback = fallback ?? (() => {
      const reply = answerConversational(t)
      ub.speak(reply ?? `I didn't quite catch that. You can ask me about TGIE — the architecture, the Blue Team, the Red Team, the graph engine — or say "what can you do".`)
    })
    setOrbVisible(true)
    askUB(t, 'chat')
      .then(res => {
        const answer = (res.answer ?? '').trim()
        if (!answer) { localFallback(); return }
        const spoken = answer
          .replace(/`+/g, '')
          .replace(/\((?:see|source[s]?:?)[^)]*\)/gi, '')
          .replace(/^[\s*\-•\d.]+/gm, '')
          .replace(/\s+/g, ' ')
          .trim()
        ub.speak(spoken || answer)
      })
      .catch(() => localFallback())
  }, [ub])

  // ── Unified risk-intelligence state ───────────────────────────────────────
  // ONE source of truth: every tooltip, the inspector, the graph glow, the top
  // bar, and UB all read propagated risk + exposure from here. Fixes the
  // "cluster is FRAUD but node reads 0%" contradiction.
  const riskIntel = useMemo(
    () => computeRiskIntel(graphData, graphComponents, fraudNodeIds),
    [graphData, graphComponents, fraudNodeIds],
  )

  // ── Fetch the server-computed investigation layout (backend chooses topology)
  // Keyed on the node-set signature so the ~1s heartbeat (same nodes) doesn't
  // refetch; a structural change (new account) refreshes it. The backend layout
  // is deterministic, so positions stay stable for an unchanged graph. On any
  // failure we fall back silently to the local layout.
  const graphNodeSig = useMemo(
    () => graphData.nodes.map(n => n.id).sort().join(','),
    [graphData],
  )
  useEffect(() => {
    if (graphData.nodes.length === 0) {
      setBackendLayout(null)
      return
    }
    let cancelled = false
    const ac = new AbortController()
    ;(async () => {
      try {
        const res = await fetch(apiUrl('/api/graph/layout?mode=auto'), {
          headers: sessionHeaders(), signal: ac.signal,
        })
        if (!res.ok) throw new Error(`layout ${res.status}`)
        const data = (await res.json()) as BackendLayout
        if (!cancelled) setBackendLayout(data?.positions ? data : null)
      } catch (err) {
        if (!cancelled && (err as Error).name !== 'AbortError') {
          console.warn('[TGIE] backend layout fetch failed; using local layout', err)
          setBackendLayout(null)
        }
      }
    })()
    return () => { cancelled = true; ac.abort() }
  }, [graphNodeSig, graphData.nodes.length])

  const selectedClusterNodeIds = useMemo<ReadonlySet<string> | null>(() => {
    if (!selectedNode || graphComponents.length === 0) return null
    const gid  = nodeToGraphId.get(selectedNode.id)
    if (!gid) return null
    const comp = graphComponents.find(g => g.graph_id === gid)
    return comp ? new Set(comp.nodes) : null
  }, [selectedNode, graphComponents, nodeToGraphId])

  // ── WebSocket ──────────────────────────────────────────────────────────────
  const onMessage = useCallback((type: string, data: unknown) => {
    if (isClearingRef.current) return
    switch (type) {
      case 'graph_update': {
        const upd = data as WSGraphUpdate
        if (upd.reset) {
          // New run starting — reset all App-level fraud state + remount scene.
          setGraphComponents([])
          setBlueTeamMultiVerdict({ graphs: [] })
          setSelectedNode(null)
          setHoveredNode(null)
          setSceneKey(k => k + 1)
          mergeGraphUpdate(upd)
          break
        }
        if (upd.current_transaction) {
          setCurrentStep(upd.current_transaction.step)
          setTotalSteps(upd.current_transaction.total)
        }
        mergeGraphUpdate(upd)
        break
      }
      case 'simulation_complete': {
        mergeGraphUpdate(data as WSGraphUpdate)
        setSimulationState('completed')
        break
      }
      case 'blue_team_analyzing': {
        setBlueTeamAnalyzing()
        setGraphComponents([])
        break
      }
      case 'blue_team_multi_verdict': {
        const payload = data as { graphs: GraphComponentResult[] }
        setBlueTeamMultiVerdict(payload)
        setGraphComponents(payload.graphs ?? [])
        const fraudGraphs = (payload.graphs ?? []).filter(g => g.flagged && g.verdict === 'FRAUD')
        if (fraudGraphs.length > 0 && monitoring) {
          // Do NOT auto-open any intel panel — the orb wakes and narrates the
          // alert, but the intelligence panels surface ONLY when the user asks
          // UB for them ("show intel"). UB still reacts like a live fraud
          // monitor: classifies the worst cluster and speaks a specific alert.
          setHudClusterIdx(0)
          setOrbVisible(true)
          ub.setFraudMode(true)
          if (!isMutedRef.current) {
            const worst = fraudGraphs.reduce((a, b) => riskValue(a) > riskValue(b) ? a : b)
            const intel = classifyCluster(worst, graphDataRef.current)
            // Brief beat before speaking so the alert state reads first.
            setTimeout(() => {
              ub.speak(spokenAlert(intel, fraudGraphs.length), () => ub.setFraudMode(false))
            }, 500)
          }
        }
        break
      }
      case 'transaction':
        addTransaction(data as LiveTransaction)
        break
      case 'fraud_alert':
        addAlert(data as FraudAlert)
        break
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mergeGraphUpdate, addTransaction, addAlert, setBlueTeamAnalyzing, setBlueTeamMultiVerdict, monitoring])

  const { connected, loadDemo } = useGraphSocket({ url: WS_URL, onMessage })

  // ── Simulation controls ────────────────────────────────────────────────────
  const onRunSimulation = useCallback(async (json: string) => {
    try {
      const transactions = JSON.parse(json) as Array<unknown>
      setSimulationState('running')
      setCurrentStep(0)
      setTotalSteps(transactions.length)
      setBlueTeamMultiVerdict({ graphs: [] })
      await fetch(apiUrl('/transaction/manual'), {
        method: 'POST',
        headers: sessionHeaders({ 'Content-Type': 'application/json' }),
        body: json,
      })
    } catch {
      setSimulationState('idle')
    }
  }, [setBlueTeamMultiVerdict])

  // ── Generate the unified sample network (empty-state button) ───────────────
  // One simulation, all data types — legit traffic + cash AML layering + a fraud
  // ring — fed together (see buildSampleTransactions). Prefers the real engine so
  // the full intelligence summary populates; falls back to an offline demo graph
  // only if the backend is unreachable.
  const generateSample = useCallback(async () => {
    const now = Date.now()
    const t = (s: number) => new Date(now + s * 1000).toISOString()
    const sample = buildSampleTransactions(t)
    setSimulationState('running'); setCurrentStep(0); setTotalSteps(sample.length)
    setBlueTeamMultiVerdict({ graphs: [] })
    try {
      const res = await fetch(apiUrl('/transaction/manual'), {
        method: 'POST', headers: sessionHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(sample),
      })
      if (!res.ok) throw new Error('engine unavailable')
    } catch {
      // Offline fallback — show a local demo graph so the canvas isn't empty.
      setSimulationState('idle')
      loadDemo()
    }
  }, [setBlueTeamMultiVerdict, loadDemo])

  const onClearGraph = useCallback(async () => {
    if (clearAnimTimerRef.current) clearTimeout(clearAnimTimerRef.current)
    isClearingRef.current = true

    // ── Step 1: imperatively nuke the Three.js scene right now ──────────────
    // This calls fg.graphData({nodes:[],links:[]}) on the live ForceGraph3D
    // instance — bypassing React prop diffing — and clears our internal caches.
    graphSceneRef.current?.nuke()

    // ── Step 2: show fade overlay + reset every piece of React/Zustand state ─
    flushSync(() => {
      setShowClearAnim(true)
      setIsClearing(true)
      clearGraph()
      setSceneKey(k => k + 1)   // remount GraphScene with fresh empty data
      setSimulationState('idle')
      setCurrentStep(0)
      setTotalSteps(0)
      setGraphComponents([])
      setSelectedNode(null)
      setHoveredNode(null)
    })

    // ── Step 3: tell backend to clear (3 s timeout so isClearing never hangs) ─
    const ac = new AbortController()
    const fetchTimeout = setTimeout(() => ac.abort(), 3000)
    try {
      await fetch(apiUrl('/graph/clear'), { method: 'POST', headers: sessionHeaders(), signal: ac.signal })
    } catch { /* ignore — network errors or abort */ } finally {
      clearTimeout(fetchTimeout)
    }

    setIsClearing(false)
    // ── Step 4: hold overlay 1 s (covers the 0.5 s backend broadcast interval)
    // then fade it out and open the WS gate ───────────────────────────────────
    clearAnimTimerRef.current = setTimeout(() => {
      setShowClearAnim(false)
      isClearingRef.current = false
    }, 1000)
  }, [clearGraph])

  const onFocusGraph   = useCallback((_gid: string, nodeIds: string[]) => focusRef.current?.(nodeIds), [])
  const handleNodeClick   = useCallback((node: GraphNode | null) => setSelectedNode(node), [])
  const handleHoverChange = useCallback((node: GraphNode | null) => setHoveredNode(node), [])

  const hoveredGraphId = hoveredNode ? nodeToGraphId.get(hoveredNode.id) : undefined
  const hoveredComp    = hoveredGraphId ? graphComponents.find(g => g.graph_id === hoveredGraphId) : undefined
  const hoveredIntel   = hoveredNode ? riskIntel.byNode.get(hoveredNode.id) ?? null : null
  const isHoveredFraud = (hoveredIntel?.clusterFlagged ?? false) || hoveredComp?.flagged || (hoveredNode ? fraudNodeIds.has(hoveredNode.id) : false)

  const isFraud = isFraudDetected || (classification === 'fraud')

  // ── UB intent handlers ────────────────────────────────────────────────────
  // Rebound on each render so they see fresh store state without restarting
  // the SpeechRecognition session.
  const flaggedGraphs = useMemo(() => graphComponents.filter(g => g.flagged), [graphComponents])
  const orderedFlagged = useMemo(
    () => [...flaggedGraphs].sort((a, b) => riskValue(b) - riskValue(a)),
    [flaggedGraphs],
  )
  const worstGraph = orderedFlagged[0]

  // ── Live classifier output for the cluster shown in the intelligence HUD ────
  const hudCluster = orderedFlagged.length
    ? orderedFlagged[Math.min(hudClusterIdx, orderedFlagged.length - 1)]
    : null
  const hudIntel = useMemo(
    () => (hudCluster ? classifyCluster(hudCluster, graphData, riskIntel.byNode) : null),
    [hudCluster, graphData, riskIntel],
  )

  // ── Live investigation thought stream ──────────────────────────────────────
  const { thoughts, push: pushThought } = useThoughtStream({
    nodeCount:    stats.nodeCount,
    linkCount:    stats.linkCount,
    flaggedNodes: stats.flaggedNodes,
    fraudRate:    stats.fraudRate,
    clusters:     graphComponents.length,
    worstRisk:    riskValue(worstGraph),
    monitoring,
  })

  // Runs a topology AnalysisResult: highlights nodes, logs a thought, speaks.
  const runAnalysis = useCallback((res: AnalysisResult) => {
    if (res.focusNodes.length) focusRef.current?.(res.focusNodes)
    pushThought(res.narration, res.flagged ? 'alert' : 'scan')
    ub.speak(res.narration)
  }, [ub, pushThought])

  // Opens a node in the inspector + frames the camera. Selecting it triggers
  // the auto-narration effect, so the node is both shown AND analyzed aloud.
  const revealNode = useCallback((node: GraphNode) => {
    setSelectedNode(node)
    focusRef.current?.([node.id])
  }, [])

  const generateEvidence = useCallback(() => {
    if (!flaggedGraphs.length) {
      ub.speak('No active fraud clusters. Run a simulation to generate evidence.')
      return
    }
    ub.speak('Compiling evidence package.', () => {
      const result = generateEvidencePDF({
        graphs: graphComponents,
        graphData,
        fraudNodeIds,
        riskByNode: riskIntel.byNode,
      })
      setEvidence(result)
      ub.speak('Evidence package prepared.')
    })
  }, [flaggedGraphs.length, graphComponents, graphData, fraudNodeIds, riskIntel, ub])

  // ── Live investigation (spec #13) ──────────────────────────────────────────
  // Classifies the focused cluster, frames it, and narrates a full conversational
  // briefing: pattern, confidence, scale, source, sink, severity, recommendation.
  const investigateCluster = useCallback(() => {
    if (!hudCluster || !hudIntel) {
      ub.speak('No active fraud cluster to investigate. Run a simulation to generate one.')
      return
    }
    focusRef.current?.(hudCluster.nodes)
    pushThought(
      `Investigating ${hudCluster.graph_id} — ${hudIntel.typeLabel} at ${Math.round(hudIntel.confidence * 100)}% confidence`,
      'alert',
    )
    ub.speak(spokenInvestigation(hudIntel))
  }, [hudCluster, hudIntel, ub, pushThought])

  handlersRef.current = {
    summarise_fraud: () => {
      if (!flaggedGraphs.length) { ub.speak('No fraud detected. Network behavior is within parameters.'); return }
      ub.speak(`${flaggedGraphs.length} cluster${flaggedGraphs.length > 1 ? 's' : ''} flagged. ` +
               `Highest risk: ${Math.round(riskValue(worstGraph) * 100)} percent in ${worstGraph?.graph_id ?? 'unknown'}. ` +
               `Reason: ${(worstGraph?.suspicious_reason ?? 'unspecified').replace(/_/g, ' ')}.`)
    },
    fraud_type: () => {
      if (!hudIntel) { ub.speak('No active fraud classification. Run a simulation first.'); return }
      ub.speak(`This cluster classifies as ${hudIntel.typeLabel.toLowerCase()}, ` +
               `confidence ${Math.round(hudIntel.confidence * 100)} percent. ` +
               `Severity ${hudIntel.severity.toLowerCase()}.`)
    },
    investigate_graph: investigateCluster,
    graph_details: () => {
      ub.speak(`Graph contains ${stats.nodeCount} nodes and ${stats.linkCount} edges. ` +
               `${stats.flaggedNodes} flagged. Total volume ${fmt(stats.totalVolume)}.`)
    },
    explain_node: (t: string) => {
      // Resolve a spoken account reference; otherwise fall back to the selection.
      const ref = resolveNodeRef(t ?? '', graphData.nodes.map(n => n.id))
      const target = ref ? graphData.nodes.find(n => n.id === ref) ?? null : selectedNode
      if (!target) { ub.speak('Name or click an account first — for example, "open account 2001".'); return }
      if (target.id !== selectedNode?.id) { revealNode(target); return }  // effect narrates
      const res = analyzeNode(target, graphData, riskIntel.byNode.get(target.id) ?? null)
      pushThought(res.narration, res.flagged ? 'alert' : 'scan')
      ub.speak(res.narration)
    },
    alert_trigger: () => {
      if (!worstGraph) { ub.speak('No alerts active.'); return }
      ub.speak(`Alert triggered by ${(worstGraph.suspicious_reason ?? 'anomaly').replace(/_/g, ' ')}, ` +
               `risk ${Math.round(riskValue(worstGraph) * 100)} percent.`)
    },
    show_path: () => {
      if (!worstGraph) { ub.speak('No suspicious path available.'); return }
      focusRef.current?.(worstGraph.nodes)
      ub.speak(`Highlighting ${worstGraph.nodes.length} nodes in cluster ${worstGraph.graph_id}.`)
    },
    risk_score: () => {
      if (!worstGraph) { ub.speak('Current risk: zero. No flagged clusters.'); return }
      const pct = Math.round(riskValue(worstGraph) * 100)
      const sev = pct >= 85 ? 'critical' : pct >= 70 ? 'high' : pct >= 50 ? 'moderate' : 'low'
      ub.speak(`Risk ${pct} percent. Severity ${sev}.`)
    },
    generate_evidence: generateEvidence,
    start_monitoring: () => {
      setMonitoring(true)
      ub.speak('Monitoring resumed. Network analysis active.')
    },
    stop_monitoring: () => {
      setMonitoring(false)
      ub.speak('Monitoring paused. New alerts will be suppressed.')
    },
    sleep: () => {
      // Acknowledge, then force-hide the orb regardless of the idle timer.
      // Wake-word SR keeps running silently; next "UB" brings the orb back.
      ub.speak('Entering sleep mode.', () => setOrbVisible(false))
    },
    greeting: (t: string) => askBrainAndSpeak(t, () =>
      ub.speak(buildGreeting({ hasFraud: flaggedGraphs.length > 0, clusters: flaggedGraphs.length }))),
    thanks:  () => ub.speak('Anytime — happy to help.'),
    cancel:  () => ub.stop(),
    entities_count: () => {
      const total   = stats.nodeCount
      const flagged = fraudNodeIds.size
      ub.speak(
        flagged > 0
          ? `${total} accounts in the transaction network. ${flagged} flagged as suspicious across ${flaggedGraphs.length} cluster${flaggedGraphs.length !== 1 ? 's' : ''}.`
          : `${total} accounts currently in the graph. No flagged entities detected.`
      )
    },
    fraud_origin: () => {
      if (!worstGraph) { ub.speak('No active fraud cluster. Run a simulation to identify origin accounts.'); return }
      ub.speak(
        `Fraud cluster ${worstGraph.graph_id} involves ${worstGraph.nodes.length} accounts. The primary entry vector is the node with highest outgoing transaction frequency. Risk score: ${Math.round(riskValue(worstGraph) * 100)} percent.`
      )
    },
    show_suspicious: () => {
      if (!flaggedGraphs.length) { ub.speak('No suspicious nodes detected. Network appears clean.'); return }
      const ids = Array.from(fraudNodeIds)
      focusRef.current?.(ids)
      ub.speak(`Highlighting ${ids.length} suspicious account${ids.length !== 1 ? 's' : ''} across ${flaggedGraphs.length} flagged cluster${flaggedGraphs.length !== 1 ? 's' : ''}.`)
    },
    money_flow: () => {
      if (!worstGraph) { ub.speak('No active transaction flow to trace. Submit transactions to begin analysis.'); return }
      focusRef.current?.(worstGraph.nodes)
      ub.speak(`Tracing money flow through cluster ${worstGraph.graph_id}. ${worstGraph.nodes.length} accounts in the chain. Risk: ${Math.round(riskValue(worstGraph) * 100)} percent.`)
    },
    system_status: () => {
      ub.speak(
        `Transaction Graph Intelligence Engine operational. ${stats.nodeCount} nodes, ${stats.linkCount} edges active. Fraud rate ${(stats.fraudRate * 100).toFixed(1)} percent. Blue Team analysis ${blueTeamMultiResult.status}. All systems nominal.`
      )
    },
    connected_accounts: () => {
      if (!selectedNode) { ub.speak('No node selected. Click a node on the graph first, then ask again.'); return }
      const connected = selectedNode.connected_accounts ?? []
      ub.speak(
        connected.length > 0
          ? `Account ${selectedNode.id} has ${connected.length} direct connection${connected.length !== 1 ? 's' : ''}. Risk score ${(selectedNode.risk_score * 100).toFixed(0)} percent. ${selectedNode.is_flagged ? 'Flagged as suspicious.' : 'Not currently flagged.'}`
          : `Account ${selectedNode.id} shows no connected accounts in the current graph.`
      )
    },

    // ── Deep topology analysis (computed live from graphData) ────────────────
    explain_topology:  () => runAnalysis(summarizeTopology(graphData)),
    analyze_fanout:    () => runAnalysis(analyzeFanOut(graphData)),
    find_central:      () => runAnalysis(findCentralAccount(graphData)),
    find_circular:     () => runAnalysis(findCircularMovement(graphData)),
    detect_laundering: () => runAnalysis(detectLayering(graphData)),
    find_mules:        () => runAnalysis(findMuleAccounts(graphData)),
    hidden_loops:      () => runAnalysis(findHiddenLoops(graphData)),
    risky_accounts:    () => runAnalysis(findRiskyAccounts(graphData, fraudNodeIds)),
    anomaly_scan:      () => {
      pushThought('Running ensemble anomaly model…', 'scan')
      runAnalysis(explainNetworkScoring(graphData))
    },
    explain_cluster:   () => {
      if (selectedNode && selectedClusterNodeIds) {
        const ids = Array.from(selectedClusterNodeIds)
        focusRef.current?.(ids)
        const gid = nodeToGraphId.get(selectedNode.id)
        const comp = graphComponents.find(g => g.graph_id === gid)
        const reason = comp?.suspicious_reason?.replace(/_/g, ' ')
        ub.speak(
          `Cluster ${gid ?? 'selected'} contains ${ids.length} accounts. ` +
          (comp?.flagged
            ? `Flagged at ${Math.round(riskValue(comp) * 100)} percent. ${reason ? `Reason: ${reason}.` : ''}`
            : 'No fraud signature on this cluster — behavior within parameters.')
        )
        pushThought(`Focused cluster ${gid ?? ''} — ${ids.length} accounts`, comp?.flagged ? 'alert' : 'scan')
      } else if (worstGraph) {
        focusRef.current?.(worstGraph.nodes)
        ub.speak(`No cluster selected. Focusing the highest-risk cluster ${worstGraph.graph_id}, ${worstGraph.nodes.length} accounts.`)
      } else {
        ub.speak('No cluster selected. Click any node to choose a cluster, then ask again.')
      }
    },

    // ── Camera control ────────────────────────────────────────────────────────
    zoom_in:      () => { graphSceneRef.current?.zoomIn();      pushThought('Zooming in.', 'info') },
    zoom_out:     () => { graphSceneRef.current?.zoomOut();     pushThought('Zooming out.', 'info') },
    reset_camera: () => { graphSceneRef.current?.resetCamera(); ub.speak('Camera reset.'); pushThought('Camera reset.', 'info') },
    focus_center: () => { graphSceneRef.current?.focusCenter(); pushThought('Re-centering view.', 'info') },
    show_all:     () => { graphSceneRef.current?.showAll();     ub.speak('Framing the entire network.'); pushThought('Framing full graph.', 'info') },
    track_node:   () => {
      if (!selectedNode) { ub.speak('No node selected. Click a node to track it.'); return }
      focusRef.current?.([selectedNode.id])
      pushThought(`Tracking account ${selectedNode.id}`, 'scan')
    },

    // ── Voice control ─────────────────────────────────────────────────────────
    repeat:       () => { const last = VoiceService.getLastSpoken(); if (last) ub.speak(last); else ub.speak('Nothing to repeat yet.') },
    speak_slower: () => { const r = VoiceService.slowDown(); ub.speak(r === 'minimum' ? 'Already at the slowest setting.' : 'Slowing down.') },
    speak_faster: () => { const r = VoiceService.speedUp(); ub.speak(r === 'maximum' ? 'Already at the fastest setting.' : 'Speeding up.') },
    continue:     () => { const last = VoiceService.getLastSpoken(); if (last) ub.speak(last) },

    // ── UI control ────────────────────────────────────────────────────────────
    show_alerts:   () => {
      ub.speak(
        flaggedGraphs.length
          ? `Opening alerts. ${flaggedGraphs.length} active fraud cluster${flaggedGraphs.length !== 1 ? 's' : ''}.`
          : 'Opening intelligence panel. No active alerts.'
      )
    },
    show_intel:    () => {
      // Surface the compact Graph Intelligence HUD.
      setIntelVisible(true)
      if (!orderedFlagged.length) { ub.speak('Opening the intelligence panel. No fraud clusters flagged yet — run a simulation to populate it.'); return }
      const top = orderedFlagged[0]
      ub.speak(`Opening the intelligence panel. ${orderedFlagged.length} flagged cluster${orderedFlagged.length !== 1 ? 's' : ''}. Highest risk: ${top.graph_id} at ${Math.round(riskValue(top) * 100)} percent.`)
    },
    hide_intel:    () => { setIntelVisible(false); ub.speak('Closing the intelligence panel.') },
    toggle_labels: () => ub.speak('Label visibility is controlled from the graph view.'),
    scan_mode:     () => { pushThought('Scan mode engaged — sweeping topology.', 'scan'); ub.speak('Scan mode engaged. Sweeping network topology.') },

    // ── Node interaction — open the account in the inspector ──────────────────
    open_node: (t: string) => {
      const ids = graphData.nodes.map(n => n.id)
      const ref = resolveNodeRef(t ?? '', ids)
      if (!ref) {
        ub.speak(
          ids.length
            ? 'Which account should I open? Say its number or name — for example, "open account 2001".'
            : 'No graph loaded yet. Submit transactions, then I can open any account.'
        )
        return
      }
      const node = graphData.nodes.find(n => n.id === ref)
      if (!node) { ub.speak('That account is not in the current graph.'); return }
      if (node.id === selectedNode?.id) {
        const res = analyzeNode(node, graphData, riskIntel.byNode.get(node.id) ?? null)
        pushThought(res.narration, res.flagged ? 'alert' : 'scan')
        ub.speak(res.narration)
        return
      }
      pushThought(`Opening account ${node.id}`, 'scan')
      revealNode(node)   // auto-narration effect analyzes it aloud
    },

    // ── Conversation + knowledge ──────────────────────────────────────────────
    help:  () => ub.speak(CAPABILITIES),
    about: (t: string) => askBrainAndSpeak(t, () =>
      ub.speak(answerConversational(t ?? '') ?? ABOUT_TGIE)),
    define: (t: string) => {
      const def = defineTerm(t ?? '')
      ub.speak(def ?? 'I can define fraud terms like fan-out, layering, smurfing, mule accounts, cycles, and centrality. Which one?')
    },
    smalltalk: (t: string) => askBrainAndSpeak(t, () =>
      ub.speak(answerSmallTalk(t ?? '') ?? answerConversational(t ?? '') ?? 'I am here, monitoring the network.')),
  }

  // ── Auto-arm the mic on open — ONLY if already granted ────────────────────
  // If permission is already granted, start listening silently (no prompt) so
  // the user can just say "UB …" the moment the page opens. If it's NOT yet
  // granted, do NOTHING automatically: repeatedly calling getUserMedia without
  // a user gesture makes Chrome auto-block the site (the crossed-out mic icon).
  // First-time grant happens via an explicit click on the mic button below.
  const autoEnabledRef = useRef(false)
  useEffect(() => {
    if (autoEnabledRef.current) return
    autoEnabledRef.current = true
    const perms = (navigator as any).permissions
    if (!perms?.query) return
    perms.query({ name: 'microphone' as PermissionName })
      .then((s: PermissionStatus) => { if (s.state === 'granted') ub.enableWake() })
      .catch(() => { /* Permissions API unavailable — first-gesture grant handles it */ })
  }, [ub])

  // ── First-gesture wake-word start (replaces the removed mic button) ────────
  // The auto-arm above only fires when permission is ALREADY granted; the very
  // first start used to require clicking the mic icon. With that icon gone, the
  // FIRST interaction anywhere starts the recognizer. We do NOT pre-gate on
  // getUserMedia — SpeechRecognition manages its own microphone, and a flaky/absent
  // getUserMedia (e.g. NotFoundError) must not block it. We retry on each gesture
  // until the recognizer is actually listening; precise failures surface via
  // ub.lastError (sr.onerror) in the hint below.
  const wakeRef = useRef(false)
  useEffect(() => { wakeRef.current = ub.wakeEnabled }, [ub.wakeEnabled])
  const [micHint, setMicHint] = useState<string | null>(null)
  useEffect(() => {
    if (!window.isSecureContext) {
      setMicHint('Voice needs https or http://localhost — open the app on localhost (not a LAN IP).')
    }
    const events = ['pointerdown', 'keydown', 'touchstart'] as const
    const grant = () => {
      if (wakeRef.current) { teardown(); return }   // already listening — done
      ub.enableWake()                               // SR starts its own mic; harmless if already running
    }
    const teardown = () => events.forEach(ev => window.removeEventListener(ev, grant, true))
    events.forEach(ev => window.addEventListener(ev, grant, true))
    ;(window as any).__enableMic = () => ub.enableWake()   // manual fallback from devtools
    console.log('[mic] first-gesture wake arming — secureContext=', window.isSecureContext,
      'SpeechRecognition=', !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition),
      'mediaDevices=', !!navigator.mediaDevices)
    return teardown
  }, [ub.enableWake])

  // ── Activation chime — short cinematic ping on wake-word fire ──────────────
  const chimeCtxRef = useRef<AudioContext | null>(null)
  const playChime = useCallback(() => {
    try {
      const W = window as unknown as { AudioContext?: typeof AudioContext; webkitAudioContext?: typeof AudioContext }
      const Ctor = W.AudioContext ?? W.webkitAudioContext
      if (!Ctor) return
      if (!chimeCtxRef.current) chimeCtxRef.current = new Ctor()
      const ctx = chimeCtxRef.current
      // An AudioContext created outside a user gesture starts 'suspended' and
      // stays silent until resumed — resume defensively before every chime.
      if (ctx.state === 'suspended') ctx.resume().catch(() => {})
      const t0 = ctx.currentTime
      const o = ctx.createOscillator()
      const g = ctx.createGain()
      o.type = 'sine'
      o.frequency.setValueAtTime(880,  t0)
      o.frequency.exponentialRampToValueAtTime(1320, t0 + 0.18)
      g.gain.setValueAtTime(0.0001, t0)
      g.gain.linearRampToValueAtTime(0.07, t0 + 0.02)
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.40)
      o.connect(g); g.connect(ctx.destination)
      o.start(t0); o.stop(t0 + 0.45)
    } catch { /* noop */ }
  }, [])

  // Chime + greeting now fire from useUB's onWake callback (fresh wake only),
  // so UB greets on every call — full greeting first, short acks thereafter.

  // ── Stealth visibility ────────────────────────────────────────────────────
  // Default: hidden. Only appears when UB is actively engaged. Hides
  // immediately if the conversational right-panel is opened (avoid duplicate
  // UI), and auto-hides 8 s after returning to idle.
  const ubActive = ub.armedForCmd
    || ub.voiceState === 'listening'
    || ub.voiceState === 'processing'
    || ub.voiceState === 'speaking'
    || ub.voiceState === 'fraud'

  useEffect(() => {
    // Stealth: UB is hidden by default and only surfaces when it's actually
    // called — wake word, listening, processing, speaking, or a fraud alert.
    // Once it returns to idle it lingers briefly, then fades back out.
    if (ubActive) { setOrbVisible(true); return }
    if (!orbVisible) return
    const id = setTimeout(() => setOrbVisible(false), 8000)
    return () => clearTimeout(id)
  }, [ubActive, orbVisible])

  // ── Auto-reactivity: narrate a node the instant it's selected ─────────────
  // UB behaves like a live analyst — clicking a node triggers an immediate,
  // data-driven read of its behavior without any spoken prompt. Speech is
  // suppressed when muted or monitoring is paused, but the thought feed still
  // logs the analysis so the core always feels active.
  useEffect(() => {
    if (!selectedNode) { lastNarratedNodeRef.current = null; return }
    if (selectedNode.id === lastNarratedNodeRef.current) return
    lastNarratedNodeRef.current = selectedNode.id

    const res = analyzeNode(selectedNode, graphData, riskIntel.byNode.get(selectedNode.id) ?? null)
    pushThought(res.narration, res.flagged ? 'alert' : 'scan')

    if (isMutedRef.current || !monitoring) return
    const id = setTimeout(() => ub.speak(res.narration), 350)
    return () => clearTimeout(id)
  }, [selectedNode, graphData, monitoring, ub, pushThought, riskIntel])

  // ── Revoke prior PDF blob URL when superseded or on unmount ───────────────
  useEffect(() => () => { if (evidence?.blobUrl) URL.revokeObjectURL(evidence.blobUrl) }, [evidence])

  return (
    <div style={{
      position: 'relative',
      width: '100%',
      height: '100%',
      overflow: 'hidden',
      background: C.bg,
    }}>

      {/* ── Voice fallback warning — never fail silently ──────────────── */}
      {!speechSupported && (
        <div style={{
          position: 'fixed', top: 10, left: '50%', transform: 'translateX(-50%)',
          zIndex: 99999, padding: '8px 16px', borderRadius: 8,
          background: 'rgba(120,30,30,0.92)', border: '1px solid #f87272',
          color: '#ffe1e1', font: '12px/1.4 system-ui, sans-serif',
          boxShadow: '0 6px 24px rgba(0,0,0,0.5)',
        }}>
          ⚠ Voice system unavailable on this browser — try Chrome, Edge, or Brave.
        </div>
      )}

      {/* ── Developer voice diagnostics (?voicedebug) ─────────────────── */}
      {voiceDebug && <VoiceDebugPanel />}

      {/* ── z:1 — Full-viewport 3D graph ─────────────────────────────── */}
      <GraphScene
        ref={graphSceneRef}
        key={sceneKey}
        graphData={graphData}
        selectedNodeId={selectedNode?.id ?? null}
        selectedClusterNodeIds={selectedClusterNodeIds}
        onNodeClick={handleNodeClick}
        onHoverChange={handleHoverChange}
        fraudNodeIds={fraudNodeIds}
        graphComponents={graphComponents}
        focusRef={focusRef}
        cashNodes={cashNodes}
        cashAnimIds={cashAnimIds}
        riskIntel={riskIntel.byNode}
        backendLayout={backendLayout}
      />

      {/* Pin-to-case removed: fraud clusters are auto-registered as investigation
          cases by the Blue Team (store.register_from_detection). The Graph Engine
          is a pure monitoring/intelligence surface; the Investigations page is the
          single source of truth for cases — no manual case action here. */}

      {/* ── z:20 — Empty state (dormant until real data arrives) ───────── */}
      <AnimatePresence>
        {stats.nodeCount === 0 && !showClearAnim && (
          <EmptyState
            key="empty-state"
            connected={connected}
            onGenerateSample={generateSample}
            onLoadDataset={() => setLeftOpen(true)}
          />
        )}
      </AnimatePresence>

      {/* ── z:36 — Graph clear animation overlay ─────────────────────── */}
      {/* ── Clear overlay: fades in over the graph, dissolve particles, fades out ── */}
      <AnimatePresence>
        {showClearAnim && (
          <motion.div
            key="clear-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: 0.6, ease: [0.4, 0, 0.2, 1] } }}
            transition={{ duration: 0.15, ease: 'easeOut' }}
            style={{
              position: 'absolute', inset: 0, zIndex: 36,
              background: 'radial-gradient(ellipse at 50% 46%, rgba(8,12,20,0.97) 0%, rgba(5,8,14,0.99) 100%)',
              backdropFilter: 'blur(18px) saturate(60%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              pointerEvents: 'none',
            }}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.94 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.05, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              style={{ textAlign: 'center', userSelect: 'none' }}
            >
              {/* Particle dissolve — dots scatter upward and fade */}
              <div style={{ display: 'flex', gap: 6, justifyContent: 'center', marginBottom: 20 }}>
                {[0,1,2,3,4,5,6,7,8].map(i => (
                  <motion.div
                    key={i}
                    style={{
                      width: i % 3 === 0 ? 4 : 2.5,
                      height: i % 3 === 0 ? 4 : 2.5,
                      borderRadius: '50%',
                      background: i % 3 === 0
                        ? `rgba(248,81,73,${0.35 + i * 0.04})`
                        : `rgba(68,147,248,${0.2 + i * 0.03})`,
                    }}
                    animate={{
                      y:       [0, -(14 + i * 3), -(28 + i * 5)],
                      opacity: [0.8, 0.4, 0],
                      x:       [0, (i % 2 === 0 ? 1 : -1) * (i * 1.5)],
                    }}
                    transition={{ duration: 1.1, delay: i * 0.06, repeat: Infinity, ease: 'easeOut' }}
                  />
                ))}
              </div>

              <div style={{
                fontSize: 10, fontWeight: 700, letterSpacing: '.20em', textTransform: 'uppercase',
                color: 'rgba(255,255,255,0.22)', fontFamily: '"JetBrains Mono", ui-monospace, monospace',
              }}>
                Graph Cleared
              </div>
              <div style={{
                marginTop: 6, fontSize: 8, color: 'rgba(255,255,255,0.08)',
                letterSpacing: '.14em', fontFamily: 'ui-monospace, monospace',
              }}>
                ████░░░░░░░░░░░░
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Top header bar — removed for the clean / minimal layout ────── */}
      {false && (
      <motion.header
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        style={{
          position: 'absolute', top: 0, left: 0, right: 0,
          height: 44, zIndex: 60,
          display: 'flex', alignItems: 'center', gap: 14,
          padding: '0 16px',
          background: 'rgba(13,17,23,0.92)',
          borderBottom: `1px solid ${C.border}`,
          backdropFilter: 'blur(20px)',
          userSelect: 'none',
        }}
      >
        {/* Wordmark */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none" style={{ flexShrink: 0 }}>
            <circle cx="9" cy="9" r="2" fill={C.accent} opacity="0.85"/>
            <circle cx="2.5" cy="4.5" r="1.3" fill={C.text3} opacity="0.7"/>
            <circle cx="15.5" cy="4.5" r="1.3" fill={C.danger} opacity="0.6"/>
            <circle cx="2.5" cy="13.5" r="1.3" fill={C.text3} opacity="0.5"/>
            <circle cx="15.5" cy="13.5" r="1.3" fill={C.warn} opacity="0.6"/>
            <line x1="9" y1="9" x2="2.5" y2="4.5"  stroke={C.text3} strokeWidth="0.7" opacity="0.4"/>
            <line x1="9" y1="9" x2="15.5" y2="4.5" stroke={C.danger} strokeWidth="0.7" opacity="0.35"/>
            <line x1="9" y1="9" x2="2.5" y2="13.5" stroke={C.text3} strokeWidth="0.7" opacity="0.3"/>
            <line x1="9" y1="9" x2="15.5" y2="13.5" stroke={C.warn} strokeWidth="0.7" opacity="0.35"/>
          </svg>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: C.text1, letterSpacing: '.04em' }}>
              TGIE
            </div>
            <div style={{ fontSize: 9, color: C.text3, letterSpacing: '.04em', lineHeight: 1 }}>
              Transaction Graph Intelligence
            </div>
          </div>
        </div>

        <Div />

        {/* Live stats */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <StatChip label="nodes" value={stats.nodeCount} color={C.text2} />
          <StatChip label="edges" value={stats.linkCount} color={C.text2} />
          <StatChip
            label="at risk"
            value={Math.max(stats.flaggedNodes, riskIntel.flaggedCount)}
            color={riskIntel.flaggedCount > 0 ? C.danger : C.text3}
          />
          <StatChip
            label="networks"
            value={flaggedGraphs.length}
            color={flaggedGraphs.length > 0 ? C.danger : C.text3}
          />
          <StatChip label="volume" value={fmt(stats.totalVolume)} color={C.text2} />
        </div>

        <Div />

        {/* Fraud rate */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 10, color: C.text3 }}>Fraud rate</span>
          <div style={{ width: 48, height: 2, background: C.border, borderRadius: 1, overflow: 'hidden' }}>
            <motion.div
              style={{
                height: '100%', borderRadius: 1,
                background: isFraud ? C.danger : stats.fraudRate > 0.1 ? C.warn : C.success,
              }}
              animate={{ width: `${Math.min(100, stats.fraudRate * 100)}%` }}
              transition={{ duration: 0.6, ease: 'easeOut' }}
            />
          </div>
          <span style={{
            fontSize: 10, fontWeight: 600, fontVariantNumeric: 'tabular-nums',
            color: isFraud ? C.danger : stats.fraudRate > 0.1 ? C.warn : C.text2,
          }}>
            {(stats.fraudRate * 100).toFixed(1)}%
          </span>
        </div>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Waiting-for-data status (empty state) */}
        {stats.nodeCount === 0 && (
          <span style={{ fontSize: 10, color: C.text3, letterSpacing: '.04em' }}>
            Waiting for data
          </span>
        )}

        {/* Fraud state badge */}
        {isFraud && (
          <motion.div
            initial={{ opacity: 0, scale: 0.92 }}
            animate={{ opacity: 1, scale: 1 }}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '3px 10px', borderRadius: 4,
              background: 'rgba(248,81,73,0.08)',
              border: '1px solid rgba(248,81,73,0.22)',
            }}
          >
            <motion.div
              style={{ width: 5, height: 5, borderRadius: '50%', background: C.danger }}
              animate={{ opacity: [1, 0.3, 1] }}
              transition={{ repeat: Infinity, duration: 1.1 }}
            />
            <span style={{ fontSize: 10, fontWeight: 600, color: C.danger, letterSpacing: '.04em' }}>
              FRAUD DETECTED
            </span>
          </motion.div>
        )}

        <Div />

        {/* Connection status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <motion.div
            style={{
              width: 5, height: 5, borderRadius: '50%',
              background: connected ? C.success : C.danger,
            }}
            animate={connected ? { opacity: [1, 0.4, 1] } : {}}
            transition={{ repeat: Infinity, duration: 2 }}
          />
          <span style={{ fontSize: 10, color: connected ? C.text3 : C.danger }}>
            {connected ? 'Live' : 'Reconnecting'}
          </span>
        </div>
      </motion.header>
      )}

      {/* ── z:40 — Left panel: simulation + analysis + feed ───────────── */}
      <LeftPanel
        isOpen={leftOpen}
        onToggle={() => setLeftOpen(o => !o)}
        simulationState={simulationState}
        currentStep={currentStep}
        totalSteps={totalSteps}
        onRunSimulation={onRunSimulation}
        onClearGraph={onClearGraph}
        isClearingGraph={isClearing}
        blueTeamResult={blueTeamMultiResult}
        onFocusGraph={onFocusGraph}
        transactions={recentTransactions}
        fraudNodeIds={fraudNodeIds}
      />

      {/* ── z:45 — Graph Intelligence HUD (left; shown only when UB is asked) ── */}
      <AnimatePresence>
        {hudIntel && intelVisible && !leftOpen && !showClearAnim && (
          <GraphIntelHUD
            key="graph-intel-hud"
            intel={hudIntel}
            clusterCount={orderedFlagged.length}
            clusterIndex={Math.min(hudClusterIdx, orderedFlagged.length - 1)}
            onCycle={() => setHudClusterIdx(i => (i + 1) % Math.max(1, orderedFlagged.length))}
            onFocus={() => hudCluster && focusRef.current?.(hudCluster.nodes)}
            onInvestigate={investigateCluster}
            onEvidence={generateEvidence}
          />
        )}
      </AnimatePresence>


      {/* ── Red Team demo — LOCALHOST ONLY (floating toggle + drawer) ──── */}
      {isLocalhost && !redTeamOpen && (
        <motion.button
          initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
          onClick={() => setRedTeamOpen(true)}
          title="Red Team — adversarial self-play vs the deployed engine (local only)"
          style={{
            position: 'fixed', top: 14, right: 14, zIndex: 58,
            display: 'flex', alignItems: 'center', gap: 7, cursor: 'pointer',
            padding: '7px 13px', borderRadius: 7,
            background: 'rgba(40,34,28,0.5)', border: '1px solid rgba(231,224,210,0.34)',
            color: '#e7e0d2', backdropFilter: 'blur(10px)',
          }}
        >
          <Swords size={13} color="#e8504a" />
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.05em' }}>RED TEAM</span>
        </motion.button>
      )}
      {isLocalhost && (
        <RedTeamPanel isOpen={redTeamOpen} onClose={() => setRedTeamOpen(false)} />
      )}

      {/* ── Training Review queue — LOCALHOST ONLY (human-in-the-loop) ──── */}
      {isLocalhost && !trainingOpen && (
        <motion.button
          initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
          onClick={() => setTrainingOpen(true)}
          title="Training Review — approve which missed cases the Blue Team learns from (local only)"
          style={{
            position: 'fixed', top: 14, right: 132, zIndex: 58,
            display: 'flex', alignItems: 'center', gap: 7, cursor: 'pointer',
            padding: '7px 13px', borderRadius: 7,
            background: 'rgba(40,34,28,0.5)', border: '1px solid rgba(231,224,210,0.34)',
            color: '#e7e0d2', backdropFilter: 'blur(10px)',
          }}
        >
          <GraduationCap size={13} color="#4a8a52" />
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.05em' }}>TRAINING</span>
        </motion.button>
      )}
      {isLocalhost && (
        <TrainingReviewPanel isOpen={trainingOpen} onClose={() => setTrainingOpen(false)} />
      )}

      {/* ── z:70 — UB floating orb (top-right; appears only when called) ── */}
      <AnimatePresence>
        {orbVisible && (
          <UBOrb
            key="ub-orb"
            voiceState={ub.voiceState}
            wakeEnabled={ub.wakeEnabled}
            armedForCmd={ub.armedForCmd}
            supported={ub.supported}
            transcript={ub.transcript}
            onActivate={ub.armOnce}
            onStop={ub.stop}
            onToggleWake={() => (ub.wakeEnabled ? ub.disableWake() : ub.enableWake())}
          />
        )}
      </AnimatePresence>

      {/* ── z:70 — Persistent mic control: ICON REMOVED (logic unchanged) ──
          The visible mic button was removed per request. The wake-word /
          auto-trigger logic in useUB stays fully active (the recognizer arms
          itself + the first-gesture listener grants the mic), so "UB" still
          triggers hands-free. The only on-screen voice element is this transient
          hint, shown ONLY when the mic can't start (so the user isn't left blind
          without the icon); it auto-hides once the mic is listening. */}
      {!ub.wakeEnabled && (micHint || ub.lastError) && (
        <motion.div
          initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
          style={{
            position: 'absolute', left: 16, bottom: 16, zIndex: 70, maxWidth: 260,
            padding: '7px 12px', borderRadius: 8, fontSize: 11, lineHeight: 1.35,
            background: 'rgba(20,16,18,0.82)', backdropFilter: 'blur(8px)',
            border: '1px solid rgba(255,255,255,0.12)', color: '#e8dde2',
            pointerEvents: 'none',
          }}
        >
          🎙 {micHint || ub.lastError}
        </motion.div>
      )}

      {/* ── z:55 — Node inspector (floating, clears 44px right strip) ──── */}
      <NodeInspector
        node={selectedNode}
        classification={classification}
        onClose={() => setSelectedNode(null)}
        fraudNodeIds={fraudNodeIds}
        nodeToGraphId={nodeToGraphId as Map<string, string>}
        graphComponents={graphComponents}
        nodeIntel={selectedNode ? riskIntel.byNode.get(selectedNode.id) ?? null : null}
      />

      {/* ── z:50 — Hover tooltip ──────────────────────────────────────── */}
      {hoveredNode && (
        <motion.div
          key={hoveredNode.id}
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.14 }}
          style={{
            position: 'absolute', top: 52, left: '50%', transform: 'translateX(-50%)',
            zIndex: 55, pointerEvents: 'none',
          }}
        >
          {(() => {
            // Cash-rail nodes carry their own off-graph metadata (no fraud risk).
            const cash = hoveredNode as unknown as { isCashNode?: boolean; cashType?: string; amount?: number; parentAccount?: string }
            if (cash.isCashNode) {
              const isCashIn = cash.cashType === 'CASH_IN'
              const col = isCashIn ? '#22c98a' : '#e8b54a'
              const amt = cash.amount != null
                ? cash.amount >= 1e5 ? `₹${(cash.amount / 1e5).toFixed(2)}L` : `₹${cash.amount.toLocaleString('en-IN')}`
                : '—'
              return (
                <div style={{
                  minWidth: 188, padding: '9px 12px', background: 'rgba(13,17,23,0.97)',
                  border: `1px solid ${col}55`, borderRadius: 7, backdropFilter: 'blur(18px)',
                  boxShadow: `0 4px 22px ${col}33`, fontFamily: '"JetBrains Mono", ui-monospace, Menlo, monospace',
                }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: col, letterSpacing: '.06em', marginBottom: 6 }}>
                    {isCashIn ? 'CASH_IN' : 'CASH_OUT'}
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '3px 10px', fontSize: 9.5 }}>
                    <span style={{ color: C.text3 }}>Type</span>
                    <span style={{ color: col, textAlign: 'right' }}>{isCashIn ? 'External Deposit' : 'External Withdrawal'}</span>
                    <span style={{ color: C.text3 }}>Linked to</span>
                    <span style={{ color: C.cyan, textAlign: 'right' }}>{cash.parentAccount ?? '—'}</span>
                    <span style={{ color: C.text3 }}>Amount</span>
                    <span style={{ color: col, fontWeight: 700, textAlign: 'right' }}>{amt}</span>
                  </div>
                  <div style={{ marginTop: 6, fontSize: 7.5, color: C.text3, letterSpacing: '.06em' }}>
                    CASH RAIL · DETACHED · OFF-GRAPH
                  </div>
                </div>
              )
            }
            // First-class virtual cash endpoint (CASH_SOURCE / CASH_EXIT). These
            // are SYSTEM nodes, never "Account" — show their cash identity. Fraud
            // involvement is surfaced as a note while the colour stays green/gold.
            if (hoveredNode.account_type === 'cash') {
              const isCashIn = (hoveredNode.total_sent ?? 0) >= (hoveredNode.total_received ?? 0)
              const col = isCashIn ? '#00E676' : '#FFC400'
              const fraudInvolved = isHoveredFraud || (hoveredIntel?.clusterFlagged ?? false)
              return (
                <div style={{
                  minWidth: 200, padding: '9px 12px', background: 'rgba(13,17,23,0.97)',
                  border: `1px solid ${col}55`, borderRadius: 7, backdropFilter: 'blur(18px)',
                  boxShadow: `0 4px 22px ${col}33`, fontFamily: '"JetBrains Mono", ui-monospace, Menlo, monospace',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 6 }}>
                    <div style={{ width: 7, height: 7, borderRadius: '50%', background: col, boxShadow: `0 0 8px ${col}` }} />
                    <span style={{ fontSize: 11, fontWeight: 700, color: col, letterSpacing: '.05em' }}>{hoveredNode.id}</span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '3px 10px', fontSize: 9.5 }}>
                    <span style={{ color: C.text3 }}>Node Type</span>
                    <span style={{ color: col, fontWeight: 600, textAlign: 'right' }}>{isCashIn ? 'Cash Deposit' : 'Cash Withdrawal'}</span>
                    <span style={{ color: C.text3 }}>Role</span>
                    <span style={{ color: C.text2, textAlign: 'right' }}>{isCashIn ? 'Cash entered banking network' : 'Cash exited banking network'}</span>
                    <span style={{ color: C.text3 }}>Transaction</span>
                    <span style={{ color: col, fontWeight: 600, textAlign: 'right' }}>{isCashIn ? 'Cash In' : 'Cash Out'}</span>
                  </div>
                  {fraudInvolved && (
                    <div style={{ marginTop: 6, paddingTop: 6, borderTop: `1px solid ${C.border}`, fontSize: 9, color: '#ff6b6b', letterSpacing: '.04em', display: 'flex', alignItems: 'center', gap: 5 }}>
                      <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#ff3366', boxShadow: '0 0 6px #ff3366' }} />
                      ON FRAUD PATH · identity preserved
                    </div>
                  )}
                  <div style={{ marginTop: 6, fontSize: 7.5, color: C.text3, letterSpacing: '.06em' }}>
                    VIRTUAL SYSTEM NODE · {isCashIn ? 'CASH ENTRY POINT' : 'CASH EXIT POINT'}
                  </div>
                </div>
              )
            }
            const risk   = hoveredIntel?.propagatedRisk ?? hoveredNode.risk_score ?? 0
            const pct    = Math.round(risk * 100)
            const sus    = hoveredIntel?.suspicion ?? (risk >= 0.6 ? 'HIGH' : risk >= 0.35 ? 'MODERATE' : 'LOW')
            const rc     = sus === 'CRITICAL' || sus === 'HIGH' ? C.danger
                          : sus === 'MODERATE' ? C.warn
                          : sus === 'LOW' ? C.cyan : C.text2
            const expo   = hoveredIntel ? exposureLabel(hoveredIntel.exposure) : 'None'
            const inherited = hoveredIntel?.clusterFlagged && hoveredIntel.exposure !== 'origin'
            return (
              <div style={{
                minWidth: 196, padding: '9px 12px',
                background: 'rgba(13,17,23,0.97)',
                border: `1px solid ${isHoveredFraud ? 'rgba(248,81,73,0.30)' : C.border}`,
                borderRadius: 7, backdropFilter: 'blur(18px)',
                boxShadow: isHoveredFraud ? '0 4px 22px rgba(248,81,73,0.18)' : '0 4px 18px rgba(0,0,0,0.55)',
                fontFamily: '"JetBrains Mono", ui-monospace, Menlo, monospace',
              }}>
                {/* Header: id + suspicion dot */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 6 }}>
                  <span style={{ fontSize: 11, fontWeight: 600, color: C.text1 }}>{hoveredNode.id}</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                    <motion.div
                      style={{ width: 6, height: 6, borderRadius: '50%', background: rc, boxShadow: `0 0 7px ${rc}` }}
                      animate={risk >= 0.6 ? { opacity: [1, 0.35, 1] } : { opacity: 0.8 }}
                      transition={{ repeat: Infinity, duration: 1 }}
                    />
                    <span style={{ fontSize: 14, fontWeight: 700, color: rc, fontVariantNumeric: 'tabular-nums' }}>{pct}%</span>
                  </div>
                </div>
                {/* Risk bar */}
                <div style={{ height: 3, background: 'rgba(255,255,255,0.06)', borderRadius: 2, overflow: 'hidden', marginBottom: 7 }}>
                  <div style={{ height: '100%', width: `${pct}%`, background: rc, borderRadius: 2, opacity: 0.85 }} />
                </div>
                {/* Rows — node risk and cluster risk are distinct quantities */}
                <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '3px 10px', fontSize: 9.5 }}>
                  {hoveredIntel?.role && (<>
                    <span style={{ color: C.text3 }}>Role</span>
                    <span style={{ color: hoveredIntel.isBridge ? '#d946ef' : C.cyan, fontWeight: 600, textAlign: 'right' }}>
                      {roleLabel(hoveredIntel.role)}
                    </span>
                  </>)}
                  <span style={{ color: C.text3 }}>Node risk</span>
                  <span style={{ color: rc, fontWeight: 600, textAlign: 'right' }}>{pct}%</span>
                  {hoveredIntel?.clusterFlagged && (<>
                    <span style={{ color: C.text3 }}>Cluster risk</span>
                    <span style={{ color: C.danger, textAlign: 'right' }}>{Math.round((hoveredIntel?.clusterRisk ?? 0) * 100)}%</span>
                  </>)}
                  {hoveredGraphId && (<>
                    <span style={{ color: C.text3 }}>Cluster</span>
                    <span style={{ color: isHoveredFraud ? C.danger : C.text2, textAlign: 'right' }}>
                      {hoveredGraphId}{isHoveredFraud ? ' · FRAUD' : ''}
                    </span>
                  </>)}
                  <span style={{ color: C.text3 }}>Exposure</span>
                  <span style={{ color: rc, textAlign: 'right' }}>{expo}</span>
                  <span style={{ color: C.text3 }}>Suspicious</span>
                  <span style={{ color: rc, fontWeight: 600, textAlign: 'right' }}>{sus}</span>
                  <span style={{ color: C.text3 }}>Transactions</span>
                  <span style={{ color: C.text2, textAlign: 'right' }}>{hoveredIntel?.transactionCount ?? hoveredNode.transaction_count ?? 0}</span>
                </div>
                {inherited && (
                  <div style={{ marginTop: 6, paddingTop: 6, borderTop: `1px solid ${C.border}`, fontSize: 9, color: '#d98080', lineHeight: 1.4 }}>
                    Inherited from {hoveredGraphId} — {expo.toLowerCase()}
                  </div>
                )}
              </div>
            )
          })()}
        </motion.div>
      )}

      {/* ── z:30 — Bottom transaction ticker (between 44px panel strips) ─ */}
      <TransactionTicker
        transactions={recentTransactions}
        isFraudDetected={isFraudDetected}
        fraudNodeIds={fraudNodeIds}
      />

      {/* ── z:80 — Evidence panel: download + anchor to blockchain (BELS) ────── */}
      <AnimatePresence>
        {evidence && (
          <EvidenceBlockchainPanel
            evidence={evidence}
            onClose={() => setEvidence(null)}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
