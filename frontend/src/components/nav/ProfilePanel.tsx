import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { User, Settings, ScrollText, KeyRound, LogOut, ShieldCheck, Pencil } from 'lucide-react'
import { useAuth } from '../../auth/AuthContext'
import { authApi } from '../../auth/api'
import { AVATARS, avatarGlyph } from '../../auth/avatars'
import { T } from '../../theme'

function fmtTime(ts: number | null): string {
  if (!ts) return '—'
  return new Date(ts * 1000).toLocaleString('en-IN', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}

// Circular avatar badge showing the investigator's animal character.
function AvatarBadge({ glyph, size }: { glyph: string; size: number }) {
  return (
    <span style={{
      width: size, height: size, borderRadius: '50%', display: 'grid', placeItems: 'center', flexShrink: 0,
      background: T.raised, border: `1px solid ${T.goldLine}`, fontSize: Math.round(size * 0.55), lineHeight: 1,
    }}>{glyph}</span>
  )
}

export function ProfileMenu() {
  const { investigator, logout, setAvatar } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [picker, setPicker] = useState(false)
  const [session, setSession] = useState<{ started_at: number | null; ip: string | null } | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  useEffect(() => {
    if (open && !session) {
      authApi.profile().then(p => setSession(p.session)).catch(() => {})
    }
  }, [open, session])

  if (!investigator) return null

  async function doLogout() {
    setOpen(false)
    await logout()
    navigate('/login', { replace: true })
  }

  const rows: { label: string; value: string }[] = [
    { label: 'Employee ID', value: investigator.employee_id },
    { label: 'Department', value: investigator.department },
    { label: 'Role', value: investigator.role },
    { label: 'Branch', value: investigator.branch },
    { label: 'Last Login', value: fmtTime(investigator.last_login) },
    { label: 'Session Start', value: fmtTime(session?.started_at ?? null) },
  ]

  const actions = [
    { icon: User, label: 'View Profile' },
    { icon: Settings, label: 'Settings' },
    { icon: ScrollText, label: 'Activity Logs', onClick: () => { setOpen(false); navigate('/investigations') } },
    { icon: KeyRound, label: 'Change Password' },
  ]

  return (
    <div style={{ position: 'relative' }} ref={ref}>
      <button onClick={() => setOpen(o => !o)} title="Investigator profile" style={{
        display: 'flex', alignItems: 'center', gap: 9, padding: '5px 8px 5px 5px', borderRadius: 999,
        border: `1px solid ${open ? T.goldLine : T.border}`, background: T.panel, cursor: 'pointer',
      }}>
        <AvatarBadge glyph={avatarGlyph(investigator.avatar)} size={30} />
        <span style={{ textAlign: 'left', lineHeight: 1.15 }}>
          <span style={{ display: 'block', fontSize: 12, color: T.text, fontWeight: 600, maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {investigator.name}
          </span>
          <span style={{ display: 'block', fontSize: 10, color: T.text3 }}>{investigator.investigator_id}</span>
        </span>
      </button>

      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 10px)', right: 0, width: 312, background: T.panel,
          border: `1px solid ${T.border}`, borderRadius: 13, boxShadow: T.shadow, overflow: 'hidden', zIndex: 60,
        }}>
          {/* header */}
          <div style={{ padding: '18px 18px 16px', borderBottom: `1px solid ${T.border}`, display: 'flex', gap: 13 }}>
            <button onClick={() => setPicker(p => !p)} title="Change avatar" style={{
              position: 'relative', padding: 0, border: 'none', background: 'none', cursor: 'pointer', flexShrink: 0,
            }}>
              <AvatarBadge glyph={avatarGlyph(investigator.avatar)} size={46} />
              <span style={{
                position: 'absolute', right: -2, bottom: -2, width: 18, height: 18, borderRadius: '50%',
                background: T.gold, display: 'grid', placeItems: 'center', border: `2px solid ${T.panel}`,
              }}><Pencil size={9} color={T.textOn} /></span>
            </button>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 14.5, fontWeight: 700, color: T.text }}>{investigator.name}</div>
              <div style={{ fontSize: 11.5, color: T.text2, marginTop: 2 }}>{investigator.email}</div>
              <div style={{
                display: 'inline-flex', alignItems: 'center', gap: 5, marginTop: 7, fontSize: 10.5,
                color: T.gold, background: T.goldDim, border: `1px solid ${T.goldLine}`,
                padding: '2px 8px', borderRadius: 999,
              }}>
                <ShieldCheck size={11} /> {investigator.role}
              </div>
            </div>
          </div>

          {/* avatar picker */}
          {picker && (
            <div style={{ padding: '12px 18px', borderBottom: `1px solid ${T.border}`, background: T.bg2 }}>
              <div style={{ fontSize: 10.5, color: T.text3, letterSpacing: '.06em', marginBottom: 10 }}>
                CHOOSE YOUR CHARACTER
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 8 }}>
                {AVATARS.map(a => {
                  const active = a.key === investigator.avatar
                  return (
                    <button key={a.key} title={a.label} onClick={async () => { await setAvatar(a.key); setPicker(false) }}
                      style={{
                        aspectRatio: '1', borderRadius: 9, cursor: 'pointer', fontSize: 18, lineHeight: 1,
                        display: 'grid', placeItems: 'center',
                        background: active ? T.goldDim : T.raised,
                        border: `1px solid ${active ? T.gold : T.border}`,
                      }}>{a.glyph}</button>
                  )
                })}
              </div>
            </div>
          )}

          {/* detail rows */}
          <div style={{ padding: '10px 18px' }}>
            {rows.map(r => (
              <div key={r.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', fontSize: 12 }}>
                <span style={{ color: T.text3 }}>{r.label}</span>
                <span style={{ color: T.text2, fontWeight: 500, textAlign: 'right', maxWidth: 170, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {r.value}
                </span>
              </div>
            ))}
          </div>

          {/* actions */}
          <div style={{ padding: 8, borderTop: `1px solid ${T.border}` }}>
            {actions.map(a => (
              <button key={a.label} onClick={a.onClick} style={menuItem}>
                <a.icon size={15} color={T.text2} /> {a.label}
              </button>
            ))}
            <button onClick={doLogout} style={{ ...menuItem, color: T.danger }}>
              <LogOut size={15} color={T.danger} /> Logout
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

const menuItem: React.CSSProperties = {
  width: '100%', display: 'flex', alignItems: 'center', gap: 11, padding: '9px 11px',
  background: 'none', border: 'none', borderRadius: 8, cursor: 'pointer',
  color: T.text, fontSize: 12.5, textAlign: 'left', fontFamily: T.font,
}
