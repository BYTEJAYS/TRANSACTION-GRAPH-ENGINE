// ── Recovery Clock ───────────────────────────────────────────────────────────
// The window is closing. A live countdown of the optimal recovery window, then
// the recovery probability the case will hold at +24h, +3d and +7d if nothing
// changes — so the cost of waiting is impossible to miss.
import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Clock } from 'lucide-react'
import { T } from '../../theme'
import { recoveryColor, recoveryAtHour, type DecayPoint } from '../api'

const STOPS: { hours: number; label: string }[] = [
  { hours: 0, label: 'Now' },
  { hours: 24, label: 'In 24 hours' },
  { hours: 72, label: 'In 3 days' },
  { hours: 168, label: 'In 7 days' },
]

export function RecoveryClock({ curve, windowSeconds }: { curve: DecayPoint[]; windowSeconds: number }) {
  const [remaining, setRemaining] = useState(windowSeconds)
  useEffect(() => { setRemaining(windowSeconds) }, [windowSeconds])
  useEffect(() => {
    if (remaining <= 0) return
    const id = setInterval(() => setRemaining(r => Math.max(0, r - 1)), 1000)
    return () => clearInterval(id)
  }, [remaining > 0])

  const open = remaining > 0
  const now = recoveryAtHour(curve, 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* countdown banner */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 13, padding: '15px 16px', borderRadius: 12,
        background: open ? 'linear-gradient(90deg, rgba(229,72,77,0.10), rgba(229,72,77,0.02))' : T.raised,
        border: `1px solid ${open ? 'rgba(229,72,77,0.32)' : T.border}`,
      }}>
        <div style={{ width: 40, height: 40, borderRadius: 10, display: 'grid', placeItems: 'center', background: open ? T.dangerDim : T.raised, border: `1px solid ${open ? 'rgba(229,72,77,0.3)' : T.border}` }}>
          <Clock size={20} color={open ? T.danger : T.text3} />
        </div>
        <div>
          <div style={{ fontSize: 9.5, letterSpacing: '.12em', color: T.text3 }}>OPTIMAL RECOVERY WINDOW</div>
          <motion.div animate={open ? { opacity: [1, 0.6, 1] } : {}} transition={{ duration: 1.8, repeat: Infinity }}
            style={{ fontSize: 23, fontWeight: 700, color: open ? T.danger : T.text3, fontFamily: T.mono, fontVariantNumeric: 'tabular-nums' }}>
            {open ? fmtCountdown(remaining) : 'Window closed'}
          </motion.div>
        </div>
      </div>

      {/* probability decay readouts */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 9 }}>
        {STOPS.map((s, i) => {
          const v = recoveryAtHour(curve, s.hours)
          const drop = v - now
          const col = recoveryColor(v)
          return (
            <motion.div key={s.hours} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.07 }}
              style={{ background: 'rgba(20,22,27,0.6)', border: `1px solid ${i === 0 ? T.goldLine : T.border}`, borderRadius: 11, padding: '12px 10px', textAlign: 'center' }}>
              <div style={{ fontSize: 9, color: T.text3, letterSpacing: '.04em', marginBottom: 7 }}>{s.label.toUpperCase()}</div>
              <div style={{ fontSize: 21, fontWeight: 700, color: col, fontFamily: T.mono }}>{v}<span style={{ fontSize: 11, color: T.text3 }}>%</span></div>
              <div style={{ fontSize: 9.5, fontWeight: 600, color: i === 0 ? T.text3 : T.danger, marginTop: 4 }}>
                {i === 0 ? 'current' : `▼ ${Math.abs(drop)} pts`}
              </div>
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}

function fmtCountdown(sec: number): string {
  const d = Math.floor(sec / 86400)
  const h = Math.floor((sec % 86400) / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  if (d > 0) return `${d}d ${String(h).padStart(2, '0')}h ${String(m).padStart(2, '0')}m`
  return `${String(h).padStart(2, '0')}h ${String(m).padStart(2, '0')}m ${String(s).padStart(2, '0')}s`
}
