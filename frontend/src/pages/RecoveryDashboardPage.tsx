// ── RECOVERY PORTFOLIO ────────────────────────────────────────────────────────
// The landing view at /recovery: an investigator's whole recovery book on one
// quiet screen. It answers — across every case — how much money is still
// recoverable, how much is at risk, and which cases need action now. Selecting a
// case opens the per-case briefing at /recovery/:caseId.
//
// Same design language as the case page: matte black, restrained gold, colour
// only for meaning, generous whitespace, no charts or decorative cards.
import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { LifeBuoy, RefreshCw, ChevronRight, AlertTriangle, Sparkles } from 'lucide-react'
import { T, fmtINR, statusColor } from '../theme'
import { recoveryApi, recoveryColor, type RecoveryDashboard, type DashboardCase } from '../recovery/api'
import { Card, Section, Eyebrow, Metric, Bar, Empty, A } from '../recovery/redesign/primitives'
import { windowMeta } from '../recovery/redesign/sections'

function useNarrow(bp = 1000) {
  const [n, setN] = useState(() => typeof window !== 'undefined' && window.innerWidth < bp)
  useEffect(() => { const on = () => setN(window.innerWidth < bp); window.addEventListener('resize', on); return () => window.removeEventListener('resize', on) }, [bp])
  return n
}

export default function RecoveryDashboardPage() {
  const navigate = useNavigate()
  const narrow = useNarrow()
  const [dash, setDash] = useState<RecoveryDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => {
    let alive = true
    recoveryApi.dashboard().then(d => { if (alive) setDash(d) }).catch(() => {}).finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [])

  const refresh = useCallback(async () => {
    setRefreshing(true)
    try { setDash(await recoveryApi.dashboard()) } catch { /* ignore */ } finally { setRefreshing(false) }
  }, [])

  if (loading) return <CenterMsg><Sparkles size={18} color={A.base} /> Loading recovery portfolio…</CenterMsg>

  // act-now cases first, then by the largest recoverable amount.
  const cases = [...(dash?.cases || [])].sort((a, b) => (Number(b.urgent) - Number(a.urgent)) || (b.expected_recoverable - a.expected_recoverable))
  const avgColor = recoveryColor(dash?.avg_recovery_probability || 0)

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: T.bg, color: T.text, fontFamily: T.font, overflow: 'hidden' }}>
      {/* command bar */}
      <header style={{ flexShrink: 0, height: 58, display: 'flex', alignItems: 'center', gap: 14, padding: '0 20px', borderBottom: `1px solid ${T.border}`, background: T.bg2, zIndex: 7 }}>
        <div style={{ width: 30, height: 30, borderRadius: 8, display: 'grid', placeItems: 'center', background: A.dim, border: `1px solid ${A.line}` }}>
          <LifeBuoy size={16} color={A.base} />
        </div>
        <div>
          <div style={{ fontSize: 13.5, fontWeight: 600, color: T.text, lineHeight: 1.2 }}>Recovery Intelligence</div>
          <div style={{ fontSize: 10, color: T.text3 }}>Fund-recovery operations · portfolio</div>
        </div>
        <div style={{ flex: 1 }} />
        <button onClick={refresh} title="Refresh portfolio" aria-label="Refresh portfolio" style={iconBtn}>
          <RefreshCw size={15} color={T.text2} style={refreshing ? { animation: 'spin 1s linear infinite' } : undefined} />
        </button>
      </header>

      {/* body */}
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: narrow ? '24px 16px 100px' : '40px 32px 128px' }}>
        <div style={{ maxWidth: 1040, margin: '0 auto' }}>
          {!dash || !dash.case_count ? (
            <CenterMsg><AlertTriangle size={18} color={T.warn} /> No cases available for recovery analysis yet.</CenterMsg>
          ) : (
            <>
              {/* portfolio overview */}
              <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}>
                <Card pad={narrow ? 24 : 36} style={{ borderRadius: 18 }}>
                  <Eyebrow>Recovery portfolio</Eyebrow>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, margin: '16px 0 4px', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 42, fontWeight: 600, color: T.success, fontFamily: T.mono, fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>{fmtINR(dash.total_recoverable)}</span>
                    <span style={{ fontSize: 15, color: T.text2 }}>still recoverable across {dash.case_count} {dash.case_count === 1 ? 'case' : 'cases'}</span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: narrow ? '1fr 1fr' : 'repeat(3, 1fr)', gap: narrow ? '26px 24px' : 0, marginTop: 28, paddingTop: 26, borderTop: `1px solid ${T.border}` }}>
                    <DashStat i={0} narrow={narrow} label="Potential loss exposure" value={fmtINR(dash.potential_loss_exposure)} color={dash.potential_loss_exposure > 0 ? '#f0883e' : T.text} sub="net loss if no action is taken" />
                    <DashStat i={1} narrow={narrow} label="Avg recovery probability" value={`${dash.avg_recovery_probability}%`} color={avgColor} sub="across all active cases" />
                    <DashStat i={2} narrow={narrow} label="Cases requiring action" value={String(dash.cases_requiring_action)} color={dash.cases_requiring_action > 0 ? T.danger : T.success} sub={dash.cases_requiring_action > 0 ? 'closing window — act now' : 'none time-critical'} />
                  </div>
                </Card>
              </motion.div>

              {/* case book */}
              <Section title="Cases" hint="Every case ranked by urgency, then by the amount still recoverable. Select a case to open its recovery briefing.">
                {!cases.length ? <Empty>No cases to display.</Empty> : (
                  <Card pad={0} style={{ overflow: 'hidden' }}>
                    {!narrow && (
                      <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 14, padding: '13px 20px', borderBottom: `1px solid ${T.border}` }}>
                        {['Case', 'Status', 'Recovery probability', 'Recoverable', 'Window', ''].map((h, i) => (
                          <span key={i} style={{ fontSize: 9.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: T.text3, fontWeight: 600, textAlign: i === 3 ? 'right' : 'left' }}>{h}</span>
                        ))}
                      </div>
                    )}
                    {cases.map((c, i) => <CaseRow key={c.case_id} c={c} i={i} narrow={narrow} onOpen={() => navigate(`/recovery/${c.case_id}`)} />)}
                  </Card>
                )}
              </Section>
            </>
          )}
        </div>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}

const COLS = '1.9fr 1.1fr 1.5fr 1fr 0.9fr 32px'

function DashStat({ label, value, color, sub, i, narrow }: { label: string; value: string; color: string; sub?: string; i: number; narrow: boolean }) {
  return (
    <div style={{ paddingLeft: !narrow && i > 0 ? 28 : 0, borderLeft: !narrow && i > 0 ? `1px solid ${T.border}` : 'none' }}>
      <Metric label={label} value={value} color={color} sub={sub} />
    </div>
  )
}

function CaseRow({ c, i, narrow, onOpen }: { c: DashboardCase; i: number; narrow: boolean; onOpen: () => void }) {
  const col = recoveryColor(c.recovery_probability)
  const win = windowMeta(c.window_seconds)
  const sColor = statusColor(c.status || '')
  return (
    <motion.div role="button" tabIndex={0} onClick={onOpen}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen() } }}
      initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: true }} transition={{ delay: i * 0.03 }}
      style={{
        display: 'grid', gridTemplateColumns: narrow ? '1fr 32px' : COLS, gap: 14, alignItems: 'center', cursor: 'pointer',
        padding: narrow ? '16px 18px' : '15px 20px', borderTop: i ? `1px solid ${T.border}` : 'none',
      }}
      onMouseEnter={e => (e.currentTarget.style.background = T.raised)}
      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
      {/* case identity */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
        {c.urgent && <span style={{ fontSize: 8.5, fontWeight: 700, color: T.danger, background: T.dangerDim, border: `1px solid rgba(229,72,77,0.3)`, borderRadius: 5, padding: '2px 5px', letterSpacing: '.03em', flexShrink: 0 }}>ACT NOW</span>}
        <span style={{ minWidth: 0 }}>
          <span style={{ display: 'block', fontSize: 12.5, fontWeight: 600, color: T.text, fontFamily: T.mono }}>{c.case_id}</span>
          <span style={{ display: 'block', fontSize: 11, color: T.text3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.title}</span>
        </span>
      </div>

      {narrow ? (
        <ChevronRight size={16} color={T.text3} style={{ justifySelf: 'end' }} />
      ) : (
        <>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: sColor, flexShrink: 0 }} />
            <span style={{ fontSize: 11.5, color: T.text2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.status || 'Open'}</span>
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: col, fontFamily: T.mono, width: 38 }}>{c.recovery_probability}%</span>
            <div style={{ flex: 1 }}><Bar value={c.recovery_probability} color={col} height={6} delay={i * 0.03} /></div>
          </div>
          <span style={{ fontSize: 12.5, fontWeight: 600, color: T.success, fontFamily: T.mono, textAlign: 'right' }}>{fmtINR(c.expected_recoverable)}</span>
          <span style={{ fontSize: 11.5, color: win.color }}>{win.label}</span>
          <ChevronRight size={16} color={T.text3} />
        </>
      )}

      {narrow && (
        <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 18, flexWrap: 'wrap', marginTop: 4 }}>
          <MiniKV label="Recovery" value={`${c.recovery_probability}%`} color={col} />
          <MiniKV label="Recoverable" value={fmtINR(c.expected_recoverable)} color={T.success} />
          <MiniKV label="Window" value={win.label} color={win.color} />
          <MiniKV label="Status" value={c.status || 'Open'} color={sColor} />
        </div>
      )}
    </motion.div>
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

function CenterMsg({ children }: { children: React.ReactNode }) {
  return <div style={{ height: '100%', minHeight: 240, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 9, color: T.text2, fontSize: 13, background: T.bg, fontFamily: T.font }}>{children}</div>
}

const iconBtn: React.CSSProperties = { display: 'grid', placeItems: 'center', width: 34, height: 34, borderRadius: 9, background: T.raised, border: `1px solid ${T.border}`, cursor: 'pointer' }
