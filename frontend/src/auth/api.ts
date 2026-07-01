// ── Auth + account-intelligence API client ───────────────────────────────────
// All calls ride the existing /api Vite proxy → FastAPI backend (:8000).
import { apiUrl } from '../config'

const ACCESS_KEY = 'tgie.access'
const REFRESH_KEY = 'tgie.refresh'

export const tokenStore = {
  get access() { return localStorage.getItem(ACCESS_KEY) },
  get refresh() { return localStorage.getItem(REFRESH_KEY) },
  set(access: string, refresh?: string) {
    localStorage.setItem(ACCESS_KEY, access)
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

export interface Investigator {
  investigator_id: string
  name: string
  employee_id: string
  department: string
  role: string
  branch: string
  email: string
  avatar_initials: string
  avatar: string
  last_login: number | null
}

export interface AccountSummary {
  account_number: string
  customer_name: string
  customer_id: string
  bank: string
  risk_score: number
  risk_band: string
  status: string
  investigation_status: string
  transaction_count: number
  linked_count: number
}

export interface AccountActivity {
  txn_id: string
  label: string
  direction: 'credit' | 'debit'
  amount: number
  rail: string
  counterparty: string
  hours_ago: number
}

export interface AccountDetail extends AccountSummary {
  ifsc: string
  balance: number
  opened_on: string
  flags: string[]
  linked_accounts: string[]
  recent_activity: AccountActivity[]
  cases: { case_id: string; title: string; opened: string }[]
  evidence: { evidence_id: string; type: string; anchored: boolean }[]
  linked_account_cards: AccountSummary[]
}

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let onAuthFailure: (() => void) | null = null
export function setAuthFailureHandler(fn: () => void) { onAuthFailure = fn }

async function refreshAccess(): Promise<boolean> {
  const refresh = tokenStore.refresh
  if (!refresh) return false
  try {
    const r = await fetch(apiUrl('/api/auth/refresh'), {
      method: 'POST',
      headers: { Authorization: `Bearer ${refresh}` },
    })
    if (!r.ok) return false
    const data = await r.json()
    tokenStore.set(data.access_token)
    return true
  } catch {
    return false
  }
}

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  const access = tokenStore.access
  if (access) headers.set('Authorization', `Bearer ${access}`)

  const res = await fetch(apiUrl(path), { ...init, headers })

  if (res.status === 401 && retry) {
    // attempt a silent refresh, then replay once
    if (await refreshAccess()) return request<T>(path, init, false)
    tokenStore.clear()
    onAuthFailure?.()
  }

  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* ignore */ }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

// Shared authenticated request (token + silent refresh + 401 handling) for other
// API clients (e.g. the Case Management client).
export function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  return request<T>(path, init)
}

export interface RegisterPayload {
  investigator_id: string
  password: string
  name: string
  employee_id: string
  department: string
  role: string
  branch: string
  email: string
}

export const authApi = {
  async login(investigator_id: string, password: string, remember_device: boolean) {
    const res = await fetch(apiUrl('/api/auth/login'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ investigator_id, password, remember_device }),
    })
    if (!res.ok) {
      let detail = 'Login failed'
      try { detail = (await res.json()).detail ?? detail } catch { /* ignore */ }
      throw new ApiError(res.status, detail)
    }
    const data = await res.json()
    tokenStore.set(data.access_token, data.refresh_token)
    return data.investigator as Investigator
  },

  async register(payload: RegisterPayload) {
    const res = await fetch(apiUrl('/api/auth/register'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) {
      let detail = 'Registration failed'
      try { detail = (await res.json()).detail ?? detail } catch { /* ignore */ }
      throw new ApiError(res.status, detail)
    }
    const data = await res.json()
    tokenStore.set(data.access_token, data.refresh_token)
    return data.investigator as Investigator
  },

  async roles(): Promise<string[]> {
    try {
      const res = await fetch(apiUrl('/api/auth/roles'))
      if (res.ok) return (await res.json()).roles as string[]
    } catch { /* ignore */ }
    return ['Investigator', 'Senior Investigator', 'Supervisor', 'Administrator']
  },

  async logout() {
    try { await request('/api/auth/logout', { method: 'POST' }, false) } catch { /* ignore */ }
    tokenStore.clear()
  },

  me() { return request<{ investigator: Investigator }>('/api/auth/me') },

  async setAvatar(avatar: string) {
    const data = await request<{ investigator: Investigator }>('/api/investigator/avatar', {
      method: 'POST',
      body: JSON.stringify({ avatar }),
    })
    return data.investigator
  },

  searchAccounts(q: string) {
    return request<{ query: string; resolved_account: string | null; count: number; results: AccountSummary[] }>(
      `/api/accounts/search?q=${encodeURIComponent(q)}`
    )
  },

  account(accountNumber: string) {
    return request<AccountDetail>(`/api/accounts/${encodeURIComponent(accountNumber)}`)
  },

  profile() {
    return request<{
      profile: Investigator
      session: { started_at: number | null; ip: string | null; expires_at: number; now: number }
      recent_activity: { ts: number; action: string; result: string; detail: string }[]
    }>('/api/investigator/profile')
  },
}

export { ApiError }
