import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { PALETTE, rgb } from '../shaders/palette'

interface Props {
  count?: number
  fraudIntensity: number
}

// Ambient drifting particle field — adds depth and "live system" feel.
// Cheap Points cloud, additive blended. Color biases to red as fraud rises.
export function Particles({ count = 1500, fraudIntensity }: Props) {
  const pointsRef = useRef<THREE.Points>(null)

  const { positions, sizes } = useMemo(() => {
    const positions = new Float32Array(count * 3)
    const sizes = new Float32Array(count)
    for (let i = 0; i < count; i++) {
      const r = 60 + Math.random() * 280
      const phi = Math.acos(2 * Math.random() - 1)
      const theta = Math.random() * Math.PI * 2
      positions[i * 3]     = r * Math.sin(phi) * Math.cos(theta)
      positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta)
      positions[i * 3 + 2] = r * Math.cos(phi)
      sizes[i] = 0.4 + Math.random() * 1.1
    }
    return { positions, sizes }
  }, [count])

  useFrame((state) => {
    if (!pointsRef.current) return
    pointsRef.current.rotation.y = state.clock.elapsedTime * 0.012
    pointsRef.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.04) * 0.05
    const mat = pointsRef.current.material as THREE.PointsMaterial
    const safe = rgb(PALETTE.hologramEdge)
    const fr   = rgb(PALETTE.fraudEdge)
    const t = fraudIntensity
    mat.color.setRGB(
      safe[0] * (1 - t) + fr[0] * t,
      safe[1] * (1 - t) + fr[1] * t,
      safe[2] * (1 - t) + fr[2] * t,
    )
  })

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" array={positions} count={count} itemSize={3} args={[positions, 3]} />
        <bufferAttribute attach="attributes-size"     array={sizes}     count={count} itemSize={1} args={[sizes, 1]} />
      </bufferGeometry>
      <pointsMaterial
        size={0.6}
        sizeAttenuation
        transparent
        opacity={0.55}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        toneMapped={false}
      />
    </points>
  )
}
