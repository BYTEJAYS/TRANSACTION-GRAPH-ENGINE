import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Lock, Camera, Network } from 'lucide-react'
import { GraphScene, type GraphSceneHandle, type CapturedSnapshot } from '../components/GraphScene'
import { GraphErrorBoundary } from '../components/GraphErrorBoundary'
import { caseApi, type CaseDetail } from '../cases/api'
import type { GraphData } from '../types'
import { T } from '../theme'

// Verbatim case graph — restores the EXACT positions + camera captured at
// detection time. No force simulation runs; nodes are pinned (fx/fy/fz).
export default function CaseGraphPage() {
  const { caseId } = useParams()
  const navigate = useNavigate()
  const sceneRef = useRef<GraphSceneHandle>(null)
  const [c, setC] = useState<CaseDetail | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    caseApi.get(caseId!).then(setC).catch(e => setErr(e.message))
  }, [caseId])

  const snap = c?.graph_snapshot
  const captured = !!snap?.captured && (snap?.nodes?.some(n => typeof n.x === 'number') ?? false)

  const restoreSnapshot: CapturedSnapshot | null = useMemo(() => {
    if (!snap || !captured) return null
    return {
      nodes: snap.nodes.map(n => ({ ...n, id: String(n.id), x: Number(n.x), y: Number(n.y), z: Number(n.z) })),
      edges: snap.edges.map(e => ({
        ...e,
        source: String((e.source ?? e.from) as string),
        target: String((e.target ?? e.to) as string),
      })),
      camera: snap.camera ?? null,
    }
  }, [snap, captured])

  const graphData = useMemo<GraphData>(() => ({
    nodes: (restoreSnapshot?.nodes ?? []) as unknown as GraphData['nodes'],
    links: (restoreSnapshot?.edges ?? []) as unknown as GraphData['links'],
  }), [restoreSnapshot])

  const fraudNodeIds = useMemo(
    () => new Set((restoreSnapshot?.nodes ?? []).filter(n => n.is_flagged).map(n => String(n.id))),
    [restoreSnapshot],
  )

  const back = () => navigate(`/investigations/${caseId}`)

  return (
    <div style={{ position: 'fixed', inset: 0, background: '#000', zIndex: 1 }}>
      {/* overlay controls */}
      <div style={{ position: 'absolute', top: 16, left: 16, zIndex: 30, display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={back} style={pill}><ArrowLeft size={15} /> Case {caseId}</button>
        <span style={{ ...pill, gap: 7, color: T.gold, cursor: 'default' }}>
          <Lock size={13} /> Verbatim restore · no simulation
        </span>
      </div>

      {restoreSnapshot ? (
        <GraphErrorBoundary>
          <GraphScene
            ref={sceneRef}
            graphData={graphData}
            restoreSnapshot={restoreSnapshot}
            selectedNodeId={null}
            fraudNodeIds={fraudNodeIds}
            onNodeClick={() => {}}
          />
        </GraphErrorBoundary>
      ) : (
        <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center' }}>
          <div style={{ textAlign: 'center', maxWidth: 420, padding: 24 }}>
            <Camera size={30} color={T.text3} style={{ opacity: 0.6 }} />
            <div style={{ fontSize: 15, fontWeight: 700, color: T.text, marginTop: 14 }}>
              {err ? 'Could not load case' : 'No graph view attached to this case'}
            </div>
            <p style={{ fontSize: 12.5, color: T.text3, lineHeight: 1.6, marginTop: 8 }}>
              {err
                ? err
                : 'This case has no captured network view. Open the live Graph Engine to explore the transaction network.'}
            </p>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center', marginTop: 18 }}>
              <button onClick={back} style={{ ...pill, position: 'static' }}><ArrowLeft size={14} /> Back to case</button>
              <button onClick={() => navigate('/graph')} style={{ ...pill, position: 'static', color: T.gold }}><Network size={14} /> Open Graph Engine</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const pill: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 8, padding: '8px 13px', borderRadius: 10,
  background: 'rgba(16,18,22,0.82)', border: `1px solid ${T.border}`, color: T.text2,
  fontSize: 12.5, fontWeight: 600, cursor: 'pointer', fontFamily: T.font, backdropFilter: 'blur(8px)',
}
