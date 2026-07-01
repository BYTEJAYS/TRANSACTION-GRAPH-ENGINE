// ── Recovery Funnel ──────────────────────────────────────────────────────────
// Fraud amount → still traceable → recoverable → likely recoverable. Each stage
// is a tapering bar so a manager sees, at a glance, how much survives each filter.
import { motion } from 'framer-motion'
import { T, fmtINR } from '../../theme'
import type { RecoveryFunnel as Funnel } from '../api'

const STAGES: { key: keyof Funnel; label: string; color: string }[] = [
  { key: 'fraud_amount',       label: 'Fraud Amount',        color: T.danger },
  { key: 'still_traceable',    label: 'Still Traceable',     color: '#f0883e' },
  { key: 'recoverable',        label: 'Recoverable',         color: T.warn },
  { key: 'likely_recoverable', label: 'Likely Recoverable',  color: T.success },
]

export function RecoveryFunnel({ funnel }: { funnel: Funnel }) {
  const max = funnel.fraud_amount || 1
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {STAGES.map((s, i) => {
        const v = funnel[s.key]
        const pct = Math.max(6, (v / max) * 100)
        const retained = Math.round((v / max) * 100)
        return (
          <div key={s.key}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 5 }}>
              <span style={{ fontSize: 11.5, color: T.text2 }}>{s.label}</span>
              <span style={{ fontSize: 14, fontWeight: 700, color: s.color, fontFamily: T.mono }}>{fmtINR(v)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'center' }}>
              <motion.div
                initial={{ width: 0, opacity: 0 }} animate={{ width: `${pct}%`, opacity: 1 }}
                transition={{ duration: 0.7, delay: i * 0.12, ease: [0.16, 1, 0.3, 1] }}
                style={{
                  height: 34, borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
                  paddingRight: 11, background: `linear-gradient(90deg, ${s.color}22, ${s.color}44)`,
                  border: `1px solid ${s.color}66`,
                }}>
                <span style={{ fontSize: 10.5, fontWeight: 700, color: s.color }}>{retained}%</span>
              </motion.div>
            </div>
            {i < STAGES.length - 1 && (
              <div style={{ textAlign: 'center', color: T.text3, fontSize: 11, lineHeight: 1, marginTop: 2 }}>▼</div>
            )}
          </div>
        )
      })}
    </div>
  )
}
