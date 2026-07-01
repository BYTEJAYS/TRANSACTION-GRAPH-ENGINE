import { useLayoutEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { edgeVert, edgeFrag } from '../shaders/glsl'
import { PALETTE, rgb } from '../shaders/palette'
import type { GraphLink, GraphNode } from '../../types'
import type { LayoutPositions } from './useForceLayout'

interface Props {
  links: GraphLink[]
  nodes: GraphNode[]
  positions: LayoutPositions
  fraudNodeIds: ReadonlySet<string>
}

const tmpObj    = new THREE.Object3D()
const tmpVecA   = new THREE.Vector3()
const tmpVecB   = new THREE.Vector3()
const tmpMid    = new THREE.Vector3()
const tmpDir    = new THREE.Vector3()
const yAxis     = new THREE.Vector3(0, 1, 0)
const tmpQuat   = new THREE.Quaternion()
const safeColor   = rgb(PALETTE.hologramEdge)
const fraudColor  = rgb(PALETTE.fraudEdge)

// Cylinder of unit length aligned along +Y, scaled per instance to span src→tgt.
export function Edges({ links, nodes, positions, fraudNodeIds }: Props) {
  const meshRef = useRef<THREE.InstancedMesh>(null)
  const matRef  = useRef<THREE.ShaderMaterial>(null)

  // node id → index in positions array
  const idIndex = useMemo(() => {
    const m = new Map<string, number>()
    nodes.forEach((n, i) => m.set(n.id, i))
    return m
  }, [nodes])

  const { iColor, iRisk, iFraud, iAmount } = useMemo(() => {
    const n = Math.max(links.length, 1)
    return {
      iColor:  new Float32Array(n * 3),
      iRisk:   new Float32Array(n),
      iFraud:  new Float32Array(n),
      iAmount: new Float32Array(n),
    }
  }, [links.length])

  // Per-instance static-ish attributes
  useLayoutEffect(() => {
    if (!meshRef.current) return
    const maxAmt = Math.max(1, ...links.map(l => l.amount || 0))
    for (let i = 0; i < links.length; i++) {
      const l = links[i]
      const srcId = typeof l.source === 'string' ? l.source : (l.source as GraphNode).id
      const tgtId = typeof l.target === 'string' ? l.target : (l.target as GraphNode).id
      const fraud = l.is_flagged || fraudNodeIds.has(srcId) || fraudNodeIds.has(tgtId)
      const c = fraud ? fraudColor : safeColor
      iColor[i * 3]     = c[0]
      iColor[i * 3 + 1] = c[1]
      iColor[i * 3 + 2] = c[2]
      iRisk[i]   = Math.min(1, l.risk_score ?? 0)
      iFraud[i]  = fraud ? 1 : 0
      iAmount[i] = Math.log10(1 + (l.amount ?? 0)) / Math.log10(1 + maxAmt)
    }
    const g = meshRef.current.geometry
    g.setAttribute('iColor',  new THREE.InstancedBufferAttribute(iColor, 3))
    g.setAttribute('iRisk',   new THREE.InstancedBufferAttribute(iRisk, 1))
    g.setAttribute('iFraud',  new THREE.InstancedBufferAttribute(iFraud, 1))
    g.setAttribute('iAmount', new THREE.InstancedBufferAttribute(iAmount, 1))
  }, [links, fraudNodeIds, iColor, iRisk, iFraud, iAmount])

  // Per-frame: align each cylinder src→tgt using live positions
  useFrame((state) => {
    if (!meshRef.current) return
    const mesh = meshRef.current
    const arr = positions.array
    if (!arr) return

    for (let i = 0; i < links.length; i++) {
      const l = links[i]
      const srcId = typeof l.source === 'string' ? l.source : (l.source as GraphNode).id
      const tgtId = typeof l.target === 'string' ? l.target : (l.target as GraphNode).id
      const si = idIndex.get(srcId)
      const ti = idIndex.get(tgtId)
      if (si == null || ti == null) {
        // Hide instances that don't have positions yet by zero-scaling them
        tmpObj.scale.set(0, 0, 0)
        tmpObj.position.set(0, 0, 0)
        tmpObj.updateMatrix()
        mesh.setMatrixAt(i, tmpObj.matrix)
        continue
      }
      tmpVecA.set(arr[si * 3], arr[si * 3 + 1], arr[si * 3 + 2])
      tmpVecB.set(arr[ti * 3], arr[ti * 3 + 1], arr[ti * 3 + 2])
      tmpMid.copy(tmpVecA).add(tmpVecB).multiplyScalar(0.5)
      tmpDir.copy(tmpVecB).sub(tmpVecA)
      const len = tmpDir.length() || 0.0001
      tmpDir.normalize()
      tmpQuat.setFromUnitVectors(yAxis, tmpDir)

      tmpObj.position.copy(tmpMid)
      tmpObj.quaternion.copy(tmpQuat)
      // Thickness scales by transaction value
      const thick = 0.35 + iAmount[i] * 0.9 + iFraud[i] * 0.5
      tmpObj.scale.set(thick, len, thick)
      tmpObj.updateMatrix()
      mesh.setMatrixAt(i, tmpObj.matrix)
    }
    mesh.instanceMatrix.needsUpdate = true
    if (matRef.current) matRef.current.uniforms.uTime.value = state.clock.elapsedTime
  })

  const uniforms = useMemo(() => ({ uTime: { value: 0 } }), [])

  if (links.length === 0) return null

  return (
    <instancedMesh
      ref={meshRef}
      args={[undefined, undefined, links.length]}
      frustumCulled={false}
    >
      <cylinderGeometry args={[1, 1, 1, 10, 1, true]} />
      <shaderMaterial
        ref={matRef}
        vertexShader={edgeVert}
        fragmentShader={edgeFrag}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        side={THREE.DoubleSide}
        blending={THREE.AdditiveBlending}
        toneMapped={false}
      />
    </instancedMesh>
  )
}
