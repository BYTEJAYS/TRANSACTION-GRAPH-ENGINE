import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShieldCheck, FolderOpen, AlertOctagon, UserCheck, CheckCircle2, ArrowUpRight, FileSearch, Search } from 'lucide-react'
import { Page } from '../components/nav/AppLayout'
import { caseApi, priorityColor, caseStatusColor, type CaseSummary, type CaseStats, type SearchHit } from '../cases/api'
import { sessionStore } from '../store/session'
import { T, riskColorFromScore } from '../theme'

type Tab = { key: string; label: string; scope?: string }
const TABS: Tab[] = [
  { key: 'all', label: 'All Cases' },
  { key: 'open', label: 'Open', scope: 'open' },
  { key: 'available', label: 'Available', scope: 'available' },
  { key: 'assigned', label: 'Assigned to Me', scope: 'assigned' },
  { key: 'closed', label: 'Closed', scope: 'closed' },
]

function fmtDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

export default function InvestigationsPage() {
  const navigate = useNavigate()
  const [tab, setTab] = useState(() => {
    const saved = sessionStore.get().cases.filters.tab as string
    return TABS.some(t => t.key === saved) ? saved : 'all'   // fall back if a removed tab (e.g. 'critical') was persisted
  })
  const [cases, setCases] = useState<CaseSummary[]>([])
  const [stats, setStats] = useState<CaseStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<SearchHit[]>([])
  const searching = query.trim().length >= 2

  // global search — case id / account / txn / evidence / hash / investigator / pattern / status
  useEffect(() => {
    if (!searching) { setHits([]); return }
    const id = setTimeout(() => { caseApi.search(query.trim()).then(r => setHits(r.results)).catch(() => {}) }, 220)
    return () => clearTimeout(id)
  }, [query, searching])

  // persist the active filter tab across navigation / refresh
  useEffect(() => { sessionStore.patch('cases', { filters: { ...sessionStore.get().cases.filters, tab } }) }, [tab])

  useEffect(() => { caseApi.stats().then(setStats).catch(() => {}) }, [])
  useEffect(() => {
    let alive = true
    setLoading(true)
    const scope = TABS.find(t => t.key === tab)?.scope
    caseApi.list(scope).then(r => { if (alive) setCases(r.cases) }).catch(() => {}).finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [tab])

  // Live refresh so cases auto-registered by Blue Team detection appear without a
  // manual reload — on tab focus / visibility and a gentle 12s poll.
  useEffect(() => {
    const refresh = () => {
      if (document.hidden) return
      const scope = TABS.find(t => t.key === tab)?.scope
      caseApi.list(scope).then(r => setCases(r.cases)).catch(() => {})
      caseApi.stats().then(setStats).catch(() => {})
    }
    const iv = setInterval(refresh, 12000)
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => { clearInterval(iv); window.removeEventListener('focus', refresh); document.removeEventListener('visibilitychange', refresh) }
  }, [tab])

  const kpis = stats ? [
    { icon: FolderOpen, label: 'Open Cases', value: stats.open, tone: T.warn },
    { icon: AlertOctagon, label: 'Critical', value: stats.critical, tone: T.danger },
    { icon: UserCheck, label: 'Assigned to Me', value: stats.assigned_to_me, tone: T.info },
    { icon: CheckCircle2, label: 'Resolved', value: stats.resolved, tone: T.success },
  ] : []

  const rows: (CaseSummary | SearchHit)[] = searching ? hits : cases
  const showLoading = loading && !searching

  return (
    <Page>
      <div style={{ display: 'flex', alignItems: 'center', gap: 11, marginBottom: 6 }}>
        <ShieldCheck size={19} color={T.gold} />
        <h1 style={{ fontSize: 19, fontWeight: 700, margin: 0 }}>Investigations</h1>
      </div>
      <p style={{ color: T.text2, fontSize: 13, marginBottom: 20 }}>
        Fraud cases auto-generated from detections, plus manually opened investigations. The case is the
        central object for evidence, risk, blockchain records and resolution.
      </p>

      {/* global search */}
      <div style={{ position: 'relative', marginBottom: 20 }}>
        <Search size={15} color={T.text3} style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)' }} />
        <input value={query} onChange={e => setQuery(e.target.value)}
          placeholder="Search any case — Case ID, account, transaction, evidence, blockchain hash, investigator, pattern, status…"
          style={{ width: '100%', boxSizing: 'border-box', padding: '12px 14px 12px 40px', background: T.panel, border: `1px solid ${query ? T.goldLine : T.border}`, borderRadius: 11, color: T.text, fontSize: 13, outline: 'none', fontFamily: T.font }} />
      </div>

      {/* KPI tiles */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 22 }}>
        {kpis.map(k => (
          <div key={k.label} style={card}>
            <span style={{ width: 34, height: 34, borderRadius: 9, display: 'grid', placeItems: 'center', background: `${k.tone}1f` }}>
              <k.icon size={17} color={k.tone} />
            </span>
            <div style={{ fontSize: 28, fontWeight: 700, marginTop: 12, color: T.text, fontVariantNumeric: 'tabular-nums' }}>{k.value}</div>
            <div style={{ fontSize: 12, color: T.text2, marginTop: 2 }}>{k.label}</div>
          </div>
        ))}
      </div>

      {/* tabs (hidden while searching) */}
      {searching ? (
        <div style={{ fontSize: 12.5, color: T.text2, marginBottom: 14 }}>
          {hits.length} result{hits.length === 1 ? '' : 's'} for “{query.trim()}”
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 4, marginBottom: 14, borderBottom: `1px solid ${T.border}` }}>
          {TABS.map(t => {
            const on = tab === t.key
            return (
              <button key={t.key} onClick={() => setTab(t.key)} style={{
                padding: '9px 14px', fontSize: 12.5, fontWeight: on ? 600 : 500, cursor: 'pointer',
                background: 'none', border: 'none', color: on ? T.text : T.text2,
                borderBottom: `2px solid ${on ? T.gold : 'transparent'}`, marginBottom: -1, fontFamily: T.font,
              }}>{t.label}</button>
            )
          })}
        </div>
      )}

      {/* table */}
      <div style={{ ...card, padding: 0, overflow: 'hidden' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '130px 1fr 110px 110px 150px 90px 70px', gap: 10, padding: '11px 18px', fontSize: 10.5, color: T.text3, letterSpacing: '.05em', borderBottom: `1px solid ${T.border}` }}>
          <span>CASE ID</span><span>TITLE</span><span>PRIORITY</span><span>STATUS</span><span>ASSIGNED</span><span>UPDATED</span><span style={{ textAlign: 'right' }}>RISK</span>
        </div>
        {showLoading && <div style={{ padding: 28, color: T.text3, fontSize: 13 }}>Loading cases…</div>}
        {!showLoading && rows.length === 0 && (
          <div style={{ padding: '50px 20px', textAlign: 'center', color: T.text3 }}>
            <FileSearch size={28} style={{ opacity: 0.5, marginBottom: 12 }} />
            <div style={{ fontSize: 13.5, color: T.text2 }}>{searching ? 'No cases match your search' : 'No cases in this view'}</div>
          </div>
        )}
        {rows.map(c => (
          <button key={c.case_id} onClick={() => navigate(`/investigations/${c.case_id}`)} style={{
            width: '100%', display: 'grid', gridTemplateColumns: '130px 1fr 110px 110px 150px 90px 70px', gap: 10,
            alignItems: 'center', padding: '13px 18px', background: 'none', border: 'none',
            borderBottom: `1px solid ${T.border}`, cursor: 'pointer', textAlign: 'left', fontFamily: T.font,
          }}
            onMouseEnter={e => (e.currentTarget.style.background = T.raised)}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >
            <span style={{ fontSize: 12, color: T.gold, fontFamily: T.mono }}>{c.case_id}</span>
            <span style={{ minWidth: 0 }}>
              <span style={{ display: 'block', fontSize: 13, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.title}</span>
              <span style={{ fontSize: 11, color: T.text3 }}>
                {c.category} · {c.account_count} accounts
                {'matched_on' in c && c.matched_on && <span style={{ color: T.gold }}> · matched on {c.matched_on}</span>}
              </span>
            </span>
            <Tag text={c.priority} color={priorityColor(c.priority)} solid />
            <Tag text={c.status} color={caseStatusColor(c.status)} />
            <span style={{ fontSize: 12, color: c.assigned_name ? T.text2 : T.text3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {c.assigned_name || 'Unassigned'}
            </span>
            <span style={{ fontSize: 11.5, color: T.text3 }}>{fmtDate(c.updated_at)}</span>
            <span style={{ textAlign: 'right', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 6 }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: riskColorFromScore(c.risk_score) }}>{c.risk_score}</span>
              <ArrowUpRight size={13} color={T.text3} />
            </span>
          </button>
        ))}
      </div>
    </Page>
  )
}

const card: React.CSSProperties = { background: T.panel, border: `1px solid ${T.border}`, borderRadius: 12, padding: 16 }

function Tag({ text, color, solid }: { text: string; color: string; solid?: boolean }) {
  return (
    <span style={{
      justifySelf: 'start', fontSize: 10.5, fontWeight: 600, color: solid ? '#fff' : color,
      background: solid ? color : `${color}1c`, border: `1px solid ${solid ? color : color + '44'}`,
      padding: '3px 9px', borderRadius: 999, whiteSpace: 'nowrap',
    }}>{text}</span>
  )
}
