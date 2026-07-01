// GLSL source for the cinematic scene.
// Shaders are inlined as template strings — Vite handles them at build time.

// ── Background: animated neural grid + volumetric fog vignette ───────────────
export const bgVert = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = vec4(position.xy, 0.999, 1.0);
  }
`

export const bgFrag = /* glsl */ `
  precision highp float;
  varying vec2 vUv;
  uniform float uTime;
  uniform vec2  uResolution;
  uniform float uFraud; // 0..1 — fraud intensity, ramps red bias

  // hash + simplex-ish noise — cheap enough for fullscreen
  float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
  float noise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
  }

  void main() {
    vec2 uv = vUv;
    vec2 p  = (uv - 0.5) * vec2(uResolution.x / uResolution.y, 1.0);

    // Neural grid — two scales, animated drift
    vec2 g1 = fract(p * 14.0 + vec2(0.0, uTime * 0.012)) - 0.5;
    vec2 g2 = fract(p * 28.0 - vec2(uTime * 0.008, 0.0)) - 0.5;
    float grid = 0.0;
    grid += smoothstep(0.02, 0.0, abs(g1.x)) * 0.35;
    grid += smoothstep(0.02, 0.0, abs(g1.y)) * 0.35;
    grid += smoothstep(0.01, 0.0, abs(g2.x)) * 0.18;
    grid += smoothstep(0.01, 0.0, abs(g2.y)) * 0.18;

    // Radial scan sweep — slow, intelligence-system feel
    float r = length(p);
    float scan = exp(-pow((r - mod(uTime * 0.10, 1.4)) * 4.0, 2.0)) * 0.18;

    // Soft volumetric clouds
    float n = noise(p * 1.6 + vec2(uTime * 0.02, -uTime * 0.015));
    n      += noise(p * 4.0 - vec2(uTime * 0.04,  uTime * 0.03)) * 0.5;
    float fog = smoothstep(0.2, 1.1, n);

    // Vignette — deep graphite at edges
    float vig = smoothstep(1.2, 0.2, length(uv - 0.5) * 1.8);

    // Base palette
    vec3 deep   = vec3(0.008, 0.016, 0.040);
    vec3 cyan   = vec3(0.000, 0.420, 0.620) * 0.18;
    vec3 violet = vec3(0.260, 0.090, 0.520) * 0.10;
    vec3 red    = vec3(0.620, 0.080, 0.180);

    vec3 col = deep;
    col += cyan   * grid;
    col += violet * fog * 0.35;
    col += cyan   * scan;
    col  = mix(col, red, uFraud * (0.18 + scan + grid * 0.4));
    col *= vig;

    // Subtle film grain
    float grain = (hash(uv * uResolution.xy + uTime) - 0.5) * 0.018;
    col += grain;

    gl_FragColor = vec4(col, 1.0);
  }
`

// ── Nodes: instanced spheres with risk-colored halo + pulse ──────────────────
export const nodeVert = /* glsl */ `
  attribute vec3 iColor;
  attribute float iRisk;     // 0..1
  attribute float iFraud;    // 0 or 1
  attribute float iSelected; // 0 or 1
  attribute float iScale;    // base radius

  varying vec3  vNormal;
  varying vec3  vViewDir;
  varying vec3  vColor;
  varying float vRisk;
  varying float vFraud;
  varying float vSelected;

  uniform float uTime;

  void main() {
    vColor    = iColor;
    vRisk     = iRisk;
    vFraud    = iFraud;
    vSelected = iSelected;

    // Risk-driven micro-pulse on suspicious nodes
    float pulse = 1.0 + sin(uTime * 2.6 + iRisk * 12.0) * (iFraud * 0.10 + iRisk * 0.05);
    vec3  pos   = position * iScale * pulse;

    vec4 mv = modelViewMatrix * instanceMatrix * vec4(pos, 1.0);
    vNormal  = normalize(normalMatrix * (mat3(instanceMatrix) * normal));
    vViewDir = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
  }
`

export const nodeFrag = /* glsl */ `
  precision highp float;
  varying vec3  vNormal;
  varying vec3  vViewDir;
  varying vec3  vColor;
  varying float vRisk;
  varying float vFraud;
  varying float vSelected;
  uniform float uTime;

  void main() {
    // Fresnel rim — the "holographic" edge glow
    float fres = pow(1.0 - max(dot(vNormal, vViewDir), 0.0), 2.4);

    // Core + rim composition
    vec3 core = vColor * 0.55;
    vec3 rim  = vColor * (1.6 + vRisk * 0.8) * fres;

    // Fraud nodes get a hot inner ember + faster pulse
    float ember = sin(uTime * 4.0 + vRisk * 18.0) * 0.5 + 0.5;
    vec3  hot   = mix(vColor, vec3(1.0, 0.35, 0.25), 0.6) * ember * vFraud;

    // Selection halo bump
    float sel = vSelected * (0.6 + fres * 1.2);

    vec3 col = core + rim + hot * 0.45 + vColor * sel;

    // Soft alpha falloff for additive feel where bloom picks it up
    float a = clamp(0.55 + fres * 0.9 + vFraud * 0.3 + sel * 0.5, 0.0, 1.0);
    gl_FragColor = vec4(col, a);
  }
`

// ── Edges: flowing energy packets along directional money flow ───────────────
// We render edges as instanced thin cylinders aligned along source→target.
// Animation is a uv.x scroll modulated by amount + fraud.
export const edgeVert = /* glsl */ `
  varying vec2  vUv;
  varying float vRisk;
  varying float vFraud;
  varying float vAmount;
  varying vec3  vColor;

  attribute vec3 iColor;
  attribute float iRisk;
  attribute float iFraud;
  attribute float iAmount;  // log-normalized 0..1

  void main() {
    vUv     = uv;
    vRisk   = iRisk;
    vFraud  = iFraud;
    vAmount = iAmount;
    vColor  = iColor;
    gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(position, 1.0);
  }
`

export const edgeFrag = /* glsl */ `
  precision highp float;
  varying vec2  vUv;
  varying float vRisk;
  varying float vFraud;
  varying float vAmount;
  varying vec3  vColor;
  uniform float uTime;

  // Smooth pulse train along the edge — packets of light moving source→target.
  float packet(float u, float t, float speed, float spacing, float width) {
    float x = fract(u - t * speed) * spacing;
    return exp(-pow((x - spacing * 0.5) / width, 2.0));
  }

  void main() {
    // Cylindrical surface — vUv.y wraps around, vUv.x runs along the edge length.
    // Soft radial alpha so it reads as a glowing strand, not a flat tube.
    float radial = smoothstep(0.0, 0.5, 1.0 - abs(vUv.y - 0.5) * 2.0);

    float speed   = 0.35 + vAmount * 1.1 + vFraud * 0.6;
    float spacing = mix(0.45, 0.18, vAmount);
    float width   = 0.06 + vFraud * 0.04;
    float p = packet(vUv.x, uTime, speed, spacing, width);

    vec3  base = vColor * (0.25 + vRisk * 0.4);
    vec3  flow = vColor * (1.8 + vFraud * 1.2);
    vec3  col  = base + flow * p;

    float alpha = (0.12 + vRisk * 0.25 + p * (0.6 + vFraud * 0.4)) * radial;
    gl_FragColor = vec4(col, clamp(alpha, 0.0, 1.0));
  }
`

// ── Selection ring: expanding holographic halo around the focused node ───────
export const ringVert = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`

export const ringFrag = /* glsl */ `
  precision highp float;
  varying vec2 vUv;
  uniform float uTime;
  uniform vec3  uColor;

  void main() {
    float d   = length(vUv - 0.5) * 2.0;
    float ring = smoothstep(0.96, 1.0, d) - smoothstep(1.0, 1.04, d);
    float sweep = pow(0.5 + 0.5 * sin(uTime * 3.0 - d * 6.2832), 4.0);
    float a = ring * (0.7 + sweep * 0.6);
    gl_FragColor = vec4(uColor, a);
  }
`

// ── Shockwave: fraud-detected ripple ────────────────────────────────────────
export const shockwaveVert = ringVert
export const shockwaveFrag = /* glsl */ `
  precision highp float;
  varying vec2 vUv;
  uniform float uTime;
  uniform float uStart; // start time
  uniform vec3  uColor;

  void main() {
    float t = clamp((uTime - uStart) / 1.6, 0.0, 1.0);
    float d = length(vUv - 0.5) * 2.0;
    float front = smoothstep(t - 0.06, t, d) - smoothstep(t, t + 0.06, d);
    float fade  = 1.0 - t;
    gl_FragColor = vec4(uColor, front * fade * 1.2);
  }
`
