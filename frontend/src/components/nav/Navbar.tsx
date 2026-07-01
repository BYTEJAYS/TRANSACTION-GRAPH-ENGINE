import { useState, useRef, useEffect, type FormEvent } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { Search } from 'lucide-react'
import { TgieMark } from './TgieMark'
import { ProfileMenu } from './ProfilePanel'
import { NotificationsBell } from './NotificationsBell'
import { authApi, type AccountSummary } from '../../auth/api'
import { T, riskColorFromScore } from '../../theme'

const NAV_LINKS = [
  { to: '/graph', label: 'Graph Engine' },
  { to: '/investigations', label: 'Investigations' },
  { to: '/recovery', label: 'Recovery' },
]

export function Navbar() {
  const navigate = useNavigate()
  const location = useLocation()
  const [q, setQ] = useState('')
  const [suggest, setSuggest] = useState<AccountSummary[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const boxRef = useRef<HTMLFormElement>(null)
  const debounce = useRef<number | null>(null)

  // live suggestions (debounced)
  useEffect(() => {
    if (debounce.current) window.clearTimeout(debounce.current)
    if (q.trim().length < 2) { setSuggest([]); setOpen(false); return }
    debounce.current = window.setTimeout(async () => {
      try {
        const res = await authApi.searchAccounts(q.trim())
        setSuggest(res.results)
        setOpen(true)
        setActive(-1)
      } catch { setSuggest([]) }
    }, 220)
    return () => { if (debounce.current) window.clearTimeout(debounce.current) }
  }, [q])

  // close on outside click
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  function go(account: string) {
    setOpen(false); setQ('')
    navigate(`/accounts/${encodeURIComponent(account)}`)
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    const term = q.trim()
    if (!term) return
    if (active >= 0 && suggest[active]) { go(suggest[active].account_number); return }
    setOpen(false)
    navigate(`/search?q=${encodeURIComponent(term)}`)
  }

  function onKey(e: React.KeyboardEvent) {
    if (!open || !suggest.length) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, suggest.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, -1)) }
    else if (e.key === 'Escape') setOpen(false)
  }

  return (
    <header style={{
      height: 64, flexShrink: 0, background: T.bg2, borderBottom: `1px solid ${T.border}`,
      display: 'flex', alignItems: 'center', gap: 20, padding: '0 22px', position: 'relative', zIndex: 50,
    }}>
      {/* LEFT — brand + nav */}
      <Link to="/graph" style={{ display: 'flex', alignItems: 'center', gap: 11, textDecoration: 'none', flexShrink: 0 }}>
        <TgieMark size={30} />
        <div>
          <div style={{ fontSize: 14.5, fontWeight: 700, color: T.text, letterSpacing: '.12em', lineHeight: 1 }}>TGIE</div>
          <div style={{ fontSize: 8.5, color: T.text3, letterSpacing: '.14em', marginTop: 3 }}>
            TRANSACTION GRAPH INTELLIGENCE
          </div>
        </div>
      </Link>

      <nav style={{ display: 'flex', gap: 4, marginLeft: 6 }}>
        {NAV_LINKS.map(l => {
          const on = location.pathname === l.to || location.pathname.startsWith(l.to + '/')
          return (
            <Link key={l.to} to={l.to} style={{
              fontSize: 12.5, color: on ? T.text : T.text2, textDecoration: 'none',
              padding: '7px 12px', borderRadius: 7, fontWeight: on ? 600 : 500,
              background: on ? T.raised : 'transparent', letterSpacing: '.01em',
            }}>{l.label}</Link>
          )
        })}
      </nav>

      {/* CENTER — global search (the primary workflow) */}
      <form onSubmit={submit} style={{ flex: 1, maxWidth: 560, margin: '0 auto', position: 'relative' }} ref={boxRef}>
        <div style={{ position: 'relative' }}>
          <Search size={15} style={{ position: 'absolute', left: 13, top: '50%', transform: 'translateY(-50%)', color: T.text3 }} />
          <input
            value={q}
            onChange={e => setQ(e.target.value)}
            onKeyDown={onKey}
            onFocus={() => suggest.length && setOpen(true)}
            placeholder="Search by Account Number, Customer ID, Transaction, Case or Evidence ID…"
            style={{
              width: '100%', padding: '9px 13px 9px 36px', background: T.panel,
              border: `1px solid ${open ? T.goldLine : T.border}`, borderRadius: 9, color: T.text,
              fontSize: 13, outline: 'none', fontFamily: T.font, boxSizing: 'border-box',
            }}
          />
          <kbd style={{
            position: 'absolute', right: 11, top: '50%', transform: 'translateY(-50%)',
            fontSize: 10, color: T.text3, border: `1px solid ${T.border}`, borderRadius: 5,
            padding: '2px 6px', fontFamily: T.mono,
          }}>↵</kbd>
        </div>

        {open && suggest.length > 0 && (
          <div style={{
            position: 'absolute', top: 'calc(100% + 8px)', left: 0, right: 0, background: T.panel,
            border: `1px solid ${T.border}`, borderRadius: 11, boxShadow: T.shadow, overflow: 'hidden', zIndex: 60,
          }}>
            <div style={{ padding: '8px 14px', fontSize: 10, color: T.text3, letterSpacing: '.1em', borderBottom: `1px solid ${T.border}` }}>
              {suggest.length} MATCH{suggest.length > 1 ? 'ES' : ''}
            </div>
            {suggest.map((r, i) => (
              <button key={r.account_number} type="button" onMouseEnter={() => setActive(i)} onClick={() => go(r.account_number)}
                style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
                  background: i === active ? T.raised : 'transparent', border: 'none', cursor: 'pointer', textAlign: 'left',
                }}>
                <span style={{
                  width: 8, height: 8, borderRadius: '50%', background: riskColorFromScore(r.risk_score), flexShrink: 0,
                }} />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ display: 'block', fontSize: 13, color: T.text, fontFamily: T.mono }}>{r.account_number}</span>
                  <span style={{ display: 'block', fontSize: 11, color: T.text2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {r.customer_name} · {r.bank}
                  </span>
                </span>
                <span style={{ fontSize: 11, color: riskColorFromScore(r.risk_score), fontWeight: 600 }}>
                  {r.risk_score} · {r.risk_band}
                </span>
              </button>
            ))}
          </div>
        )}
      </form>

      {/* RIGHT — notifications + profile */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
        <NotificationsBell />
        <ProfileMenu />
      </div>
    </header>
  )
}
