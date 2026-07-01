import { useFrame } from '@react-three/fiber'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { shockwaveVert, shockwaveFrag } from '../shaders/glsl'
import { PALETTE, rgb } from '../shaders/palette'

interface Props {
  trigger: number     // nonce — change to fire a new wave
  center: THREE.Vector3
}

// One expanding ring per fraud event. Cheap, looks expensive.
export function Shockwave({ trigger, center }: Props) {
  const ref = useRef<THREE.Mesh>(null)
  const matRef = useRef<THREE.ShaderMaterial>(null)
  const [startTime, setStartTime] = useState<number | null>(null)
  const lastTrigger = useRef(0)

  const uniforms = useMemo(() => ({
    uTime:  { value: 0 },
    uStart: { value: 0 },
    uColor: { value: new THREE.Vector3(...rgb(PALETTE.fraudEdge)) },
  }), [])

  useEffect(() => {
    if (trigger !== lastTrigger.current) {
      lastTrigger.current = trigger
      setStartTime(null) // mark "needs new start"
    }
  }, [trigger])

  useFrame((state) => {
    if (!ref.current || !matRef.current) return
    if (startTime == null) {
      uniforms.uStart.value = state.clock.elapsedTime
      setStartTime(state.clock.elapsedTime)
      ref.current.position.copy(center)
    }
    ref.current.quaternion.copy(state.camera.quaternion)
    uniforms.uTime.value = state.clock.elapsedTime
    // Auto-grow the plane so the front edge stays sharp
    const t = Math.min(1.6, state.clock.elapsedTime - uniforms.uStart.value)
    const scale = 30 + t * 220
    ref.current.scale.setScalar(scale)
    ref.current.visible = t < 1.6
  })

  return (
    <mesh ref={ref} visible={false} renderOrder={10}>
      <planeGeometry args={[1, 1, 1, 1]} />
      <shaderMaterial
        ref={matRef}
        vertexShader={shockwaveVert}
        fragmentShader={shockwaveFrag}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        toneMapped={false}
      />
    </mesh>
  )
}
