import { useRef, Suspense } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import type { VoiceState } from '../../hooks/useVoiceAssistant'

// ── Glass orb shader ─────────────────────────────────────────────────────────
const orbVert = /* glsl */`
  varying vec3 vNormal;
  varying vec3 vWorldPos;
  varying vec2 vUv;
  void main() {
    vNormal   = normalize(normalMatrix * normal);
    vWorldPos = (modelMatrix * vec4(position, 1.0)).xyz;
    vUv       = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`

const orbFrag = /* glsl */`
  precision highp float;
  uniform float uTime;
  uniform float uBreathe;
  uniform float uFraud;
  uniform float uSpeaking;
  varying vec3 vNormal;
  varying vec3 vWorldPos;
  varying vec2 vUv;

  void main() {
    vec3 camDir  = normalize(cameraPosition - vWorldPos);
    float NdotV  = max(0.0, dot(normalize(vNormal), camDir));
    float fresnel = pow(1.0 - NdotV, 2.8);

    // Base coat — very dark with slight cool tint
    vec3 base = vec3(0.035, 0.040, 0.058);

    // State-driven inner emission
    vec3 idleGlow  = vec3(0.10, 0.15, 0.26);
    vec3 fraudGlow = vec3(0.26, 0.06, 0.06);
    vec3 speakGlow = vec3(0.12, 0.20, 0.36);

    vec3 inner = mix(idleGlow, fraudGlow, uFraud);
    inner = mix(inner, speakGlow, uSpeaking * 0.65);

    float breathe = 0.55 + 0.45 * uBreathe;
    float pulse   = 0.85 + 0.15 * sin(uTime * (2.0 + uFraud * 1.5));

    // Primary specular highlight — top-left, sharp
    vec3 h1dir = normalize(vec3(-0.50, 0.75, 0.45));
    float spec1 = pow(max(0.0, dot(normalize(vNormal), h1dir)), 14.0);

    // Secondary highlight — soft, lower-right
    vec3 h2dir = normalize(vec3(0.55, -0.40, 0.65));
    float spec2 = pow(max(0.0, dot(normalize(vNormal), h2dir)), 7.0) * 0.22;

    // Edge chromatic tint — cool blue rim
    vec3 rim = mix(vec3(0.22, 0.38, 0.70), vec3(0.55, 0.10, 0.10), uFraud);

    vec3 col = base
      + inner * breathe * pulse * (0.70 + fresnel * 0.45)
      + vec3(spec1 * 0.88 + spec2 * 0.18)
      + rim * fresnel * 0.13;

    float alpha = 0.90 + fresnel * 0.10;
    gl_FragColor = vec4(col, alpha);
  }
`

// ── Inner glow core shader ───────────────────────────────────────────────────
const coreVert = /* glsl */`
  varying vec3 vNormal;
  void main() {
    vNormal = normalize(normalMatrix * normal);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`

const coreFrag = /* glsl */`
  precision mediump float;
  uniform float uTime;
  uniform float uFraud;
  uniform float uSpeaking;
  uniform float uBreathe;
  varying vec3 vNormal;

  void main() {
    vec3 idleCol  = vec3(0.15, 0.25, 0.50);
    vec3 fraudCol = vec3(0.55, 0.10, 0.10);
    vec3 speakCol = vec3(0.18, 0.30, 0.62);

    vec3 col = mix(idleCol, fraudCol, uFraud);
    col = mix(col, speakCol, uSpeaking * 0.5);

    float pulse = 0.7 + 0.3 * uBreathe;
    float alpha = (0.12 + 0.10 * pulse) * (1.0 - 0.3 * uFraud);

    gl_FragColor = vec4(col, alpha);
  }
`

// ── Scene ────────────────────────────────────────────────────────────────────
function OrbScene({ voiceState }: { voiceState: VoiceState }) {
  const orbMat  = useRef<THREE.ShaderMaterial>(null)
  const coreMat = useRef<THREE.ShaderMaterial>(null)
  const groupRef = useRef<THREE.Group>(null)

  const leftEyeRef  = useRef<THREE.Mesh>(null)
  const rightEyeRef = useRef<THREE.Mesh>(null)

  const uniforms = useRef({
    uTime:     { value: 0 },
    uBreathe:  { value: 0.5 },
    uFraud:    { value: 0 },
    uSpeaking: { value: 0 },
  })

  useFrame(({ clock }) => {
    const t   = clock.getElapsedTime()
    const u   = uniforms.current

    u.uTime.value    = t
    u.uBreathe.value = (Math.sin(t * 0.75) + 1) * 0.5

    const tFraud = voiceState === 'fraud' ? 1 : 0
    const tSpeak = voiceState === 'speaking' ? 1 : 0
    u.uFraud.value    += (tFraud - u.uFraud.value)    * 0.04
    u.uSpeaking.value += (tSpeak - u.uSpeaking.value) * 0.05

    // Apply to core material
    if (coreMat.current) {
      Object.assign(coreMat.current.uniforms, {
        uTime:     u.uTime,
        uBreathe:  u.uBreathe,
        uFraud:    u.uFraud,
        uSpeaking: u.uSpeaking,
      })
    }

    // Float animation
    if (groupRef.current) {
      groupRef.current.position.y = Math.sin(t * 0.55) * 0.055
      groupRef.current.rotation.y = t * 0.06
    }

    // Micro eye drift
    if (leftEyeRef.current) {
      leftEyeRef.current.position.y  = -0.19 + Math.sin(t * 0.38) * 0.008
    }
    if (rightEyeRef.current) {
      rightEyeRef.current.position.y = -0.19 + Math.sin(t * 0.38 + 0.3) * 0.008
    }
  })

  return (
    <group ref={groupRef}>
      {/* Inner emission core */}
      <mesh>
        <sphereGeometry args={[1.35, 32, 32]} />
        <shaderMaterial
          ref={coreMat}
          vertexShader={coreVert}
          fragmentShader={coreFrag}
          uniforms={uniforms.current}
          transparent
          depthWrite={false}
        />
      </mesh>

      {/* Outer glass sphere */}
      <mesh>
        <sphereGeometry args={[1.68, 80, 80]} />
        <shaderMaterial
          ref={orbMat}
          vertexShader={orbVert}
          fragmentShader={orbFrag}
          uniforms={uniforms.current}
          transparent
          side={THREE.FrontSide}
        />
      </mesh>

      {/* Eye dots — subtle, forward-facing */}
      <group position={[0, 0, 1.55]}>
        <mesh ref={leftEyeRef} position={[-0.28, -0.19, 0]}>
          <sphereGeometry args={[0.065, 12, 12]} />
          <meshBasicMaterial color="#060810" />
        </mesh>
        <mesh ref={rightEyeRef} position={[0.28, -0.19, 0]}>
          <sphereGeometry args={[0.065, 12, 12]} />
          <meshBasicMaterial color="#060810" />
        </mesh>
      </group>
    </group>
  )
}

// ── Waveform bars ────────────────────────────────────────────────────────────
function WaveformBar({ i, state }: { i: number; state: VoiceState }) {
  const barRef = useRef<THREE.Mesh>(null)
  const phase  = (i / 20) * Math.PI * 2

  useFrame(({ clock }) => {
    if (!barRef.current) return
    const t = clock.getElapsedTime()
    let h: number
    if (state === 'speaking') {
      h = 0.08 + 0.22 * Math.abs(Math.sin(t * 3.5 + phase))
    } else if (state === 'fraud') {
      h = 0.06 + 0.16 * Math.abs(Math.sin(t * 4.5 + phase))
    } else {
      h = 0.01 + 0.03 * Math.abs(Math.sin(t * 0.8 + phase))
    }
    barRef.current.scale.y = Math.max(0.05, h * 8)
  })

  const x = (i - 10) * 0.18
  const color = state === 'fraud' ? '#f85149' : '#4493f8'

  return (
    <mesh ref={barRef} position={[x, 0, 0]}>
      <boxGeometry args={[0.08, 1, 0.08]} />
      <meshBasicMaterial color={color} opacity={0.65} transparent />
    </mesh>
  )
}

function WaveformScene({ state }: { state: VoiceState }) {
  return (
    <group>
      {Array.from({ length: 20 }, (_, i) => (
        <WaveformBar key={i} i={i} state={state} />
      ))}
    </group>
  )
}

// ── Exports ──────────────────────────────────────────────────────────────────
export function AIOrb({
  voiceState = 'idle',
  size = 168,
}: {
  voiceState?: VoiceState
  size?: number
}) {
  return (
    <Canvas
      style={{ width: size, height: size }}
      camera={{ position: [0, 0, 4.8], fov: 38 }}
      gl={{ alpha: true, antialias: true, preserveDrawingBuffer: false }}
      dpr={[1, 2]}
    >
      <ambientLight intensity={0.06} />
      <pointLight position={[-3, 4, 3]} intensity={0.4} color="#7baeff" />
      <pointLight position={[3, -3, 2]} intensity={0.12} color="#ff7070" />
      <Suspense fallback={null}>
        <OrbScene voiceState={voiceState} />
      </Suspense>
    </Canvas>
  )
}

export function OrbWaveform({
  voiceState = 'idle',
  width = 220,
  height = 32,
}: {
  voiceState?: VoiceState
  width?: number
  height?: number
}) {
  return (
    <Canvas
      style={{ width, height }}
      camera={{ position: [0, 0, 3], fov: 55 }}
      gl={{ alpha: true, antialias: false }}
    >
      <Suspense fallback={null}>
        <WaveformScene state={voiceState} />
      </Suspense>
    </Canvas>
  )
}
