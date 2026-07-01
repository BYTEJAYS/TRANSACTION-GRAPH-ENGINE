import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft, Activity, Network, Link2, FileText, ShieldAlert, StickyNote,
  AlertTriangle, ArrowUpRight, CheckCircle2, UserCheck, FileDown,
  XCircle, Clock, Hash, Send, Plus, LifeBuoy, Users, Coins,
  UploadCloud, Download, RefreshCw, Box, Snowflake, Link as LinkIcon, ShieldCheck,
  MessageSquare, ListChecks, UsersRound,
} from 'lucide-react'
import { Page } from '../components/nav/AppLayout'
import { useAuth } from '../auth/AuthContext'
import {
  caseApi, collabApi, priorityColor, caseStatusColor, type CaseDetail,
} from '../cases/api'
import { CommentsPanel, TasksPanel, TeamPanel, PresenceBar } from '../cases/CollabPanels'
import { useCaseSocket } from '../hooks/useCaseSocket'
import { recoveryApi, recoveryColor, type RecoveryAnalysis } from '../recovery/api'
import { T, riskColorFromScore, fmtINR } from '../theme'

type CaseTab = 'transactions' | 'accounts' | 'recovery' | 'evidence' | 'blockchain'
  | 'team' | 'comments' | 'tasks' | 'timeline' | 'notes' | 'reports'
const TABS: { id: CaseTab; label: string; icon: any }[] = [
  { id: 'transactions', label: 'Transactions', icon: Activity },
  { id: 'accounts', label: 'Accounts', icon: Users },
  { id: 'recovery', label: 'Recovery', icon: Coins },
  { id: 'evidence', label: 'Evidence', icon: FileText },
  { id: 'blockchain', label: 'Blockchain', icon: LinkIcon },
  { id: 'team', label: 'Team', icon: UsersRound },
  { id: 'comments', label: 'Comments', icon: MessageSquare },
  { id: 'tasks', label: 'Tasks', icon: ListChecks },
  { id: 'timeline', label: 'Activity', icon: Clock },
  { id: 'notes', label: 'Notes', icon: StickyNote },
  { id: 'reports', label: 'Reports', icon: FileDown },
]

const ROLE_COLOR: Record<string, string> = {
  'Primary Source': '#ff3366', 'Destination': '#f59e0b',
  'Intermediary': '#7c8cff', 'Victim': '#38bdf8', 'Linked': '#64748b',
}

const EVIDENCE_TYPES = ['Graph snapshot', 'Transaction trail', 'KYC record', 'Device fingerprint', 'Bank statement', 'CCTV / Branch record']
const RESOLUTIONS = ['Resolved', 'Closed', 'False Positive', 'Archived']

function fmtDateTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export default function CaseDetailPage() {
  const { caseId } = useParams()
  const navigate = useNavigate()
  const { investigator } = useAuth()
  const [c, setC] = useState<CaseDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [note, setNote] = useState('')
  const [evType, setEvType] = useState(EVIDENCE_TYPES[0])
  const [evRef, setEvRef] = useState('')
  const [showClose, setShowClose] = useState(false)
  const [resolution, setResolution] = useState(RESOLUTIONS[0])
  const [closeSummary, setCloseSummary] = useState('')
  const [tab, setTab] = useState<CaseTab>('transactions')
  const [rec, setRec] = useState<RecoveryAnalysis | null>(null)

  // accounts table controls
  const [acctQuery, setAcctQuery] = useState('')
  const [acctRole, setAcctRole] = useState('All')
  const [acctSort, setAcctSort] = useState<'risk' | 'incoming' | 'outgoing' | 'transactions'>('risk')
  // evidence upload + blockchain
  const [uploadType, setUploadType] = useState(EVIDENCE_TYPES[0])
  const [uploadRemarks, setUploadRemarks] = useState('')
  const [verifyMsg, setVerifyMsg] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true); setErr(null)
    caseApi.get(caseId!).then(setC).catch(e => setErr(e.message)).finally(() => setLoading(false))
    recoveryApi.forCase(caseId!).then(setRec).catch(() => setRec(null))
  }, [caseId])
  useEffect(() => { load() }, [load])

  // ── Collaboration: my capabilities (gate actions) + live case room ──────────
  const [caps, setCaps] = useState<string[]>([])
  useEffect(() => { collabApi.capabilities().then(r => setCaps(r.capabilities)).catch(() => {}) }, [])
  // silent refetch so OTHER investigators' changes appear without a reload/flicker
  const refetch = useCallback(() => { caseApi.get(caseId!).then(setC).catch(() => {}) }, [caseId])
  const { present, connected } = useCaseSocket(caseId, investigator, refetch)

  if (loading) return <Page><div style={{ color: T.text3, fontSize: 13 }}>Loading case…</div></Page>
  if (err || !c) return (
    <Page>
      <button onClick={() => navigate('/investigations')} style={backBtn}><ArrowLeft size={15} /> Investigations</button>
      <div style={{ marginTop: 30, color: T.danger }}>{err ?? 'Case not found'}</div>
    </Page>
  )

  const risk = riskColorFromScore(c.risk_score)
  const closed = !['New', 'Under Review', 'Evidence Collection', 'Active Investigation', 'Escalated', 'Pending Approval'].includes(c.status)

  async function act<T>(fn: () => Promise<T>) {
    setBusy(true)
    try { const r = await fn(); setC(r as CaseDetail) } catch (e) { setErr(e instanceof Error ? e.message : 'Action failed') } finally { setBusy(false) }
  }
  const addNote = async () => { if (!note.trim()) return; await act(() => caseApi.addNote(c!.case_id, note)); setNote('') }
  const addEvidence = async () => { await act(() => caseApi.addEvidence(c!.case_id, { type: evType, reference: evRef })); setEvRef('') }
  const assignMe = () => act(() => caseApi.assign(c!.case_id, {}))
  const doClose = async () => { await act(() => caseApi.close(c!.case_id, resolution, closeSummary)); setShowClose(false); setCloseSummary('') }

  const uploadFile = async (file: File) => {
    await act(() => caseApi.uploadEvidence(c!.case_id, file, uploadType, uploadRemarks))
    setUploadRemarks('')
  }
  const anchor = () => act(() => caseApi.anchorBlockchain(c!.case_id))
  const verifyAnchor = async () => {
    setBusy(true); setVerifyMsg(null)
    try {
      const r = await caseApi.verifyBlockchain(c!.case_id)
      setVerifyMsg(r.verified ? 'Verified — bundle matches the ledger.'
        : r.tampered ? 'TAMPERED — case data no longer matches the anchored hash.'
        : 'Verification could not be completed.')
      load()
    } catch (e) { setErr(e instanceof Error ? e.message : 'Verify failed') } finally { setBusy(false) }
  }
  const downloadBundle = () => caseApi.downloadBundle(c!.case_id).catch(e => setErr(e.message))
  const downloadEvidence = (eid: string) => caseApi.downloadEvidence(c!.case_id, eid).catch(e => setErr(e.message))
  const downloadReceipt = () => caseApi.downloadReceipt(c!.case_id).catch(e => setErr(e.message))

  function generateReport(format: 'json' | 'pdf' | 'docx') {
    if (!c) return
    if (format === 'json') {
      downloadBlob(JSON.stringify(c, null, 2), `${c.case_id}_report.json`, 'application/json')
      return
    }
    const html = reportHtml(c, investigator?.name ?? 'Investigator')
    if (format === 'docx') {
      downloadBlob(html, `${c.case_id}_report.doc`, 'application/msword')
      return
    }
    const w = window.open('', '_blank')
    if (w) { w.document.write(html); w.document.close(); w.focus(); setTimeout(() => w.print(), 350) }
  }

  return (
    <Page>
      <button onClick={() => navigate('/investigations')} style={backBtn}><ArrowLeft size={15} /> Investigations</button>

      {/* ── slim header ────────────────────────────────────────── */}
      <div style={{ ...card, marginTop: 14, padding: 0, overflow: 'hidden' }}>
        <div style={{ height: 3, background: priorityColor(c.priority) }} />
        <div style={{ padding: '18px 22px', display: 'flex', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 13, color: T.gold, fontFamily: T.mono }}>{c.case_id}</span>
              <Tag text={c.priority} color={priorityColor(c.priority)} solid />
              <Tag text={c.status} color={caseStatusColor(c.status)} />
            </div>
            <h1 style={{ fontSize: 21, fontWeight: 700, margin: '9px 0 0' }}>{c.title}</h1>
            <div style={{ fontSize: 12, color: T.text3, marginTop: 4 }}>{c.category} · Updated {fmtDateTime(c.updated_at)}</div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end' }}>
            <PresenceBar present={present.filter(p => p.investigator_id !== investigator?.investigator_id)} connected={connected} />
            {!c.assigned_to && !closed && <ActBtn onClick={assignMe} disabled={busy} icon={UserCheck} label="Assign to Me" primary />}
            {!closed && <ActBtn onClick={() => setShowClose(true)} disabled={busy} icon={XCircle} label="Close Case" danger />}
          </div>
        </div>
      </div>

      {/* ── Risk Assessment summary (explainable score) ────────── */}
      {c.risk_assessment && <RiskSummary a={c.risk_assessment} />}

      {/* ── Cross-Bank Indicators (only when there is a cross-bank signal) ── */}
      {c.cross_bank && <CrossBankIndicators cb={c.cross_bank} />}

      {/* ── LEVEL 1 · what should I do next? ────────────────────── */}
      <div style={{ ...card, marginTop: 14 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 14 }}>
          <AnswerCell label="Case Status" value={c.status} color={caseStatusColor(c.status)} />
          <AnswerCell label="Risk Level" value={`${c.risk_score}`} color={risk} sub={`fraud confidence ${Math.round(c.fraud_confidence * 100)}%`} />
          <button onClick={() => navigate(`/recovery/${c.case_id}`)} style={{ all: 'unset', cursor: 'pointer' }}>
            <AnswerCell label="Recovery Potential" value={rec ? `${rec.recovery_probability}%` : '—'} color={rec ? recoveryColor(rec.recovery_probability) : T.text3} sub={rec ? `${fmtINR(rec.expected_recoverable)} recoverable →` : 'open recovery →'} />
          </button>
        </div>

        <div style={{ marginTop: 18 }}>
          <div style={{ fontSize: 9.5, color: T.text3, letterSpacing: '.08em', marginBottom: 7 }}>CASE SUMMARY</div>
          <p style={{ fontSize: 13, color: T.text2, lineHeight: 1.65, margin: 0 }}>{c.ub_analysis}</p>
          <div style={{ fontSize: 11.5, color: T.text3, marginTop: 8, display: 'flex', gap: 7, alignItems: 'flex-start' }}>
            <AlertTriangle size={13} color={T.warn} style={{ marginTop: 2, flexShrink: 0 }} /> {c.detection_reason}
          </div>
        </div>

        <div style={{ marginTop: 18, padding: '15px 17px', borderRadius: 12, background: T.goldDim, border: `1px solid ${T.goldLine}`, display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontSize: 9.5, color: T.gold, letterSpacing: '.1em', marginBottom: 5, fontWeight: 700 }}>NEXT RECOMMENDED ACTION</div>
            <div style={{ fontSize: 15, fontWeight: 700, color: T.text }}>{rec?.headline_action ?? nextAction(c)}</div>
          </div>
          {rec && (
            <button onClick={() => navigate(`/recovery/${c.case_id}`)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 7, padding: '10px 16px', borderRadius: 9, border: 'none', background: T.gold, color: T.textOn, fontWeight: 700, fontSize: 12.5, cursor: 'pointer', fontFamily: T.font }}>
              <LifeBuoy size={15} /> Open recovery
            </button>
          )}
        </div>
      </div>

      {/* ── tabs ───────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 4, marginTop: 18, marginBottom: 16, flexWrap: 'wrap', borderBottom: `1px solid ${T.border}`, paddingBottom: 2 }}>
        {TABS.map(t => {
          const on = tab === t.id
          const count = t.id === 'transactions' ? c.transactions.length : t.id === 'accounts' ? (c.account_roles ?? c.accounts).length : t.id === 'evidence' ? c.evidence.length : t.id === 'notes' ? c.notes.length
            : t.id === 'team' ? (c.participants?.length ?? 0)
            : t.id === 'comments' ? (c.comments?.filter(x => !x.archived).length ?? 0)
            : t.id === 'tasks' ? (c.tasks?.length ?? 0) : undefined
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '10px 15px', borderRadius: '9px 9px 0 0', cursor: 'pointer', fontFamily: T.font, fontSize: 12.5, fontWeight: on ? 700 : 500,
                background: on ? T.panel : 'transparent', border: `1px solid ${on ? T.border : 'transparent'}`, borderBottom: on ? `1px solid ${T.panel}` : '1px solid transparent', marginBottom: -2, color: on ? T.text : T.text2 }}>
              <t.icon size={14} color={on ? T.gold : T.text3} /> {t.label}
              {count != null && <span style={{ fontSize: 10.5, color: T.text3, fontFamily: T.mono }}>{count}</span>}
            </button>
          )
        })}
      </div>

      {/* ── tab content ────────────────────────────────────────── */}
      {tab === 'transactions' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.6fr) minmax(0,1fr)', gap: 14, alignItems: 'start' }}>
          <Section icon={Activity} title={`Related Transactions · ${c.transactions.length}`}>
            {c.transactions.map(t => (
              <div key={t.txn_id} style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '9px 0', borderTop: `1px solid ${T.border}` }}>
                <span style={{ width: 26, height: 26, borderRadius: 7, display: 'grid', placeItems: 'center', background: T.dangerDim, flexShrink: 0 }}>
                  <ArrowUpRight size={13} color={T.danger} />
                </span>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ display: 'block', fontSize: 12, color: T.text, fontFamily: T.mono }}>{t.txn_id} <span style={{ color: T.text3 }}>· {t.rail}</span></span>
                  <span style={{ display: 'block', fontSize: 11, color: T.text3 }}>{t.from_account} → {t.to_account}</span>
                  <span style={{ display: 'block', fontSize: 10.5, color: T.warn, marginTop: 2 }}>{t.reason}</span>
                </span>
                <span style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{fmtINR(t.amount)}</span>
              </div>
            ))}
            {!c.transactions.length && <Empty text="No transactions attached." />}
          </Section>
          <div style={{ display: 'grid', gap: 14 }}>
            <Section icon={Network} title="Graph Snapshot">
              <GraphSnapshot snap={c.graph_snapshot} risk={risk} />
              {c.graph_snapshot?.captured ? (
                <button onClick={() => navigate(`/investigations/${c.case_id}/graph`)} style={{ width: '100%', marginTop: 10, padding: '8px 0', borderRadius: 8, border: `1px solid ${T.goldLine}`, background: T.gold, color: T.textOn, fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: T.font }}>Open verbatim graph (exact view) →</button>
              ) : (
                <button onClick={() => navigate('/graph')} style={{ width: '100%', marginTop: 10, padding: '8px 0', borderRadius: 8, border: `1px solid ${T.goldLine}`, background: T.goldDim, color: T.gold, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: T.font }}>Open in Graph Engine →</button>
              )}
            </Section>
            <Section icon={Link2} title={`Linked Accounts · ${c.accounts.length}`}>
              {c.accounts.map(a => (
                <Link key={a} to={`/accounts/${a}`} style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 9, padding: '7px 0', borderTop: `1px solid ${T.border}` }}>
                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: a === c.primary_account ? T.danger : T.text3 }} />
                  <span style={{ fontSize: 12.5, color: T.text, fontFamily: T.mono }}>{a}</span>
                  {a === c.primary_account && <span style={{ fontSize: 10, color: T.danger }}>PRIMARY</span>}
                </Link>
              ))}
            </Section>
          </div>
        </div>
      )}

      {tab === 'accounts' && (() => {
        const rows = (c.account_roles ?? []).filter(r =>
          (acctRole === 'All' || r.role === acctRole) &&
          (!acctQuery || r.account.toLowerCase().includes(acctQuery.toLowerCase())))
          .sort((a, b) => (b[acctSort] as number) - (a[acctSort] as number))
        const roles = ['All', ...Array.from(new Set((c.account_roles ?? []).map(r => r.role)))]
        return (
          <Section icon={Users} title={`Accounts Involved · ${(c.account_roles ?? []).length}`}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              <input value={acctQuery} onChange={e => setAcctQuery(e.target.value)} placeholder="Search account…"
                style={{ flex: 1, minWidth: 160, padding: '8px 11px', background: T.bg2, border: `1px solid ${T.border}`, borderRadius: 8, color: T.text, fontSize: 12, outline: 'none', fontFamily: T.font }} />
              <select value={acctRole} onChange={e => setAcctRole(e.target.value)} style={selStyle}>
                {roles.map(r => <option key={r} value={r}>{r === 'All' ? 'All roles' : r}</option>)}
              </select>
              <select value={acctSort} onChange={e => setAcctSort(e.target.value as any)} style={selStyle}>
                <option value="risk">Sort: Risk</option>
                <option value="transactions">Sort: Txns</option>
                <option value="incoming">Sort: Incoming</option>
                <option value="outgoing">Sort: Outgoing</option>
              </select>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1.2fr 0.6fr 1fr 1fr 0.9fr', gap: 8, fontSize: 9.5, color: T.text3, letterSpacing: '.05em', padding: '0 4px 7px' }}>
              <span>ACCOUNT</span><span>ROLE</span><span>RISK</span><span>INCOMING</span><span>OUTGOING</span><span>STATUS</span>
            </div>
            {rows.map(r => (
              <Link key={r.account} to={`/accounts/${r.account}`} style={{ textDecoration: 'none', display: 'grid', gridTemplateColumns: '1.4fr 1.2fr 0.6fr 1fr 1fr 0.9fr', gap: 8, alignItems: 'center', padding: '9px 4px', borderTop: `1px solid ${T.border}` }}>
                <span style={{ fontSize: 12, color: T.text, fontFamily: T.mono }}>{r.account}</span>
                <RoleChip role={r.role} />
                <span style={{ fontSize: 12.5, fontWeight: 700, color: riskColorFromScore(r.risk) }}>{r.risk}</span>
                <span style={{ fontSize: 11.5, color: T.success }}>{fmtINR(r.incoming)}</span>
                <span style={{ fontSize: 11.5, color: T.danger }}>{fmtINR(r.outgoing)}</span>
                <span style={{ fontSize: 10.5, color: /frozen/i.test(r.status) ? T.info : T.text3 }}>{r.status}</span>
              </Link>
            ))}
            {!rows.length && <Empty text="No accounts match the filter." />}
          </Section>
        )
      })()}

      {tab === 'recovery' && (() => {
        const rv = c.recovery
        if (!rv) return <Section icon={Coins} title="Recovery"><Empty text="Recovery analysis not yet baked for this case." /></Section>
        return (
          <div style={{ display: 'grid', gap: 14 }}>
            <Section icon={Coins} title="Fund Recovery Analysis">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px,1fr))', gap: 14 }}>
                <AnswerCell label="Recovery Probability" value={`${rv.probability}%`} color={recoveryColor(rv.probability)} sub={rv.band ?? undefined} />
                <AnswerCell label="Expected Recoverable" value={fmtINR(rv.expected_recoverable)} color={T.success} />
                <AnswerCell label="Estimated Loss" value={fmtINR(rv.estimated_loss)} color={T.danger} />
                <AnswerCell label="Action Window" value={rv.timeline} color={T.warn} sub={`confidence ${rv.confidence}%`} />
              </div>
              <div style={{ marginTop: 16, padding: '13px 15px', borderRadius: 11, background: T.goldDim, border: `1px solid ${T.goldLine}` }}>
                <div style={{ fontSize: 9.5, color: T.gold, letterSpacing: '.1em', fontWeight: 700, marginBottom: 5 }}>HEADLINE ACTION</div>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{rv.headline_action ?? 'Freeze high-exposure accounts and anchor evidence.'}</div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 14 }}>
                <Mini label="Most recoverable branch" value={rv.most_recoverable_branch ?? '—'} color={T.success} />
                <Mini label="Least recoverable branch" value={rv.least_recoverable_branch ?? '—'} color={T.danger} />
              </div>
            </Section>
            <Section icon={Snowflake} title={`Accounts to Freeze · ${rv.accounts_to_freeze.length}`}>
              {rv.critical_accounts.length ? rv.critical_accounts.map(a => (
                <div key={a.account} style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr 1fr 0.8fr', gap: 8, alignItems: 'center', padding: '9px 4px', borderTop: `1px solid ${T.border}` }}>
                  <span style={{ fontSize: 12, color: T.text, fontFamily: T.mono }}>{a.account}</span>
                  <span style={{ fontSize: 11.5, color: T.text2 }}>{fmtINR(a.held_amount)} held</span>
                  <span style={{ fontSize: 11.5, color: T.success }}>preserves {a.freeze_impact}%</span>
                  <span style={{ fontSize: 11, color: T.text3 }}>{a.freeze_success}% success</span>
                </div>
              )) : rv.accounts_to_freeze.map(a => (
                <div key={a} style={{ fontSize: 12, color: T.text, fontFamily: T.mono, padding: '6px 4px', borderTop: `1px solid ${T.border}` }}>{a}</div>
              ))}
              {!rv.accounts_to_freeze.length && <Empty text="No freezable holding accounts identified." />}
              <button onClick={() => navigate(`/recovery/${c.case_id}`)} style={{ width: '100%', marginTop: 12, padding: '9px 0', borderRadius: 8, border: `1px solid ${T.goldLine}`, background: T.goldDim, color: T.gold, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: T.font }}>Open full Recovery Engine →</button>
            </Section>
          </div>
        )
      })()}

      {tab === 'evidence' && (
        <Section icon={FileText} title={`Evidence Vault · ${c.evidence.length}`}>
          {c.evidence.map(e => (
            <div key={e.evidence_id} style={{ padding: '10px 0', borderTop: `1px solid ${T.border}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                <FileText size={14} color={T.info} />
                <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, color: T.text }}>
                  {e.name ?? e.type}
                  <span style={{ color: T.text3, fontSize: 10.5 }}> · {e.type}{e.size_bytes ? ` · ${fmtBytes(e.size_bytes)}` : ''}</span>
                </span>
                {e.verification_status && <Tag text={e.verification_status} color={e.verification_status === 'Anchored' ? T.success : T.text3} />}
                {e.anchored
                  ? <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10.5, color: T.success }}><CheckCircle2 size={11} /> Anchored</span>
                  : <span style={{ fontSize: 10.5, color: T.text3 }}>Pending</span>}
                {e.has_file && (
                  <button onClick={() => downloadEvidence(e.evidence_id)} title="Download original"
                    style={{ padding: '4px 8px', borderRadius: 7, border: `1px solid ${T.border}`, background: T.raised, color: T.text2, cursor: 'pointer', display: 'grid', placeItems: 'center' }}>
                    <Download size={13} />
                  </button>
                )}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 4, fontSize: 10, color: T.text3, fontFamily: T.mono }}>
                <Hash size={10} /> {e.hash.slice(0, 30)}… {e.uploader ? <span style={{ marginLeft: 8 }}>· {e.uploader}</span> : null}
              </div>
              {e.remarks && <div style={{ fontSize: 11, color: T.text3, marginTop: 3 }}>{e.remarks}</div>}
            </div>
          ))}
          {!c.evidence.length && <Empty text="No evidence collected." />}
          {!closed && (
            <div style={{ marginTop: 14, borderTop: `1px solid ${T.border}`, paddingTop: 14, display: 'grid', gap: 10 }}>
              <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap' }}>
                <select value={uploadType} onChange={e => setUploadType(e.target.value)} style={selStyle}>
                  {EVIDENCE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
                <input value={uploadRemarks} onChange={e => setUploadRemarks(e.target.value)} placeholder="Remarks (optional)"
                  style={{ flex: 1, minWidth: 140, padding: '8px 11px', background: T.bg2, border: `1px solid ${T.border}`, borderRadius: 8, color: T.text, fontSize: 11.5, outline: 'none', fontFamily: T.font }} />
              </div>
              <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 9, padding: '14px', borderRadius: 10, border: `1.5px dashed ${T.goldLine}`, background: T.goldDim, color: T.gold, fontSize: 12.5, fontWeight: 600, cursor: busy ? 'default' : 'pointer' }}>
                <UploadCloud size={16} /> {busy ? 'Uploading…' : 'Upload evidence file (PNG, PDF, CSV, JSON, DOCX, ZIP, A/V…)'}
                <input type="file" disabled={busy} style={{ display: 'none' }}
                  onChange={e => { const f = e.target.files?.[0]; if (f) uploadFile(f); e.currentTarget.value = '' }} />
              </label>
              <div style={{ display: 'flex', gap: 7 }}>
                <input value={evRef} onChange={e => setEvRef(e.target.value)} placeholder="…or record a reference hash (no file)"
                  style={{ flex: 1, padding: '8px 11px', background: T.bg2, border: `1px solid ${T.border}`, borderRadius: 8, color: T.text, fontSize: 11.5, outline: 'none', fontFamily: T.font }} />
                <select value={evType} onChange={e => setEvType(e.target.value)} style={selStyle}>
                  {EVIDENCE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
                <button onClick={addEvidence} disabled={busy} title="Add reference evidence" style={{ padding: '0 11px', borderRadius: 8, border: `1px solid ${T.border}`, background: T.raised, color: T.text, cursor: 'pointer', display: 'grid', placeItems: 'center' }}>
                  <Plus size={15} />
                </button>
              </div>
            </div>
          )}
        </Section>
      )}

      {tab === 'blockchain' && (() => {
        const bc = c.blockchain
        const anchored = !!bc?.anchored_at
        return (
          <Section icon={LinkIcon} title="Blockchain Evidence Anchor">
            <p style={{ fontSize: 12.5, color: T.text2, lineHeight: 1.6, margin: '0 0 14px' }}>
              Anchoring computes a SHA-256 over the graph, transactions, recovery report and evidence,
              then registers it on the BELS evidence ledger — producing an immutable, independently verifiable receipt.
            </p>
            {anchored ? (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '13px 15px', borderRadius: 11, marginBottom: 14,
                  background: bc!.verified ? 'rgba(0,200,120,0.08)' : T.warnDim, border: `1px solid ${bc!.verified ? '#00c87844' : T.warn + '44'}` }}>
                  {bc!.verified ? <ShieldCheck size={20} color={T.success} /> : <AlertTriangle size={20} color={T.warn} />}
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: bc!.verified ? T.success : T.warn }}>
                      {bc!.verified ? 'Blockchain Verified' : bc!.status}
                    </div>
                    <div style={{ fontSize: 11, color: T.text3 }}>Provider: {bc!.provider} · anchored {fmtDateTime(bc!.anchored_at!)}</div>
                  </div>
                </div>
                <KV k="Bundle hash" v={bc!.hash ?? '—'} mono />
                <KV k="Evidence ID" v={bc!.evidence_id ?? '—'} mono />
                <KV k="Transaction" v={bc!.txid ?? '—'} mono />
                {bc!.block_index != null && <KV k="Block" v={`#${bc!.block_index} · ${(bc!.block_hash ?? '').slice(0, 22)}…`} mono />}
                <div style={{ fontSize: 10, color: T.text3, letterSpacing: '.05em', margin: '14px 0 7px' }}>ANCHORED COMPONENTS</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {bc!.items.map(it => <span key={it.component} style={{ fontSize: 10.5, color: T.text2, background: T.bg2, border: `1px solid ${T.border}`, padding: '3px 9px', borderRadius: 999, fontFamily: T.mono }}>{it.component}</span>)}
                </div>
                {verifyMsg && <div style={{ marginTop: 12, fontSize: 12, color: verifyMsg.startsWith('Verified') ? T.success : T.danger }}>{verifyMsg}</div>}
                <div style={{ display: 'flex', gap: 10, marginTop: 16, flexWrap: 'wrap' }}>
                  <ActBtn onClick={verifyAnchor} disabled={busy} icon={RefreshCw} label="Re-verify on ledger" />
                  <ActBtn onClick={downloadReceipt} disabled={busy} icon={Download} label="Download receipt" />
                </div>
              </>
            ) : (
              <div style={{ textAlign: 'center', padding: '20px 0' }}>
                <LinkIcon size={26} color={T.text3} />
                <div style={{ fontSize: 12.5, color: T.text3, margin: '10px 0 16px' }}>This case has not been anchored to the blockchain yet.</div>
                {!closed && <div style={{ display: 'flex', justifyContent: 'center' }}><ActBtn onClick={anchor} disabled={busy} icon={LinkIcon} label={busy ? 'Anchoring…' : 'Push Evidence to Blockchain'} primary /></div>}
              </div>
            )}
          </Section>
        )
      })()}

      {tab === 'team' &&<TeamPanel c={c} caps={caps} me={investigator} busy={busy} run={(fn) => act(fn)} onErr={(m) => setErr(m)} />}
      {tab === 'comments' && <CommentsPanel c={c} caps={caps} me={investigator} busy={busy} run={(fn) => act(fn)} onErr={(m) => setErr(m)} />}
      {tab === 'tasks' && <TasksPanel c={c} caps={caps} me={investigator} busy={busy} run={(fn) => act(fn)} onErr={(m) => setErr(m)} />}

      {tab === 'timeline' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.4fr) minmax(0,1fr)', gap: 14, alignItems: 'start' }}>
          <Section icon={Clock} title="Activity Timeline">
            <div style={{ position: 'relative', paddingLeft: 22 }}>
              <div style={{ position: 'absolute', left: 5, top: 4, bottom: 4, width: 1, background: T.border }} />
              {c.timeline.map(ev => (
                <div key={ev.id} style={{ position: 'relative', paddingBottom: 16 }}>
                  <span style={{ position: 'absolute', left: -22, top: 3, width: 11, height: 11, borderRadius: '50%', background: T.panel, border: `2px solid ${T.gold}` }} />
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                    <span style={{ fontSize: 13, color: T.text, fontWeight: 600 }}>{ev.event}</span>
                    <span style={{ fontSize: 11, color: T.text3, whiteSpace: 'nowrap' }}>{fmtDateTime(ev.ts)}</span>
                  </div>
                  <div style={{ fontSize: 11.5, color: T.text3, marginTop: 2 }}>{ev.actor}{ev.detail ? ` · ${ev.detail}` : ''}</div>
                </div>
              ))}
            </div>
          </Section>
          <Section icon={ShieldAlert} title="Risk History">
            {c.risk_history.map((h, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '5px 0', fontSize: 12 }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: riskColorFromScore(h.score) }} />
                <span style={{ fontWeight: 600, color: riskColorFromScore(h.score), width: 26 }}>{h.score}</span>
                <span style={{ color: T.text3, flex: 1 }}>{h.reason}</span>
              </div>
            ))}
            {c.graph_snapshot.indicators.length > 0 && <>
              <div style={{ fontSize: 10.5, color: T.text3, letterSpacing: '.05em', margin: '12px 0 8px' }}>FRAUD INDICATORS</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {c.graph_snapshot.indicators.map(f => (
                  <span key={f} style={{ fontSize: 11, color: T.warn, background: T.warnDim, border: `1px solid ${T.warn}44`, padding: '2px 8px', borderRadius: 999 }}>{f}</span>
                ))}
              </div>
            </>}
          </Section>
        </div>
      )}

      {tab === 'notes' && (
        <Section icon={StickyNote} title={`Investigator Notes · ${c.notes.length}`}>
          {!closed && (
            <div style={{ display: 'flex', gap: 8, marginBottom: c.notes.length ? 14 : 0 }}>
              <input value={note} onChange={e => setNote(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') addNote() }}
                placeholder="Add a note… (e.g. Customer unreachable, escalated)"
                style={{ flex: 1, padding: '10px 12px', background: T.bg2, border: `1px solid ${T.border}`, borderRadius: 8, color: T.text, fontSize: 12.5, outline: 'none', fontFamily: T.font }} />
              <button onClick={addNote} disabled={busy || !note.trim()} style={{ padding: '0 14px', borderRadius: 8, border: 'none', background: T.gold, color: T.textOn, cursor: 'pointer', display: 'grid', placeItems: 'center' }}>
                <Send size={15} />
              </button>
            </div>
          )}
          {c.notes.map(n => (
            <div key={n.id} style={{ padding: '10px 0', borderTop: `1px solid ${T.border}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontSize: 12, color: T.gold, fontWeight: 600 }}>{n.author_name}</span>
                <span style={{ fontSize: 11, color: T.text3 }}>{fmtDateTime(n.ts)}</span>
              </div>
              <div style={{ fontSize: 13, color: T.text2, lineHeight: 1.5 }}>{n.text}</div>
            </div>
          ))}
          {!c.notes.length && <Empty text="No notes yet." />}
        </Section>
      )}

      {tab === 'reports' && (
        <Section icon={FileDown} title="Reports & Export">
          <p style={{ fontSize: 12.5, color: T.text2, lineHeight: 1.6, margin: '0 0 14px' }}>Compile this case into an evidence-grade report, download the complete case bundle, or export the raw record.</p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
            {(['pdf', 'docx', 'json'] as const).map(f => (
              <button key={f} onClick={() => generateReport(f)}
                style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '15px 16px', borderRadius: 11, cursor: 'pointer', textAlign: 'left', fontFamily: T.font,
                  background: f === 'pdf' ? T.gold : T.panel, border: `1px solid ${f === 'pdf' ? T.gold : T.border}`, color: f === 'pdf' ? T.textOn : T.text }}>
                <FileDown size={17} color={f === 'pdf' ? T.textOn : T.gold} />
                <span style={{ fontSize: 12.5, fontWeight: 600 }}>Export {f.toUpperCase()}</span>
              </button>
            ))}
            <button onClick={downloadBundle}
              style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '15px 16px', borderRadius: 11, cursor: 'pointer', textAlign: 'left', fontFamily: T.font, background: T.panel, border: `1px solid ${T.goldLine}`, color: T.text }}>
              <Box size={17} color={T.gold} />
              <span style={{ fontSize: 12.5, fontWeight: 600 }}>Case Bundle (ZIP)</span>
            </button>
          </div>
        </Section>
      )}

      {/* close modal */}
      {showClose && (
        <div onClick={() => setShowClose(false)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'grid', placeItems: 'center', zIndex: 100 }}>
          <div onClick={e => e.stopPropagation()} style={{ width: 420, background: T.panel, border: `1px solid ${T.border}`, borderRadius: 14, padding: 24, boxShadow: T.shadow }}>
            <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 16 }}>Close Case {c.case_id}</div>
            <div style={{ fontSize: 11.5, color: T.text2, marginBottom: 7 }}>Resolution</div>
            <select value={resolution} onChange={e => setResolution(e.target.value)} style={{ width: '100%', padding: '10px 12px', background: T.bg2, border: `1px solid ${T.border}`, borderRadius: 8, color: T.text, fontSize: 13, marginBottom: 14, fontFamily: T.font }}>
              {RESOLUTIONS.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
            <div style={{ fontSize: 11.5, color: T.text2, marginBottom: 7 }}>Resolution summary</div>
            <textarea value={closeSummary} onChange={e => setCloseSummary(e.target.value)} rows={3} placeholder="Outcome / justification…"
              style={{ width: '100%', padding: '10px 12px', background: T.bg2, border: `1px solid ${T.border}`, borderRadius: 8, color: T.text, fontSize: 13, fontFamily: T.font, resize: 'vertical', boxSizing: 'border-box' }} />
            <div style={{ display: 'flex', gap: 10, marginTop: 18, justifyContent: 'flex-end' }}>
              <button onClick={() => setShowClose(false)} style={{ padding: '9px 16px', borderRadius: 8, border: `1px solid ${T.border}`, background: 'none', color: T.text2, cursor: 'pointer', fontSize: 12.5, fontFamily: T.font }}>Cancel</button>
              <button onClick={doClose} disabled={busy} style={{ padding: '9px 16px', borderRadius: 8, border: 'none', background: T.danger, color: '#fff', cursor: 'pointer', fontSize: 12.5, fontWeight: 600, fontFamily: T.font }}>Confirm Close</button>
            </div>
          </div>
        </div>
      )}
    </Page>
  )
}

// ── pieces ───────────────────────────────────────────────────────────────────
const card: React.CSSProperties = { background: T.panel, border: `1px solid ${T.border}`, borderRadius: 12, padding: 16 }
const backBtn: React.CSSProperties = { display: 'inline-flex', alignItems: 'center', gap: 7, background: 'none', border: 'none', color: T.text2, fontSize: 12.5, cursor: 'pointer', padding: 0, fontFamily: T.font }

function Section({ icon: Icon, title, children, accent }: { icon: any; title: string; children: React.ReactNode; accent?: boolean }) {
  return (
    <div style={{ ...card, ...(accent ? { borderColor: T.goldLine, background: 'linear-gradient(180deg, rgba(198,162,83,0.05), transparent)' } : {}) }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 12, fontSize: 13.5, fontWeight: 600 }}>
        <Icon size={16} color={T.gold} /> {title}
      </div>
      {children}
    </div>
  )
}

function Tag({ text, color, solid }: { text: string; color: string; solid?: boolean }) {
  return <span style={{ fontSize: 10.5, fontWeight: 600, color: solid ? '#fff' : color, background: solid ? color : `${color}1c`, border: `1px solid ${solid ? color : color + '44'}`, padding: '3px 9px', borderRadius: 999, whiteSpace: 'nowrap' }}>{text}</span>
}

function Empty({ text }: { text: string }) { return <div style={{ padding: '12px 0', fontSize: 12, color: T.text3 }}>{text}</div> }

const selStyle: React.CSSProperties = { padding: '8px 9px', background: T.bg2, border: `1px solid ${T.border}`, borderRadius: 8, color: T.text, fontSize: 11.5, outline: 'none', fontFamily: T.font }

function RoleChip({ role }: { role: string }) {
  const color = ROLE_COLOR[role] ?? T.text3
  return <span style={{ fontSize: 10.5, fontWeight: 600, color, background: `${color}1c`, border: `1px solid ${color}44`, padding: '2px 8px', borderRadius: 999, width: 'fit-content', whiteSpace: 'nowrap' }}>{role}</span>
}

function Mini({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ padding: '10px 12px', borderRadius: 9, background: T.bg2, border: `1px solid ${T.border}` }}>
      <div style={{ fontSize: 9, color: T.text3, letterSpacing: '.05em', marginBottom: 5 }}>{label.toUpperCase()}</div>
      <div style={{ fontSize: 14, fontWeight: 700, color: color ?? T.text }}>{value}</div>
    </div>
  )
}

function KV({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '7px 0', borderTop: `1px solid ${T.border}` }}>
      <span style={{ fontSize: 11.5, color: T.text3 }}>{k}</span>
      <span style={{ fontSize: 11.5, color: T.text, fontFamily: mono ? T.mono : T.font, textAlign: 'right', wordBreak: 'break-all' }}>{v}</span>
    </div>
  )
}

const RISK_LEVEL_COLOR: Record<string, string> = {
  Safe: '#22c55e', Monitor: '#38bdf8', Suspicious: '#f59e0b', 'High Risk': '#fb7185', Critical: '#ff3366',
}

function CrossBankIndicators({ cb }: { cb: NonNullable<CaseDetail['cross_bank']> }) {
  const col = cb.risk >= 70 ? '#fb7185' : cb.risk >= 45 ? '#f59e0b' : '#38bdf8'
  const Stat = ({ label, value }: { label: string; value: string | number }) => (
    <div>
      <div style={{ fontSize: 18, fontWeight: 700, color: T.text, fontFamily: T.mono }}>{value}</div>
      <div style={{ fontSize: 10, color: T.text3, marginTop: 2 }}>{label}</div>
    </div>
  )
  return (
    <div style={{ ...card, marginTop: 14, borderColor: `${col}55`, background: `linear-gradient(180deg, ${col}0d, transparent)` }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: '.04em', color: T.text }}>CROSS-BANK INDICATORS</span>
        <span style={{ fontSize: 11, padding: '2px 9px', borderRadius: 12, fontWeight: 700, color: col, background: `${col}18`, border: `1px solid ${col}40` }}>
          {cb.band} · {cb.risk}/100
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(96px, 1fr))', gap: 14 }}>
        <Stat label="Banks involved" value={cb.linked_banks} />
        <Stat label="Linked accounts" value={cb.linked_accounts} />
        <Stat label="Shared devices" value={cb.shared_devices} />
        <Stat label="Shared phones" value={cb.shared_phones} />
        <Stat label="Known entities" value={cb.known_suspicious_entities} />
      </div>
      {cb.banks_involved?.length > 0 && (
        <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {cb.banks_involved.map(b => (
            <span key={b} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 4, color: T.text2, background: T.raised, border: `1px solid ${T.border}` }}>{b}</span>
          ))}
        </div>
      )}
      {cb.patterns?.length > 0 && (
        <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {cb.patterns.map(p => (
            <span key={p} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 4, color: col, background: `${col}12`, border: `1px solid ${col}30` }}>
              {p.replace(/_/g, ' ')}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function RiskSummary({ a }: { a: NonNullable<CaseDetail['risk_assessment']> }) {
  const col = RISK_LEVEL_COLOR[a.level] ?? T.text2
  const maxPts = Math.max(1, ...a.factors.map(f => f.points))
  return (
    <div style={{ ...card, marginTop: 14, borderColor: `${col}55`, background: `linear-gradient(180deg, ${col}0d, transparent)` }}>
      <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', alignItems: 'center' }}>
        <RiskDial score={a.score} color={col} conf={a.confidence / 100} />
        <div style={{ minWidth: 200, flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 4 }}>
            <span style={{ fontSize: 9.5, color: T.text3, letterSpacing: '.1em', fontWeight: 700 }}>RISK ASSESSMENT</span>
            <Tag text={a.level} color={col} solid />
            {a.suppressed && <Tag text="SUPPRESSED" color={T.text3} />}
          </div>
          <div style={{ fontSize: 21, fontWeight: 800, color: col, lineHeight: 1 }}>{a.score}<span style={{ fontSize: 12, color: T.text3, fontWeight: 600 }}> / 100</span></div>
          <div style={{ fontSize: 11.5, color: T.text2, marginTop: 6 }}>Confidence {a.confidence}% · threshold for case ≥ {a.investigation_threshold}</div>
          <div style={{ fontSize: 12, color: T.text, marginTop: 8, fontWeight: 600 }}>{a.action}</div>
        </div>
      </div>

      {/* explainable factor breakdown */}
      <div style={{ marginTop: 14 }}>
        <div style={{ fontSize: 9.5, color: T.text3, letterSpacing: '.08em', marginBottom: 8 }}>WHY THIS SCORE — CONTRIBUTING FACTORS</div>
        {a.factors.length === 0 && <div style={{ fontSize: 12, color: T.text3 }}>No risk indicators present.</div>}
        {a.factors.map(f => (
          <div key={f.key} style={{ display: 'grid', gridTemplateColumns: '150px 1fr 42px', gap: 10, alignItems: 'center', padding: '4px 0' }}>
            <span style={{ fontSize: 11.5, color: T.text2 }}>{f.label}</span>
            <span style={{ position: 'relative', height: 7, background: T.bg2, borderRadius: 4, overflow: 'hidden' }}>
              <span style={{ position: 'absolute', inset: 0, width: `${(f.points / maxPts) * 100}%`, background: col, opacity: 0.7, borderRadius: 4 }} />
            </span>
            <span style={{ fontSize: 11.5, fontWeight: 700, color: col, textAlign: 'right' }}>+{f.points}</span>
          </div>
        ))}
        {a.factors.length > 0 && (
          <div style={{ fontSize: 10.5, color: T.text3, marginTop: 8, lineHeight: 1.5 }}>
            {a.factors.map(f => f.detail).filter(Boolean).slice(0, 4).join(' · ')}
          </div>
        )}
        {a.suppressed && a.suppression_reason && (
          <div style={{ fontSize: 11, color: T.info, marginTop: 8, lineHeight: 1.5 }}>ℹ {a.suppression_reason}</div>
        )}
      </div>
    </div>
  )
}

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function AnswerCell({ label, value, color, sub }: { label: string; value: string; color: string; sub?: string }) {
  return (
    <div>
      <div style={{ fontSize: 9.5, color: T.text3, letterSpacing: '.06em', marginBottom: 7 }}>{label.toUpperCase()}</div>
      <div style={{ fontSize: 19, fontWeight: 700, color, lineHeight: 1.15 }}>{value}</div>
      {sub && <div style={{ fontSize: 10.5, color: T.text3, marginTop: 5 }}>{sub}</div>}
    </div>
  )
}

// fallback "what next" when no recovery analysis exists for the case
function nextAction(c: CaseDetail): string {
  if (!c.assigned_to) return 'Assign this case to an investigator'
  if (!c.evidence.length) return 'Collect and anchor first evidence'
  if (c.risk_score >= 70) return 'Escalate — freeze beneficiary accounts'
  return 'Review transactions and progress the investigation'
}

function ActBtn({ onClick, disabled, icon: Icon, label, primary, danger }: { onClick: () => void; disabled?: boolean; icon: any; label: string; primary?: boolean; danger?: boolean }) {
  const bg = primary ? T.gold : danger ? T.dangerDim : T.raised
  const col = primary ? T.textOn : danger ? T.danger : T.text
  return (
    <button onClick={onClick} disabled={disabled} style={{
      display: 'flex', alignItems: 'center', gap: 8, padding: '9px 14px', borderRadius: 9,
      border: `1px solid ${primary ? T.gold : danger ? T.danger + '55' : T.border}`, background: bg, color: col,
      fontSize: 12.5, fontWeight: 600, cursor: disabled ? 'default' : 'pointer', fontFamily: T.font, whiteSpace: 'nowrap', minWidth: 160, justifyContent: 'center',
    }}>
      <Icon size={15} /> {label}
    </button>
  )
}

function RiskDial({ score, color, conf, small }: { score: number; color: string; conf: number; small?: boolean }) {
  const size = small ? 52 : 66, r = small ? 21 : 27, cc = 2 * Math.PI * r, off = cc * (1 - score / 100)
  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={T.border} strokeWidth={5} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={5} strokeLinecap="round" strokeDasharray={cc} strokeDashoffset={off} />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', lineHeight: 1 }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: small ? 15 : 18, fontWeight: 700, color }}>{score}</div>
          <div style={{ fontSize: 7, color: T.text3 }}>{Math.round(conf * 100)}%</div>
        </div>
      </div>
    </div>
  )
}

function GraphSnapshot({ snap, risk }: { snap: CaseDetail['graph_snapshot']; risk: string }) {
  const linked = snap.nodes.filter(n => n.role !== 'primary').slice(0, 6)
  const cx = 130, cy = 90, R = 62
  return (
    <svg viewBox="0 0 260 180" style={{ width: '100%', height: 170, background: T.bg2, borderRadius: 9, border: `1px solid ${T.border}` }}>
      {linked.map((_, i) => {
        const a = (i / linked.length) * Math.PI * 2 - Math.PI / 2
        return <line key={i} x1={cx} y1={cy} x2={cx + Math.cos(a) * R} y2={cy + Math.sin(a) * R} stroke={T.border} strokeWidth={1} />
      })}
      {linked.map((n, i) => {
        const a = (i / linked.length) * Math.PI * 2 - Math.PI / 2
        const x = cx + Math.cos(a) * R, y = cy + Math.sin(a) * R
        return (
          <g key={n.id}>
            <circle cx={x} cy={y} r={6} fill={T.raised} stroke={riskColorFromScore(n.risk)} strokeWidth={1.4} />
            <text x={x} y={y + 15} fontSize={6} fill={T.text3} textAnchor="middle" fontFamily="monospace">{n.id.slice(-6)}</text>
          </g>
        )
      })}
      <circle cx={cx} cy={cy} r={11} fill={risk} opacity={0.18} />
      <circle cx={cx} cy={cy} r={8} fill={risk} />
    </svg>
  )
}

// ── report helpers ────────────────────────────────────────────────────────────
function downloadBlob(content: string, filename: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function reportHtml(c: CaseDetail, investigator: string): string {
  const row = (k: string, v: string) => `<tr><td style="color:#666;padding:3px 12px 3px 0">${k}</td><td>${v}</td></tr>`
  const list = (items: string[]) => items.length ? `<ul>${items.map(i => `<li>${i}</li>`).join('')}</ul>` : '<p style="color:#888">None.</p>'
  const dt = (ts: number) => new Date(ts * 1000).toLocaleString('en-IN')
  return `<!doctype html><html><head><meta charset="utf-8"><title>${c.case_id} — Investigation Report</title>
  <style>body{font-family:Georgia,serif;max-width:820px;margin:32px auto;color:#1a1a1a;line-height:1.5}
  h1{font-size:22px;margin:0} h2{font-size:15px;border-bottom:1px solid #ccc;padding-bottom:4px;margin-top:26px}
  .muted{color:#666;font-size:12px} table{font-size:13px;border-collapse:collapse} li{margin:3px 0}</style></head><body>
  <div class="muted">TGIE · Transaction Graph Intelligence Engine — CONFIDENTIAL</div>
  <h1>Investigation Report — ${c.case_id}</h1>
  <div class="muted">${c.title} · Generated by ${investigator} on ${new Date().toLocaleString('en-IN')}</div>
  <h2>Executive Summary</h2><p>${c.ub_analysis}</p>
  <h2>Case Overview</h2><table>
  ${row('Case ID', c.case_id)}${row('Category', c.category)}${row('Status', c.status)}${row('Priority', c.priority)}
  ${row('Risk Score', String(c.risk_score) + '/100')}${row('Fraud Confidence', Math.round(c.fraud_confidence * 100) + '%')}
  ${row('Assigned', c.assigned_name || '—')}${row('Created', dt(c.created_at))}</table>
  <h2>Detection Reason</h2><p>${c.detection_reason}</p>
  <h2>Accounts Involved (${c.accounts.length})</h2>${list(c.accounts)}
  <h2>Transactions (${c.transactions.length})</h2>${list(c.transactions.map(t => `${t.txn_id} — ₹${t.amount.toLocaleString('en-IN')} (${t.from_account} → ${t.to_account}) — ${t.reason}`))}
  <h2>Risk Analysis</h2>${list(c.graph_snapshot.indicators)}
  <h2>Evidence Summary (${c.evidence.length})</h2>${list(c.evidence.map(e => `${e.type} — ${e.hash} ${e.anchored ? '(anchored)' : '(pending)'}`))}
  <h2>Investigator Notes (${c.notes.length})</h2>${list(c.notes.map(n => `[${dt(n.ts)}] ${n.author_name}: ${n.text}`))}
  <h2>Recommendations</h2><p>Freeze high-exposure accounts, complete KYC/device evidence collection, anchor the graph snapshot to the evidence ledger, and escalate to a supervisor where fraud confidence exceeds 90%.</p>
  </body></html>`
}
