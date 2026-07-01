import { Canvas } from '@react-three/fiber'
import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { Background } from './Background'
import { Nodes } from './Nodes'
import { Edges } from './Edges'
import { Particles } from './Particles'
import { Shockwave } from './Shockwave'
import { CameraRig } from './CameraRig'
import { PostFX } from './PostFX'
import { ClusterLabels } from './ClusterLabels'
import { useForceLayout } from './useForceLayout'
import type { ClusterSector } from './useForceLayout'
import type { GraphData, GraphNode, GraphComponentResult } from '../../types'

interface Props {
  graphData: GraphData
  fraudNodeIds: ReadonlySet<string>
  selectedNode: GraphNode | null
  clusterIds: ReadonlySet<string> | null
  isFraudDetected: boolean
  clearNonce: number
  graphComponents: GraphComponentResult[]
  nodeToGraphId: Map<string, string>
  onHover: (node: GraphNode | null) => void
  onSelect: (node: GraphNode | null) => void
}

const ORIGIN = new THREE.Vector3(0, 0, 0)

export function CinematicScene({
  graphData, fraudNodeIds, selectedNode, clusterIds, isFraudDetected,
  clearNonce, graphComponents, nodeToGraphId, onHover, onSelect,
}: Props) {
  const { positions, clusters } = useForceLayout({
    nodes: graphData.nodes,
    links: graphData.links,
    nodeGroupIds: nodeToGraphId.size > 0 ? nodeToGraphId : undefined,
  })

  // Smoothed fraud intensity for background + bloom modulation
  const [fraudIntensity, setFraudIntensity] = useState(0)
  useEffect(() => {
    const target = isFraudDetected ? 1 : (fraudNodeIds.size > 0 ? 0.55 : 0)
    const id = setInterval(() => {
      setFraudIntensity(prev => prev + (target - prev) * 0.15)
    }, 50)
    return () => clearInterval(id)
  }, [isFraudDetected, fraudNodeIds.size])

  // Shockwave nonce — bump every time a new fraud node arrives
  const [shockNonce, setShockNonce] = useState(0)
  const lastFraudCount = useRef(0)
  useEffect(() => {
    if (fraudNodeIds.size > lastFraudCount.current) setShockNonce(n => n + 1)
    lastFraudCount.current = fraudNodeIds.size
  }, [fraudNodeIds.size])

  // Reset internal scene state on graph clear
  useEffect(() => {
    if (clearNonce === 0) return
    setFraudIntensity(0)
    setShockNonce(0)
    lastFraudCount.current = 0
  }, [clearNonce])

  // Shockwave origin: average position of fraud nodes
  const shockCenter = useMemo(() => {
    const arr = positions.array
    if (!arr || fraudNodeIds.size === 0) return ORIGIN.clone()
    let cx = 0, cy = 0, cz = 0, n = 0
    graphData.nodes.forEach((node, i) => {
      if (fraudNodeIds.has(node.id) && arr.length >= (i + 1) * 3) {
        cx += arr[i * 3]; cy += arr[i * 3 + 1]; cz += arr[i * 3 + 2]; n++
      }
    })
    if (n === 0) return ORIGIN.clone()
    return new THREE.Vector3(cx / n, cy / n, cz / n)
  }, [shockNonce, fraudNodeIds, graphData.nodes, positions.array])

  return (
    <Canvas
      gl={{
        antialias: false,
        powerPreference: 'high-performance',
        alpha: false,
        toneMapping: THREE.ACESFilmicToneMapping,
      }}
      dpr={[1, 1.75]}
      camera={{ position: [0, 0, 280], fov: 60, near: 0.1, far: 6000 }}
      style={{ position: 'absolute', inset: 0, background: '#02040a' }}
    >
      <color attach="background" args={['#02040a']} />
      <fog attach="fog" args={['#02040a', 400, 2000]} />

      <Background fraudIntensity={fraudIntensity} />

      <Suspense fallback={null}>
        <Particles count={1800} fraudIntensity={fraudIntensity} />

        <Edges
          links={graphData.links}
          nodes={graphData.nodes}
          positions={positions}
          fraudNodeIds={fraudNodeIds}
        />

        <Nodes
          nodes={graphData.nodes}
          positions={positions}
          fraudNodeIds={fraudNodeIds}
          selectedId={selectedNode?.id ?? null}
          clusterIds={clusterIds}
          onHover={onHover}
          onClick={onSelect}
        />

        {shockNonce > 0 && (
          <Shockwave trigger={shockNonce} center={shockCenter} />
        )}

        {/* Cluster region labels — shown once Blue Team has identified graphs */}
        {graphComponents.length > 0 && (
          <ClusterLabels
            nodes={graphData.nodes}
            positions={positions}
            graphComponents={graphComponents}
          />
        )}
      </Suspense>

      <CameraRig
        selectedNode={selectedNode}
        nodes={graphData.nodes}
        positions={positions}
        clusters={clusters}
        fraudJustDetected={shockNonce}
        clearNonce={clearNonce}
      />

      <PostFX fraudIntensity={fraudIntensity} />
    </Canvas>
  )
}
