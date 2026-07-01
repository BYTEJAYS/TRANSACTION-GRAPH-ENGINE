// ── Critical Account Center ──────────────────────────────────────────────────
// Answers one question: which account do I freeze first? Accounts ranked by the
// share of recoverable funds they control, with a clear freeze recommendation
// and recovery impact. The top row is the decisive freeze.
import { motion } from 'framer-motion'
import { Snowflake, ChevronRight } from 'lucide-react'
import { T, fmtINR, riskColorFromScore } from '../../theme'
import { impactColor, type CriticalAccount } from '../api'

function recommendation(c: CriticalAccount): { label: string; color: string } {
  if (c.freeze_impact >= 35 && c.freeze_success >= 65) return { label: 'Freeze immediately', color: T.danger }
  if (c.freeze_impact >= 20) return { label: 'Freeze — high priority', color: '#f0883e' }
  if (c.freeze_success >= 70) return { label: 'Freeze if capacity', color: T.warn }
  return { label: 'Monitor', color: T.text2 }
}

function impactLabel(control: number): string {
  if (control >= 40) return 'Very High'
  if (control >= 20) return 'High'
  if (control >= 8) return 'Medium'
  return 'Low'
}

export function CriticalAccountCenter({ accounts, onFreeze }: {
  accounts: CriticalAccount[]; onFreeze?: (c: CriticalAccount) => void
}) {
  if (!accounts.length) return <div style={{ color: T.text3, fontSize: 12 }}>No critical holding accounts identified.</div>
  const cols = '1.3fr 1fr 1.5fr 0.8fr 1.5fr 44px'

  return (
    <div style={{ background: 'rgba(20,22,27,0.55)', border: `1px solid ${T.border}`, borderRadius: 13, overflow: 'hidden' }}>
      {/* header */}
      <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 10, padding: '11px 16px', borderBottom: `1px solid ${T.border}`, background: 'rgba(20,22,27,0.5)' }}>
        {['Account', 'Funds Held', 'Control', 'Risk', 'Freeze Recommendation', ''].map(h => (
          <span key={h} style={{ fontSize: 9.5, color: T.text3, letterSpacing: '.06em', fontWeight: 600 }}>{h.toUpperCase()}</span>
        ))}
      </div>

      {accounts.map((c, i) => {
        const rec = recommendation(c)
        const riskCol = riskColorFromScore(c.risk)
        const imp = impactLabel(c.freeze_impact)
        const impCol = impactColor(imp)
        const lead = i === 0
        return (
          <motion.div key={c.account}
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.05 }}
            style={{
              display: 'grid', gridTemplateColumns: cols, gap: 10, alignItems: 'center', padding: '13px 16px',
              borderBottom: i < accounts.length - 1 ? `1px solid ${T.border}` : 'none',
              background: lead ? 'rgba(229,72,77,0.05)' : 'transparent',
            }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
              {lead && <span style={{ fontSize: 8, fontWeight: 800, color: T.danger, background: T.dangerDim, border: `1px solid rgba(229,72,77,0.3)`, borderRadius: 5, padding: '2px 5px', letterSpacing: '.04em' }}>1ST</span>}
              <span style={{ fontSize: 12.5, fontWeight: 600, color: T.text, fontFamily: T.mono, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.account}</span>
            </div>
            <span style={{ fontSize: 12.5, fontWeight: 700, color: T.text, fontFamily: T.mono }}>{fmtINR(c.held_amount)}</span>
            {/* control bar */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <div style={{ flex: 1, height: 6, background: T.bg2, borderRadius: 3, overflow: 'hidden' }}>
                <motion.div initial={{ width: 0 }} animate={{ width: `${c.freeze_impact}%` }} transition={{ duration: 0.7, delay: i * 0.05 }}
                  style={{ height: '100%', background: impCol, borderRadius: 3 }} />
              </div>
              <span style={{ fontSize: 12, fontWeight: 700, color: impCol, fontFamily: T.mono, width: 34, textAlign: 'right' }}>{c.freeze_impact}%</span>
            </div>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, color: riskCol, fontWeight: 600 }}>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: riskCol }} /> {Math.round(c.risk)}
            </span>
            <span style={{ fontSize: 11.5, fontWeight: 600, color: rec.color }}>{rec.label}</span>
            {onFreeze ? (
              <button onClick={() => onFreeze(c)} title={`Freeze ${c.account}`}
                style={{ display: 'grid', placeItems: 'center', width: 30, height: 30, borderRadius: 8, background: T.raised, border: `1px solid ${T.border}`, cursor: 'pointer', color: T.gold }}>
                <Snowflake size={14} />
              </button>
            ) : <ChevronRight size={14} color={T.text3} />}
          </motion.div>
        )
      })}
    </div>
  )
}
