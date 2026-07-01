import { useEffect, useRef } from 'react'
import { useThree, useFrame } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import gsap from 'gsap'
import * as THREE from 'three'
import type { GraphNode } from '../../types'
import type { LayoutPositions, ClusterSector } from './useForceLayout'

interface Props {
  selectedNode: GraphNode | null
  nodes: GraphNode[]
  positions: LayoutPositions
  clusters: ClusterSector[]
  fraudJustDetected: number
  clearNonce: number
}

const tmpVec    = new THREE.Vector3()
const tmpTarget = new THREE.Vector3()
const tmpBox    = new THREE.Box3()

// Camera choreography:
// • OrbitControls for free navigation
// • GSAP focus when a node is selected
// • Auto-frame when a new cluster spawns (positions changed dramatically)
// • Subtle idle drift when nothing is selected
// • Fraud kick + smooth clear-reset
export function CameraRig({
  selectedNode, nodes, positions, clusters, fraudJustDetected, clearNonce,
}: Props) {
  const { camera } = useThree()
  const controlsRef    = useRef<any>(null)
  const lastFraudRef   = useRef(0)
  const lastClearRef   = useRef(0)
  const lastClusterRef = useRef(0)          // last seen cluster count
  const autoFrameTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Initial pose
  useEffect(() => {
    camera.position.set(0, 0, 280)
    camera.lookAt(0, 0, 0)
  }, [camera])

  // ── Auto-frame on new cluster ────────────────────────────────────────────────
  // When a second (or third…) disconnected component appears, the graph world
  // expands significantly. We detect this via the cluster list from the worker
  // and trigger a smooth zoom-out so all clusters are visible.
  useEffect(() => {
    const clusterCount = clusters.length
    if (clusterCount <= lastClusterRef.current) {
      lastClusterRef.current = clusterCount
      return
    }
    lastClusterRef.current = clusterCount

    // Let the force layout settle for ~2.5 s before computing the bounding box
    if (autoFrameTimer.current) clearTimeout(autoFrameTimer.current)
    autoFrameTimer.current = setTimeout(() => {
      const arr = positions.array
      if (!arr || arr.length < 3 || selectedNode) return

      // Build bounding sphere of all node positions
      tmpBox.makeEmpty()
      for (let i = 0; i < arr.length; i += 3) {
        tmpBox.expandByPoint(tmpVec.set(arr[i], arr[i + 1], arr[i + 2]))
      }
      const center = new THREE.Vector3()
      tmpBox.getCenter(center)
      const radius = tmpBox.min.distanceTo(tmpBox.max) * 0.5

      // Desired camera distance: fits the bounding sphere with 20% margin
      const fovRad   = (60 * Math.PI) / 180
      const desired  = Math.min(1300, (radius / Math.sin(fovRad / 2)) * 1.2 + 80)
      const direction = camera.position.clone().normalize()
      if (direction.lengthSq() < 0.01) direction.set(0, 0, 1)

      // Pan orbit target to bounding-sphere center, pull camera back
      gsap.killTweensOf(camera.position)
      if (controlsRef.current) {
        gsap.killTweensOf(controlsRef.current.target)
        gsap.to(controlsRef.current.target, {
          x: center.x, y: center.y, z: center.z,
          duration: 2.2, ease: 'power2.inOut',
          onUpdate: () => controlsRef.current?.update(),
        })
      }
      gsap.to(camera.position, {
        x: center.x + direction.x * desired,
        y: center.y + direction.y * desired,
        z: center.z + direction.z * desired,
        duration: 2.2, ease: 'power2.inOut',
      })
    }, 2500)

    return () => { if (autoFrameTimer.current) clearTimeout(autoFrameTimer.current) }
  }, [clusters.length, camera, selectedNode, positions])

  // ── Graph clear: smooth reset to default pose ─────────────────────────────
  useEffect(() => {
    if (clearNonce === 0 || clearNonce === lastClearRef.current) return
    lastClearRef.current = clearNonce
    if (autoFrameTimer.current) clearTimeout(autoFrameTimer.current)
    lastClusterRef.current = 0

    gsap.killTweensOf(camera.position)
    gsap.to(camera.position, {
      x: 0, y: 0, z: 280,
      duration: 1.1, ease: 'power3.inOut',
    })
    if (controlsRef.current) {
      gsap.killTweensOf(controlsRef.current.target)
      gsap.to(controlsRef.current.target, {
        x: 0, y: 0, z: 0,
        duration: 1.1, ease: 'power3.inOut',
        onUpdate: () => controlsRef.current?.update(),
      })
    }
  }, [clearNonce, camera])

  // ── Cinematic focus when a node is selected ───────────────────────────────
  useEffect(() => {
    if (!selectedNode) return
    const idx = nodes.findIndex(n => n.id === selectedNode.id)
    if (idx < 0) return
    const arr = positions.array
    if (!arr || arr.length < (idx + 1) * 3) return

    tmpTarget.set(arr[idx * 3], arr[idx * 3 + 1], arr[idx * 3 + 2])
    // Offset camera 80 units back from node along current view direction
    tmpVec
      .copy(camera.position)
      .sub(controlsRef.current?.target ?? new THREE.Vector3())
      .normalize()
      .multiplyScalar(80)
    const camTarget = tmpTarget.clone().add(tmpVec)

    gsap.to(camera.position, {
      x: camTarget.x, y: camTarget.y, z: camTarget.z,
      duration: 1.4, ease: 'power3.inOut',
    })
    if (controlsRef.current) {
      gsap.to(controlsRef.current.target, {
        x: tmpTarget.x, y: tmpTarget.y, z: tmpTarget.z,
        duration: 1.4, ease: 'power3.inOut',
        onUpdate: () => controlsRef.current?.update(),
      })
    }
  }, [selectedNode, nodes, positions, camera])

  // ── Fraud detection kick ──────────────────────────────────────────────────
  useEffect(() => {
    if (fraudJustDetected === lastFraudRef.current) return
    lastFraudRef.current = fraudJustDetected
    const start = camera.position.clone()
    gsap.to(camera.position, {
      x: start.x * 0.92, y: start.y * 0.92, z: start.z * 0.92,
      duration: 0.45, ease: 'power2.out',
      yoyo: true, repeat: 1,
    })
  }, [fraudJustDetected, camera])

  // ── Gentle idle drift ─────────────────────────────────────────────────────
  useFrame((state) => {
    if (selectedNode) return
    if (!controlsRef.current) return
    const t    = state.clock.elapsedTime
    const ctrl = controlsRef.current
    ctrl.target.x += (Math.sin(t * 0.13) * 4 - ctrl.target.x) * 0.0015
    ctrl.target.y += (Math.cos(t * 0.10) * 3 - ctrl.target.y) * 0.0015
  })

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      enableDamping
      dampingFactor={0.08}
      rotateSpeed={0.55}
      zoomSpeed={0.8}
      minDistance={20}
      maxDistance={1400}
      enablePan={true}
      panSpeed={0.6}
    />
  )
}
