// ──────────────────────────────────────────────────────────────────────────────
// ubBrain — frontend client for the local UB (Universal Brain) cognitive layer.
//
// Lets the voice orb (and any component) ask the local Ollama-backed RAG service
// mounted on the TGIE backend at /ub/*. Dev: Vite proxies /ub → :8000. Prod: set
// VITE_API_URL (apiUrl prefixes it).
// ──────────────────────────────────────────────────────────────────────────────
import { apiUrl } from '../config'

export interface UBSource { component: string; path: string; lines: string; score: number }
export interface UBReply { mode: string; answer: string; sources: UBSource[]; model: string }

export type UBMode = 'chat' | 'founder' | 'developer' | 'presentation' | 'demo' | 'judge'

/** A stable session id so spoken conversation keeps multi-turn memory. */
export const VOICE_SESSION = 'voice-orb'

/**
 * Ask UB a free-form question. Resolves to the grounded answer.
 * Throws if the service/Ollama is unavailable so callers can fall back gracefully.
 */
export async function askUB(
  message: string,
  mode: UBMode = 'chat',
  opts: { sessionId?: string; signal?: AbortSignal; timeoutMs?: number } = {},
): Promise<UBReply> {
  const { sessionId = VOICE_SESSION, signal, timeoutMs = 30000 } = opts
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  // chain an external abort signal into our timeout controller
  if (signal) signal.addEventListener('abort', () => ctrl.abort(), { once: true })
  try {
    const r = await fetch(apiUrl('/ub/chat'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, mode, session_id: sessionId }),
      signal: ctrl.signal,
    })
    if (!r.ok) throw new Error(`UB service ${r.status}`)
    return (await r.json()) as UBReply
  } finally {
    clearTimeout(timer)
  }
}

/** Is the local UB brain reachable right now? (used to decide whether to route voice to it) */
export async function ubAvailable(): Promise<boolean> {
  try {
    const r = await fetch(apiUrl('/ub/health'), { method: 'GET' })
    if (!r.ok) return false
    const h = await r.json()
    return Boolean(h?.up && h?.model_available)
  } catch {
    return false
  }
}
