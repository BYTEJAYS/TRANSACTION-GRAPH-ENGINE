// ── Recovery Action Center ───────────────────────────────────────────────────
// Ranked, automatically-prioritised interventions. Each card shows the expected
// recovery increase so an investigator can act on the highest-leverage move first.
import { motion } from 'framer-motion'
import { Snowflake, Scissors, Undo2, Bell, AlertTriangle, ChevronRight } from 'lucide-react'
import { T } from '../../theme'
import { impactColor, type RecoveryAction } from '../api'

const ICONS: Record<string, any> = {
  freeze: Snowflake, isolate: Scissors, recall: Undo2, escalate: AlertTriangle, monitor: Bell,
}

export function ActionCenter({ actions, onSimulate }: {
  actions: RecoveryAction[]; onSimulate?: (a: RecoveryAction) => void
}) {
  if (!actions.length) return <div style={{ color: T.text3, fontSize: 12 }}>No recovery actions available.</div>
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {actions.map((a, i) => {
        const Icon = ICONS[a.type] || Bell
        const col = impactColor(a.impact)
        return (
          <motion.div key={a.priority + a.action}
            initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.06 }}
            style={{
              display: 'flex', alignItems: 'center', gap: 13, padding: '13px 15px', borderRadius: 11,
              background: 'rgba(20,22,27,0.72)', border: `1px solid ${i === 0 ? col + '66' : T.border}`,
            }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, width: 30 }}>
              <span style={{ fontSize: 9, color: T.text3 }}>P{a.priority}</span>
              <div style={{ width: 30, height: 30, borderRadius: 8, display: 'grid', placeItems: 'center', background: `${col}1c`, border: `1px solid ${col}55` }}>
                <Icon size={15} color={col} />
              </div>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{a.action}</div>
              <div style={{ fontSize: 11, color: T.text3, marginTop: 2 }}>{a.rationale}</div>
            </div>
            <div style={{ textAlign: 'right', flexShrink: 0 }}>
              <div style={{ fontSize: 16, fontWeight: 700, color: T.success, fontFamily: T.mono }}>+{a.expected_recovery_increase}%</div>
              <div style={{ fontSize: 9.5, color: col, fontWeight: 600 }}>{a.impact} impact</div>
            </div>
            {onSimulate && a.type === 'freeze' && a.target && (
              <button onClick={() => onSimulate(a)} title="Simulate this freeze"
                style={{ background: T.raised, border: `1px solid ${T.border}`, borderRadius: 8, padding: '7px 9px', cursor: 'pointer', color: T.gold, display: 'grid', placeItems: 'center' }}>
                <ChevronRight size={15} />
              </button>
            )}
          </motion.div>
        )
      })}
    </div>
  )
}
