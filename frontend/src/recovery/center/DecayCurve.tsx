// ── Recovery Timeline — decay curve + live window countdown ───────────────────
// Recovery probability falls every hour. The curve projects it forward; the
// banner counts down the optimal action window remaining.
import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Clock } from 'lucide-react'
import { T } from '../../theme'
import { recoveryColor, type DecayPoint } from '../api'

export function DecayCurve({ curve, windowSeconds }: { curve: DecayPoint[]; windowSeconds: number }) {
  const [remaining, setRemaining] = useState(windowSeconds)
  useEffect(() => { setRemaining(windowSeconds) }, [windowSeconds])
  useEffect(() => {
    if (remaining <= 0) return
    const id = setInterval(() => setRemaining(r => Math.max(0, r - 1)), 1000)
    return () => clearInterval(id)
  }, [remaining > 0])

  const W = 520, H = 150, pad = 28
  const xs = curve.map(c => c.hours)
  const maxH = Math.max(...xs, 1)
  const x = (h: number) => pad + (h / maxH) * (W - pad * 2)
  const y = (v: number) => pad + (1 - v / 100) * (H - pad * 2)
  const line = curve.map((c, i) => `${i === 0 ? 'M' : 'L'}${x(c.hours).toFixed(1)} ${y(c.recovery).toFixed(1)}`).join(' ')
  const area = `${line} L ${x(maxH)} ${H - pad} L ${x(0)} ${H - pad} Z`
  const open = remaining > 0

  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 11, padding: '12px 15px', borderRadius: 11, marginBottom: 14,
        background: open ? 'rgba(229,72,77,0.07)' : T.raised,
        border: `1px solid ${open ? 'rgba(229,72,77,0.3)' : T.border}`,
      }}>
        <Clock size={20} color={open ? T.danger : T.text3} />
        <div>
          <div style={{ fontSize: 9.5, letterSpacing: '.1em', color: T.text3 }}>OPTIMAL RECOVERY WINDOW</div>
          <motion.div animate={open ? { opacity: [1, 0.55, 1] } : {}} transition={{ duration: 1.6, repeat: Infinity }}
            style={{ fontSize: 20, fontWeight: 700, color: open ? T.danger : T.text3, fontFamily: T.mono }}>
            {open ? fmtCountdown(remaining) : 'Window closed'}
          </motion.div>
        </div>
        {open && <span style={{ marginLeft: 'auto', fontSize: 10.5, color: T.text3, maxWidth: 150, textAlign: 'right' }}>
          recovery probability decays every hour — act within this window
        </span>}
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto' }}>
        {[0, 25, 50, 75, 100].map(g => (
          <g key={g}>
            <line x1={pad} y1={y(g)} x2={W - pad} y2={y(g)} stroke={T.border} strokeOpacity={0.5} strokeWidth={1} />
            <text x={pad - 6} y={y(g) + 3} textAnchor="end" fontSize={8} fill={T.text3}>{g}</text>
          </g>
        ))}
        <defs>
          <linearGradient id="decayFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={T.gold} stopOpacity={0.28} />
            <stop offset="100%" stopColor={T.gold} stopOpacity={0} />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#decayFill)" />
        <motion.path d={line} fill="none" stroke={T.gold} strokeWidth={2}
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.1 }} />
        {curve.map(c => (
          <g key={c.hours}>
            <circle cx={x(c.hours)} cy={y(c.recovery)} r={3} fill={recoveryColor(c.recovery)} stroke={T.bg} strokeWidth={1} />
            <text x={x(c.hours)} y={H - pad + 13} textAnchor="middle" fontSize={8} fill={T.text3}>
              {c.hours === 0 ? 'now' : c.hours < 24 ? `${c.hours}h` : `${c.hours / 24}d`}
            </text>
          </g>
        ))}
      </svg>
    </div>
  )
}

function fmtCountdown(sec: number): string {
  const d = Math.floor(sec / 86400)
  const h = Math.floor((sec % 86400) / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  if (d > 0) return `${d}d ${h}h ${m}m`
  return `${String(h).padStart(2, '0')}h ${String(m).padStart(2, '0')}m ${String(s).padStart(2, '0')}s`
}
