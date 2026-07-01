import { createContext, useContext, useEffect, useState, useCallback, useRef, type ReactNode } from 'react'
import { authApi, tokenStore, setAuthFailureHandler, type Investigator, type RegisterPayload } from './api'

interface AuthState {
  investigator: Investigator | null
  loading: boolean
  login: (id: string, password: string, remember: boolean) => Promise<void>
  register: (payload: RegisterPayload) => Promise<void>
  setAvatar: (avatar: string) => Promise<void>
  logout: () => Promise<void>
  refreshProfile: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

// Idle session timeout — auto-logout after inactivity (security requirement).
const IDLE_TIMEOUT_MS = 30 * 60 * 1000 // 30 minutes

export function AuthProvider({ children }: { children: ReactNode }) {
  const [investigator, setInvestigator] = useState<Investigator | null>(null)
  const [loading, setLoading] = useState(true)
  const idleTimer = useRef<number | null>(null)

  const doLogout = useCallback(async () => {
    await authApi.logout()
    setInvestigator(null)
  }, [])

  // Wire API 401 handler → clear session
  useEffect(() => {
    setAuthFailureHandler(() => setInvestigator(null))
  }, [])

  // Bootstrap from an existing token on first load
  useEffect(() => {
    let alive = true
    ;(async () => {
      if (!tokenStore.access) { setLoading(false); return }
      try {
        const { investigator } = await authApi.me()
        if (alive) setInvestigator(investigator)
      } catch {
        tokenStore.clear()
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => { alive = false }
  }, [])

  // Idle-timeout watchdog (only while authenticated)
  useEffect(() => {
    if (!investigator) return
    const reset = () => {
      if (idleTimer.current) window.clearTimeout(idleTimer.current)
      idleTimer.current = window.setTimeout(() => { void doLogout() }, IDLE_TIMEOUT_MS)
    }
    const events = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart']
    events.forEach(e => window.addEventListener(e, reset, { passive: true }))
    reset()
    return () => {
      events.forEach(e => window.removeEventListener(e, reset))
      if (idleTimer.current) window.clearTimeout(idleTimer.current)
    }
  }, [investigator, doLogout])

  const login = useCallback(async (id: string, password: string, remember: boolean) => {
    const inv = await authApi.login(id, password, remember)
    setInvestigator(inv)
  }, [])

  const register = useCallback(async (payload: RegisterPayload) => {
    const inv = await authApi.register(payload)
    setInvestigator(inv)
  }, [])

  const setAvatar = useCallback(async (avatar: string) => {
    const inv = await authApi.setAvatar(avatar)
    setInvestigator(inv)
  }, [])

  const refreshProfile = useCallback(async () => {
    try {
      const { investigator } = await authApi.me()
      setInvestigator(investigator)
    } catch { /* ignore */ }
  }, [])

  return (
    <AuthContext.Provider value={{ investigator, loading, login, register, setAvatar, logout: doLogout, refreshProfile }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
