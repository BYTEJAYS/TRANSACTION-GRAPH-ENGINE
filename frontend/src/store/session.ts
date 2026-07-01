// ── INVESTIGATION SESSION STORE ───────────────────────────────────────────────
// A single, application-wide investigation session that lives OUTSIDE the React
// route tree. Pages mount and unmount as the investigator navigates, but this
// store does not — so graph selections, recovery analyses, case
// filters, search results, UB conversations and the current view all survive
// navigation AND a browser refresh.
//
// Design: a dependency-free module singleton (no Zustand/Redux needed — the
// codebase already rolls its own stores) exposed to React via useSyncExternalStore,
// with debounced localStorage persistence (auto-save) and a schema version guard.
//
// RULE: investigation DATA belongs here. Page-level useState is only for ephemeral
// UI (hovers, transient inputs). Anything an investigator would be upset to lose
// on navigation lives in this store.
import { useSyncExternalStore } from 'react'

const KEY = 'tgie.session.v1'
const SAVE_DEBOUNCE_MS = 400

export interface RecoverySlice {
  selectedCase: string | null
  panel: 'plan' | 'why' | 'ub' | null
  byCase: Record<string, unknown>           // case_id -> RecoveryAnalysis (cached)
  simByCase: Record<string, unknown>        // case_id -> last simulation result
}
export interface CasesSlice {
  filters: Record<string, unknown>          // list filters (status/priority/query/sort)
  selected: string | null
}
export interface SearchSlice {
  query: string
  results: unknown | null                   // last global-search payload
}
// UB conversation, keyed by a context id (e.g. `recovery:CASE`)
export type UbThread = { role: 'user' | 'ub'; text: string }[]

export interface SessionState {
  // navigation + resume
  lastPath: string
  startedAt: number
  updatedAt: number
  resumeDismissed: boolean
  // shared investigation context
  currentCaseId: string | null
  currentAccount: string | null
  // per-area state + result caches (serialisable, modest in size)
  recovery: RecoverySlice
  cases: CasesSlice
  search: SearchSlice
  ub: Record<string, UbThread>
}

function emptyState(): SessionState {
  const now = Date.now()
  return {
    lastPath: '/graph',
    startedAt: now,
    updatedAt: now,
    resumeDismissed: false,
    currentCaseId: null,
    currentAccount: null,
    recovery: { selectedCase: null, panel: null, byCase: {}, simByCase: {} },
    cases: { filters: {}, selected: null },
    search: { query: '', results: null },
    ub: {},
  }
}

function load(): SessionState {
  if (typeof window === 'undefined') return emptyState()
  try {
    const raw = window.localStorage.getItem(KEY)
    if (!raw) return emptyState()
    const parsed = JSON.parse(raw)
    // shallow-merge over defaults so older/partial payloads never crash the app
    const base = emptyState()
    return {
      ...base, ...parsed,
      recovery: { ...base.recovery, ...(parsed.recovery ?? {}) },
      cases: { ...base.cases, ...(parsed.cases ?? {}) },
      search: { ...base.search, ...(parsed.search ?? {}) },
      ub: { ...(parsed.ub ?? {}) },
    }
  } catch {
    return emptyState()
  }
}

let state: SessionState = load()
const listeners = new Set<() => void>()

let saveTimer: ReturnType<typeof setTimeout> | null = null
function persist() {
  if (typeof window === 'undefined') return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    try { window.localStorage.setItem(KEY, JSON.stringify(state)) } catch { /* quota / private mode — ignore */ }
  }, SAVE_DEBOUNCE_MS)
}

function emit() {
  state = { ...state, updatedAt: Date.now() }
  listeners.forEach(l => l())
  persist()
}

export const sessionStore = {
  get: () => state,
  subscribe(fn: () => void) { listeners.add(fn); return () => { listeners.delete(fn) } },

  /** Patch the top level of the session (shallow). */
  set(patch: Partial<SessionState>) { state = { ...state, ...patch }; emit() },

  /** Patch one slice (shallow-merged into the existing slice). */
  patch<K extends keyof SessionState>(key: K, value: Partial<SessionState[K]>) {
    state = { ...state, [key]: { ...(state[key] as object), ...(value as object) } as SessionState[K] }
    emit()
  },

  // ── focused helpers ────────────────────────────────────────────────────────
  setPath(path: string) { if (path !== state.lastPath) { state = { ...state, lastPath: path }; emit() } },
  setCurrentCase(id: string | null) { if (id !== state.currentCaseId) { state = { ...state, currentCaseId: id }; emit() } },
  setCurrentAccount(acc: string | null) { if (acc !== state.currentAccount) { state = { ...state, currentAccount: acc }; emit() } },

  cacheRecovery(caseId: string, analysis: unknown) {
    state = { ...state, recovery: { ...state.recovery, byCase: { ...state.recovery.byCase, [caseId]: analysis } } }
    emit()
  },
  cacheRecoverySim(caseId: string, sim: unknown) {
    state = { ...state, recovery: { ...state.recovery, simByCase: { ...state.recovery.simByCase, [caseId]: sim } } }
    emit()
  },
  ubThread(ctx: string) { return state.ub[ctx] ?? [] },
  pushUb(ctx: string, ...turns: UbThread) {
    const next = [...(state.ub[ctx] ?? []), ...turns].slice(-40)
    state = { ...state, ub: { ...state.ub, [ctx]: next } }
    emit()
  },

  /** Wipe everything (e.g. "start a new investigation" or on logout). */
  reset() { state = emptyState(); emit() },
}

/** Subscribe to a derived slice of the session in a component. */
export function useSession<T>(selector: (s: SessionState) => T): T {
  return useSyncExternalStore(sessionStore.subscribe, () => selector(state), () => selector(state))
}
