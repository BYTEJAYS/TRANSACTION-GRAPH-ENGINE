import { Navigate, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from './AuthContext'
import { T } from '../theme'

// Role hierarchy for optional clearance gating
const ROLE_RANK: Record<string, number> = {
  'Investigator': 0,
  'Senior Investigator': 1,
  'Supervisor': 2,
  'Administrator': 3,
}

function FullScreenSpinner() {
  return (
    <div style={{
      position: 'fixed', inset: 0, background: T.bg, color: T.text2,
      display: 'grid', placeItems: 'center', fontFamily: T.font, fontSize: 13, letterSpacing: '.04em',
    }}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
        <div style={{
          width: 26, height: 26, border: `2px solid ${T.border}`,
          borderTopColor: T.gold, borderRadius: '50%', animation: 'tgieSpin 0.8s linear infinite',
        }} />
        AUTHENTICATING SESSION…
        <style>{'@keyframes tgieSpin{to{transform:rotate(360deg)}}'}</style>
      </div>
    </div>
  )
}

export function ProtectedRoute({ children, minRole }: { children: ReactNode; minRole?: string }) {
  const { investigator, loading } = useAuth()
  const location = useLocation()

  if (loading) return <FullScreenSpinner />

  if (!investigator) {
    // Preserve intended destination so login can bounce back to it
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }

  if (minRole && (ROLE_RANK[investigator.role] ?? 0) < (ROLE_RANK[minRole] ?? 0)) {
    return (
      <div style={{
        position: 'fixed', inset: 0, background: T.bg, color: T.text2,
        display: 'grid', placeItems: 'center', fontFamily: T.font, textAlign: 'center',
      }}>
        <div>
          <div style={{ color: T.danger, fontSize: 15, fontWeight: 600, marginBottom: 8 }}>
            Insufficient Clearance
          </div>
          <div style={{ fontSize: 13 }}>
            This module requires <strong style={{ color: T.gold }}>{minRole}</strong> access or above.
          </div>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
