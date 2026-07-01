// ── Recovery Decision Center ─────────────────────────────────────────────────
// The business heart of the page. Interventions ranked by expected recovery
// gain, each annotated with impact, urgency, gain and execution difficulty, with
// a single decisive "Execute" control. The #1 move is visually promoted.
import { motion } from 'framer-motion'
import { Snowflake, Scissors, Undo2, Bell, AlertTriangle, ArrowRight, FlaskConical } from 'lucide-react'
import { T } from '../../theme'
import {
  impactColor, actionUrgency, actionDifficulty,
  type RecoveryAction, type CriticalAccount,
} from '../api'

const ICONS: Record<string, any> = {
  freeze: Snowflake, isolate: Scissors, recall: Undo2, escalate: AlertTriangle, monitor: Bell,
}

export function DecisionCenter({ actions, criticalAccounts, onExecute, onSimulate }: {
  actions: RecoveryAction[]
  criticalAccounts: CriticalAccount[]
  onExecute: (a: RecoveryAction) => void
  onSimulate: (a: RecoveryAction) => void
}) {
  if (!actions.length) return <div style={{ color: T.text3, fontSize: 12 }}>No recovery actions available for this case.</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {actions.map((a, i) => {
        const Icon = ICONS[a.type] || Bell
        const col = impactColor(a.impact)
        const lead = i === 0
        const fs = a.target ? criticalAccounts.find(c => c.account === a.target)?.freeze_success : undefined
        const urg = actionUrgency(a.type)
        const diff = actionDifficulty(a.type, fs)
        return (
          <motion.div key={a.priority + a.action}
            initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.06 }}
            style={{
              borderRadius: 13, padding: lead ? '16px 17px' : '14px 16px',
              background: lead ? `linear-gradient(135deg, ${col}14, rgba(20,22,27,0.72))` : 'rgba(20,22,27,0.62)',
              border: `1px solid ${lead ? col + '66' : T.border}`,
            }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, width: 40 }}>
                <span style={{ fontSize: 9, color: lead ? col : T.text3, fontWeight: 700, letterSpacing: '.05em' }}>
                  {lead ? 'PRIORITY' : `P${a.priority}`}
                </span>
                <div style={{ width: 36, height: 36, borderRadius: 9, display: 'grid', placeItems: 'center', background: `${col}1c`, border: `1px solid ${col}55` }}>
                  <Icon size={17} color={col} />
                </div>
                {lead && <span style={{ fontSize: 16, fontWeight: 800, color: col, fontFamily: T.mono, lineHeight: 1 }}>#1</span>}
              </div>

              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: lead ? 15 : 13.5, fontWeight: 700, color: T.text }}>{a.action}</div>
                <div style={{ fontSize: 11.5, color: T.text3, marginTop: 3, lineHeight: 1.45 }}>{a.rationale}</div>
              </div>

              <div style={{ textAlign: 'right', flexShrink: 0 }}>
                <div style={{ fontSize: lead ? 26 : 20, fontWeight: 800, color: T.success, fontFamily: T.mono, lineHeight: 1 }}>
                  +{a.expected_recovery_increase}<span style={{ fontSize: 12, color: T.text3 }}>%</span>
                </div>
                <div style={{ fontSize: 9, color: T.text3, letterSpacing: '.04em', marginTop: 3 }}>RECOVERY GAIN</div>
              </div>
            </div>

            {/* attribute chips */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 13, paddingLeft: 54 }}>
              <Chip label="Impact" value={a.impact} color={col} />
              <Chip label="Urgency" value={urg.label} color={urg.color} />
              <Chip label="Difficulty" value={diff.label} color={diff.color} />
            </div>

            {/* controls */}
            <div style={{ display: 'flex', gap: 9, marginTop: 13, paddingLeft: 54 }}>
              <button onClick={() => onExecute(a)}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 7, padding: '9px 16px', borderRadius: 9, cursor: 'pointer', fontFamily: T.font, fontSize: 12, fontWeight: 700,
                  border: 'none', background: lead ? T.gold : T.raised, color: lead ? T.textOn : T.text,
                  boxShadow: lead ? '0 2px 14px rgba(198,162,83,0.25)' : 'none',
                }}>
                Execute Action <ArrowRight size={14} />
              </button>
              {a.type === 'freeze' && a.target && (
                <button onClick={() => onSimulate(a)} title="Model this freeze first"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '9px 13px', borderRadius: 9, cursor: 'pointer', fontFamily: T.font, fontSize: 12, fontWeight: 600, background: T.raised, border: `1px solid ${T.border}`, color: T.text2 }}>
                  <FlaskConical size={13} color={T.gold} /> Simulate
                </button>
              )}
            </div>
          </motion.div>
        )
      })}
    </div>
  )
}

function Chip({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 10px', borderRadius: 7, background: T.bg2, border: `1px solid ${T.border}` }}>
      <span style={{ fontSize: 9.5, color: T.text3, letterSpacing: '.04em' }}>{label}</span>
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: color }} />
      <span style={{ fontSize: 11, fontWeight: 700, color }}>{value}</span>
    </span>
  )
}
