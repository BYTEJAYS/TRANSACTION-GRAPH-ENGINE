import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate, Link } from 'react-router-dom'
import { Search, ArrowUpRight, SearchX } from 'lucide-react'
import { Page } from '../components/nav/AppLayout'
import { authApi, type AccountSummary } from '../auth/api'
import { sessionStore } from '../store/session'
import { T, riskColorFromScore, statusColor } from '../theme'

type SearchHit = { results: AccountSummary[]; resolved: string | null }

export default function SearchResults() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const q = params.get('q') ?? ''
  const hit0 = (() => { const s = sessionStore.get().search; return s.query === q ? (s.results as SearchHit | null) : null })()
  const [results, setResults] = useState<AccountSummary[]>(hit0?.results ?? [])
  const [resolved, setResolved] = useState<string | null>(hit0?.resolved ?? null)
  const [loading, setLoading] = useState(!hit0)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    // reuse the cached search for this query — navigating away never re-searches
    const s = sessionStore.get().search
    if (s.query === q && s.results) {
      const hit = s.results as SearchHit
      setResults(hit.results); setResolved(hit.resolved); setLoading(false); setErr(null)
      return () => { alive = false }
    }
    setLoading(true); setErr(null)
    authApi.searchAccounts(q)
      .then(r => {
        if (!alive) return
        setResults(r.results); setResolved(r.resolved_account)
        sessionStore.set({ search: { query: q, results: { results: r.results, resolved: r.resolved_account } } })
        // Exact identifier match → jump straight to the account view
        if (r.resolved_account && r.count === 1) navigate(`/accounts/${r.resolved_account}`, { replace: true })
      })
      .catch(e => alive && setErr(e.message))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [q, navigate])

  return (
    <Page>
      <div style={{ display: 'flex', alignItems: 'center', gap: 11, marginBottom: 6 }}>
        <Search size={18} color={T.gold} />
        <h1 style={{ fontSize: 19, fontWeight: 700, margin: 0 }}>Search Results</h1>
      </div>
      <p style={{ color: T.text2, fontSize: 13, marginBottom: 22 }}>
        Query <span style={{ color: T.text, fontFamily: T.mono }}>“{q}”</span>
        {!loading && ` · ${results.length} match${results.length === 1 ? '' : 'es'}`}
        {resolved && <span style={{ color: T.gold }}> · resolved to {resolved}</span>}
      </p>

      {loading && <div style={{ color: T.text3, fontSize: 13 }}>Searching intelligence registry…</div>}
      {err && <div style={{ color: T.danger, fontSize: 13 }}>{err}</div>}

      {!loading && !err && results.length === 0 && (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: T.text3 }}>
          <SearchX size={32} style={{ marginBottom: 14, opacity: 0.6 }} />
          <div style={{ fontSize: 14, color: T.text2 }}>No accounts match this identifier.</div>
          <div style={{ fontSize: 12.5, marginTop: 6 }}>
            Try an account number (ACC-…), customer ID (CUST-…), transaction, case or evidence reference.
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gap: 12 }}>
        {results.map(a => (
          <Link key={a.account_number} to={`/accounts/${a.account_number}`} style={{ textDecoration: 'none' }}>
            <div style={{
              background: T.panel, border: `1px solid ${T.border}`, borderRadius: 12, padding: '16px 18px',
              display: 'grid', gridTemplateColumns: '4px 1fr auto', gap: 16, alignItems: 'center',
            }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = T.borderHi)}
              onMouseLeave={e => (e.currentTarget.style.borderColor = T.border)}
            >
              <span style={{ width: 4, height: 42, borderRadius: 3, background: riskColorFromScore(a.risk_score) }} />
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 5 }}>
                  <span style={{ fontSize: 15, color: T.text, fontFamily: T.mono, fontWeight: 600 }}>{a.account_number}</span>
                  <Pill text={a.status} color={statusColor(a.status)} />
                  <Pill text={a.investigation_status} color={statusColor(a.investigation_status)} />
                </div>
                <div style={{ fontSize: 13, color: T.text2 }}>
                  {a.customer_name} · {a.customer_id} · {a.bank}
                </div>
                <div style={{ fontSize: 11.5, color: T.text3, marginTop: 3 }}>
                  {a.transaction_count.toLocaleString('en-IN')} transactions · {a.linked_count} linked accounts
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 22, fontWeight: 700, color: riskColorFromScore(a.risk_score) }}>{a.risk_score}</div>
                <div style={{ fontSize: 10.5, color: T.text3, letterSpacing: '.06em' }}>{a.risk_band.toUpperCase()} RISK</div>
                <ArrowUpRight size={15} color={T.text3} style={{ marginTop: 4 }} />
              </div>
            </div>
          </Link>
        ))}
      </div>
    </Page>
  )
}

function Pill({ text, color }: { text: string; color: string }) {
  return (
    <span style={{
      fontSize: 11, color, background: `${color}1c`, border: `1px solid ${color}44`,
      padding: '2px 8px', borderRadius: 999, fontWeight: 500,
    }}>{text}</span>
  )
}
