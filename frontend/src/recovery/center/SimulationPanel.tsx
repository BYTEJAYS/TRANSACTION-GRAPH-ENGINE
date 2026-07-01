// ── Predictive Recovery Mode ─────────────────────────────────────────────────
// A banking decision simulator: freeze an account, take no action, or delay, and
// watch the recovery probability and recoverable amount recompute.
import { useState } from 'react'
import { motion } from 'framer-motion'
import { Snowflake, Hand, Hourglass, Play } from 'lucide-react'
import { T, fmtINR } from '../../theme'
import { recoveryApi, recoveryColor, type CriticalAccount, type RecoverySimulation } from '../api'

type Scenario = 'freeze' | 'no_action' | 'delay'

export function SimulationPanel({ caseId, criticalAccounts }: { caseId: string; criticalAccounts: CriticalAccount[] }) {
  const [scenario, setScenario] = useState<Scenario>('freeze')
  const [account, setAccount] = useState(criticalAccounts[0]?.account ?? '')
  const [delay, setDelay] = useState(24)
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<RecoverySimulation | null>(null)

  async function run() {
    setBusy(true)
    try { setRes(await recoveryApi.simulate(caseId, scenario, scenario === 'freeze' ? account : undefined, delay)) }
    catch { /* ignore */ } finally { setBusy(false) }
  }

  const tabs: { id: Scenario; label: string; icon: any }[] = [
    { id: 'freeze', label: 'Freeze account', icon: Snowflake },
    { id: 'no_action', label: 'Take no action', icon: Hand },
    { id: 'delay', label: 'Delay action', icon: Hourglass },
  ]

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
        {tabs.map(t => {
          const on = scenario === t.id
          return (
            <button key={t.id} onClick={() => { setScenario(t.id); setRes(null) }}
              style={{
                display: 'flex', alignItems: 'center', gap: 7, padding: '9px 13px', borderRadius: 9, cursor: 'pointer', fontFamily: T.font,
                background: on ? T.goldDim : T.raised, border: `1px solid ${on ? T.goldLine : T.border}`,
                color: on ? T.text : T.text2, fontSize: 12, fontWeight: on ? 600 : 500,
              }}>
              <t.icon size={14} color={on ? T.gold : T.text3} /> {t.label}
            </button>
          )
        })}
      </div>

      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 16 }}>
        {scenario === 'freeze' && (
          <Field label="Account to freeze">
            <select value={account} onChange={e => setAccount(e.target.value)} style={selectStyle}>
              {criticalAccounts.length === 0 && <option value="">no holding accounts</option>}
              {criticalAccounts.map(c => <option key={c.account} value={c.account}>{c.account} · holds {c.freeze_impact}%</option>)}
            </select>
          </Field>
        )}
        {scenario === 'delay' && (
          <Field label={`Delay by ${delay}h`}>
            <input type="range" min={1} max={168} value={delay} onChange={e => setDelay(Number(e.target.value))}
              style={{ width: 220, accentColor: T.gold }} />
          </Field>
        )}
        <button onClick={run} disabled={busy}
          style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '10px 18px', borderRadius: 9, border: 'none', background: T.gold, color: T.textOn, fontWeight: 600, fontSize: 12.5, cursor: 'pointer', fontFamily: T.font }}>
          <Play size={14} /> {busy ? 'Simulating…' : 'Run simulation'}
        </button>
      </div>

      {res && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <Outcome label="Recovery probability" base={`${res.baseline_probability}%`} now={`${res.simulated_probability}%`}
            delta={res.delta} unit="pts" color={recoveryColor(res.simulated_probability)} />
          <Outcome label="Expected recoverable" base={fmtINR(res.baseline_recoverable)} now={fmtINR(res.simulated_recoverable)}
            delta={res.recoverable_delta} unit="₹" money color={res.recoverable_delta >= 0 ? T.success : T.danger} />
          <div style={{ gridColumn: '1 / -1', fontSize: 12, color: T.text2, background: T.bg2, border: `1px solid ${T.border}`, borderRadius: 10, padding: '11px 13px' }}>
            {res.note}
          </div>
        </motion.div>
      )}
    </div>
  )
}

function Outcome({ label, base, now, delta, unit, money, color }: {
  label: string; base: string; now: string; delta: number; unit: string; money?: boolean; color: string
}) {
  const up = delta >= 0
  return (
    <div style={{ background: 'rgba(20,22,27,0.72)', border: `1px solid ${T.border}`, borderRadius: 11, padding: '13px 15px' }}>
      <div style={{ fontSize: 10, color: T.text3, letterSpacing: '.05em', marginBottom: 8 }}>{label.toUpperCase()}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 13, color: T.text3, textDecoration: 'line-through' }}>{base}</span>
        <span style={{ color: T.text3 }}>→</span>
        <span style={{ fontSize: 22, fontWeight: 700, color, fontFamily: T.mono }}>{now}</span>
      </div>
      <div style={{ fontSize: 11.5, fontWeight: 600, color: up ? T.success : T.danger, marginTop: 5 }}>
        {up ? '▲' : '▼'} {money ? fmtINR(Math.abs(delta)) : `${Math.abs(delta)} ${unit}`}
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span style={{ fontSize: 10.5, color: T.text3 }}>{label}</span>
      {children}
    </label>
  )
}

const selectStyle: React.CSSProperties = {
  padding: '9px 11px', background: T.bg2, border: `1px solid ${T.border}`, borderRadius: 8,
  color: T.text, fontSize: 12, outline: 'none', fontFamily: T.font, minWidth: 240,
}
