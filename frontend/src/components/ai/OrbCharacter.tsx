import { useEffect, useRef } from 'react'
import type { VoiceState } from '../../hooks/useVoiceAssistant'

// Internal orb modes (matches orb-character.html original)
type OrbMode = 'idle' | 'listening' | 'speaking' | 'alert'

function voiceToMode(v: VoiceState): OrbMode {
  if (v === 'speaking') return 'speaking'
  if (v === 'fraud')    return 'alert'
  // 'listening' and 'processing' (thinking) both drive the listening shimmer
  // + ripples so the orb visibly reacts before it speaks.
  if (v === 'listening' || v === 'processing') return 'listening'
  return 'idle'
}

interface Props {
  voiceState?: VoiceState
  size?: number
  /** If true, the orb's eyes & light follow the page pointer. */
  interactive?: boolean
  /** Sphere radius as a fraction of the smaller canvas dimension. */
  radiusFactor?: number
}

export function OrbCharacter({
  voiceState = 'idle',
  size = 200,
  interactive = true,
  radiusFactor = 0.42,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const modeRef   = useRef<OrbMode>(voiceToMode(voiceState))

  // Keep the mode ref synced with the prop without restarting the animation loop.
  useEffect(() => {
    modeRef.current = voiceToMode(voiceState)
  }, [voiceState])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    canvas.width  = size * dpr
    canvas.height = size * dpr
    canvas.style.width  = `${size}px`
    canvas.style.height = `${size}px`
    ctx.scale(dpr, dpr)

    const W  = size
    const H  = size
    const CX = W / 2
    const CY = H / 2
    const R  = Math.min(W, H) * radiusFactor

    // ── Offscreen layers ─────────────────────────────────────────────────────
    const ocSize = Math.ceil(R * 2) + 16
    const colorC = document.createElement('canvas')
    const sheenC = document.createElement('canvas')
    colorC.width = colorC.height = ocSize
    sheenC.width = sheenC.height = ocSize
    const colorCtx = colorC.getContext('2d')!
    const sheenCtx = sheenC.getContext('2d')!

    // ── State ────────────────────────────────────────────────────────────────
    let alertMix = 0, listenMix = 0, speakMix = 0, speakWave = 0
    let pX: number | null = null, pY: number | null = null
    let lightX = -0.28, lightY = -0.30
    let eX = 0, eY = 0
    let floatY = 0
    let blinkOpen = 1, blinkDir = 0, blinkTimer = 3.5 + Math.random() * 2.5
    let idleTimer: ReturnType<typeof setTimeout> | undefined
    let raf = 0

    // ── Helpers ──────────────────────────────────────────────────────────────
    type RGB = [number, number, number]
    const mix = (a: RGB, b: RGB, t: number): RGB =>
      [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]
    const rgba = (c: RGB, a: number) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`

    // ── Idle look-around ─────────────────────────────────────────────────────
    const resetIdle = () => {
      if (idleTimer) clearTimeout(idleTimer)
      idleTimer = setTimeout(() => {
        const a = Math.random() * Math.PI * 2
        const d = R * (0.30 + Math.random() * 1.1)
        pX = CX + Math.cos(a) * d
        pY = CY + Math.sin(a) * d
        resetIdle()
      }, 2400 + Math.random() * 3600)
    }

    // ── Pointer (page-relative; we project onto the canvas bounds) ──────────
    const onPointer = (clientX: number, clientY: number) => {
      const rect = canvas.getBoundingClientRect()
      // Translate page coords into canvas-local coords (clamped to a generous box).
      pX = ((clientX - rect.left) / rect.width)  * W
      pY = ((clientY - rect.top)  / rect.height) * H
      resetIdle()
    }
    const onMouseMove = (e: MouseEvent)  => onPointer(e.clientX, e.clientY)
    const onTouchMove = (e: TouchEvent)  => {
      if (e.touches[0]) onPointer(e.touches[0].clientX, e.touches[0].clientY)
    }
    if (interactive) {
      document.addEventListener('mousemove', onMouseMove)
      document.addEventListener('touchmove', onTouchMove, { passive: true })
    }

    // Click to blink
    const onClick = () => { blinkDir = -1; blinkTimer = 0 }
    canvas.addEventListener('click', onClick)

    // ── Drawing routines (ported from orb-character.html) ───────────────────
    function drawBlob(
      s: CanvasRenderingContext2D, cx: number, cy: number, r: number,
      phase: number, ox: number, oy: number, ax: number, ay: number, radF: number,
      stops: Array<[number, number, number, number, number]>,
      aMix: number, alertCol: RGB,
    ) {
      const x = cx + (ox + Math.sin(phase) * ax) * r
      const y = cy + (oy + Math.cos(phase * 0.85) * ay) * r
      const g = s.createRadialGradient(x, y, 0, x, y, r * radF)
      for (const stop of stops) {
        const m = mix([stop[1], stop[2], stop[3]], alertCol, aMix)
        g.addColorStop(stop[0], rgba(m, stop[4]))
      }
      g.addColorStop(1, 'transparent')
      s.fillStyle = g
      s.fillRect(0, 0, ocSize, ocSize)
    }

    function hotSpot(
      s: CanvasRenderingContext2D, cx: number, cy: number, r: number,
      phase: number, ax: number, ay: number, rad: number,
      col: [number, number, number, number],
    ) {
      const x = cx + Math.sin(phase) * ax * r
      const y = cy + Math.cos(phase * 1.15) * ay * r
      const g = s.createRadialGradient(x, y, 0, x, y, r * rad)
      g.addColorStop(0, `rgba(${col[0]},${col[1]},${col[2]},${col[3]})`)
      g.addColorStop(1, 'transparent')
      s.fillStyle = g
      s.fillRect(0, 0, ocSize, ocSize)
    }

    function renderColorLayer(r: number, t: number) {
      const s  = colorCtx
      const sz = ocSize
      const cx = sz / 2, cy = sz / 2

      s.globalCompositeOperation = 'source-over'
      s.clearRect(0, 0, sz, sz)
      s.fillStyle = '#000'
      s.fillRect(0, 0, sz, sz)

      s.globalCompositeOperation = 'screen'
      const wash = s.createRadialGradient(cx - r * 0.15, cy - r * 0.05, 0, cx, cy, r * 1.08)
      const cBlue:   RGB = mix([ 30, 130, 220], [200,  70, 20], alertMix)
      const cPurple: RGB = mix([ 80,  40, 200], [220,  60, 30], alertMix)
      const cPink:   RGB = mix([180,  20, 130], [255, 100, 20], alertMix)
      const cOrange: RGB = mix([230,  60,  20], [255, 130, 20], alertMix)
      wash.addColorStop(0,    rgba(cBlue,   0.95))
      wash.addColorStop(0.45, rgba(cPurple, 0.78))
      wash.addColorStop(0.78, rgba(cPink,   0.52))
      wash.addColorStop(1,    rgba(cOrange, 0.28))
      s.fillStyle = wash
      s.fillRect(0, 0, sz, sz)

      const flow = 1 + listenMix * 0.6 + speakMix * 1.1 + alertMix * 0.4

      drawBlob(s, cx, cy, r, t * 0.42 * flow, -0.22, -0.18, 0.16, 0.14, 0.95, [
        [0.00,  90, 235, 255, 1.00],
        [0.18,  40, 170, 255, 0.92],
        [0.42,  18,  85, 245, 0.62],
        [0.72,   8,  30, 210, 0.22],
      ], alertMix, [255, 180, 30])

      drawBlob(s, cx, cy, r, t * 0.30 * flow + 1.2, -0.05, 0.28, 0.18, 0.12, 0.50, [
        [0.00, 70, 200, 255, 0.85],
        [0.50, 25, 110, 235, 0.40],
      ], alertMix, [255, 140, 30])

      drawBlob(s, cx, cy, r, t * 0.28 * flow + 2.1, 0.22, 0.02, 0.14, 0.16, 0.88, [
        [0.00, 255,  40, 175, 1.00],
        [0.22, 245,  10, 145, 0.90],
        [0.50, 195,   0, 100, 0.55],
        [0.85, 115,   0,  60, 0.18],
      ], alertMix, [255, 120, 40])

      drawBlob(s, cx, cy, r, t * 0.36 * flow + 5.1, -0.02, 0.05, 0.20, 0.18, 0.55, [
        [0.00, 165,  30, 240, 0.90],
        [0.50, 120,   0, 200, 0.45],
      ], alertMix, [240, 80, 60])

      drawBlob(s, cx, cy, r, t * 0.23 * flow + 4.35, 0.10, 0.40, 0.10, 0.08, 0.74, [
        [0.00, 255, 95, 50, 0.62],
        [0.30, 235, 50, 20, 0.46],
        [0.65, 170, 20, 10, 0.18],
      ], alertMix, [255, 80, 30])

      hotSpot(s, cx, cy, r, t * 0.55 + 0.7, 0.18, 0.22, 0.18, [255, 200, 255, 0.55])
      hotSpot(s, cx, cy, r, t * 0.48 + 3.2, 0.25, 0.18, 0.14, [180, 255, 255, 0.45])
      hotSpot(s, cx, cy, r, t * 0.62 + 1.9, 0.20, 0.30, 0.12, [255, 230, 255, 0.40])

      s.globalCompositeOperation = 'source-over'
      const rim = s.createRadialGradient(cx, cy, r * 0.74, cx, cy, r + 2)
      rim.addColorStop(0,    'transparent')
      rim.addColorStop(0.85, 'rgba(50, 0, 70, 0.20)')
      rim.addColorStop(1,    'rgba(20, 0, 40, 0.32)')
      s.fillStyle = rim
      s.fillRect(0, 0, sz, sz)
    }

    function renderSheenLayer(r: number, _t: number) {
      const s  = sheenCtx
      const sz = ocSize
      const cx = sz / 2, cy = sz / 2

      s.globalCompositeOperation = 'source-over'
      s.clearRect(0, 0, sz, sz)

      const sx = cx + lightX * r * 0.34
      const sy = cy + lightY * r * 0.34
      let g = s.createRadialGradient(sx, sy, 0, sx, sy, r * 0.62)
      g.addColorStop(0,    'rgba(255,255,255,0.86)')
      g.addColorStop(0.13, 'rgba(255,255,255,0.55)')
      g.addColorStop(0.35, 'rgba(255,255,255,0.20)')
      g.addColorStop(0.60, 'rgba(255,255,255,0.04)')
      g.addColorStop(1,    'transparent')
      s.fillStyle = g
      s.fillRect(0, 0, sz, sz)

      const hx = cx + lightX * r * 0.40
      const hy = cy + lightY * r * 0.40
      g = s.createRadialGradient(hx, hy, 0, hx, hy, r * 0.13)
      g.addColorStop(0,   'rgba(255,255,255,0.92)')
      g.addColorStop(0.5, 'rgba(255,255,255,0.20)')
      g.addColorStop(1,   'transparent')
      s.fillStyle = g
      s.fillRect(0, 0, sz, sz)

      s.save()
      s.translate(cx, cy)
      s.rotate(Math.atan2(lightY, lightX) + Math.PI * 0.5)
      s.translate(r * 0.55, 0)
      s.scale(0.32, 1.05)
      const sheen = s.createRadialGradient(0, 0, 0, 0, 0, r * 0.7)
      sheen.addColorStop(0,   'rgba(255,255,255,0.55)')
      sheen.addColorStop(0.5, 'rgba(255,255,255,0.10)')
      sheen.addColorStop(1,   'transparent')
      s.fillStyle = sheen
      s.beginPath()
      s.arc(0, 0, r * 0.7, 0, Math.PI * 2)
      s.fill()
      s.restore()

      const sheen2 = s.createLinearGradient(0, cy + r * 0.35, 0, cy + r * 1.0)
      sheen2.addColorStop(0,   'transparent')
      sheen2.addColorStop(0.7, 'rgba(255,255,255,0.04)')
      sheen2.addColorStop(1,   'rgba(255,255,255,0.14)')
      s.fillStyle = sheen2
      s.fillRect(0, 0, sz, sz)

      const b2x = cx - lightX * r * 0.55
      const b2y = cy - lightY * r * 0.55
      g = s.createRadialGradient(b2x, b2y, 0, b2x, b2y, r * 0.28)
      g.addColorStop(0, 'rgba(255,255,255,0.13)')
      g.addColorStop(1, 'transparent')
      s.fillStyle = g
      s.fillRect(0, 0, sz, sz)
    }

    function drawGlow(cy: number, r: number, t: number) {
      const pulse = 1 + Math.sin(t * 1.7) * 0.04
                     + speakMix  * 0.10 * (0.5 + 0.5 * Math.sin(t * 5 + speakWave))
                     + listenMix * 0.04 * Math.sin(t * 8)

      // Cool palette tuned to the app accent (#4493f8). Alert tilts toward a
      // muted amber so it still reads as a warning without going neon.
      const cyan:   RGB = mix([ 68, 147, 248], [220, 110,  40], alertMix)
      const navy:   RGB = mix([ 20,  60, 140], [120,  50,  20], alertMix)

      // Tight outer halo — fades to fully transparent well inside the canvas
      // bounds so no rectangular edge can show against the panel.
      const g = ctx!.createRadialGradient(CX, cy, r * 0.55, CX, cy, r * 1.40 * pulse)
      g.addColorStop(0,    rgba(cyan, 0.18))
      g.addColorStop(0.35, rgba(cyan, 0.09))
      g.addColorStop(0.70, rgba(navy, 0.03))
      g.addColorStop(1,    'transparent')
      ctx!.fillStyle = g
      ctx!.fillRect(0, 0, W, H)

      // Cool under-glow (replaces the warm orange wash) — barely-there ambient.
      const ug = ctx!.createRadialGradient(CX, cy + r * 0.40, 0, CX, cy + r * 0.40, r * 1.10)
      ug.addColorStop(0,   `rgba(70, 140, 240, ${0.05 + alertMix * 0.06})`)
      ug.addColorStop(0.6, 'rgba(30, 70, 150, 0.015)')
      ug.addColorStop(1,   'transparent')
      ctx!.fillStyle = ug
      ctx!.fillRect(0, 0, W, H)
    }

    // Listening ripples
    const ripples: Array<{ age: number; life: number }> = []
    let rippleTimer = 0
    function tickRipples(dt: number) {
      if (listenMix > 0.1) {
        rippleTimer -= dt
        if (rippleTimer <= 0) {
          ripples.push({ age: 0, life: 2.2 })
          rippleTimer = 0.55
        }
      }
      for (let i = ripples.length - 1; i >= 0; i--) {
        ripples[i].age += dt
        if (ripples[i].age > ripples[i].life) ripples.splice(i, 1)
      }
    }
    function drawRipples(cy: number, r: number) {
      if (listenMix < 0.02) return
      for (const ring of ripples) {
        const p = ring.age / ring.life
        const rad = r * (1.0 + p * 0.85)
        const alpha = listenMix * (1 - p) * 0.5
        ctx!.beginPath()
        ctx!.arc(CX, cy, rad, 0, Math.PI * 2)
        ctx!.strokeStyle = `rgba(140, 200, 255, ${alpha})`
        ctx!.lineWidth = 1 + (1 - p) * 1.2
        ctx!.stroke()
      }
    }

    function drawSphere(cy: number, r: number, t: number) {
      renderColorLayer(r, t)
      renderSheenLayer(r, t)

      ctx!.save()
      ctx!.beginPath()
      ctx!.arc(CX, cy, r, 0, Math.PI * 2)
      ctx!.clip()

      ctx!.filter = `blur(${Math.max(6, r * 0.045)}px) saturate(115%)`
      ctx!.drawImage(colorC, CX - ocSize / 2, cy - ocSize / 2)
      ctx!.filter = 'none'

      ctx!.filter = `blur(${Math.max(2, r * 0.014)}px)`
      ctx!.drawImage(sheenC, CX - ocSize / 2, cy - ocSize / 2)
      ctx!.filter = 'none'

      ctx!.restore()

      const ra = Math.atan2(lightY, lightX) + Math.PI
      ctx!.save()
      ctx!.beginPath()
      ctx!.arc(CX, cy, r, ra - 0.55, ra + Math.PI * 0.58)
      ctx!.strokeStyle = 'rgba(255,240,255,0.55)'
      ctx!.lineWidth   = 2.0
      ctx!.shadowColor = 'rgba(255,255,255,0.6)'
      ctx!.shadowBlur  = 8
      ctx!.stroke()
      ctx!.restore()
    }

    function pill(x: number, y: number, w: number, h: number) {
      const rr = w / 2
      ctx!.beginPath()
      if (h >= w) {
        ctx!.arc(x, y - h / 2 + rr, rr, Math.PI, 0)
        ctx!.arc(x, y + h / 2 - rr, rr, 0, Math.PI)
      } else {
        ctx!.ellipse(x, y, w / 2, Math.max(h / 2, 0.5), 0, 0, Math.PI * 2)
      }
      ctx!.closePath()
    }
    function drawEyes(cy: number, r: number) {
      if (blinkOpen < 0.015) return
      const ew  = r * 0.114
      const eh  = r * 0.208 * blinkOpen
      const gap = r * 0.140
      ctx!.save()
      ctx!.shadowColor = 'rgba(255,255,255,0.65)'
      ctx!.shadowBlur  = 22
      ctx!.fillStyle   = '#fff'
      pill(CX - gap + eX, cy + eY, ew, eh); ctx!.fill()
      pill(CX + gap + eX, cy + eY, ew, eh); ctx!.fill()
      ctx!.restore()
    }

    function tickBlink(dt: number) {
      if (blinkDir === 0) {
        blinkTimer -= dt
        if (blinkTimer <= 0) blinkDir = -1
      } else {
        blinkOpen += blinkDir * dt * 13
        if (blinkOpen <= 0) { blinkOpen = 0; blinkDir = 1 }
        if (blinkOpen >= 1) { blinkOpen = 1; blinkDir = 0; blinkTimer = 3 + Math.random() * 4 }
      }
    }

    // ── Main loop ────────────────────────────────────────────────────────────
    let lastTS = 0
    const loop = (ts: number) => {
      raf = requestAnimationFrame(loop)
      const dt = Math.min((ts - lastTS) / 1000, 0.05)
      lastTS = ts
      const t = ts / 1000

      const mode = modeRef.current
      const tA = mode === 'alert'     ? 1 : 0
      const tL = mode === 'listening' ? 1 : 0
      const tS = mode === 'speaking'  ? 1 : 0
      const m  = 1 - Math.pow(0.94, dt * 60)
      alertMix  += (tA - alertMix ) * m
      listenMix += (tL - listenMix) * m
      speakMix  += (tS - speakMix ) * m

      speakWave = Math.sin(t * 7) * 0.5 + Math.sin(t * 11.3 + 1.3) * 0.3 + Math.sin(t * 5.1 + 2.7) * 0.2

      const dx = (pX ?? CX) - CX
      const dy = (pY ?? CY) - CY
      const tLX = -0.28 + (dx / W) * 0.55
      const tLY = -0.30 + (dy / H) * 0.55
      const le  = 1 - Math.pow(0.912, dt * 60)
      lightX += (tLX - lightX) * le
      lightY += (tLY - lightY) * le

      const tEX = Math.tanh(dx / (R * 2.4)) * R * 0.22
      const tEY = Math.tanh(dy / (R * 2.4)) * R * 0.22
      const ee  = 1 - Math.pow(0.875, dt * 60)
      eX += (tEX - eX) * ee
      eY += (tEY - eY) * ee

      tickBlink(dt)
      tickRipples(dt)

      const breatheSpeed = 1.8 + speakMix * 1.4 + listenMix * 0.4
      const breatheAmp   = 0.014
                         + speakMix  * 0.025 * (0.7 + 0.3 * Math.sin(t * 6 + speakWave))
                         + listenMix * 0.008
                         + alertMix  * 0.012 * Math.sin(t * 3.6)
      const r  = R * (1 + Math.sin(t * breatheSpeed) * breatheAmp)

      const targetFloat = -Math.sin(t * 0.7) * R * 0.025
                        + speakMix * Math.sin(t * 4) * R * 0.012
      floatY += (targetFloat - floatY) * (1 - Math.pow(0.95, dt * 60))
      const cy = CY + floatY

      ctx!.clearRect(0, 0, W, H)

      drawGlow(cy, r, t)
      drawRipples(cy, r)
      drawSphere(cy, r, t)
      drawEyes(cy, r)
    }

    pX = CX
    pY = CY
    resetIdle()
    raf = requestAnimationFrame(loop)

    return () => {
      cancelAnimationFrame(raf)
      if (idleTimer) clearTimeout(idleTimer)
      if (interactive) {
        document.removeEventListener('mousemove', onMouseMove)
        document.removeEventListener('touchmove', onTouchMove)
      }
      canvas.removeEventListener('click', onClick)
    }
  }, [size, interactive, radiusFactor])

  // Soft radial mask: keeps the orb crisp at center, fades any residual glow
  // to true transparency at the corners so the canvas blends seamlessly into
  // the dark panel — no visible rectangular container.
  const maskGradient =
    'radial-gradient(circle at 50% 50%, black 55%, rgba(0,0,0,0.55) 78%, transparent 100%)'

  return (
    <canvas
      ref={canvasRef}
      style={{
        width: size,
        height: size,
        display: 'block',
        cursor: 'pointer',
        WebkitMaskImage: maskGradient,
        maskImage: maskGradient,
      }}
    />
  )
}
