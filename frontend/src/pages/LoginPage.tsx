import { useState, type FormEvent } from 'react'
import { useNavigate, useLocation, Navigate, Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { IntelligenceParticleEngine } from '../components/login/IntelligenceParticleEngine'
import { T, cream } from '../theme'

export default function LoginPage() {
  const { investigator, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from || '/graph'

  const [id, setId] = useState('')
  const [pw, setPw] = useState('')
  const [remember, setRemember] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (investigator) return <Navigate to={from} replace />

  const excite = () => window.dispatchEvent(new CustomEvent('tgie:excite'))

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    window.dispatchEvent(new CustomEvent('tgie:activate'))  // "accessing the TGIE intelligence network"
    setBusy(true)
    try {
      await login(id.trim(), pw, remember)
      navigate(from, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authentication failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', background: '#000000', color: T.text, fontFamily: T.font,
      display: 'grid', gridTemplateColumns: '1.1fr 1fr', position: 'relative', overflow: 'hidden',
    }}>
      {/* ── Living financial-intelligence network background ─────────── */}
      <IntelligenceParticleEngine />

      {/* deep vignette — darkens edges so the white network reads with contrast */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 0,
        background:
          'radial-gradient(1100px 620px at 22% 38%, rgba(255,255,255,0.025), transparent 62%),' +
          'radial-gradient(140% 120% at 50% 50%, transparent 40%, rgba(0,0,0,0.55) 100%)',
      }} />

      {/* ── Left brand rail ─────────────────────────────────────────── */}
      <aside style={{
        position: 'relative', zIndex: 1, padding: '56px 64px', display: 'flex', flexDirection: 'column',
        justifyContent: 'space-between', borderRight: `1px solid ${T.border}`,
      }}>
        <div>
          <div style={{ fontSize: 19, fontWeight: 700, letterSpacing: '.14em' }}>TGIE</div>
          <div style={{ fontSize: 10.5, color: T.text3, letterSpacing: '.18em' }}>
            SECURE INVESTIGATION TERMINAL
          </div>
        </div>

        <div style={{ maxWidth: 460 }}>
          <h1 style={{ fontSize: 34, lineHeight: 1.18, fontWeight: 700, margin: 0, letterSpacing: '-0.01em' }}>
            Transaction Graph<br />Intelligence Engine
          </h1>
          <p style={{ fontSize: 14.5, color: T.text2, marginTop: 18, lineHeight: 1.6 }}>
            Fraud Investigation &amp; Financial Intelligence Platform for authorised
            investigators, cyber-crime units, compliance and risk teams.
          </p>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 24 }}>
            {['Fraud Investigation', 'Cyber Crime', 'Compliance', 'Risk & Audit'].map(t => (
              <span key={t} style={{
                fontSize: 11, color: T.text2, padding: '5px 11px', borderRadius: 999,
                border: `1px solid ${T.border}`, background: T.panel, letterSpacing: '.03em',
              }}>{t}</span>
            ))}
          </div>
        </div>

        <div style={{ fontSize: 11, color: T.text3, letterSpacing: '.04em', lineHeight: 1.7 }}>
          <div style={{ color: T.goldLine, display: 'flex', alignItems: 'center', gap: 7 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: T.gold, display: 'inline-block' }} />
            RESTRICTED ACCESS · AUTHORISED PERSONNEL ONLY
          </div>
          All sessions are authenticated, logged and monitored. Unauthorised access is an offence.
        </div>
      </aside>

      {/* ── Right login card ────────────────────────────────────────── */}
      <main style={{ position: 'relative', zIndex: 1, display: 'grid', placeItems: 'center', padding: 32 }}>
        <form onSubmit={submit} style={{
          width: '100%', maxWidth: 380, background: cream.panel, border: `1px solid ${cream.border}`,
          borderRadius: 14, padding: '34px 32px', boxShadow: T.shadow, color: cream.text,
        }}>
          <div style={{ textAlign: 'center', marginBottom: 26 }}>
            <div style={{ fontSize: 17, fontWeight: 700, letterSpacing: '.02em', color: cream.text }}>Investigator Sign In</div>
            <div style={{ fontSize: 12, color: cream.text3, marginTop: 6 }}>
              Authenticate to access the investigation workspace
            </div>
          </div>

          {error && (
            <div role="alert" style={{
              background: 'rgba(178,38,30,0.10)', border: '1px solid rgba(178,38,30,0.45)', color: '#9e241c',
              fontSize: 12.5, padding: '10px 12px', borderRadius: 8, marginBottom: 16, lineHeight: 1.5,
            }}>{error}</div>
          )}

          <Field label="Investigator ID">
            <input
              value={id} onChange={e => setId(e.target.value)} autoFocus onFocus={excite}
              placeholder="e.g. INV-2041" autoComplete="username" style={inputStyle}
            />
          </Field>

          <Field label="Password">
            <input
              type="password" value={pw} onChange={e => setPw(e.target.value)} onFocus={excite}
              placeholder="••••••••••" autoComplete="current-password" style={inputStyle}
            />
          </Field>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '4px 0 22px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: cream.text2, cursor: 'pointer' }}>
              <input
                type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)}
                style={{ accentColor: cream.green, width: 14, height: 14 }}
              />
              Remember this device
            </label>
            <button type="button" onClick={() => setError('Contact your supervisor to reset credentials.')}
              style={{ background: 'none', border: 'none', color: cream.greenDim, fontSize: 12, cursor: 'pointer', padding: 0 }}>
              Forgot password?
            </button>
          </div>

          <button type="submit" disabled={busy || !id || !pw} style={{
            width: '100%', padding: '12px 0', borderRadius: 9, border: 'none', cursor: busy ? 'wait' : 'pointer',
            background: busy || !id || !pw ? '#9aa68f' : `linear-gradient(180deg, ${cream.greenHi}, ${cream.green})`,
            color: '#ffffff', fontWeight: 700, fontSize: 13.5, letterSpacing: '.03em',
            transition: 'filter .15s', fontFamily: T.font,
            boxShadow: busy || !id || !pw ? 'none' : '0 4px 14px rgba(47,158,68,0.35)',
          }}>
            {busy ? 'Verifying…' : 'Sign In'}
          </button>

          <div style={{
            marginTop: 20, paddingTop: 16, borderTop: `1px solid ${cream.border}`,
            textAlign: 'center', fontSize: 12.5, color: cream.text3,
          }}>
            New to TGIE?{' '}
            <Link to="/register" style={{ color: cream.greenDim, fontWeight: 600, textDecoration: 'none' }}>
              Create an investigator profile
            </Link>
          </div>
        </form>
      </main>
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '11px 13px', background: cream.input, border: `1px solid ${cream.border}`,
  borderRadius: 9, color: cream.text, fontSize: 14, outline: 'none', fontFamily: T.font,
  transition: 'border-color .15s, box-shadow .15s', boxSizing: 'border-box',
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'block', marginBottom: 16 }}>
      <span style={{ display: 'block', fontSize: 11.5, color: cream.text2, marginBottom: 7, letterSpacing: '.04em', fontWeight: 600 }}>
        {label}
      </span>
      {children}
    </label>
  )
}
