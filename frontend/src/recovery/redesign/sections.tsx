// ── Recovery redesign · section components ───────────────────────────────────
// Each component answers one question an investigator actually has, and is built
// only from figures the Recovery Probability Engine derives (no fabricated
// metrics). The page composes these top-to-bottom with generous whitespace.
import { motion } from 'framer-motion'
import { ArrowRight, Clock, FlaskConical, Snowflake } from 'lucide-react'
import { T, fmtINR, statusColor } from '../../theme'
import {
  recoveryColor, recoveryAtHour,
  type RecoveryAnalysis, type RecoveryAction, type CriticalAccount,
  type TraceAccount, type RecoveryPath, type RecoveryFunnel, type DecayPoint,
} from '../api'
import { Card, Eyebrow, Bar, StatusPill, Metric, Empty, hexA, A } from './primitives'

// Normalised target handed to the freeze confirmation. freeze_success is only
// present when the engine actually computed it for a critical account.
export interface FreezeTarget { account: string; held_amount: number; freeze_impact: number; freeze_success?: number }

// ── time-window meaning ──────────────────────────────────────────────────────
export function windowMeta(sec: number): { label: string; color: string } {
  if (sec <= 0) return { label: 'Window closed', color: T.danger }
  const h = Math.floor(sec / 3600)
  const label = h < 1 ? `${Math.floor(sec / 60)} min` : h < 24 ? `${h} hours` : `${Math.floor(h / 24)}d ${h % 24}h`
  const color = sec < 6 * 3600 ? T.danger : sec < 48 * 3600 ? T.warn : T.text2
  return { label, color }
}

// ── 1 · HERO — the answer in three seconds ───────────────────────────────────
export function RecoveryHero({ a, risk, narrow, onExecute }: {
  a: RecoveryAnalysis; risk: { label: string; color: string }; narrow: boolean; onExecute: () => void
}) {
  const color = recoveryColor(a.recovery_probability)
  const win = windowMeta(a.window_seconds)
  return (
    <Card pad={narrow ? 24 : 36} style={{ borderRadius: 18 }}>
      {/* case identity line */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: narrow ? 24 : 30 }}>
        <span style={{ fontFamily: T.mono, fontSize: 12.5, color: T.text, fontWeight: 600 }}>{a.case_id}</span>
        <span style={{ width: 3, height: 3, borderRadius: '50%', background: T.text3 }} />
        <span style={{ fontSize: 13, color: T.text2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: narrow ? 200 : 360 }}>{a.title}</span>
        <span style={{ flex: 1 }} />
        <StatusPill label={`Risk · ${risk.label}`} color={risk.color} strong />
        <StatusPill label={a.status || 'Open'} color={statusColor(a.status || '')} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: narrow ? '1fr' : 'minmax(0,1fr) 1px minmax(0,1.15fr)', gap: narrow ? 28 : 44, alignItems: 'start' }}>
        {/* recovery probability */}
        <div>
          <Eyebrow>Recovery probability</Eyebrow>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginTop: 16 }}>
            <span style={{ fontSize: 46, fontWeight: 600, color, fontFamily: T.mono, fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>
              {a.recovery_probability}<span style={{ fontSize: 20, fontWeight: 500, color: T.text3 }}>%</span>
            </span>
            <span style={{ fontSize: 13, fontWeight: 600, color }}>{a.band}</span>
          </div>
          <div style={{ marginTop: 20, maxWidth: 300 }}><Bar value={a.recovery_probability} color={color} height={8} delay={0.15} /></div>
          <div style={{ fontSize: 12, color: T.text2, marginTop: 14 }}>
            Model confidence <b style={{ color: T.text, fontFamily: T.mono }}>{a.confidence}%</b>
          </div>
        </div>

        {!narrow && <div style={{ width: 1, background: T.border, alignSelf: 'stretch' }} />}

        {/* recommended action */}
        <div>
          <Eyebrow>Recommended next action</Eyebrow>
          <div style={{ fontSize: narrow ? 16 : 18.5, fontWeight: 600, color: T.text, lineHeight: 1.4, margin: '16px 0 20px', maxWidth: 440 }}>
            {a.headline_action}
          </div>
          <button onClick={onExecute} disabled={!a.actions[0]} style={primaryBtn} aria-label="Execute recommended action">
            Execute recommended action <ArrowRight size={15} />
          </button>
          <div style={{ display: 'flex', gap: 36, marginTop: 24, flexWrap: 'wrap' }}>
            <InlineStat label="Expected recovery" value={fmtINR(a.expected_recoverable)} color={T.success} />
            <InlineStat label="Window remaining" value={win.label} color={win.color} />
          </div>
        </div>
      </div>
    </Card>
  )
}

function InlineStat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div>
      <div style={{ fontSize: 10.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: T.text3, marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 17, fontWeight: 600, color, fontFamily: T.mono, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
    </div>
  )
}

// ── 2 · FUNDS SNAPSHOT — where the money stands, in one glance ────────────────
export function FundsSnapshot({ funnel, narrow }: { funnel: RecoveryFunnel; narrow: boolean }) {
  const items = [
    { label: 'Total fraud', value: fmtINR(funnel.fraud_amount), color: T.text, sub: 'originated by the fraud' },
    { label: 'Still traceable', value: fmtINR(funnel.still_traceable), color: T.text, sub: 'inside the banking network' },
    { label: 'Held in-network', value: fmtINR(funnel.recoverable), color: T.success, sub: 'sitting in accounts · freezable' },
    { label: 'Cashed out', value: fmtINR(funnel.cashed_out), color: funnel.cashed_out > 0 ? '#f0883e' : T.text3, sub: 'withdrawn off-network' },
  ]
  return (
    <div style={{ display: 'grid', gridTemplateColumns: narrow ? '1fr 1fr' : 'repeat(4, 1fr)', gap: narrow ? '28px 24px' : 0 }}>
      {items.map((it, i) => (
        <div key={it.label} style={{
          paddingLeft: !narrow && i > 0 ? 28 : 0,
          borderLeft: !narrow && i > 0 ? `1px solid ${T.border}` : 'none',
        }}>
          <Metric label={it.label} value={it.value} color={it.color} sub={it.sub} />
        </div>
      ))}
    </div>
  )
}

// ── 3 · RECOVERY FLOW — the route back to the money ──────────────────────────
// Built from recovery_paths: origin → laundering layers → the account still
// holding funds, with the recoverable amount at the terminal. A clean chain,
// never a tangled graph.
export function RecoveryFlow({ paths }: { paths: RecoveryPath[] }) {
  if (!paths?.length) return <Empty>No traceable recovery path remains — funds were dispersed off-network or withdrawn to cash.</Empty>
  const top = paths.slice(0, 3)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {top.map((p, i) => <FlowRow key={`${p.terminal}-${i}`} p={p} lead={i === 0} />)}
    </div>
  )
}

function FlowRow({ p, lead }: { p: RecoveryPath; lead: boolean }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap', padding: '16px 18px', borderRadius: 14,
      background: lead ? hexA(T.success, 0.05) : T.panel,
      border: `1px solid ${lead ? hexA(T.success, 0.22) : T.border}`,
    }}>
      <span style={{ fontSize: 10.5, color: T.text3, fontFamily: T.mono, width: 22, flexShrink: 0 }}>P{p.priority}</span>
      <div style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        {p.path.map((n, i) => {
          const terminal = i === p.path.length - 1
          const role = i === 0 ? 'Origin' : terminal ? 'Holding' : `Layer ${i}`
          return (
            <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
              <FlowNode id={n} role={role} terminal={terminal} />
              {!terminal && <ArrowRight size={13} color={T.text3} />}
            </span>
          )
        })}
      </div>
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        <div style={{ fontSize: 9.5, color: T.text3, letterSpacing: '0.06em', textTransform: 'uppercase' }}>Recoverable</div>
        <div style={{ fontSize: 15, fontWeight: 600, color: T.success, fontFamily: T.mono, marginTop: 4 }}>{fmtINR(p.recoverable_amount)}</div>
      </div>
    </div>
  )
}

function FlowNode({ id, role, terminal }: { id: string; role: string; terminal: boolean }) {
  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', gap: 5 }}>
      <span style={{ fontSize: 8.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: terminal ? T.success : T.text3 }}>{role}</span>
      <span style={{
        fontSize: 11.5, fontFamily: T.mono, color: terminal ? T.text : T.text2, padding: '4px 10px', borderRadius: 8,
        background: terminal ? hexA(T.success, 0.1) : T.raised, border: `1px solid ${terminal ? hexA(T.success, 0.32) : T.border}`,
      }}>{id}</span>
    </span>
  )
}

// ── 4 · RECOVERABLE ACCOUNTS — what to freeze first ──────────────────────────
const ACCOUNT_STATUS_COLOR: Record<string, string> = {
  'Holding funds': T.success,
  'Pass-through': T.info,
  'Withdrew to cash': '#f0883e',
  'Cash-out destination (off-network)': T.danger,
  'Source (victim/origin)': T.text2,
}

export function RecoverableAccounts({ rows, critical, onFreeze, narrow }: {
  rows: TraceAccount[]; critical: CriticalAccount[]; onFreeze: (t: FreezeTarget) => void; narrow: boolean
}) {
  const holders = (rows || []).filter(r => r.traceable_balance > 0)
  const list = (holders.length ? holders : (rows || []).filter(r => r.recovery_importance > 0)).slice(0, 8)
  if (!list.length) return <Empty>No accounts are currently holding recoverable funds.</Empty>

  const totalHeld = list.reduce((s, r) => s + r.traceable_balance, 0) || 1
  const findCrit = (acc: string) => critical?.find(c => c.account === acc)
  const cols = '1.4fr 1.5fr 1fr 1.3fr 0.9fr 84px'

  const head: CSSish = { fontSize: 9.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: T.text3, fontWeight: 600 }

  return (
    <Card pad={0} style={{ overflow: 'hidden' }}>
      {!narrow && (
        <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 14, padding: '13px 20px', borderBottom: `1px solid ${T.border}` }}>
          <span style={head}>Account</span>
          <span style={head}>Status</span>
          <span style={{ ...head, textAlign: 'right' }}>Balance held</span>
          <span style={head}>Recoverable control</span>
          <span style={{ ...head, textAlign: 'right' }}>Confidence</span>
          <span style={head} />
        </div>
      )}
      {list.map((r, i) => {
        const c = findCrit(r.account)
        const control = c ? c.freeze_impact : Math.round((r.traceable_balance / totalHeld) * 100)
        const sColor = ACCOUNT_STATUS_COLOR[r.status] || T.text2
        const freeze = () => onFreeze({ account: r.account, held_amount: r.traceable_balance, freeze_impact: control, freeze_success: c?.freeze_success })
        return (
          <motion.div key={r.account}
            initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: true }} transition={{ delay: i * 0.04 }}
            style={{
              display: 'grid', gridTemplateColumns: narrow ? '1fr 84px' : cols, gap: 14, alignItems: 'center',
              padding: narrow ? '16px 18px' : '15px 20px', borderTop: i ? `1px solid ${T.border}` : 'none',
            }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
              {i === 0 && <span style={{ fontSize: 8.5, fontWeight: 700, color: A.base, background: A.dim, border: `1px solid ${A.line}`, borderRadius: 5, padding: '2px 5px' }}>1ST</span>}
              <span style={{ fontSize: 12.5, fontWeight: 600, color: T.text, fontFamily: T.mono, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.account}</span>
            </div>

            {narrow ? (
              <FreezeBtn onClick={freeze} account={r.account} />
            ) : (
              <>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: sColor, flexShrink: 0 }} />
                  <span style={{ fontSize: 11.5, color: T.text2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.status}</span>
                </span>
                <span style={{ fontSize: 12.5, fontWeight: 600, color: r.traceable_balance > 0 ? T.success : T.text3, fontFamily: T.mono, textAlign: 'right' }}>{fmtINR(r.traceable_balance)}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ flex: 1 }}><Bar value={control} color={A.base} height={6} delay={i * 0.04} /></div>
                  <span style={{ fontSize: 11.5, fontWeight: 600, color: T.text2, fontFamily: T.mono, width: 34, textAlign: 'right' }}>{control}%</span>
                </div>
                <span style={{ fontSize: 12, color: c ? T.text2 : T.text3, fontFamily: T.mono, textAlign: 'right' }}>{c ? `${c.freeze_success}%` : '—'}</span>
                <FreezeBtn onClick={freeze} account={r.account} />
              </>
            )}

            {narrow && (
              <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 18, flexWrap: 'wrap', marginTop: 2 }}>
                <MiniKV label="Status" value={r.status} color={sColor} />
                <MiniKV label="Held" value={fmtINR(r.traceable_balance)} color={T.success} />
                <MiniKV label="Control" value={`${control}%`} color={T.text2} />
                {c && <MiniKV label="Confidence" value={`${c.freeze_success}%`} color={T.text2} />}
              </div>
            )}
          </motion.div>
        )
      })}
    </Card>
  )
}

function FreezeBtn({ onClick, account }: { onClick: () => void; account: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
      <button onClick={onClick} title={`Freeze ${account}`} aria-label={`Freeze ${account}`}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 12px', borderRadius: 8, cursor: 'pointer',
          background: T.raised, border: `1px solid ${T.border}`, color: T.text2, fontFamily: T.font, fontSize: 11.5, fontWeight: 600,
        }}
        onMouseEnter={e => { e.currentTarget.style.borderColor = A.line; e.currentTarget.style.color = T.text }}
        onMouseLeave={e => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.color = T.text2 }}>
        <Snowflake size={13} color={A.base} /> Freeze
      </button>
    </div>
  )
}

function MiniKV({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <span style={{ fontSize: 10, color: T.text3 }}>{label}</span>
      <span style={{ fontSize: 11.5, color, fontFamily: T.mono }}>{value}</span>
    </span>
  )
}

// ── 5 · RECOVERY STRATEGY — interventions, ranked by recovery gain ───────────
export function RecoveryStrategy({ actions, critical, onExecute, onSimulate }: {
  actions: RecoveryAction[]; critical: CriticalAccount[]; onExecute: (a: RecoveryAction) => void; onSimulate: () => void
}) {
  if (!actions?.length) return <Empty>No recovery interventions are available for this case.</Empty>
  return (
    <div>
      {actions.map((a, i) => {
        const lead = i === 0
        const target = a.target ? critical?.find(c => c.account === a.target) : undefined
        return (
          <div key={`${a.priority}-${a.action}`} style={{ display: 'flex', gap: 18, alignItems: 'flex-start', padding: '20px 0', borderTop: i ? `1px solid ${T.border}` : 'none' }}>
            <span style={{ fontSize: 12.5, fontFamily: T.mono, fontWeight: 600, color: lead ? A.base : T.text3, width: 36, flexShrink: 0, paddingTop: 1 }}>P{a.priority}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: T.text }}>{a.action}</div>
              <div style={{ fontSize: 12.5, color: T.text2, marginTop: 6, lineHeight: 1.55, maxWidth: 580 }}>{a.rationale}</div>
              <div style={{ display: 'flex', gap: 9, marginTop: 14, flexWrap: 'wrap' }}>
                <button onClick={() => onExecute(a)} style={lead ? primaryBtnSm : ghostBtnSm}>Execute</button>
                {a.type === 'freeze' && a.target && (
                  <button onClick={onSimulate} style={ghostBtnSm}><FlaskConical size={13} color={A.base} /> Simulate first</button>
                )}
              </div>
            </div>
            <div style={{ textAlign: 'right', flexShrink: 0, minWidth: 116 }}>
              {target ? (
                <>
                  <div style={{ fontSize: 9.5, color: T.text3, letterSpacing: '0.06em', textTransform: 'uppercase' }}>Protects</div>
                  <div style={{ fontSize: 16, fontWeight: 600, color: T.success, fontFamily: T.mono, marginTop: 4 }}>{fmtINR(target.held_amount)}</div>
                  <div style={{ fontSize: 11, color: T.text3, marginTop: 5 }}>freeze likelihood {target.freeze_success}%</div>
                </>
              ) : (
                <>
                  <div style={{ fontSize: 9.5, color: T.text3, letterSpacing: '0.06em', textTransform: 'uppercase' }}>Recovery gain</div>
                  <div style={{ fontSize: 16, fontWeight: 600, color: T.success, fontFamily: T.mono, marginTop: 4 }}>+{a.expected_recovery_increase}%</div>
                  <div style={{ fontSize: 11, color: T.text3, marginTop: 5 }}>{a.impact} impact</div>
                </>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── 6 · RECOVERY TIMELINE — the cost of waiting ──────────────────────────────
// A time-based timeline: the recovery odds the case holds now and how they decay
// at +24h / +3d / +7d if nothing changes, ending with the closing window. Real
// figures read off the engine's decay curve — no charts, no invented events.
const STOPS: { h: number; label: string }[] = [
  { h: 0, label: 'Now' },
  { h: 24, label: 'In 24 hours' },
  { h: 72, label: 'In 3 days' },
  { h: 168, label: 'In 7 days' },
]

export function RecoveryTimeline({ curve, windowSeconds, score }: { curve: DecayPoint[]; windowSeconds: number; score: number }) {
  const now = curve?.length ? recoveryAtHour(curve, 0) : score
  const win = windowMeta(windowSeconds)
  const stops = STOPS.map(s => ({ ...s, v: curve?.length ? recoveryAtHour(curve, s.h) : score }))
  return (
    <div style={{ position: 'relative', paddingLeft: 24 }}>
      <div aria-hidden style={{ position: 'absolute', left: 5, top: 7, bottom: 46, width: 1, background: T.border }} />
      {stops.map((s, i) => {
        const drop = s.v - now
        const col = recoveryColor(s.v)
        return (
          <div key={s.h} style={{ position: 'relative', paddingBottom: 22 }}>
            <span style={{ position: 'absolute', left: -24, top: 2, width: 11, height: 11, borderRadius: '50%', background: T.bg, border: `2px solid ${i === 0 ? A.base : col}` }} />
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 12, color: T.text2, width: 92 }}>{s.label}</span>
              <span style={{ fontSize: 15, fontWeight: 600, color: col, fontFamily: T.mono }}>{s.v}%</span>
              <span style={{ fontSize: 11.5, color: i === 0 ? T.text3 : drop < 0 ? T.danger : T.text3 }}>
                {i === 0 ? 'current recovery odds' : drop < 0 ? `▼ ${Math.abs(drop)} pts vs now` : 'holds steady'}
              </span>
            </div>
          </div>
        )
      })}
      <div style={{ position: 'relative', marginTop: 4, paddingTop: 18, borderTop: `1px solid ${T.border}`, display: 'flex', alignItems: 'center', gap: 10 }}>
        <Clock size={15} color={win.color} />
        <span style={{ fontSize: 12.5, color: T.text2 }}>
          Optimal recovery window {windowSeconds > 0 ? 'closes in ' : ''}<b style={{ color: win.color, fontFamily: T.mono }}>{win.label}</b>
        </span>
      </div>
    </div>
  )
}

// ── shared button styles ─────────────────────────────────────────────────────
type CSSish = React.CSSProperties
export const primaryBtn: CSSish = {
  display: 'inline-flex', alignItems: 'center', gap: 8, padding: '11px 18px', borderRadius: 10, border: 'none',
  background: A.base, color: T.textOn, fontWeight: 600, fontSize: 13, cursor: 'pointer', fontFamily: T.font,
}
export const primaryBtnSm: CSSish = {
  display: 'inline-flex', alignItems: 'center', gap: 7, padding: '8px 16px', borderRadius: 9, border: 'none',
  background: A.base, color: T.textOn, fontWeight: 600, fontSize: 12, cursor: 'pointer', fontFamily: T.font,
}
export const ghostBtnSm: CSSish = {
  display: 'inline-flex', alignItems: 'center', gap: 7, padding: '8px 14px', borderRadius: 9,
  background: T.raised, border: `1px solid ${T.border}`, color: T.text2, fontWeight: 600, fontSize: 12, cursor: 'pointer', fontFamily: T.font,
}
