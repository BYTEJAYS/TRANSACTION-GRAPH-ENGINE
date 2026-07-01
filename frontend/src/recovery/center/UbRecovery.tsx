// ── UB Recovery Analyst ──────────────────────────────────────────────────────
// A senior fund-recovery officer on the right rail. On every case it proactively
// generates a recovery summary, then answers follow-ups in plain banking
// language. Every prompt hits /api/recovery/explain (UB / Ollama) with a
// deterministic fallback, so it always responds.
import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Brain, Sparkles, FileSignature } from 'lucide-react'
import { T } from '../../theme'
import { recoveryApi } from '../api'
import { sessionStore } from '../../store/session'

const PROMPTS = [
  'Explain the recovery score',
  'Best intervention',
  'Freeze strategy',
  'What accounts to freeze?',
  'Summarise for the manager',
  'Suggested questions',
]

export function UbRecovery({ caseId }: { caseId: string }) {
  // Conversation persists in the investigation session (thread[0] = proactive
  // summary, then user/ub follow-ups), so UB never forgets when pages change.
  const ctx = `recovery:${caseId}`
  const seed = sessionStore.ubThread(ctx)
  const lastUb = [...seed].slice(1).reverse().find(t => t.role === 'ub')
  const [summary, setSummary] = useState<string>(seed[0]?.role === 'ub' ? seed[0].text : '')
  const [summaryLoading, setSummaryLoading] = useState(seed.length === 0)
  const [answer, setAnswer] = useState<string | null>(lastUb?.text ?? null)
  const [busy, setBusy] = useState(false)
  const [active, setActive] = useState<string | null>(null)

  // proactive recovery summary — restored from the session if already generated
  useEffect(() => {
    let alive = true
    const existing = sessionStore.ubThread(ctx)
    const prevAns = [...existing].slice(1).reverse().find(t => t.role === 'ub')
    setActive(null)
    setAnswer(prevAns?.text ?? null)
    if (existing[0]?.role === 'ub') {
      setSummary(existing[0].text); setSummaryLoading(false)
      return () => { alive = false }
    }
    setSummaryLoading(true); setSummary('')
    recoveryApi.explain(caseId, 'Give a concise recovery summary: where the funds are, who controls them, and the single most important intervention.')
      .then(r => { if (alive) { setSummary(r.answer); sessionStore.pushUb(ctx, { role: 'ub', text: r.answer }) } })
      .catch(() => { if (alive) setSummary('Recovery desk offline — the factors, flow map and ranked actions on this page reflect the same analysis.') })
      .finally(() => { if (alive) setSummaryLoading(false) })
    return () => { alive = false }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId])

  async function ask(q: string) {
    setActive(q); setBusy(true); setAnswer('Analysing recovery posture…')
    try {
      const r = await recoveryApi.explain(caseId, q)
      setAnswer(r.answer)
      sessionStore.pushUb(ctx, { role: 'user', text: q }, { role: 'ub', text: r.answer })
    }
    catch { setAnswer('UB is unreachable right now — the recovery factors and ranked actions on this page reflect the same analysis.') }
    finally { setBusy(false) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 13 }}>
        <div style={{ position: 'relative', width: 32, height: 32, borderRadius: '50%', display: 'grid', placeItems: 'center', background: T.goldDim, border: `1px solid ${T.goldLine}` }}>
          <Brain size={17} color={T.gold} />
          <motion.div style={{ position: 'absolute', inset: -2, borderRadius: '50%', border: `1px solid ${T.gold}` }}
            animate={{ opacity: [0.5, 0, 0.5], scale: [1, 1.3, 1] }} transition={{ duration: 3.4, repeat: Infinity }} />
        </div>
        <div>
          <div style={{ fontSize: 12.5, fontWeight: 700, color: T.text }}>UB · Recovery Analyst</div>
          <div style={{ fontSize: 9.5, color: T.success }}>● online · senior fund-recovery desk</div>
        </div>
      </div>

      {/* proactive recovery summary */}
      <div style={{ background: 'linear-gradient(135deg, rgba(198,162,83,0.07), rgba(20,22,27,0.5))', border: `1px solid ${T.goldLine}`, borderRadius: 11, padding: '12px 13px', marginBottom: 11 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 8 }}>
          <FileSignature size={12} color={T.gold} />
          <span style={{ fontSize: 9.5, letterSpacing: '.1em', color: T.gold, fontWeight: 700 }}>RECOVERY SUMMARY</span>
        </div>
        <AnimatePresence mode="wait">
          <motion.div key={summary || 'loading'} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            style={{ fontSize: 11.5, lineHeight: 1.6, color: T.text2, whiteSpace: 'pre-wrap' }}>
            {summaryLoading
              ? <span style={{ color: T.text3 }}><Sparkles size={12} color={T.gold} style={{ verticalAlign: -2, marginRight: 5 }} />Generating recovery summary…</span>
              : summary}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* follow-up answer */}
      <div style={{ flex: 1, minHeight: 90, background: T.bg2, border: `1px solid ${T.border}`, borderRadius: 10, padding: '12px 13px', overflowY: 'auto' }}>
        <AnimatePresence mode="wait">
          <motion.div key={answer ?? 'idle'} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            style={{ fontSize: 12, lineHeight: 1.6, color: T.text2, whiteSpace: 'pre-wrap' }}>
            {busy && <Sparkles size={13} color={T.gold} style={{ verticalAlign: -2, marginRight: 6 }} />}
            {answer ?? 'Ask a follow-up — recovery score, what to freeze first, the strongest intervention, or a manager-ready summary.'}
          </motion.div>
        </AnimatePresence>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 11 }}>
        {PROMPTS.map(p => (
          <button key={p} onClick={() => ask(p)} disabled={busy}
            style={{
              fontSize: 10.5, color: active === p ? T.textOn : T.text2,
              background: active === p ? T.gold : T.raised,
              border: `1px solid ${active === p ? T.gold : T.border}`,
              borderRadius: 7, padding: '6px 9px', cursor: busy ? 'default' : 'pointer', fontFamily: T.font,
            }}>
            {p}
          </button>
        ))}
      </div>
    </div>
  )
}
