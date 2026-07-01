// ── Recovery Ring Intelligence System ────────────────────────────────────────
// The hero dial. Outer 270° arc = recovery probability; thin inner arc =
// confidence. A single slow "intelligence pulse" breathes behind it — restrained,
// never neon. Below the number sits the plain-language recovery classification.
import { motion } from 'framer-motion'
import { T } from '../../theme'
import { recoveryColor, recoveryClass } from '../api'

export function RecoveryGauge({ score, band, confidence, size = 268 }: {
  score: number; band: string; confidence: number; size?: number
}) {
  const r = size / 2 - 22
  const cx = size / 2, cy = size / 2
  const START = 135, SWEEP = 270
  const col = recoveryColor(score)
  const arc = describeArc(cx, cy, r, START, START + SWEEP)
  const fill = describeArc(cx, cy, r, START, START + SWEEP * (score / 100))
  const ir = r - 16
  const cArc = describeArc(cx, cy, ir, START, START + SWEEP)
  const cFill = describeArc(cx, cy, ir, START, START + SWEEP * (confidence / 100))
  const cls = recoveryClass(score)

  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      {/* intelligence pulse — one slow, faint breath */}
      <motion.div aria-hidden
        style={{ position: 'absolute', inset: size * 0.14, borderRadius: '50%', background: `radial-gradient(circle, ${col}22 0%, transparent 70%)` }}
        animate={{ opacity: [0.35, 0.7, 0.35], scale: [0.92, 1.04, 0.92] }}
        transition={{ duration: 5.5, repeat: Infinity, ease: 'easeInOut' }} />

      <svg width={size} height={size} style={{ position: 'relative' }}>
        {/* outer track + recovery fill */}
        <path d={arc} fill="none" stroke={T.raised} strokeWidth={14} strokeLinecap="round" />
        <motion.path d={fill} fill="none" stroke={col} strokeWidth={14} strokeLinecap="round"
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.2, ease: 'easeOut' }}
          style={{ filter: `drop-shadow(0 0 5px ${col}55)` }} />
        {/* inner confidence ring */}
        <path d={cArc} fill="none" stroke={T.border} strokeWidth={3} strokeLinecap="round" />
        <motion.path d={cFill} fill="none" stroke={T.gold} strokeWidth={3} strokeLinecap="round"
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.2, delay: 0.25 }} />
      </svg>

      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: '0 18px' }}>
        <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
          style={{ fontSize: size * 0.27, fontWeight: 700, color: col, lineHeight: 1, fontFamily: T.mono, fontVariantNumeric: 'tabular-nums' }}>
          {score}<span style={{ fontSize: size * 0.1, color: T.text3 }}>%</span>
        </motion.div>
        <div style={{ fontSize: 9, letterSpacing: '.16em', color: T.text3, marginTop: 5 }}>RECOVERY PROBABILITY</div>
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '.04em', color: col, marginTop: 11, lineHeight: 1.3 }}>{cls}</div>
        <div style={{ fontSize: 10, color: T.gold, marginTop: 7 }}>confidence {confidence}%</div>
      </div>

      <div style={{ position: 'absolute', bottom: 2, left: 0, right: 0, textAlign: 'center', fontSize: 10.5, fontWeight: 600, color: col }}>
        {band}
      </div>
    </div>
  )
}

function polar(cx: number, cy: number, r: number, deg: number) {
  const a = (deg - 90) * Math.PI / 180
  return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) }
}
function describeArc(cx: number, cy: number, r: number, start: number, end: number) {
  const s = polar(cx, cy, r, end), e = polar(cx, cy, r, start)
  const large = end - start <= 180 ? 0 : 1
  return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 0 ${e.x} ${e.y}`
}
