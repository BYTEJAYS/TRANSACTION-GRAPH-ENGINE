// Cases resource — v1-first with legacy fallback (Phase 6 cutover starts here).
import { api, type Page } from '../api'

// Cases carry a large enrich payload; keep the type permissive at this layer.
export type CaseRecord = Record<string, unknown> & {
  case_id: string
  title?: string
  status?: string
  priority?: string
  risk_score?: number
  assigned_to?: string
}

export const casesApi = {
  /** Paginated list. Uses /api/v1/cases; falls back to legacy /api/cases. */
  list(params: { limit?: number; cursor?: string | null; status?: string } = {}): Promise<Page<CaseRecord>> {
    return api.v1First(
      () => api.getPage<CaseRecord>('/api/v1/cases', params),
      async () => {
        // legacy returns the full set; adapt to the Page shape so callers are uniform
        const raw = await api.get<CaseRecord[] | { cases: CaseRecord[] }>('/api/cases')
        const items = Array.isArray(raw) ? raw : (raw.cases ?? [])
        const filtered = params.status ? items.filter(c => c.status === params.status) : items
        return { items: filtered, next_cursor: null, limit: filtered.length }
      },
    )
  },

  get(caseId: string): Promise<CaseRecord> {
    const id = encodeURIComponent(caseId)
    return api.v1First(
      () => api.get<CaseRecord>(`/api/v1/cases/${id}`),
      () => api.get<CaseRecord>(`/api/cases/${id}`),
    )
  },
}
