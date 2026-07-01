// Resource API modules (v1-first with legacy fallback). Thin, typed wrappers
// over the central client so panels never call fetch() directly.
import { api } from '../api'

export interface AlertRecord {
  alert_id: string; alert_type?: string; severity?: string
  risk_score?: number; description?: string; timestamp?: string
  accounts_involved?: string[]
}

export const alertsApi = {
  list: () => api.v1First(
    () => api.get<{ items: AlertRecord[] }>('/api/v1/alerts').then(r => r.items),
    () => api.get<AlertRecord[]>('/api/alerts'),
  ),
}

export const riskApi = {
  // cumulative multi-factor risk for a component/account (graceful: returns null)
  assess: (id: string) => api.get<any>(`/api/risk/assess/${encodeURIComponent(id)}`).catch(() => null),
  stats: () => api.get<any>('/api/stats').catch(() => null),
}

export const auditApi = {
  recent: (limit = 100) =>
    api.get<{ items: any[] }>(`/api/v1/audit/recent?limit=${limit}`).then(r => r.items).catch(() => []),
}

export const evidenceApi = {
  generate: (payload: unknown) => api.post<any>('/api/evidence/generate', payload),
  list: () => api.get<any>('/api/evidence/list').catch(() => ({ files: [] })),
}

export const replayApi = {
  recent: () => api.get<any>('/api/replay/recent', { session: true }).catch(() => ({ events: [] })),
}
