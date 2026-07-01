import { useEffect, useRef } from 'react'

/**
 * TGIE Intelligence Particle Engine (IPE)
 *
 * A premium canvas background for the login page that simulates a living
 * financial-intelligence network being monitored in real time: drifting account
 * nodes, fading transaction links, money-movement pulses, rare fraud-cluster
 * illuminations and continuous monitoring scan-waves. Gold-on-matte-black,
 * deliberately restrained — never a generic particle field.
 *
 * - 3 parallax depth layers · density biased to the left (behind the TGIE title)
 * - a soft "safety zone" around the login card keeps the right side clear
 * - reacts to input focus (gentle brighten) and Sign-In (intelligence activation)
 * - respects prefers-reduced-motion, pauses when hidden, scales density by device
 */

// White particles (nodes, links and pulses) on the matte-black canvas.
const GOLD = [255, 255, 255]
const GOLD_HI = [255, 255, 255]

type Node = {
  x: number; y: number; vx: number; vy: number; r: number; baseA: number
  layer: number; bright: number
}
type Pulse = { path: number[]; t: number; dur: number }
type Cluster = { idx: number[]; t: number; dur: number }
type Scan = { x: number; w: number; speed: number }

export function IntelligenceParticleEngine() {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d', { alpha: true })
    if (!ctx) return

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let W = 0, H = 0, dpr = 1
    let nodes: Node[] = []
    const pulses: Pulse[] = []
    const clusters: Cluster[] = []
    let scan: Scan | null = null
    let raf = 0
    let last = performance.now()
    let nextPulse = 1200, nextCluster = 22000, nextScan = 9000
    let excite = 0          // input-focus brighten
    let activate = 0        // sign-in activation surge
    const mouse = { x: 0.5, y: 0.5, tx: 0.5, ty: 0.5 }

    // layer config: [rMin,rMax, aMin,aMax, speed, parallax, links]
    const LAYERS = [
      { rMin: 0.9, rMax: 2.0, aMin: 0.18, aMax: 0.34, speed: 6, par: 6, links: false },
      { rMin: 1.8, rMax: 3.4, aMin: 0.34, aMax: 0.55, speed: 11, par: 16, links: true },
      { rMin: 2.4, rMax: 5.0, aMin: 0.48, aMax: 0.78, speed: 16, par: 30, links: true },
    ]
    const LINK_DIST = () => Math.min(190, W * 0.16)

    function density() {
      const w = window.innerWidth
      if (w < 640) return [16, 26, 16]      // mobile — minimal
      if (w < 1100) return [30, 52, 32]     // tablet — reduced
      return [52, 96, 60]                   // desktop — full (denser graph)
    }

    // soft elliptical clear-zone around the login card (right side, desktop only)
    function clarity(x: number, y: number): number {
      if (W < 900) return 1
      const cx = W * 0.78, cy = H * 0.5, rx = W * 0.2, ry = H * 0.36
      const d = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
      return d >= 1 ? 1 : 0.12 + 0.88 * d
    }

    function resize() {
      dpr = Math.min(2, window.devicePixelRatio || 1)
      W = window.innerWidth; H = window.innerHeight
      canvas.width = W * dpr; canvas.height = H * dpr
      canvas.style.width = W + 'px'; canvas.style.height = H + 'px'
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      build()
    }

    function build() {
      nodes = []
      const counts = density()
      counts.forEach((count, layer) => {
        const L = LAYERS[layer]
        for (let i = 0; i < count; i++) {
          // bias x toward the left (denser behind the TGIE title)
          const left = Math.random() < 0.62
          const x = left ? Math.pow(Math.random(), 1.5) * W * 0.62 : Math.random() * W
          const ang = Math.random() * Math.PI * 2
          nodes.push({
            x, y: Math.random() * H,
            vx: Math.cos(ang) * (L.speed / 1000),
            vy: Math.sin(ang) * (L.speed / 1000),
            r: L.rMin + Math.random() * (L.rMax - L.rMin),
            baseA: L.aMin + Math.random() * (L.aMax - L.aMin),
            layer, bright: 0,
          })
        }
      })
    }

    function neighbors(i: number, maxD: number, exclude: Set<number>): number[] {
      const a = nodes[i], out: number[] = []
      for (let j = 0; j < nodes.length; j++) {
        if (j === i || exclude.has(j) || nodes[j].layer === 0) continue
        const dx = nodes[j].x - a.x, dy = nodes[j].y - a.y
        if (dx * dx + dy * dy < maxD * maxD) out.push(j)
      }
      return out
    }

    function spawnPulse() {
      const linkIdx = nodes.map((n, i) => (n.layer >= 1 ? i : -1)).filter(i => i >= 0)
      if (!linkIdx.length) return
      const start = linkIdx[(Math.random() * linkIdx.length) | 0]
      const path = [start]; const used = new Set<number>([start]); let cur = start
      const steps = 3 + ((Math.random() * 3) | 0)
      for (let s = 0; s < steps; s++) {
        const nbs = neighbors(cur, LINK_DIST() * 1.25, used)
        if (!nbs.length) break
        const next = nbs[(Math.random() * Math.min(3, nbs.length)) | 0]
        path.push(next); used.add(next); cur = next
      }
      if (path.length >= 2 && pulses.length < 6) pulses.push({ path, t: 0, dur: 2 + Math.random() * 2 })
    }

    function spawnCluster() {
      const linkIdx = nodes.map((n, i) => (n.layer >= 1 ? i : -1)).filter(i => i >= 0)
      if (!linkIdx.length) return
      const seed = linkIdx[(Math.random() * linkIdx.length) | 0]
      const near = neighbors(seed, LINK_DIST() * 1.6, new Set([seed]))
        .sort((a, b) => {
          const da = (nodes[a].x - nodes[seed].x) ** 2 + (nodes[a].y - nodes[seed].y) ** 2
          const db = (nodes[b].x - nodes[seed].x) ** 2 + (nodes[b].y - nodes[seed].y) ** 2
          return da - db
        }).slice(0, 5 + ((Math.random() * 5) | 0))
      if (near.length >= 3) clusters.push({ idx: [seed, ...near], t: 0, dur: 1.6 })
    }

    function spawnScan() { scan = { x: -80, w: Math.max(120, W * 0.12), speed: W / 3 } }

    // ── update ──────────────────────────────────────────────────────────────
    function step(dt: number) {
      excite = Math.max(0, excite - dt * 0.8)
      activate = Math.max(0, activate - dt * 0.5)
      mouse.x += (mouse.tx - mouse.x) * 0.05
      mouse.y += (mouse.ty - mouse.y) * 0.05

      for (const n of nodes) {
        n.x += n.vx * dt * 60; n.y += n.vy * dt * 60
        if (n.x < -20) n.x = W + 20; else if (n.x > W + 20) n.x = -20
        if (n.y < -20) n.y = H + 20; else if (n.y > H + 20) n.y = -20
        n.bright *= 0.94
      }

      // timed events
      if ((nextPulse -= dt * 1000) <= 0) { spawnPulse(); nextPulse = 900 + Math.random() * 1800 }
      if ((nextCluster -= dt * 1000) <= 0) { spawnCluster(); nextCluster = 20000 + Math.random() * 10000 }
      if ((nextScan -= dt * 1000) <= 0) { spawnScan(); nextScan = 15000 + Math.random() * 5000 }

      for (let i = pulses.length - 1; i >= 0; i--) {
        pulses[i].t += dt
        if (pulses[i].t >= pulses[i].dur) pulses.splice(i, 1)
      }
      for (let i = clusters.length - 1; i >= 0; i--) {
        clusters[i].t += dt
        for (const idx of clusters[i].idx) nodes[idx].bright = Math.max(nodes[idx].bright, 1 - clusters[i].t / clusters[i].dur)
        if (clusters[i].t >= clusters[i].dur) clusters.splice(i, 1)
      }
      if (scan) {
        scan.x += scan.speed * dt
        for (const n of nodes) {
          const d = Math.abs(n.x - scan.x)
          if (d < scan.w) n.bright = Math.max(n.bright, (1 - d / scan.w) * 0.7)
        }
        if (scan.x > W + scan.w) scan = null
      }
    }

    // ── render ──────────────────────────────────────────────────────────────
    function rgba(c: number[], a: number) { return `rgba(${c[0]},${c[1]},${c[2]},${a})` }

    function draw(time: number) {
      ctx.clearRect(0, 0, W, H)
      const px = (mouse.x - 0.5), py = (mouse.y - 0.5)

      // links (transaction relationships)
      const LD = LINK_DIST()
      ctx.lineWidth = 1
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i]
        if (!LAYERS[a.layer].links) continue
        const ax = a.x - px * LAYERS[a.layer].par, ay = a.y - py * LAYERS[a.layer].par
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j]
          if (!LAYERS[b.layer].links) continue
          const dx = b.x - a.x, dy = b.y - a.y
          const dist = Math.hypot(dx, dy)
          if (dist > LD) continue
          const bx = b.x - px * LAYERS[b.layer].par, by = b.y - py * LAYERS[b.layer].par
          const flick = 0.5 + 0.5 * Math.sin(time * 0.0006 + (i * 13 + j * 7))
          const cl = Math.min(clarity(ax, ay), clarity(bx, by))
          const a0 = (1 - dist / LD) * 0.2 * flick * cl + (a.bright + b.bright) * 0.06 * cl
          if (a0 < 0.012) continue
          ctx.strokeStyle = rgba(GOLD, a0)
          ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke()
        }
      }

      // transaction pulses
      for (const p of pulses) {
        const segs = p.path.length - 1
        const prog = p.t / p.dur
        const fade = prog < 0.15 ? prog / 0.15 : prog > 0.8 ? (1 - prog) / 0.2 : 1
        const sf = Math.min(segs - 1e-6, prog * segs)
        const si = sf | 0, lf = sf - si
        const A = nodes[p.path[si]], B = nodes[p.path[si + 1]]
        const par = LAYERS[A.layer].par
        const x = (A.x + (B.x - A.x) * lf) - px * par
        const y = (A.y + (B.y - A.y) * lf) - py * par
        nodes[p.path[si]].bright = Math.max(nodes[p.path[si]].bright, 0.8)
        const cl = clarity(x, y)
        // trail on current segment
        const tx = (A.x + (B.x - A.x) * Math.max(0, lf - 0.5)) - px * par
        const ty = (A.y + (B.y - A.y) * Math.max(0, lf - 0.5)) - py * par
        const grad = ctx.createLinearGradient(tx, ty, x, y)
        grad.addColorStop(0, rgba(GOLD_HI, 0)); grad.addColorStop(1, rgba(GOLD_HI, 0.5 * fade * cl))
        ctx.strokeStyle = grad; ctx.lineWidth = 1.4
        ctx.beginPath(); ctx.moveTo(tx, ty); ctx.lineTo(x, y); ctx.stroke()
        // glowing head
        const r = 7
        const g = ctx.createRadialGradient(x, y, 0, x, y, r)
        g.addColorStop(0, rgba(GOLD_HI, 0.85 * fade * cl)); g.addColorStop(1, rgba(GOLD_HI, 0))
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill()
        ctx.fillStyle = rgba(GOLD_HI, 0.95 * fade * cl)
        ctx.beginPath(); ctx.arc(x, y, 1.5, 0, Math.PI * 2); ctx.fill()
      }

      // nodes
      for (const n of nodes) {
        const par = LAYERS[n.layer].par
        const x = n.x - px * par, y = n.y - py * par
        const cl = clarity(x, y)
        const boost = n.bright + excite * 0.18 + activate * 0.35
        const a = Math.min(0.95, (n.baseA + boost * 0.5)) * cl
        if (a < 0.015) continue
        const r = n.r + boost * 1.4
        if (boost > 0.25) {
          const g = ctx.createRadialGradient(x, y, 0, x, y, r * 3.2)
          g.addColorStop(0, rgba(GOLD_HI, 0.25 * boost * cl)); g.addColorStop(1, rgba(GOLD_HI, 0))
          ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r * 3.2, 0, Math.PI * 2); ctx.fill()
        }
        ctx.fillStyle = rgba(boost > 0.3 ? GOLD_HI : GOLD, a)
        ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill()
      }

      // fraud-cluster stronger links
      for (const c of clusters) {
        const k = 1 - c.t / c.dur
        ctx.lineWidth = 1.2
        for (let i = 0; i < c.idx.length; i++) {
          for (let j = i + 1; j < c.idx.length; j++) {
            const A = nodes[c.idx[i]], B = nodes[c.idx[j]]
            const d = Math.hypot(A.x - B.x, A.y - B.y)
            if (d > LD * 1.7) continue
            ctx.strokeStyle = rgba(GOLD_HI, 0.22 * k * clarity(A.x, A.y))
            ctx.beginPath(); ctx.moveTo(A.x - px * LAYERS[A.layer].par, A.y - py * LAYERS[A.layer].par)
            ctx.lineTo(B.x - px * LAYERS[B.layer].par, B.y - py * LAYERS[B.layer].par); ctx.stroke()
          }
        }
      }
    }

    function loop(ts: number) {
      const dt = Math.min(0.05, (ts - last) / 1000); last = ts
      step(dt); draw(ts)
      raf = requestAnimationFrame(loop)
    }

    function staticFrame() { build(); step(0.016); draw(performance.now()) }

    // ── events ────────────────────────────────────────────────────────────────
    const onResize = () => resize()
    const onExcite = () => { excite = Math.min(1, excite + 0.7) }
    const onActivate = () => {
      activate = 1
      for (let i = 0; i < 5; i++) spawnPulse()
      spawnScan()
    }
    const onMouse = (e: MouseEvent) => { mouse.tx = e.clientX / window.innerWidth; mouse.ty = e.clientY / window.innerHeight }
    const onVisibility = () => {
      if (document.hidden) { cancelAnimationFrame(raf); raf = 0 }
      else if (!raf && !reduce) { last = performance.now(); raf = requestAnimationFrame(loop) }
    }

    resize()
    window.addEventListener('resize', onResize)
    window.addEventListener('tgie:excite', onExcite)
    window.addEventListener('tgie:activate', onActivate)
    window.addEventListener('mousemove', onMouse)
    document.addEventListener('visibilitychange', onVisibility)

    if (reduce) staticFrame()
    else raf = requestAnimationFrame(loop)

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
      window.removeEventListener('tgie:excite', onExcite)
      window.removeEventListener('tgie:activate', onActivate)
      window.removeEventListener('mousemove', onMouse)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])

  return (
    <canvas
      ref={ref}
      aria-hidden="true"
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 0 }}
    />
  )
}
