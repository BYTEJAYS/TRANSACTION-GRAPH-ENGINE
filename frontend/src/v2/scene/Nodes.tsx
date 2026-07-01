import { useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import { useFrame, ThreeEvent } from '@react-three/fiber'
import * as THREE from 'three'
import { nodeVert, nodeFrag, ringVert, ringFrag } from '../shaders/glsl'
import { riskRgb, PALETTE, rgb } from '../shaders/palette'
import type { GraphNode } from '../../types'
import type { LayoutPositions } from './useForceLayout'

interface Props {
  nodes: GraphNode[]
  positions: LayoutPositions
  fraudNodeIds: ReadonlySet<string>
  selectedId: string | null
  clusterIds: ReadonlySet<string> | null
  onHover: (node: GraphNode | null) => void
  onClick: (node: GraphNode | null) => void
}

const tmpObj = new THREE.Object3D()
const RADIUS = 4.6

export function Nodes({
  nodes, positions, fraudNodeIds, selectedId, clusterIds, onHover, onClick,
}: Props) {
  const meshRef = useRef<THREE.InstancedMesh>(null)
  const matRef  = useRef<THREE.ShaderMaterial>(null)
  const ringRef = useRef<THREE.Mesh>(null)
  const ringMatRef = useRef<THREE.ShaderMaterial>(null)

  // Allocate buffers sized to current node count
  const { iColor, iRisk, iFraud, iSelected, iScale } = useMemo(() => {
    const n = Math.max(nodes.length, 1)
    return {
      iColor:    new Float32Array(n * 3),
      iRisk:     new Float32Array(n),
      iFraud:    new Float32Array(n),
      iSelected: new Float32Array(n),
      iScale:    new Float32Array(n),
    }
  }, [nodes.length])

  // Per-instance attributes — refresh when graph data changes
  useLayoutEffect(() => {
    if (!meshRef.current) return
    const mesh = meshRef.current
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i]
      const flagged = n.is_flagged || fraudNodeIds.has(n.id)
      const c = riskRgb(n.risk_score, flagged)
      iColor[i * 3]     = c[0]
      iColor[i * 3 + 1] = c[1]
      iColor[i * 3 + 2] = c[2]
      iRisk[i]  = Math.min(1, n.risk_score)
      iFraud[i] = flagged ? 1 : 0
      const sel = (n.id === selectedId) || (clusterIds?.has(n.id) ?? false)
      iSelected[i] = sel ? 1 : 0
      // Base size: account_type + transaction count
      const sizeBoost = Math.min(2.2, 1 + Math.log10(1 + (n.transaction_count ?? 0)) * 0.35)
      iScale[i] = (n.account_type === 'high_value' ? 1.25 : 1.0) * sizeBoost
    }
    const geom = mesh.geometry
    geom.setAttribute('iColor',    new THREE.InstancedBufferAttribute(iColor, 3))
    geom.setAttribute('iRisk',     new THREE.InstancedBufferAttribute(iRisk, 1))
    geom.setAttribute('iFraud',    new THREE.InstancedBufferAttribute(iFraud, 1))
    geom.setAttribute('iSelected', new THREE.InstancedBufferAttribute(iSelected, 1))
    geom.setAttribute('iScale',    new THREE.InstancedBufferAttribute(iScale, 1))
    mesh.instanceMatrix.needsUpdate = true
  }, [nodes, fraudNodeIds, selectedId, clusterIds, iColor, iRisk, iFraud, iSelected, iScale])

  // Per-frame: read positions from layout worker, write matrices
  useFrame((state) => {
    if (!meshRef.current) return
    const mesh = meshRef.current
    const arr  = positions.array
    if (!arr || arr.length < nodes.length * 3) return

    for (let i = 0; i < nodes.length; i++) {
      tmpObj.position.set(arr[i * 3], arr[i * 3 + 1], arr[i * 3 + 2])
      tmpObj.updateMatrix()
      mesh.setMatrixAt(i, tmpObj.matrix)
    }
    mesh.instanceMatrix.needsUpdate = true

    if (matRef.current) matRef.current.uniforms.uTime.value = state.clock.elapsedTime

    // Position the selection ring at the focused node, billboard to camera
    if (ringRef.current && ringMatRef.current) {
      const idx = selectedId ? nodes.findIndex(n => n.id === selectedId) : -1
      if (idx >= 0 && arr) {
        ringRef.current.position.set(arr[idx * 3], arr[idx * 3 + 1], arr[idx * 3 + 2])
        ringRef.current.quaternion.copy(state.camera.quaternion)
        ringRef.current.visible = true
        ringMatRef.current.uniforms.uTime.value = state.clock.elapsedTime
      } else {
        ringRef.current.visible = false
      }
    }
  })

  // ── Raycast hover/click ─────────────────────────────────────────────────
  const handleHover = (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation()
    const id = e.instanceId
    if (id == null) return
    const node = nodes[id]
    if (node) onHover(node)
    document.body.style.cursor = 'pointer'
  }
  const handleOut = () => {
    onHover(null)
    document.body.style.cursor = ''
  }
  const handleClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation()
    const id = e.instanceId
    if (id == null) return
    const node = nodes[id]
    if (node) onClick(node)
  }

  const nodeUniforms = useMemo(() => ({ uTime: { value: 0 } }), [])
  const ringUniforms = useMemo(() => ({
    uTime:  { value: 0 },
    uColor: { value: new THREE.Vector3(...rgb(PALETTE.hologramEdge)) },
  }), [])

  // Update ring color when selection switches between fraud / safe nodes
  useEffect(() => {
    if (!ringMatRef.current || !selectedId) return
    const sel = nodes.find(n => n.id === selectedId)
    if (!sel) return
    const flagged = sel.is_flagged || fraudNodeIds.has(sel.id)
    const c = riskRgb(sel.risk_score, flagged)
    ringMatRef.current.uniforms.uColor.value.set(c[0], c[1], c[2])
  }, [selectedId, nodes, fraudNodeIds])

  if (nodes.length === 0) return null

  return (
    <group>
      <instancedMesh
        ref={meshRef}
        args={[undefined, undefined, nodes.length]}
        onPointerOver={handleHover}
        onPointerMove={handleHover}
        onPointerOut={handleOut}
        onClick={handleClick}
      >
        <sphereGeometry args={[RADIUS, 24, 24]} />
        <shaderMaterial
          ref={matRef}
          vertexShader={nodeVert}
          fragmentShader={nodeFrag}
          uniforms={nodeUniforms}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </instancedMesh>

      <mesh ref={ringRef} visible={false} renderOrder={5}>
        <planeGeometry args={[RADIUS * 5, RADIUS * 5]} />
        <shaderMaterial
          ref={ringMatRef}
          vertexShader={ringVert}
          fragmentShader={ringFrag}
          uniforms={ringUniforms}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </mesh>
    </group>
  )
}
