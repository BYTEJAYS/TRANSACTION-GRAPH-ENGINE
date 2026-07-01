import { EffectComposer, Bloom, ChromaticAberration, Vignette, Noise } from '@react-three/postprocessing'
import { BlendFunction, KernelSize } from 'postprocessing'
import * as THREE from 'three'

interface Props {
  fraudIntensity: number
}

// Cinematic postprocessing stack.
// - Bloom: punches up the additive node/edge shaders so fraud reads "hot"
// - Chromatic aberration: cyberpunk lens feel, subtle
// - Vignette: pulls focus to the center, hides edge tiling
// - Noise: tiny grain layer for filmic texture
export function PostFX({ fraudIntensity }: Props) {
  // Bloom intensity ramps with fraud so detections feel hotter on screen
  const bloomIntensity = 0.95 + fraudIntensity * 0.6

  return (
    <EffectComposer multisampling={0}>
      <Bloom
        intensity={bloomIntensity}
        luminanceThreshold={0.18}
        luminanceSmoothing={0.4}
        mipmapBlur
        kernelSize={KernelSize.LARGE}
      />
      <ChromaticAberration
        offset={new THREE.Vector2(0.0008, 0.0008)}
        radialModulation={true}
        modulationOffset={0.5}
      />
      <Vignette eskil={false} offset={0.18} darkness={0.85} />
      <Noise opacity={0.035} blendFunction={BlendFunction.OVERLAY} />
    </EffectComposer>
  )
}
