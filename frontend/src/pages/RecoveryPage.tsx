// ── RECOVERY PAGE ─────────────────────────────────────────────────────────────
// A calm, single-column recovery briefing for a fraud investigator. It answers,
// in order: how likely is recovery and what do I do next (hero) · where the money
// stands (funds snapshot) · the route back to it (flow) · which accounts to freeze
// (table) · the ranked plan (strategy) · the cost of waiting (timeline). Deeper
// model detail (reasons, the ten factors, the simulator, the UB analyst) is kept
// one tap away so the page itself stays quiet.
//
// Design: matte black canvas, restrained gold for the platform's own voice
// (primary action), and green/amber/red strictly for recovery meaning. No
// particle backgrounds, gauges, gradient fills, or glowing borders.
import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { jsPDF } from 'jspdf'
import {
  LifeBuoy, ChevronDown, ChevronLeft, RefreshCw, FileText, FileType, FileDown,
  AlertTriangle, ShieldCheck, Snowflake, X, Sparkles, HelpCircle, FlaskConical, Brain,
} from 'lucide-react'
import { T, fmtINR } from '../theme'
import { sessionStore } from '../store/session'
import {
  recoveryApi, recoveryColor, caseCriticality,
  type RecoveryAnalysis, type RecoveryDashboard, type RecoveryAction,
  type RecoveryReason, type RecoveryObstacle,
} from '../recovery/api'
import { Section, Eyebrow, StatusPill, A } from '../recovery/redesign/primitives'
import {
  RecoveryHero, FundsSnapshot, RecoveryFlow, RecoverableAccounts, RecoveryStrategy, RecoveryTimeline,
  type FreezeTarget,
} from '../recovery/redesign/sections'
import { FactorGrid } from '../recovery/center/FactorGrid'
import { SimulationPanel } from '../recovery/center/SimulationPanel'
import { UbRecovery } from '../recovery/center/UbRecovery'

type DeepPanel = 'why' | 'sim' | 'ub' | null

function useNarrow(bp = 1000) {
  const [n, setN] = useState(() => typeof window !== 'undefined' && window.innerWidth < bp)
  useEffect(() => { const on = () => setN(window.innerWidth < bp); window.addEventListener('resize', on); return () => window.removeEventListener('resize', on) }, [bp])
  return n
}

export default function RecoveryPage() {
  const { caseId: routeCase } = useParams()
  const navigate = useNavigate()
  const narrow = useNarrow()

  const [dash, setDash] = useState<RecoveryDashboard | null>(null)
  const [selected, setSelected] = useState<string>(() => routeCase ?? sessionStore.get().recovery.selectedCase ?? '')
  const [analysis, setAnalysis] = useState<RecoveryAnalysis | null>(
    () => (sessionStore.get().recovery.byCase[routeCase ?? sessionStore.get().recovery.selectedCase ?? ''] as RecoveryAnalysis) ?? null,
  )
  const [loading, setLoading] = useState(() => !sessionStore.get().recovery.byCase[routeCase ?? sessionStore.get().recovery.selectedCase ?? ''])
  const [refreshing, setRefreshing] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [confirm, setConfirm] = useState<{ title: string; detail: string } | null>(null)
  const [deep, setDeep] = useState<DeepPanel>(null)
  const simRef = useRef<HTMLDivElement>(null)

  const flash = useCallback((m: string) => { setToast(m); setTimeout(() => setToast(null), 2800) }, [])

  useEffect(() => {
    let alive = true
    recoveryApi.dashboard().then(d => {
      if (!alive) return
      setDash(d)
      if (!selected) setSelected(routeCase || d.cases.find(c => c.urgent)?.case_id || d.cases[0]?.case_id || '')
    }).catch(() => {}).finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!selected) return
    let alive = true
    sessionStore.patch('recovery', { selectedCase: selected })
    sessionStore.setCurrentCase(selected)
    const cached = sessionStore.get().recovery.byCase[selected] as RecoveryAnalysis | undefined
    if (cached) setAnalysis(cached)
    else recoveryApi.forCase(selected)
      .then(a => { if (alive) { setAnalysis(a); sessionStore.cacheRecovery(selected, a) } })
      .catch(() => alive && setAnalysis(null))
    if (routeCase !== selected) navigate(`/recovery/${selected}`, { replace: true })
    return () => { alive = false }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected])

  const rerun = useCallback(async () => {
    if (!selected) return
    setRefreshing(true)
    try { const a = await recoveryApi.analyze(selected, true); setAnalysis(a); sessionStore.cacheRecovery(selected, a); flash('Recovery analysis re-run') }
    catch { /* ignore */ } finally { setRefreshing(false) }
  }, [selected, flash])

  const scrollToSim = useCallback(() => { setDeep('sim'); setTimeout(() => simRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 60) }, [])

  // execute / freeze intents — logged for the operations desk (no live execution).
  const onExecuteAction = useCallback((a: RecoveryAction) => {
    setConfirm({ title: a.action, detail: `${a.impact} impact · expected +${a.expected_recovery_increase}% recovery. ${a.rationale}` })
  }, [])
  const onExecuteHeadline = useCallback(() => { if (analysis?.actions[0]) onExecuteAction(analysis.actions[0]) }, [analysis, onExecuteAction])
  const onFreeze = useCallback((t: FreezeTarget) => {
    const conf = t.freeze_success != null ? ` Freeze success likelihood ${t.freeze_success}%.` : ''
    setConfirm({ title: `Freeze account ${t.account}`, detail: `Preserves an estimated ${t.freeze_impact}% of recoverable funds (${fmtINR(t.held_amount)} currently held).${conf}` })
  }, [])
  const confirmExecute = useCallback(() => { if (confirm) flash(`Action dispatched to operations desk — ${confirm.title}`); setConfirm(null) }, [confirm, flash])

  // exports
  const exportJSON = useCallback(() => { if (!analysis) return; dl(new Blob([JSON.stringify(analysis, null, 2)], { type: 'application/json' }), `${analysis.case_id}_recovery.json`); flash('Recovery analysis exported (JSON)') }, [analysis, flash])
  const exportDOCX = useCallback(() => { if (!analysis) return; dl(new Blob(['﻿' + recoveryReportHTML(analysis)], { type: 'application/msword' }), `${analysis.case_id}_recovery_report.doc`); flash('Recovery report exported (DOCX)') }, [analysis, flash])
  const exportPDF = useCallback(() => { if (!analysis) return; recoveryReportPDF(analysis); flash('Recovery report generated (PDF)') }, [analysis, flash])

  const risk = useMemo(() => analysis ? caseCriticality(analysis.recovery_probability, analysis.estimated_loss) : null, [analysis])

  if (loading) return <CenterMsg><Sparkles size={18} color={A.base} /> Computing recovery intelligence…</CenterMsg>

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: T.bg, color: T.text, fontFamily: T.font, overflow: 'hidden' }}>
      {/* ── COMMAND BAR ─────────────────────────────────────────────────────── */}
      <header style={{ flexShrink: 0, height: 58, display: 'flex', alignItems: 'center', gap: 14, padding: '0 20px', borderBottom: `1px solid ${T.border}`, background: T.bg2, zIndex: 7 }}>
        <button onClick={() => navigate('/recovery')} title="Back to recovery portfolio" aria-label="Back to recovery portfolio" style={{ ...iconBtn, marginRight: -4 }}>
          <ChevronLeft size={16} color={T.text2} />
        </button>
        <div style={{ width: 30, height: 30, borderRadius: 8, display: 'grid', placeItems: 'center', background: A.dim, border: `1px solid ${A.line}` }}>
          <LifeBuoy size={16} color={A.base} />
        </div>
        <div style={{ marginRight: 6 }}>
          <div style={{ fontSize: 13.5, fontWeight: 600, color: T.text, lineHeight: 1.2 }}>Recovery Intelligence</div>
          <div style={{ fontSize: 10, color: T.text3 }}>Fund-recovery operations</div>
        </div>

        {/* case picker */}
        <div style={{ position: 'relative' }}>
          <button onClick={() => setPickerOpen(o => !o)}
            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderRadius: 9, background: T.raised, border: `1px solid ${T.border}`, color: T.text, cursor: 'pointer', fontFamily: T.font, fontSize: 12.5 }}>
            <span style={{ fontFamily: T.mono }}>{selected || 'Select case'}</span>
            <ChevronDown size={14} color={T.text3} />
          </button>
          <AnimatePresence>
            {pickerOpen && dash && (
              <>
                <div onClick={() => setPickerOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 19 }} />
                <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
                  style={{ position: 'absolute', top: 44, left: 0, width: 380, maxHeight: 420, overflowY: 'auto', background: T.panel, border: `1px solid ${T.borderHi}`, borderRadius: 12, boxShadow: T.shadow, zIndex: 20, padding: 6 }}>
                  {dash.cases.map(c => (
                    <button key={c.case_id} onClick={() => { setSelected(c.case_id); setPickerOpen(false); setDeep(null) }}
                      style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 11, padding: '10px 11px', borderRadius: 8, background: c.case_id === selected ? A.dim : 'transparent', border: 'none', cursor: 'pointer', textAlign: 'left', fontFamily: T.font }}
                      onMouseEnter={e => (e.currentTarget.style.background = c.case_id === selected ? A.dim : T.raised)}
                      onMouseLeave={e => (e.currentTarget.style.background = c.case_id === selected ? A.dim : 'transparent')}>
                      <span style={{ width: 30, fontSize: 14, fontWeight: 600, color: recoveryColor(c.recovery_probability), fontFamily: T.mono }}>{c.recovery_probability}</span>
                      <span style={{ flex: 1, minWidth: 0 }}>
                        <span style={{ display: 'block', fontSize: 12, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.title}</span>
                        <span style={{ fontSize: 10, color: T.text3, fontFamily: T.mono }}>{c.case_id} · {fmtINR(c.expected_recoverable)} recoverable</span>
                      </span>
                      {c.urgent && <span style={{ fontSize: 9, color: T.danger, fontWeight: 700, letterSpacing: '.04em' }}>ACT NOW</span>}
                    </button>
                  ))}
                </motion.div>
              </>
            )}
          </AnimatePresence>
        </div>

        <div style={{ flex: 1 }} />
        <button onClick={rerun} title="Re-run analysis" aria-label="Re-run analysis" style={iconBtn}>
          <RefreshCw size={15} color={T.text2} style={refreshing ? { animation: 'spin 1s linear infinite' } : undefined} />
        </button>
        <button onClick={exportPDF} style={pillBtn}><FileText size={14} /> PDF</button>
        <button onClick={exportDOCX} style={pillBtn}><FileType size={14} /> DOCX</button>
        <button onClick={exportJSON} style={pillBtn}><FileDown size={14} /> JSON</button>
      </header>

      {/* ── BODY ────────────────────────────────────────────────────────────── */}
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: narrow ? '24px 16px 100px' : '40px 32px 128px' }}>
        <div style={{ maxWidth: 1040, margin: '0 auto' }}>
          {analysis?.insufficient_evidence ? (
            <InsufficientEvidence message={analysis.evidence_message} />
          ) : !analysis || !risk ? (
            <CenterMsg><AlertTriangle size={18} color={T.danger} /> No recovery analysis for this case.</CenterMsg>
          ) : (
            <>
              <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}>
                <RecoveryHero a={analysis} risk={risk} narrow={narrow} onExecute={onExecuteHeadline} />
                <div style={{ marginTop: 36 }}>
                  <FundsSnapshot funnel={analysis.funnel} narrow={narrow} />
                </div>
              </motion.div>

              <Section title="Recovery flow" hint="The route from the fraud origin to the accounts still holding money, ranked by how much can be reclaimed along each path.">
                <RecoveryFlow paths={analysis.recovery_paths || []} />
              </Section>

              <Section title="Recoverable accounts" hint="Accounts currently holding traceable funds — ordered by recovery priority, with the freeze likelihood the engine assigns each one.">
                <RecoverableAccounts rows={analysis.traceability || []} critical={analysis.critical_accounts} onFreeze={onFreeze} narrow={narrow} />
              </Section>

              <Section title="Recovery strategy" hint="Interventions ranked by expected recovery gain. Execute the top move first, or simulate a freeze before committing.">
                <RecoveryStrategy actions={analysis.actions} critical={analysis.critical_accounts} onExecute={onExecuteAction} onSimulate={scrollToSim} />
              </Section>

              <Section title="Recovery timeline" hint="How the odds of recovery decay if no action is taken. The window closes when recovery is no longer realistically achievable.">
                <RecoveryTimeline curve={analysis.decay_curve} windowSeconds={analysis.window_seconds} score={analysis.recovery_probability} />
              </Section>

              {/* ── DEEPER ANALYSIS — quiet, one tap away ─────────────────────── */}
              <div style={{ marginTop: 64 }}>
                <Eyebrow style={{ marginBottom: 8 }}>Deeper analysis</Eyebrow>
                <Disclosure icon={HelpCircle} title="Why this recovery score" hint={`${analysis.recovery_probability}% at ${analysis.confidence}% confidence — every point cites this case's fund flow.`} open={deep === 'why'} onToggle={() => setDeep(d => d === 'why' ? null : 'why')}>
                  {!!analysis.reasons?.length && <div style={{ marginBottom: 24 }}><SubLabel>Drivers</SubLabel><ReasonList reasons={analysis.reasons} /></div>}
                  {!!analysis.obstacles?.length && <div style={{ marginBottom: 24 }}><SubLabel>Obstacles to recovery</SubLabel><ObstacleList obstacles={analysis.obstacles} /></div>}
                  <SubLabel>The ten weighted factors</SubLabel>
                  <FactorGrid factors={analysis.factors} weights={analysis.weights} />
                </Disclosure>
                <div ref={simRef}>
                  <Disclosure icon={FlaskConical} title="Simulate an intervention" hint="Model a freeze, a delay, or no action and watch recovery recompute." open={deep === 'sim'} onToggle={() => setDeep(d => d === 'sim' ? null : 'sim')}>
                    <SimulationPanel caseId={analysis.case_id} criticalAccounts={analysis.critical_accounts} />
                  </Disclosure>
                </div>
                <Disclosure icon={Brain} title="Ask the recovery analyst" hint="Question UB about this case in plain banking language." open={deep === 'ub'} onToggle={() => setDeep(d => d === 'ub' ? null : 'ub')}>
                  <div style={{ minHeight: 320 }}><UbRecovery caseId={analysis.case_id} /></div>
                </Disclosure>
              </div>
            </>
          )}
        </div>
      </div>

      {/* execute confirmation */}
      <AnimatePresence>
        {confirm && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setConfirm(null)}
            style={{ position: 'absolute', inset: 0, zIndex: 60, background: 'rgba(6,7,9,0.62)', display: 'grid', placeItems: 'center', padding: 20 }}>
            <motion.div initial={{ scale: 0.96, y: 8 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.97, opacity: 0 }} onClick={e => e.stopPropagation()}
              style={{ width: 440, maxWidth: '100%', background: T.panel, border: `1px solid ${T.borderHi}`, borderRadius: 16, padding: 24, boxShadow: T.shadow }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                <div style={{ width: 34, height: 34, borderRadius: 9, display: 'grid', placeItems: 'center', background: A.dim, border: `1px solid ${A.line}` }}>
                  <Snowflake size={16} color={A.base} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Eyebrow>Confirm recovery action</Eyebrow>
                  <div style={{ fontSize: 14.5, fontWeight: 600, color: T.text, marginTop: 3 }}>{confirm.title}</div>
                </div>
                <button onClick={() => setConfirm(null)} aria-label="Cancel" style={{ ...iconBtn, width: 30, height: 30 }}><X size={15} color={T.text3} /></button>
              </div>
              <p style={{ fontSize: 12.5, color: T.text2, lineHeight: 1.6, margin: '0 0 20px' }}>{confirm.detail}</p>
              <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
                <button onClick={() => setConfirm(null)} style={{ ...pillBtn, padding: '9px 16px' }}>Cancel</button>
                <button onClick={confirmExecute}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 7, padding: '9px 18px', borderRadius: 9, border: 'none', background: A.base, color: T.textOn, fontWeight: 600, fontSize: 12.5, cursor: 'pointer', fontFamily: T.font }}>
                  <ShieldCheck size={15} /> Dispatch to operations
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {toast && (
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 12 }}
            style={{ position: 'absolute', left: '50%', bottom: 24, transform: 'translateX(-50%)', zIndex: 50, background: T.panel, border: `1px solid ${T.borderHi}`, color: T.text, fontSize: 12.5, padding: '11px 16px', borderRadius: 10, boxShadow: T.shadow, display: 'flex', alignItems: 'center', gap: 9 }}>
            <ShieldCheck size={15} color={A.base} /> {toast}
          </motion.div>
        )}
      </AnimatePresence>

      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}

// ── pieces ───────────────────────────────────────────────────────────────────
function Disclosure({ icon: Icon, title, hint, open, onToggle, children }: {
  icon: any; title: string; hint?: string; open: boolean; onToggle: () => void; children: React.ReactNode
}) {
  return (
    <div style={{ borderTop: `1px solid ${T.border}` }}>
      <button onClick={onToggle}
        style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 13, padding: '20px 2px', background: 'transparent', border: 'none', cursor: 'pointer', textAlign: 'left', fontFamily: T.font }}>
        <Icon size={16} color={open ? A.base : T.text3} />
        <span style={{ flex: 1, minWidth: 0 }}>
          <span style={{ display: 'block', fontSize: 14, fontWeight: 600, color: T.text }}>{title}</span>
          {hint && <span style={{ display: 'block', fontSize: 12, color: T.text2, marginTop: 4, lineHeight: 1.5 }}>{hint}</span>}
        </span>
        <ChevronDown size={16} color={T.text3} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .2s ease', flexShrink: 0 }} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }} style={{ overflow: 'hidden' }}>
            <div style={{ padding: '6px 2px 30px' }}>{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function SubLabel({ children }: { children: React.ReactNode }) {
  return <div style={{ fontSize: 10.5, letterSpacing: '0.08em', textTransform: 'uppercase', color: T.text3, fontWeight: 600, marginBottom: 14 }}>{children}</div>
}

function ReasonList({ reasons }: { reasons: RecoveryReason[] }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {reasons.map((r, i) => {
        const col = r.polarity === 'positive' ? T.success : T.danger
        return (
          <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 11 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: col, marginTop: 7, flexShrink: 0 }} />
            <span style={{ fontSize: 12.5, color: T.text2, lineHeight: 1.55 }}>{r.text}</span>
          </div>
        )
      })}
    </div>
  )
}

const SEV_COLOR: Record<string, string> = { Critical: T.danger, High: '#f0883e', Medium: T.warn, Low: T.text3 }
function ObstacleList({ obstacles }: { obstacles: RecoveryObstacle[] }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {obstacles.map((o, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <span style={{ paddingTop: 1 }}><StatusPill label={o.severity} color={SEV_COLOR[o.severity] || T.text3} strong /></span>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{o.obstacle}</div>
            <div style={{ fontSize: 11.5, color: T.text3, marginTop: 3, lineHeight: 1.5 }}>{o.detail}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

function InsufficientEvidence({ message }: { message?: string }) {
  return (
    <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 16, padding: 36, textAlign: 'center', maxWidth: 520, margin: '40px auto 0' }}>
      <AlertTriangle size={24} color={T.warn} />
      <div style={{ fontSize: 16, fontWeight: 600, color: T.text, margin: '14px 0 8px' }}>Insufficient evidence to estimate recovery</div>
      <div style={{ fontSize: 12.5, color: T.text2, lineHeight: 1.65 }}>
        {message || 'This case carries no traceable fund flow. The engine will not produce a recovery figure until transaction evidence is attached.'}
      </div>
    </div>
  )
}

function CenterMsg({ children }: { children: React.ReactNode }) {
  return <div style={{ height: '100%', minHeight: 240, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 9, color: T.text2, fontSize: 13, background: T.bg, fontFamily: T.font }}>{children}</div>
}

const iconBtn: React.CSSProperties = { display: 'grid', placeItems: 'center', width: 34, height: 34, borderRadius: 9, background: T.raised, border: `1px solid ${T.border}`, cursor: 'pointer' }
const pillBtn: React.CSSProperties = { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 12px', borderRadius: 9, background: T.raised, border: `1px solid ${T.border}`, color: T.text2, cursor: 'pointer', fontFamily: T.font, fontSize: 11.5, fontWeight: 600 }

function dl(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = name; a.click()
  URL.revokeObjectURL(url)
}

// ── forensic report builders (unchanged data contract) ───────────────────────
function recoveryReportPDF(a: RecoveryAnalysis) {
  const doc = new jsPDF({ unit: 'pt', format: 'a4' })
  const W = doc.internal.pageSize.getWidth()
  doc.setFillColor(10, 11, 13); doc.rect(0, 0, W, 84, 'F')
  doc.setTextColor(198, 162, 83); doc.setFont('helvetica', 'bold'); doc.setFontSize(18)
  doc.text('RECOVERY INTELLIGENCE REPORT', 40, 46)
  doc.setTextColor(150, 160, 175); doc.setFont('helvetica', 'normal'); doc.setFontSize(10)
  doc.text(`${a.case_id} · ${a.title} · generated ${new Date().toLocaleString('en-GB')}`, 40, 66)
  let y = 116
  const line = (l: string, v: string) => { doc.setFont('helvetica', 'bold'); doc.setTextColor(90, 100, 112); doc.text(l, 40, y); doc.setFont('helvetica', 'normal'); doc.setTextColor(20, 22, 27); doc.text(v, 230, y); y += 19 }
  line('Recovery Probability', `${a.recovery_probability}%  (${a.band})`)
  line('Confidence', `${a.confidence}%`)
  line('Fraud Amount (originated)', fmtINR(a.funnel.fraud_amount))
  line('Expected Recoverable', fmtINR(a.expected_recoverable))
  line('Projected Loss', fmtINR(a.estimated_loss))
  line('Recommended Action', a.headline_action)
  if (a.kill_node) line('Network Kill Node', `${a.kill_node.account} (disrupts ${a.kill_node.disruption_pct}%)`)
  y += 8; doc.setFont('helvetica', 'bold'); doc.setFontSize(12); doc.setTextColor(20, 22, 27); doc.text('Money Survival Pipeline', 40, y); y += 17; doc.setFontSize(10)
  ;[['Fraud amount', a.funnel.fraud_amount], ['Still traceable', a.funnel.still_traceable], ['Recoverable', a.funnel.recoverable], ['Likely recoverable', a.funnel.likely_recoverable]].forEach(([l, v]) => { doc.setTextColor(90, 100, 112); doc.text(`${l}: ${fmtINR(v as number)}`, 48, y); y += 15 })
  y += 8; doc.setFont('helvetica', 'bold'); doc.setFontSize(12); doc.setTextColor(20, 22, 27); doc.text('Critical Accounts to Freeze', 40, y); y += 17; doc.setFontSize(10); doc.setFont('helvetica', 'normal'); doc.setTextColor(90, 100, 112)
  ;(a.critical_accounts || []).slice(0, 4).forEach(c => { doc.text(`${c.account} — controls ${c.freeze_impact}% (freeze success ${c.freeze_success}%)`, 48, y); y += 15 })
  y += 8; doc.setFont('helvetica', 'bold'); doc.setFontSize(12); doc.setTextColor(20, 22, 27); doc.text('Recommended Actions', 40, y); y += 17; doc.setFontSize(10); doc.setFont('helvetica', 'normal'); doc.setTextColor(90, 100, 112)
  a.actions.slice(0, 6).forEach(act => { doc.text(`P${act.priority}. ${act.action}  (+${act.expected_recovery_increase}%, ${act.impact})`, 48, y); y += 15 })
  doc.save(`${a.case_id}_recovery_report.pdf`)
}

function recoveryReportHTML(a: RecoveryAnalysis): string {
  const row = (l: string, v: string) => `<tr><td style="padding:4px 14px 4px 0;color:#555"><b>${l}</b></td><td>${v}</td></tr>`
  const acts = a.actions.slice(0, 6).map(x => `<li>P${x.priority}. ${x.action} — +${x.expected_recovery_increase}% (${x.impact}). ${x.rationale}</li>`).join('')
  const critRows = (a.critical_accounts || []).slice(0, 4).map(c => `<li>${c.account}: controls ${c.freeze_impact}% (freeze success ${c.freeze_success}%)</li>`).join('')
  return `<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word'><head><meta charset='utf-8'><title>Recovery Report ${a.case_id}</title></head>
  <body style="font-family:Calibri,Arial,sans-serif;color:#111">
  <h1 style="color:#a8842f">Recovery Intelligence Report</h1>
  <p style="color:#666">${a.case_id} — ${a.title} · generated ${new Date().toLocaleString('en-GB')}</p>
  <table>${row('Recovery Probability', `${a.recovery_probability}% (${a.band})`)}${row('Confidence', `${a.confidence}%`)}${row('Fraud Amount (originated)', fmtINR(a.funnel.fraud_amount))}${row('Expected Recoverable', fmtINR(a.expected_recoverable))}${row('Projected Loss', fmtINR(a.estimated_loss))}${row('Recommended Action', a.headline_action)}${a.kill_node ? row('Network Kill Node', `${a.kill_node.account} (disrupts ${a.kill_node.disruption_pct}%)`) : ''}</table>
  <h3>Money Survival Pipeline</h3><ul><li>Fraud amount: ${fmtINR(a.funnel.fraud_amount)}</li><li>Still traceable: ${fmtINR(a.funnel.still_traceable)}</li><li>Recoverable: ${fmtINR(a.funnel.recoverable)}</li><li>Likely recoverable: ${fmtINR(a.funnel.likely_recoverable)}</li></ul>
  <h3>Critical Accounts to Freeze</h3><ul>${critRows || '<li>None identified</li>'}</ul>
  <h3>Recommended Actions</h3><ol>${acts}</ol>
  <h3>Recovery Factors</h3><ul>${a.factors.map(f => `<li>${f.name}: ${f.score}/100 — ${f.label}</li>`).join('')}</ul>
  </body></html>`
}
