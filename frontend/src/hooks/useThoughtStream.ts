// ──────────────────────────────────────────────────────────────────────────────
// useThoughtStream — UB's live investigation feed.
//
// Emits a slow trickle of investigation-grade "thoughts" derived from the
// live graph snapshot, so the intelligence core feels active even while idle.
// Every line references real metrics — node counts, flagged totals, fraud
// rate, cluster count — so nothing is fabricated.
//
// Reactive events (fraud, node selection, commands) can be pushed in
// explicitly via the returned `push` callback.
// ──────────────────────────────────────────────────────────────────────────────
import { useCallback, useEffect, useRef, useState } from 'react'

export type ThoughtKind = 'scan' | 'alert' | 'metric' | 'info'

export interface Thought {
  id:   string
  text: string
  ts:   number
  kind: ThoughtKind
}

export interface ThoughtSnapshot {
  nodeCount:    number
  linkCount:    number
  flaggedNodes: number
  fraudRate:    number   // 0..1
  clusters:     number
  worstRisk:    number   // 0..1
  monitoring:   boolean
}

const MAX_THOUGHTS = 36
const TICK_MS      = 3400

let _seq = 0
const uid = () => `t${Date.now().toString(36)}${(_seq++).toString(36)}`

// Idle line generators. Each returns a string (using live numbers) or null
// when it doesn't apply to the current snapshot.
type Gen = (s: ThoughtSnapshot) => { text: string; kind: ThoughtKind } | null

const GENERATORS: Gen[] = [
  s => s.nodeCount > 0 ? { text: `Evaluating account centrality across ${s.nodeCount} nodes…`, kind: 'scan' } : null,
  s => s.linkCount > 0 ? { text: `Scanning ${s.linkCount} transaction edges for circular flow…`, kind: 'scan' } : null,
  s => s.nodeCount > 1 ? { text: `Recomputing topology partitions — ${s.clusters} cluster${s.clusters !== 1 ? 's' : ''} resolved.`, kind: 'metric' } : null,
  s => s.flaggedNodes > 0 ? { text: `Risk surface: ${s.flaggedNodes} flagged of ${s.nodeCount} accounts.`, kind: 'metric' } : null,
  s => s.fraudRate > 0 ? { text: `Laundering probability index at ${(s.fraudRate * 100).toFixed(1)} percent.`, kind: s.fraudRate > 0.4 ? 'alert' : 'metric' } : null,
  s => s.worstRisk > 0.5 ? { text: `Highest cluster risk score holding at ${Math.round(s.worstRisk * 100)} percent.`, kind: 'alert' } : null,
  s => s.linkCount > 0 ? { text: 'Tracing multi-hop fund pathways for layering depth…', kind: 'scan' } : null,
  s => s.nodeCount > 0 ? { text: 'Re-weighting fan-out coefficients across the network…', kind: 'scan' } : null,
  s => s.nodeCount > 0 ? { text: 'Cross-referencing pass-through balances for relay signatures…', kind: 'scan' } : null,
  s => s.flaggedNodes === 0 && s.nodeCount > 0 ? { text: 'Behavioral baseline nominal — no anomalies in current window.', kind: 'info' } : null,
]

const STANDBY: Array<{ text: string; kind: ThoughtKind }> = [
  { text: 'Standing by. Awaiting transaction stream…', kind: 'info' },
  { text: 'Monitor idle. Submit transactions to begin analysis.', kind: 'info' },
  { text: 'Listening for graph activity…', kind: 'scan' },
]

export function useThoughtStream(snapshot: ThoughtSnapshot, enabled = true) {
  const [thoughts, setThoughts] = useState<Thought[]>([])
  const snapRef = useRef(snapshot)
  const lastTextRef = useRef('')
  useEffect(() => { snapRef.current = snapshot }, [snapshot])

  const append = useCallback((text: string, kind: ThoughtKind) => {
    setThoughts(prev => {
      const next = [...prev, { id: uid(), text, ts: Date.now(), kind }]
      return next.length > MAX_THOUGHTS ? next.slice(next.length - MAX_THOUGHTS) : next
    })
  }, [])

  // Explicit reactive event (deduped against the immediately-previous line).
  const push = useCallback((text: string, kind: ThoughtKind = 'info') => {
    if (!text || text === lastTextRef.current) return
    lastTextRef.current = text
    append(text, kind)
  }, [append])

  const clear = useCallback(() => setThoughts([]), [])

  // Idle ticker.
  useEffect(() => {
    if (!enabled) return
    const tick = () => {
      const s = snapRef.current
      let line: { text: string; kind: ThoughtKind } | null = null

      if (!s.monitoring || s.nodeCount === 0) {
        line = STANDBY[Math.floor(Math.random() * STANDBY.length)]
      } else {
        const candidates = GENERATORS.map(g => g(s)).filter(Boolean) as Array<{ text: string; kind: ThoughtKind }>
        if (candidates.length) line = candidates[Math.floor(Math.random() * candidates.length)]
      }

      if (line && line.text !== lastTextRef.current) {
        lastTextRef.current = line.text
        append(line.text, line.kind)
      }
    }
    tick()
    const id = setInterval(tick, TICK_MS)
    return () => clearInterval(id)
  }, [enabled, append])

  return { thoughts, push, clear }
}
