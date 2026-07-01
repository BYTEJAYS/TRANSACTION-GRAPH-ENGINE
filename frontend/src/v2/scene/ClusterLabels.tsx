import { useRef, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import type { GraphNode, GraphComponentResult } from '../../types'
import type { LayoutPositions } from './useForceLayout'

interface Props {
  nodes: GraphNode[]
  positions: LayoutPositions
  graphComponents: GraphComponentResult[]
}

interface Centroid {
  graphId: string
  flagged: boolean
  riskScore: number
  nodeCount: number
  x: number; y: number; z: number
}

// Cinematic cluster region labels — lives inside <Canvas>, renders HTML via
// drei's Html portal. Computes cluster centroids from live force-layout
// positions and re-anchors labels as the simulation animates.
export function ClusterLabels({ nodes, positions, graphComponents }: Props) {
  const [centroids, setCentroids] = useState<Centroid[]>([])
  const tickRef   = useRef(0)
  const idxMapRef = useRef<Map<string, number>>(new Map())

  useFrame(() => {
    // Update at ~10 fps — no need to recompute every frame for text labels
    if (++tickRef.current % 6 !== 0) return

    const arr = positions.array
    if (!arr || graphComponents.length === 0) {
      if (centroids.length) setCentroids([])
      return
    }

    // Rebuild node-index map when the node list changes
    if (idxMapRef.current.size !== nodes.length) {
      idxMapRef.current = new Map(nodes.map((n, i) => [n.id, i]))
    }

    const next: Centroid[] = []
    for (const comp of graphComponents) {
      if (comp.nodes.length === 0) continue
      let cx = 0, cy = 0, cz = 0, n = 0
      for (const nid of comp.nodes) {
        const i = idxMapRef.current.get(nid)
        if (i === undefined || arr.length < (i + 1) * 3) continue
        cx += arr[i * 3]; cy += arr[i * 3 + 1]; cz += arr[i * 3 + 2]; n++
      }
      if (n === 0) continue
      next.push({
        graphId:   comp.graph_id,
        flagged:   comp.flagged,
        riskScore: comp.risk_score ?? 0,
        nodeCount: comp.nodes.length,
        x: cx / n,
        y: cy / n,
        z: cz / n,
      })
    }
    setCentroids(next)
  })

  return (
    <>
      {centroids.map(c => (
        // Anchor label above cluster centroid; Html handles 3D → screen projection
        <Html
          key={c.graphId}
          position={[c.x, c.y + 52, c.z]}
          center
          distanceFactor={220}
          zIndexRange={[55, 56]}
          occlude={false}
        >
          <ClusterLabelCard label={c} />
        </Html>
      ))}
    </>
  )
}

// ── Label card ────────────────────────────────────────────────────────────────
function ClusterLabelCard({ label }: { label: Centroid }) {
  const danger   = label.flagged
  const warn     = !danger && label.riskScore > 0.5
  const accent   = danger ? '#ff3366' : warn ? '#f59e0b' : '#00f5ff'
  const rgb      = danger ? '255,51,102' : warn ? '245,158,11' : '0,245,255'
  const verdict  = danger ? 'FRAUD' : warn ? 'SUSPECT' : 'CLEAN'
  const score    = `${Math.round(label.riskScore * 100)}%`

  return (
    <div style={{
      fontFamily:  '"JetBrains Mono", monospace',
      pointerEvents: 'none',
      userSelect:  'none',
      textAlign:   'center',
      whiteSpace:  'nowrap',
    }}>
      {/* Connector tick from label down to cluster centroid */}
      <div style={{
        width:      1,
        height:     16,
        background: `rgba(${rgb},0.45)`,
        margin:     '0 auto 3px',
        boxShadow:  `0 0 6px rgba(${rgb},0.35)`,
      }} />

      {/* Main pill */}
      <div style={{
        display:        'inline-flex',
        flexDirection:  'column',
        alignItems:     'center',
        gap:            3,
        padding:        '5px 14px 6px',
        background:     `rgba(2,4,10,${danger ? '0.88' : '0.78'})`,
        border:         `1px solid rgba(${rgb},${danger ? '0.60' : '0.35'})`,
        borderRadius:   7,
        backdropFilter: 'blur(8px)',
        boxShadow: [
          `0 0 24px rgba(${rgb},${danger ? '0.22' : '0.12'})`,
          '0 4px 18px rgba(0,0,0,0.6)',
          danger ? `inset 0 0 14px rgba(255,51,102,0.10)` : '',
        ].filter(Boolean).join(','),
      }}>
        {/* Graph ID — primary label */}
        <div style={{
          fontSize:      10,
          fontWeight:    800,
          letterSpacing: '.24em',
          color:         accent,
          textTransform: 'uppercase',
          textShadow:    `0 0 14px rgba(${rgb},0.75)`,
          lineHeight:    1,
        }}>
          {label.graphId}
        </div>

        {/* Divider */}
        <div style={{ width: '100%', height: 1, background: `rgba(${rgb},0.22)` }} />

        {/* Meta row */}
        <div style={{ display: 'flex', gap: 7, alignItems: 'center' }}>
          <span style={{
            fontSize:      8,
            fontWeight:    700,
            letterSpacing: '.08em',
            color:         danger ? '#ff3366' : warn ? '#f59e0b' : 'rgba(0,245,255,0.60)',
          }}>
            {verdict}
          </span>
          <span style={{ color: 'rgba(255,255,255,0.15)', fontSize: 7 }}>·</span>
          <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.35)', letterSpacing: '.04em' }}>
            RISK {score}
          </span>
          <span style={{ color: 'rgba(255,255,255,0.15)', fontSize: 7 }}>·</span>
          <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.28)', letterSpacing: '.04em' }}>
            {label.nodeCount}N
          </span>
        </div>
      </div>
    </div>
  )
}
