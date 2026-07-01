import { useEffect, useRef, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { History, X } from 'lucide-react'
import { Navbar } from './Navbar'
import { T } from '../../theme'
import { sessionStore } from '../../store/session'

// Deep, investigation-bearing routes worth offering to resume.
const RESUMABLE = ['/graph', '/recovery/', '/investigations/', '/accounts/']
const RESUME_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000

function routeLabel(path: string): string {
  if (path.startsWith('/graph')) return 'Graph Engine'
  if (path.startsWith('/recovery/')) return `Recovery · ${path.split('/')[2]}`
  if (path.startsWith('/investigations/')) return `Case · ${path.split('/')[2]}`
  if (path.startsWith('/accounts/')) return `Account · ${path.split('/')[2]}`
  return path
}

// Authenticated shell: fixed navbar + globally accessible search, content below.
// The shell persists across navigation (only the <Outlet> child remounts), which
// is why session/resume logic lives here rather than in any individual page.
export function AppLayout() {
  const location = useLocation()
  const navigate = useNavigate()

  // Capture where the investigator left off BEFORE we start tracking the new path.
  const [resume, setResume] = useState<string | null>(() => {
    const s = sessionStore.get()
    const fresh = Date.now() - s.updatedAt < RESUME_MAX_AGE_MS
    const deep = RESUMABLE.some(p => s.lastPath.startsWith(p))
    return !s.resumeDismissed && fresh && deep && s.lastPath !== window.location.pathname ? s.lastPath : null
  })
  const dismissedOnce = useRef(false)

  // Auto-save the current view so a refresh resumes exactly here.
  useEffect(() => { sessionStore.setPath(location.pathname) }, [location.pathname])
  // Any deliberate navigation clears the stale resume prompt.
  useEffect(() => { if (dismissedOnce.current) setResume(null) }, [location.pathname])

  const dismiss = () => { dismissedOnce.current = true; sessionStore.set({ resumeDismissed: true }); setResume(null) }
  const go = () => { if (resume) { dismissedOnce.current = true; navigate(resume) } setResume(null) }

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: T.bg, color: T.text, fontFamily: T.font }}>
      <Navbar />
      {resume && (
        <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 12, padding: '9px 18px', borderBottom: `1px solid ${T.goldLine}`, background: T.goldDim }}>
          <History size={15} color={T.gold} />
          <span style={{ fontSize: 12.5, color: T.text }}>
            Resume your investigation — <b style={{ color: T.gold }}>{routeLabel(resume)}</b>?
          </span>
          <button onClick={go} style={{ marginLeft: 6, padding: '6px 13px', borderRadius: 8, border: 'none', background: T.gold, color: T.textOn, fontWeight: 700, fontSize: 12, cursor: 'pointer', fontFamily: T.font }}>
            Resume
          </button>
          <button onClick={dismiss} title="Dismiss" style={{ marginLeft: 'auto', display: 'grid', placeItems: 'center', width: 28, height: 28, borderRadius: 7, background: 'transparent', border: `1px solid ${T.border}`, color: T.text3, cursor: 'pointer' }}>
            <X size={14} />
          </button>
        </div>
      )}
      <main style={{ flex: 1, minHeight: 0, position: 'relative', overflow: 'hidden' }}>
        <Outlet />
      </main>
    </div>
  )
}

// Scrollable page wrapper for non-graph content pages.
export function Page({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ height: '100%', overflowY: 'auto', background: T.bg }}>
      <div style={{ maxWidth: 1180, margin: '0 auto', padding: '28px 28px 64px' }}>
        {children}
      </div>
    </div>
  )
}
