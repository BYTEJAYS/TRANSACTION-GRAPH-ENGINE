// Central typed API client (Phase 6).
//
// One place for HTTP: reuses the existing auth-aware request (JWT + silent
// refresh + 401 handling) from auth/api.ts and the per-session headers from
// config.ts, and adds cursor pagination + a v1-first/legacy fallback helper.
// The 9 scattered fetch() callers migrate behind typed resource modules
// (services/resources/*).

import { apiRequest, ApiError } from '../auth/api'
import { sessionHeaders } from '../config'

export { ApiError }

export interface Page<T> {
  items: T[]
  next_cursor: string | null
  limit: number
}

export interface PageParams {
  limit?: number
  cursor?: string | null
  // extra query params (status filters etc.)
  [k: string]: string | number | null | undefined
}

function qs(params: PageParams): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export const api = {
  /** Authenticated GET. Pass `session:true` to attach X-Session-Id (graph routes). */
  get<T>(path: string, opts: { session?: boolean } = {}): Promise<T> {
    return apiRequest<T>(path, { headers: opts.session ? sessionHeaders() : undefined })
  },

  post<T>(path: string, body?: unknown, opts: { session?: boolean } = {}): Promise<T> {
    return apiRequest<T>(path, {
      method: 'POST',
      body: body !== undefined ? JSON.stringify(body) : undefined,
      headers: opts.session ? sessionHeaders() : undefined,
    })
  },

  /** Paginated GET returning {items,next_cursor,limit}. */
  getPage<T>(path: string, params: PageParams = {}): Promise<Page<T>> {
    const { limit = 50, cursor, ...rest } = params
    return apiRequest<Page<T>>(`${path}${qs({ limit, cursor, ...rest })}`)
  },

  /**
   * Try the v1 path; if it 404s (router not mounted yet) fall back to legacy.
   * Lets the frontend cut over to /api/v1 per-resource without a big-bang.
   */
  async v1First<T>(v1: () => Promise<T>, legacy: () => Promise<T>): Promise<T> {
    try {
      return await v1()
    } catch (e) {
      if (e instanceof ApiError && (e.status === 404 || e.status === 405)) return legacy()
      throw e
    }
  },
}
