import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft, Network, ShieldAlert, FileText, Link2, Activity,
  AlertTriangle, FolderOpen, ArrowDownLeft, ArrowUpRight, CheckCircle2,
} from 'lucide-react'
import { Page } from '../components/nav/AppLayout'
import { authApi, type AccountDetail } from '../auth/api'
import { caseApi, priorityColor, caseStatusColor, type CaseSummary } from '../cases/api'
import { T, riskColorFromScore, statusColor, fmtINR } from '../theme'

export default function AccountView() {
  const { accountNumber } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState<AccountDetail | null>(null)
  const [cases, setCases] = useState<CaseSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    let alive = true
    setLoading(true); setErr(null); setData(null); setCases([])
    authApi.account(accountNumber!)
      .then(d => { if (alive) { setData(d); caseApi.byAccount(d.account_number).then(r => alive && setCases(r.cases)).catch(() => {}) } })
      .catch(e => alive && setErr(e.message))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [accountNumber])

  async function openCase() {
    if (!data) return
    setCreating(true)
    try {
      const created = await caseApi.create({ account_number: data.account_number })
      navigate(`/investigations/${created.case_id}`)
    } catch { setCreating(false) }
  }

  if (loading) return <Page><div style={{ color: T.text3, fontSize: 13 }}>Loading account dossier…</div></Page>
  if (err || !data) return (
    <Page>
      <button onClick={() => navigate(-1)} style={backBtn}><ArrowLeft size={15} /> Back</button>
      <div style={{ marginTop: 30, color: T.danger, fontSize: 14 }}>{err ?? 'Account not found'}</div>
    </Page>
  )

  const risk = riskColorFromScore(data.risk_score)

  return (
    <Page>
      <button onClick={() => navigate(-1)} style={backBtn}><ArrowLeft size={15} /> Back to results</button>

      {/* ── header ─────────────────────────────────────────────── */}
      <div style={{ ...card, marginTop: 14, padding: 0, overflow: 'hidden' }}>
        <div style={{ height: 3, background: risk }} />
        <div style={{ padding: '20px 22px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <h1 style={{ fontSize: 23, fontWeight: 700, margin: 0, fontFamily: T.mono }}>{data.account_number}</h1>
              <Pill text={data.status} color={statusColor(data.status)} />
              <Pill text={data.investigation_status} color={statusColor(data.investigation_status)} />
            </div>
            <div style={{ fontSize: 15, color: T.text, marginTop: 10, fontWeight: 600 }}>{data.customer_name}</div>
            <div style={{ fontSize: 12.5, color: T.text3, marginTop: 4 }}>
              {data.customer_id} · {data.bank} · IFSC {data.ifsc} · Opened {data.opened_on}
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
            <RiskDial score={data.risk_score} color={risk} band={data.risk_band} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <button onClick={openCase} disabled={creating} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 9, padding: '11px 18px', borderRadius: 10, border: 'none',
                background: `linear-gradient(180deg, ${T.goldHi}, ${T.gold})`, color: T.textOn, fontWeight: 700,
                fontSize: 13, cursor: creating ? 'wait' : 'pointer', fontFamily: T.font, minWidth: 158,
              }}>
                <FolderOpen size={16} /> {creating ? 'Opening…' : 'Open Case'}
              </button>
              <button onClick={() => navigate('/graph')} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 9, padding: '11px 18px', borderRadius: 10,
                border: `1px solid ${T.border}`, background: T.raised, color: T.text, fontWeight: 600,
                fontSize: 13, cursor: 'pointer', fontFamily: T.font, minWidth: 158,
              }}>
                <Network size={16} /> Launch Graph
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── stat strip ─────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginTop: 14 }}>
        <Stat label="Transactions" value={data.transaction_count.toLocaleString('en-IN')} />
        <Stat label="Linked Accounts" value={data.linked_count} />
        <Stat label="Current Balance" value={fmtINR(data.balance)} />
        <Stat label="Risk Band" value={data.risk_band} tone={risk} />
      </div>

      {/* flags */}
      {data.flags.length > 0 && (
        <div style={{ ...card, marginTop: 14, display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <AlertTriangle size={16} color={T.warn} />
          <span style={{ fontSize: 12, color: T.text2, marginRight: 4 }}>Risk indicators:</span>
          {data.flags.map(f => (
            <span key={f} style={{ fontSize: 11.5, color: T.warn, background: T.warnDim, border: `1px solid ${T.warn}44`, padding: '3px 10px', borderRadius: 999 }}>{f}</span>
          ))}
        </div>
      )}

      {/* linked cases */}
      {cases.length > 0 && (
        <div style={{ ...card, marginTop: 14, padding: 0, overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '13px 16px', borderBottom: `1px solid ${T.border}`, fontSize: 13.5, fontWeight: 600 }}>
            <FolderOpen size={16} color={T.gold} /> Linked Cases · {cases.length}
          </div>
          {cases.map(c => (
            <button key={c.case_id} onClick={() => navigate(`/investigations/${c.case_id}`)} style={{
              width: '100%', display: 'grid', gridTemplateColumns: '130px 1fr 110px 110px', gap: 10, alignItems: 'center',
              padding: '11px 16px', background: 'none', border: 'none', borderTop: `1px solid ${T.border}`, cursor: 'pointer', textAlign: 'left', fontFamily: T.font,
            }}
              onMouseEnter={e => (e.currentTarget.style.background = T.raised)}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            >
              <span style={{ fontSize: 12, color: T.gold, fontFamily: T.mono }}>{c.case_id}</span>
              <span style={{ fontSize: 12.5, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.title}</span>
              <Pill text={c.priority} color={priorityColor(c.priority)} />
              <Pill text={c.status} color={caseStatusColor(c.status)} />
            </button>
          ))}
        </div>
      )}

      {/* ── two-column body ────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: 14, marginTop: 14, alignItems: 'start' }}>
        {/* recent activity */}
        <Section icon={Activity} title="Recent Activity">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', fontSize: 10.5, color: T.text3, letterSpacing: '.05em', padding: '0 4px 8px' }}>
            <span>TRANSACTION</span><span style={{ textAlign: 'right' }}>AMOUNT</span><span style={{ textAlign: 'right', paddingLeft: 16 }}>WHEN</span>
          </div>
          {data.recent_activity.map(a => (
            <div key={a.txn_id} style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', alignItems: 'center', padding: '9px 4px', borderTop: `1px solid ${T.border}` }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                <span style={{ width: 26, height: 26, borderRadius: 7, display: 'grid', placeItems: 'center', background: a.direction === 'credit' ? T.successDim : T.dangerDim, flexShrink: 0 }}>
                  {a.direction === 'credit' ? <ArrowDownLeft size={13} color={T.success} /> : <ArrowUpRight size={13} color={T.danger} />}
                </span>
                <span style={{ minWidth: 0 }}>
                  <span style={{ display: 'block', fontSize: 12.5, color: T.text }}>{a.label} <span style={{ color: T.text3 }}>· {a.rail}</span></span>
                  <span style={{ display: 'block', fontSize: 10.5, color: T.text3, fontFamily: T.mono }}>{a.txn_id} → {a.counterparty}</span>
                </span>
              </span>
              <span style={{ textAlign: 'right', fontSize: 12.5, fontWeight: 600, color: a.direction === 'credit' ? T.success : T.text, fontVariantNumeric: 'tabular-nums' }}>
                {a.direction === 'credit' ? '+' : '−'}{fmtINR(a.amount)}
              </span>
              <span style={{ textAlign: 'right', paddingLeft: 16, fontSize: 11, color: T.text3, whiteSpace: 'nowrap' }}>{a.hours_ago}h ago</span>
            </div>
          ))}
        </Section>

        <div style={{ display: 'grid', gap: 14 }}>
          {/* graph preview */}
          <Section icon={Network} title="Network Preview">
            <GraphPreview center={data.account_number} linked={data.linked_accounts} risk={risk} />
            <button onClick={() => navigate('/graph')} style={{
              width: '100%', marginTop: 12, padding: '9px 0', borderRadius: 8, border: `1px solid ${T.goldLine}`,
              background: T.goldDim, color: T.gold, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: T.font,
            }}>Open in Graph Engine →</button>
          </Section>

          {/* linked accounts */}
          <Section icon={Link2} title={`Linked Accounts · ${data.linked_count}`}>
            {data.linked_account_cards.map(l => (
              <Link key={l.account_number} to={`/accounts/${l.account_number}`} style={{ textDecoration: 'none' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 4px', borderTop: `1px solid ${T.border}` }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: riskColorFromScore(l.risk_score) }} />
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ display: 'block', fontSize: 12, color: T.text, fontFamily: T.mono }}>{l.account_number}</span>
                    <span style={{ display: 'block', fontSize: 10.5, color: T.text3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.customer_name}</span>
                  </span>
                  <span style={{ fontSize: 12, fontWeight: 600, color: riskColorFromScore(l.risk_score) }}>{l.risk_score}</span>
                </div>
              </Link>
            ))}
          </Section>
        </div>
      </div>

      {/* ── cases & evidence ───────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginTop: 14 }}>
        <Section icon={FolderOpen} title="Linked Cases">
          {data.cases.length ? data.cases.map(c => (
            <div key={c.case_id} style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '10px 4px', borderTop: `1px solid ${T.border}` }}>
              <ShieldAlert size={15} color={T.warn} />
              <span style={{ flex: 1 }}>
                <span style={{ display: 'block', fontSize: 12.5, color: T.text }}>{c.title}</span>
                <span style={{ fontSize: 10.5, color: T.text3, fontFamily: T.mono }}>{c.case_id} · opened {c.opened}</span>
              </span>
            </div>
          )) : <Empty text="No cases linked to this account." />}
        </Section>

        <Section icon={FileText} title="Evidence Records">
          {data.evidence.length ? data.evidence.map(ev => (
            <div key={ev.evidence_id} style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '10px 4px', borderTop: `1px solid ${T.border}` }}>
              <FileText size={15} color={T.info} />
              <span style={{ flex: 1 }}>
                <span style={{ display: 'block', fontSize: 12.5, color: T.text }}>{ev.type}</span>
                <span style={{ fontSize: 10.5, color: T.text3, fontFamily: T.mono }}>{ev.evidence_id}</span>
              </span>
              {ev.anchored
                ? <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 10.5, color: T.success }}><CheckCircle2 size={12} /> Anchored</span>
                : <span style={{ fontSize: 10.5, color: T.text3 }}>Pending</span>}
            </div>
          )) : <Empty text="No evidence on record." />}
        </Section>
      </div>
    </Page>
  )
}

// ── pieces ───────────────────────────────────────────────────────────────────
const card: React.CSSProperties = { background: T.panel, border: `1px solid ${T.border}`, borderRadius: 12, padding: 16 }
const backBtn: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 7, background: 'none', border: 'none',
  color: T.text2, fontSize: 12.5, cursor: 'pointer', padding: 0, fontFamily: T.font,
}

function Section({ icon: Icon, title, children }: { icon: any; title: string; children: React.ReactNode }) {
  return (
    <div style={card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 12, fontSize: 13.5, fontWeight: 600 }}>
        <Icon size={16} color={T.gold} /> {title}
      </div>
      {children}
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: string | number; tone?: string }) {
  return (
    <div style={card}>
      <div style={{ fontSize: 11, color: T.text3, letterSpacing: '.04em' }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, marginTop: 6, color: tone ?? T.text, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
    </div>
  )
}

function Pill({ text, color }: { text: string; color: string }) {
  return <span style={{ fontSize: 11, color, background: `${color}1c`, border: `1px solid ${color}44`, padding: '3px 10px', borderRadius: 999, fontWeight: 500 }}>{text}</span>
}

function Empty({ text }: { text: string }) {
  return <div style={{ padding: '14px 4px', fontSize: 12, color: T.text3 }}>{text}</div>
}

function RiskDial({ score, color, band }: { score: number; color: string; band: string }) {
  const r = 26, c = 2 * Math.PI * r, off = c * (1 - score / 100)
  return (
    <div style={{ position: 'relative', width: 64, height: 64 }}>
      <svg width={64} height={64} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={32} cy={32} r={r} fill="none" stroke={T.border} strokeWidth={5} />
        <circle cx={32} cy={32} r={r} fill="none" stroke={color} strokeWidth={5} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={off} />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', lineHeight: 1 }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 17, fontWeight: 700, color }}>{score}</div>
          <div style={{ fontSize: 7.5, color: T.text3, letterSpacing: '.08em' }}>{band.toUpperCase()}</div>
        </div>
      </div>
    </div>
  )
}

// Simple radial network sketch (center node + linked nodes) — a static preview,
// the live force graph lives in the Graph Engine.
function GraphPreview({ center, linked, risk }: { center: string; linked: string[]; risk: string }) {
  const nodes = linked.slice(0, 6)
  const cx = 130, cy = 90, R = 62
  return (
    <svg viewBox="0 0 260 180" style={{ width: '100%', height: 170, background: T.bg2, borderRadius: 9, border: `1px solid ${T.border}` }}>
      {nodes.map((_, i) => {
        const a = (i / nodes.length) * Math.PI * 2 - Math.PI / 2
        const x = cx + Math.cos(a) * R, y = cy + Math.sin(a) * R
        return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke={T.border} strokeWidth={1} />
      })}
      {nodes.map((n, i) => {
        const a = (i / nodes.length) * Math.PI * 2 - Math.PI / 2
        const x = cx + Math.cos(a) * R, y = cy + Math.sin(a) * R
        return (
          <g key={n}>
            <circle cx={x} cy={y} r={6} fill={T.raised} stroke={T.borderHi} strokeWidth={1} />
            <text x={x} y={y + 16} fontSize={6} fill={T.text3} textAnchor="middle" fontFamily="monospace">{n.slice(-6)}</text>
          </g>
        )
      })}
      <circle cx={cx} cy={cy} r={11} fill={risk} opacity={0.18} />
      <circle cx={cx} cy={cy} r={8} fill={risk} />
      <text x={cx} y={cy + 22} fontSize={6.5} fill={T.text2} textAnchor="middle" fontFamily="monospace">{center.slice(-6)}</text>
    </svg>
  )
}
