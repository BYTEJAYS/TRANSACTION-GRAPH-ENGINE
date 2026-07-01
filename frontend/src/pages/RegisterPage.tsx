import { useState, useEffect, type FormEvent } from 'react'
import { useNavigate, Navigate, Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { authApi } from '../auth/api'
import { TgieMark } from '../components/nav/TgieMark'
import { T, cream } from '../theme'

const DEPARTMENTS = [
  'Financial Crime Investigation',
  'Cyber Crime Unit',
  'Risk & Compliance',
  'Internal Audit',
  'Fraud Investigation',
  'Anti-Money Laundering',
  'Platform Administration',
]

export default function RegisterPage() {
  const { investigator, register } = useAuth()
  const navigate = useNavigate()

  const [roles, setRoles] = useState<string[]>(['Investigator', 'Senior Investigator', 'Supervisor', 'Administrator'])
  const [f, setF] = useState({
    name: '', investigator_id: '', employee_id: '', email: '',
    department: DEPARTMENTS[0], role: 'Investigator', branch: '',
    password: '', confirm: '',
  })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { authApi.roles().then(setRoles).catch(() => {}) }, [])

  if (investigator) return <Navigate to="/graph" replace />

  const set = (k: keyof typeof f) => (e: { target: { value: string } }) =>
    setF(prev => ({ ...prev, [k]: e.target.value }))

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (f.password !== f.confirm) { setError('Passwords do not match.'); return }
    if (f.password.length < 8) { setError('Password must be at least 8 characters.'); return }
    setBusy(true)
    try {
      const { confirm, ...payload } = f
      void confirm
      await register(payload)
      navigate('/graph', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', background: T.bg, color: T.text, fontFamily: T.font,
      display: 'grid', gridTemplateColumns: '1fr 1.15fr', position: 'relative', overflow: 'hidden',
    }}>
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        background:
          'radial-gradient(1200px 600px at 10% -10%, rgba(198,162,83,0.06), transparent 60%),' +
          'radial-gradient(900px 500px at 100% 120%, rgba(255,255,255,0.03), transparent 60%)',
      }} />

      {/* Left brand rail */}
      <aside style={{
        position: 'relative', padding: '56px 56px', display: 'flex', flexDirection: 'column',
        justifyContent: 'space-between', borderRight: `1px solid ${T.border}`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <TgieMark size={40} />
          <div>
            <div style={{ fontSize: 19, fontWeight: 700, letterSpacing: '.14em' }}>TGIE</div>
            <div style={{ fontSize: 10.5, color: T.text3, letterSpacing: '.18em' }}>
              SECURE INVESTIGATION TERMINAL
            </div>
          </div>
        </div>
        <div style={{ maxWidth: 420 }}>
          <h1 style={{ fontSize: 30, lineHeight: 1.2, fontWeight: 700, margin: 0 }}>
            Create your<br />investigator profile
          </h1>
          <p style={{ fontSize: 14, color: T.text2, marginTop: 16, lineHeight: 1.65 }}>
            Register your credentials to access the Transaction Graph Intelligence Engine.
            Your profile drives access control, audit logging and case attribution.
          </p>
        </div>
        <div style={{ fontSize: 11, color: T.text3, letterSpacing: '.04em', lineHeight: 1.7 }}>
          <div style={{ color: T.goldLine, display: 'flex', alignItems: 'center', gap: 7 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: T.gold, display: 'inline-block' }} />
            RESTRICTED ACCESS · AUTHORISED PERSONNEL ONLY
          </div>
          Passwords are stored only as salted hashes. All actions are logged for audit.
        </div>
      </aside>

      {/* Right form */}
      <main style={{ position: 'relative', display: 'grid', placeItems: 'center', padding: '32px 40px', overflowY: 'auto' }}>
        <form onSubmit={submit} style={{
          width: '100%', maxWidth: 520, background: cream.panel, border: `1px solid ${cream.border}`,
          borderRadius: 14, padding: '30px 30px', boxShadow: T.shadow, margin: '24px 0', color: cream.text,
        }}>
          <div style={{ marginBottom: 22 }}>
            <div style={{ fontSize: 17, fontWeight: 700, color: cream.text }}>Investigator Registration</div>
            <div style={{ fontSize: 12, color: cream.text3, marginTop: 5 }}>
              Fill in your details to create your access profile
            </div>
          </div>

          {error && (
            <div role="alert" style={{
              background: 'rgba(178,38,30,0.10)', border: '1px solid rgba(178,38,30,0.45)', color: '#9e241c',
              fontSize: 12.5, padding: '10px 12px', borderRadius: 8, marginBottom: 16, lineHeight: 1.5,
            }}>{error}</div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <Field label="Full Name" full>
              <input value={f.name} onChange={set('name')} placeholder="e.g. Aarav Mehta" autoFocus style={inputStyle} />
            </Field>
            <Field label="Investigator ID">
              <input value={f.investigator_id} onChange={set('investigator_id')} placeholder="e.g. INV-2041" style={inputStyle} />
            </Field>
            <Field label="Employee ID">
              <input value={f.employee_id} onChange={set('employee_id')} placeholder="e.g. EMP-100241" style={inputStyle} />
            </Field>
            <Field label="Department">
              <select value={f.department} onChange={set('department')} style={inputStyle}>
                {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
              </select>
            </Field>
            <Field label="Role">
              <select value={f.role} onChange={set('role')} style={inputStyle}>
                {roles.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </Field>
            <Field label="Branch / Office" full>
              <input value={f.branch} onChange={set('branch')} placeholder="e.g. Mumbai — Central Operations" style={inputStyle} />
            </Field>
            <Field label="Official Email" full>
              <input type="email" value={f.email} onChange={set('email')} placeholder="name@tgie.gov.in" style={inputStyle} />
            </Field>
            <Field label="Password">
              <input type="password" value={f.password} onChange={set('password')} placeholder="Min. 8 characters" autoComplete="new-password" style={inputStyle} />
            </Field>
            <Field label="Confirm Password">
              <input type="password" value={f.confirm} onChange={set('confirm')} placeholder="Re-enter password" autoComplete="new-password" style={inputStyle} />
            </Field>
          </div>

          <button type="submit" disabled={busy} style={{
            width: '100%', marginTop: 22, padding: '12px 0', borderRadius: 9, border: 'none',
            cursor: busy ? 'wait' : 'pointer',
            background: busy ? '#9aa68f' : `linear-gradient(180deg, ${cream.greenHi}, ${cream.green})`,
            color: '#ffffff', fontWeight: 700, fontSize: 13.5, letterSpacing: '.03em', fontFamily: T.font,
            boxShadow: busy ? 'none' : '0 4px 14px rgba(47,158,68,0.35)',
          }}>
            {busy ? 'Creating profile…' : 'Create Profile'}
          </button>

          <div style={{ textAlign: 'center', marginTop: 16, fontSize: 12.5, color: cream.text3 }}>
            Already registered?{' '}
            <Link to="/login" style={{ color: cream.greenDim, fontWeight: 600, textDecoration: 'none' }}>Sign in</Link>
          </div>
        </form>
      </main>
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '11px 13px', background: cream.input, border: `1px solid ${cream.border}`,
  borderRadius: 9, color: cream.text, fontSize: 14, outline: 'none', fontFamily: T.font,
  boxSizing: 'border-box',
}

function Field({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return (
    <label style={{ display: 'block', gridColumn: full ? '1 / -1' : 'auto' }}>
      <span style={{ display: 'block', fontSize: 11.5, color: cream.text2, marginBottom: 7, letterSpacing: '.04em', fontWeight: 600 }}>
        {label}
      </span>
      {children}
    </label>
  )
}
