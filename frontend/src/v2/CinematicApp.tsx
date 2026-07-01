import { useCallback, useMemo, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { CinematicScene } from './scene/CinematicScene'
import { HeaderBadge } from './ui/HeaderBadge'
import { ThreatMeter } from './ui/ThreatMeter'
import { LiveFeed } from './ui/LiveFeed'
import { CommandRail } from './ui/CommandRail'
import { StatusBar } from './ui/StatusBar'
import { HoverProbe } from './ui/HoverProbe'
import { NodeDossier } from './ui/NodeDossier'
import { useGraphStore } from '../store/graphStore'
import { useGraphSocket } from '../hooks/useGraphSocket'
import { WS_URL, apiUrl } from '../config'
import { PALETTE } from './shaders/palette'
import type { GraphNode, WSGraphUpdate, LiveTransaction, FraudAlert, GraphComponentResult } from '../types'
import type { SimulationState } from '../types/transaction'

// Cinematic dashboard — opt-in via ?v=2 or /v2.
// Reuses the existing graph store + WS hook verbatim, so the backend contract
// remains identical to the v1 app.
export default function CinematicApp() {
  const {
    graphData,
    stats,
    recentTransactions,
    fraudNodeIds,
    isFraudDetected,
    nodeToGraphId,
    blueTeamMultiResult,
    mergeGraphUpdate,
    addAlert,
    addTransaction,
    clearGraph,
    setBlueTeamAnalyzing,
    setBlueTeamMultiVerdict,
  } = useGraphStore()

  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [hoveredNode,  setHoveredNode]  = useState<GraphNode | null>(null)

  const [simulationState, setSimulationState] = useState<SimulationState>('idle')
  const [currentStep, setCurrentStep] = useState(0)
  const [totalSteps,  setTotalSteps]  = useState(0)

  // clearNonce: bumped on each clear → signals CinematicScene to reset internal Three.js state
  const [clearNonce, setClearNonce] = useState(0)
  const [isClearing, setIsClearing] = useState(false)
  const [showClearToast, setShowClearToast] = useState(false)
  const clearToastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const isClearingRef = useRef(false)

  const onMessage = useCallback((type: string, data: unknown) => {
    if (isClearingRef.current) return
    switch (type) {
      case 'graph_update': {
        const upd = data as WSGraphUpdate
        if (upd.current_transaction) {
          setCurrentStep(upd.current_transaction.step)
          setTotalSteps(upd.current_transaction.total)
        }
        mergeGraphUpdate(upd)
        break
      }
      case 'simulation_complete':
        mergeGraphUpdate(data as WSGraphUpdate)
        setSimulationState('completed')
        break
      case 'blue_team_analyzing':
        setBlueTeamAnalyzing()
        break
      case 'blue_team_multi_verdict':
        setBlueTeamMultiVerdict(data as { graphs: GraphComponentResult[] })
        break
      case 'transaction':
        addTransaction(data as LiveTransaction)
        break
      case 'fraud_alert':
        addAlert(data as FraudAlert)
        break
    }
  }, [mergeGraphUpdate, addTransaction, addAlert, setBlueTeamAnalyzing, setBlueTeamMultiVerdict])

  const { connected } = useGraphSocket({ url: WS_URL, onMessage })

  const onRun = useCallback(async (json: string) => {
    try {
      const txns = JSON.parse(json) as Array<unknown>
      setSimulationState('running')
      setCurrentStep(0)
      setTotalSteps(txns.length)
      setBlueTeamMultiVerdict({ graphs: [] })

      await fetch(apiUrl('/transaction/manual'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: json,
      })
    } catch {
      setSimulationState('idle')
    }
  }, [setBlueTeamMultiVerdict])

  const onClear = useCallback(async () => {
    // Guard against double-fire during in-flight clear
    if (isClearingRef.current) return
    isClearingRef.current = true

    // Cancel any pending toast dismissal from a previous clear
    if (clearToastTimerRef.current) clearTimeout(clearToastTimerRef.current)

    // Synchronously flush all state in one render pass so the canvas goes blank
    // before the browser paints the next frame — no ghost nodes/edges.
    flushSync(() => {
      clearGraph()
      setSimulationState('idle')
      setCurrentStep(0)
      setTotalSteps(0)
      setSelectedNode(null)
      setHoveredNode(null)
      setIsClearing(true)
      setClearNonce(n => n + 1)   // signals CinematicScene to reset fraudIntensity/shockNonce/camera
      setShowClearToast(true)
    })

    // Dismiss the toast after 1.6 s
    clearToastTimerRef.current = setTimeout(() => setShowClearToast(false), 1600)

    // Tell the backend to clear its in-memory graph; hold the WS gate open
    // for 600 ms so the backend broadcast loop stops before we re-enable it.
    try {
      await fetch(apiUrl('/graph/clear'), { method: 'POST' })
    } catch { /* ignore network errors */ }

    // Keep gate closed for a beat so stale WS frames are dropped, then re-enable
    setTimeout(() => {
      isClearingRef.current = false
      setIsClearing(false)
    }, 600)
  }, [clearGraph])

  // Cluster IDs for the selected node — same approach as v1 App.tsx
  const clusterIds = useMemo<ReadonlySet<string> | null>(() => {
    if (!selectedNode) return null
    const gid = nodeToGraphId.get(selectedNode.id)
    if (!gid) return null
    return null // cluster highlight is optional in v2 — selected node alone is enough for camera focus
  }, [selectedNode, nodeToGraphId])

  const fraudIntensity = isFraudDetected ? 1 : Math.min(1, fraudNodeIds.size / 10)
  const hoveredGraphId = hoveredNode ? nodeToGraphId.get(hoveredNode.id) : undefined
  const isHoveredFraud = !!hoveredNode && (hoveredNode.is_flagged || fraudNodeIds.has(hoveredNode.id))
  const selectedGraphId = selectedNode ? nodeToGraphId.get(selectedNode.id) : undefined
  const isSelectedFraud = !!selectedNode && (selectedNode.is_flagged || fraudNodeIds.has(selectedNode.id))

  return (
    <div style={{
      position: 'relative', width: '100vw', height: '100vh', overflow: 'hidden',
      background: '#02040a',
      fontFamily: '"JetBrains Mono", monospace',
    }}>
      {/* Full-viewport cinematic 3D scene — z:0 */}
      <CinematicScene
        graphData={graphData}
        fraudNodeIds={fraudNodeIds}
        selectedNode={selectedNode}
        clusterIds={clusterIds}
        isFraudDetected={isFraudDetected}
        clearNonce={clearNonce}
        graphComponents={blueTeamMultiResult.graphs}
        nodeToGraphId={nodeToGraphId}
        onHover={setHoveredNode}
        onSelect={setSelectedNode}
      />

      {/* Top bar — z:50 */}
      <div style={{
        position: 'absolute', top: 18, left: 18, right: 18, zIndex: 50,
        display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
        pointerEvents: 'none',
      }}>
        <div style={{ pointerEvents: 'auto' }}>
          <HeaderBadge connected={connected} />
        </div>
        <div style={{ pointerEvents: 'auto' }}>
          <ThreatMeter
            fraudRate={stats.fraudRate}
            flaggedNodes={stats.flaggedNodes}
            isFraudDetected={isFraudDetected}
          />
        </div>
      </div>

      {/* Hover probe — z:60 */}
      <HoverProbe node={hoveredNode} isFraud={isHoveredFraud} graphId={hoveredGraphId} />

      {/* Left command rail — z:50 */}
      <div style={{ position: 'absolute', top: 90, left: 18, zIndex: 50 }}>
        <CommandRail
          simulationState={simulationState}
          currentStep={currentStep}
          totalSteps={totalSteps}
          onRun={onRun}
          onClear={onClear}
          isClearing={isClearing}
        />
      </div>

      {/* Graph-cleared micro-toast — z:70 */}
      <AnimatePresence>
        {showClearToast && (
          <motion.div
            key="clear-toast"
            initial={{ opacity: 0, scale: 0.92, y: 6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -4 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            style={{
              position: 'absolute',
              top: '50%', left: '50%',
              transform: 'translate(-50%, -50%)',
              zIndex: 70,
              pointerEvents: 'none',
              textAlign: 'center',
              userSelect: 'none',
            }}
          >
            {/* Dissolve dots */}
            <div style={{ display: 'flex', gap: 5, justifyContent: 'center', marginBottom: 14 }}>
              {[0,1,2,3,4,5,6].map(i => (
                <motion.div
                  key={i}
                  style={{
                    width: i % 2 === 0 ? 3 : 2,
                    height: i % 2 === 0 ? 3 : 2,
                    borderRadius: '50%',
                    background: i % 3 === 0
                      ? `rgba(0,245,255,${0.35 + i * 0.04})`
                      : `rgba(255,51,102,${0.18 + i * 0.03})`,
                  }}
                  animate={{
                    y:       [0, -(10 + i * 4), -(22 + i * 6)],
                    opacity: [0.7, 0.3, 0],
                    x:       [0, (i % 2 === 0 ? 1 : -1) * (i * 1.8)],
                  }}
                  transition={{ duration: 1.0, delay: i * 0.07, ease: 'easeOut' }}
                />
              ))}
            </div>
            <div style={{
              fontSize: 9, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase',
              color: `rgba(0,245,255,0.35)`,
              fontFamily: '"JetBrains Mono", monospace',
              textShadow: `0 0 18px ${PALETTE.safe}`,
            }}>
              GRAPH CLEARED
            </div>
            <div style={{
              marginTop: 5, fontSize: 7.5, color: 'rgba(255,255,255,0.08)',
              letterSpacing: '.12em', fontFamily: 'monospace',
            }}>
              ───────────────
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Right dossier — z:50 */}
      <NodeDossier
        node={selectedNode}
        isFraud={isSelectedFraud}
        graphId={selectedGraphId}
        onClose={() => setSelectedNode(null)}
      />

      {/* Bottom-left live feed — z:50 */}
      <div style={{ position: 'absolute', bottom: 18, left: 18, zIndex: 50 }}>
        <LiveFeed transactions={recentTransactions} fraudNodeIds={fraudNodeIds} />
      </div>

      {/* Bottom-right status bar — z:50 */}
      <div style={{ position: 'absolute', bottom: 18, right: 18, zIndex: 50 }}>
        <StatusBar stats={stats} connected={connected} fraudIntensity={fraudIntensity} />
      </div>

      {/* Subtle ambient grid overlay over the canvas — z:10 */}
      <div style={{
        position: 'absolute', inset: 0, zIndex: 10, pointerEvents: 'none',
        backgroundImage: [
          'linear-gradient(rgba(0,245,255,0.012) 1px, transparent 1px)',
          'linear-gradient(90deg, rgba(0,245,255,0.012) 1px, transparent 1px)',
        ].join(','),
        backgroundSize: '90px 90px',
        mixBlendMode: 'screen',
      }} />
    </div>
  )
}
