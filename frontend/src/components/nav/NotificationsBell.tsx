import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell } from 'lucide-react'
import { caseApi } from '../../cases/api'
import { T } from '../../theme'

interface Notif { case_id: string; title: string; event: string; detail: string; ts: number }

function ago(ts: number): string {
  const s = Date.now() / 1000 - ts
  if (s < 3600) return `${Math.max(1, Math.floor(s / 60))}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

export function NotificationsBell() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<Notif[]>([])
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    caseApi.notifications().then(r => setItems(r.notifications)).catch(() => {})
  }, [])

  useEffect(() => {
    const onClick = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  return (
    <div style={{ position: 'relative' }} ref={ref}>
      <button title="Notifications" onClick={() => setOpen(o => !o)} style={{
        position: 'relative', width: 38, height: 38, borderRadius: 9,
        border: `1px solid ${open ? T.goldLine : T.border}`, background: T.panel, display: 'grid', placeItems: 'center', cursor: 'pointer',
      }}>
        <Bell size={17} color={T.text2} />
        {items.length > 0 && (
          <span style={{ position: 'absolute', top: 7, right: 8, width: 7, height: 7, borderRadius: '50%', background: T.danger, border: `1.5px solid ${T.bg2}` }} />
        )}
      </button>

      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 10px)', right: 0, width: 340, background: T.panel,
          border: `1px solid ${T.border}`, borderRadius: 13, boxShadow: T.shadow, overflow: 'hidden', zIndex: 60,
        }}>
          <div style={{ padding: '13px 16px', borderBottom: `1px solid ${T.border}`, fontSize: 13, fontWeight: 600 }}>
            Notifications
          </div>
          <div style={{ maxHeight: 380, overflowY: 'auto' }}>
            {items.length === 0 && <div style={{ padding: 24, fontSize: 12.5, color: T.text3, textAlign: 'center' }}>No notifications</div>}
            {items.map((n, i) => (
              <button key={i} onClick={() => { setOpen(false); navigate(`/investigations/${n.case_id}`) }} style={{
                width: '100%', textAlign: 'left', padding: '11px 16px', background: 'none', border: 'none',
                borderBottom: `1px solid ${T.border}`, cursor: 'pointer', fontFamily: T.font,
              }}
                onMouseEnter={e => (e.currentTarget.style.background = T.raised)}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                  <span style={{ fontSize: 12.5, color: T.text, fontWeight: 600 }}>{n.event}</span>
                  <span style={{ fontSize: 10.5, color: T.text3, whiteSpace: 'nowrap' }}>{ago(n.ts)}</span>
                </div>
                <div style={{ fontSize: 11, color: T.gold, fontFamily: T.mono, marginTop: 2 }}>{n.case_id}</div>
                <div style={{ fontSize: 11, color: T.text3, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.detail || n.title}</div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
