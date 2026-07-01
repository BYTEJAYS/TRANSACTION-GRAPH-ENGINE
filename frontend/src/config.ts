// In production set VITE_API_URL=https://your-backend.onrender.com
// In dev the Vite proxy handles all /api, /transaction, /graph, /ws routes
export const API_BASE: string = import.meta.env.VITE_API_URL ?? ''

// ── Per-browser session id ─────────────────────────────────────────────────
// A fresh id per page load isolates this tab's graph from every other browser
// on the backend (sent as ?session= on the WS and X-Session-Id on requests).
// New id each load → opening/reloading always starts from a clean, private graph.
export const SESSION_ID: string =
  (typeof crypto !== 'undefined' && 'randomUUID' in crypto)
    ? crypto.randomUUID()
    : `s_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`

const WS_BASE: string = API_BASE
  ? `${API_BASE.replace('https://', 'wss://').replace('http://', 'ws://')}/ws/live`
  : `${typeof location !== 'undefined' && location.protocol === 'https:' ? 'wss' : 'ws'}://${typeof location !== 'undefined' ? location.host : 'localhost:3000'}/ws/live`

export const WS_URL: string = `${WS_BASE}?session=${encodeURIComponent(SESSION_ID)}`

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}

// ── BELS — Blockchain Evidence Ledger ──────────────────────────────────────
// The evidence-anchoring service runs as a separate module (default :8200).
// Override with VITE_BELS_API in production.
export const BELS_API: string = import.meta.env.VITE_BELS_API ?? 'http://localhost:8200'

export function belsUrl(path: string): string {
  return `${BELS_API}${path}`
}

// Headers to attach to every state-changing request so the backend routes the
// work to THIS browser's session.
export function sessionHeaders(extra?: Record<string, string>): Record<string, string> {
  return { 'X-Session-Id': SESSION_ID, ...(extra ?? {}) }
}
