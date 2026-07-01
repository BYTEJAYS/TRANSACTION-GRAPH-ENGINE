import { useMemo, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { bgVert, bgFrag } from '../shaders/glsl'

interface Props {
  fraudIntensity: number
}

// Fullscreen quad rendered as the absolute backmost layer.
// Drives the cinematic neural-grid + fog + scan-sweep look.
export function Background({ fraudIntensity }: Props) {
  const { size } = useThree()
  const matRef = useRef<THREE.ShaderMaterial>(null)
  const fraudRef = useRef(0)

  const uniforms = useMemo(() => ({
    uTime:       { value: 0 },
    uResolution: { value: new THREE.Vector2(size.width, size.height) },
    uFraud:      { value: 0 },
  }), [])

  useFrame((state) => {
    if (!matRef.current) return
    const u = matRef.current.uniforms
    u.uTime.value = state.clock.elapsedTime
    u.uResolution.value.set(state.size.width, state.size.height)
    // Smooth lerp toward target fraud intensity — avoids harsh flips
    fraudRef.current += (fraudIntensity - fraudRef.current) * 0.04
    u.uFraud.value = fraudRef.current
  })

  return (
    <mesh frustumCulled={false} renderOrder={-1000}>
      <planeGeometry args={[2, 2]} />
      <shaderMaterial
        ref={matRef}
        vertexShader={bgVert}
        fragmentShader={bgFrag}
        uniforms={uniforms}
        depthTest={false}
        depthWrite={false}
        toneMapped={false}
      />
    </mesh>
  )
}
