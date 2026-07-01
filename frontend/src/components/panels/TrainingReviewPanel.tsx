// ──────────────────────────────────────────────────────────────────────────────
// TrainingReviewPanel — LOCALHOST-only human-in-the-loop training queue.
//
// The ONLY door into the Blue Team's knowledge base. When the Blue Team MISSES a
// Red Team evasion, the case is enqueued here. The investigator reviews each case
// and decides — "Learn from this Case" is the only action that adds it to the Blue
// Knowledge Base (deduped + audited). Detected attacks never appear here (those
// drive the Red Team to evolve a harder variant instead).
//
// Backed by /api/redteam/training/{queue,decide,audit,similar,reset}.
// ──────────────────────────────────────────────────────────────────────────────
import { useEffect, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, GraduationCap, RefreshCw, Check, Ban, Archive, Eye, GitCompare, ScrollText, ShieldAlert } from 'lucide-react'
import { apiUrl } from '../../config'

const C = {
  glass: 'rgba(234,229,219,0.96)', glassHi: 'rgba(225,219,207,0.97)', raised: 'rgba(243,239,231,0.82)',
  border: 'rgba(70,60,48,0.16)', text1: '#352f27', text2: '#6b6052', text3: '#9d9180',
  red: '#bd4040', redDim: 'rgba(189,64,64,0.10)', green: '#4a8a52', greenDim: 'rgba(74,138,82,0.13)',
  amber: '#b07d22', amberDim: 'rgba(176,125,34,0.14)', cyan: '#3f7ab5', cyanDim: 'rgba(63,122,181,0.12)',
} as const
const MONO = '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace'
const PANEL_W = 500

interface GNode { id: string; role: 'source' | 'sink' | 'relay' }
interface GEdge { source: string; target: string; amount: number }
type Status = 'pending' | 'reviewing' | 'learned' | 'rejected' | 'archived' | 'ignored'
interface Case {
  case_id: string; candidate_id: string; created_iso: string
  detection_status: string; red_confidence: number; blue_confidence: number
  fraud_type: string; risk_score: number; explanation: string; techniques: string[]
  status: Status; duplicate_of: string | null; nodes_total: number; edges_total: number
  signature: string; graph: { nodes: GNode[]; edges: GEdge[]; shown_edges: number }
}
interface Stats {
  total: number; pending: number; reviewing: number; learned: number; rejected: number
  archived: number; ignored: number; knowledge_base: number; audit_events: number
}
interface AuditEntry {
  case_id: string; generated_by: string; blue_result: string; investigator: string
  decision: string; training_status: string; note: string; time: string
}
interface Similar { case_id: string; fraud_type: string; status: Status; match: 'exact' | 'similar'; technique_overlap: number }

const roleColor = (r: GNode['role']) => r === 'source' ? C.red : r === 'sink' ? C.amber : C.cyan

// ── compact source→relay→sink graph viz (Review Graph) ──
function MiniGraph({ g }: { g: Case['graph'] }) {
  const W = 452, H = 132, pad = 14
  const cols: Record<string, GNode[]> = { source: [], relay: [], sink: [] }
  g.nodes.forEach(n => cols[n.role].push(n))
  const xOf = { source: pad + 8, relay: W / 2, sink: W - pad - 8 } as Record<string, number>
  const pos: Record<string, { x: number; y: number }> = {}
  ;(['source', 'relay', 'sink'] as const).forEach(role => {
    const arr = cols[role]
    arr.forEach((n, i) => {
      const y = arr.length === 1 ? H / 2 : pad + (i / (arr.length - 1)) * (H - 2 * pad)
      pos[n.id] = { x: xOf[role], y }
    })
  })
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block', background: 'rgba(255,255,255,0.4)', borderRadius: 6 }}>
      {g.edges.map((e, i) => {
        const a = pos[e.source], b = pos[e.target]
        if (!a || !b) return null
        return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="rgba(70,60,48,0.22)" strokeWidth={0.8} />
      })}
      {Object.entries(pos).map(([id, p]) => {
        const node = g.nodes.find(n => n.id === id)!
        return <circle key={id} cx={p.x} cy={p.y} r={3.4} fill={roleColor(node.role)} />
      })}
    </svg>
  )
}

const Pct = ({ v, c }: { v: number; c: string }) => (
  <span style={{ color: c, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{Math.round(v * 100)}%</span>
)

export function TrainingReviewPanel({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const [cases, setCases] = useState<Case[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [tab, setTab] = useState<'queue' | 'audit'>('queue')
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [similar, setSimilar] = useState<Record<string, Similar[]>>({})
  const [flash, setFlash] = useState<Record<string, string>>({})

  const loadQueue = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch(apiUrl('/api/redteam/training/queue'))
      const d = await r.json()
      if (d.ok) { setCases(d.cases); setStats(d.stats) }
    } catch { /* offline */ } finally { setLoading(false) }
  }, [])

  const loadAudit = useCallback(async () => {
    try {
      const r = await fetch(apiUrl('/api/redteam/training/audit?limit=60'))
      const d = await r.json()
      if (d.ok) { setAudit(d.audit); setStats(d.stats) }
    } catch { /* offline */ }
  }, [])

  useEffect(() => { if (isOpen) { loadQueue(); loadAudit() } }, [isOpen, loadQueue, loadAudit])

  const decide = useCallback(async (caseId: string, action: string) => {
    try {
      const r = await fetch(apiUrl('/api/redteam/training/decide'), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ case_id: caseId, action, investigator: 'investigator' }),
      })
      const d = await r.json()
      if (d.ok) {
        const msg = d.dedup?.merged_into
          ? `merged into ${d.dedup.merged_into} (×${d.dedup.count})`
          : d.audit?.training_status ?? action
        setFlash(f => ({ ...f, [caseId]: msg }))
        await loadQueue(); await loadAudit()
      }
    } catch { /* offline */ }
  }, [loadQueue, loadAudit])

  const compare = useCallback(async (caseId: string) => {
    try {
      const r = await fetch(apiUrl(`/api/redteam/training/similar?case_id=${caseId}`))
      const d = await r.json()
      if (d.ok) setSimilar(s => ({ ...s, [caseId]: d.similar }))
    } catch { /* offline */ }
  }, [])

  const pending = cases.filter(c => c.status === 'pending' || c.status === 'reviewing')
  const decided = cases.filter(c => c.status !== 'pending' && c.status !== 'reviewing')

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ x: PANEL_W }} animate={{ x: 0 }} exit={{ x: PANEL_W }}
          transition={{ type: 'spring', stiffness: 320, damping: 34 }}
          style={{
            position: 'fixed', top: 0, right: 0, bottom: 0, width: PANEL_W, zIndex: 60,
            background: C.glass, backdropFilter: 'blur(22px)', borderLeft: `1px solid ${C.border}`,
            boxShadow: '-12px 0 40px rgba(0,0,0,0.22)', display: 'flex', flexDirection: 'column',
            fontFamily: MONO, color: C.text1,
          }}
        >
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '13px 16px', borderBottom: `1px solid ${C.border}`, background: C.glassHi }}>
            <GraduationCap size={16} color={C.green} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: '.06em' }}>TRAINING REVIEW</div>
              <div style={{ fontSize: 8.5, color: C.text3, letterSpacing: '.04em' }}>human-in-the-loop · nothing learns without your approval</div>
            </div>
            <button onClick={() => { loadQueue(); loadAudit() }} title="refresh" style={iconBtn}><RefreshCw size={13} color={C.text2} /></button>
            <button onClick={onClose} title="close" style={iconBtn}><X size={15} color={C.text2} /></button>
          </div>

          {/* Stat strip */}
          {stats && (
            <div style={{ display: 'flex', gap: 12, padding: '7px 16px', borderBottom: `1px solid ${C.border}`, fontSize: 9.5, color: C.text2, background: C.raised }}>
              <span title="awaiting your review">⏳ pending <b style={{ color: C.amber }}>{stats.pending}</b></span>
              <span title="added to the Blue Knowledge Base">🎓 learned <b style={{ color: C.green }}>{stats.learned}</b></span>
              <span title="distinct patterns in the Blue Knowledge Base">📚 KB <b style={{ color: C.cyan }}>{stats.knowledge_base}</b></span>
              <span title="discarded">🗑 discarded <b>{stats.rejected + stats.ignored + stats.archived}</b></span>
            </div>
          )}

          {/* Tabs */}
          <div style={{ display: 'flex', borderBottom: `1px solid ${C.border}` }}>
            {(['queue', 'audit'] as const).map(t => (
              <button key={t} onClick={() => { setTab(t); t === 'audit' ? loadAudit() : loadQueue() }}
                style={{
                  flex: 1, padding: '8px 0', background: tab === t ? C.glassHi : 'transparent', border: 'none',
                  borderBottom: tab === t ? `2px solid ${C.green}` : '2px solid transparent',
                  color: tab === t ? C.text1 : C.text3, cursor: 'pointer', fontSize: 10, fontWeight: 700,
                  letterSpacing: '.06em', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                }}>
                {t === 'queue' ? <ShieldAlert size={11} /> : <ScrollText size={11} />}
                {t === 'queue' ? 'TRAINING QUEUE' : 'AUDIT TRAIL'}
              </button>
            ))}
          </div>

          {/* Body */}
          <div style={{ flex: 1, overflowY: 'auto', padding: 14 }}>
            {tab === 'queue' && (
              <>
                {loading && pending.length === 0 && <div style={{ color: C.text3, fontSize: 10 }}>loading…</div>}
                {!loading && pending.length === 0 && (
                  <div style={{ color: C.text3, fontSize: 10.5, lineHeight: 1.6, padding: '10px 2px' }}>
                    No cases awaiting review. Generate attacks in the Red Team panel — any evasion the
                    Blue Team <b>misses</b> will appear here for your decision.
                  </div>
                )}
                {pending.map(c => (
                  <CaseCard key={c.case_id} c={c} flash={flash[c.case_id]} expanded={expanded === c.case_id}
                    onToggle={() => setExpanded(e => e === c.case_id ? null : c.case_id)}
                    onDecide={decide} onCompare={compare} similar={similar[c.case_id]} />
                ))}

                {decided.length > 0 && (
                  <div style={{ marginTop: 16, paddingTop: 10, borderTop: `1px solid ${C.border}` }}>
                    <div style={{ fontSize: 9, color: C.text3, letterSpacing: '.06em', marginBottom: 6 }}>RESOLVED ({decided.length})</div>
                    {decided.map(c => (
                      <div key={c.case_id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 9.5, color: C.text2, padding: '3px 0' }}>
                        <span style={{ color: c.status === 'learned' ? C.green : C.text3 }}>
                          {c.status === 'learned' ? '🎓' : '🗑'}
                        </span>
                        <span style={{ fontWeight: 700 }}>{c.case_id}</span>
                        <span style={{ color: C.text3 }}>{c.fraud_type}</span>
                        <span style={{ marginLeft: 'auto', color: c.status === 'learned' ? C.green : C.text3 }}>
                          {c.status}{c.duplicate_of ? ` · dup of ${c.duplicate_of}` : ''}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}

            {tab === 'audit' && (
              <>
                {audit.length === 0 && <div style={{ color: C.text3, fontSize: 10 }}>No learning events yet.</div>}
                {audit.map((a, i) => (
                  <div key={i} style={{ padding: '7px 0', borderBottom: `1px solid ${C.border}`, fontSize: 9.5 }}>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <span style={{ fontWeight: 700, color: C.text1 }}>{a.case_id}</span>
                      <span style={{
                        padding: '0 6px', borderRadius: 3, fontSize: 8.5, fontWeight: 700,
                        background: a.decision === 'learn' ? C.greenDim : a.decision === 'enqueued' ? C.amberDim : C.redDim,
                        color: a.decision === 'learn' ? C.green : a.decision === 'enqueued' ? C.amber : C.red,
                      }}>{a.decision.toUpperCase()}</span>
                      <span style={{ marginLeft: 'auto', color: C.text3, fontSize: 8.5 }}>{a.time}</span>
                    </div>
                    <div style={{ color: C.text2, marginTop: 2 }}>
                      {a.generated_by} → Blue <b>{a.blue_result}</b> · {a.investigator} → {a.training_status}
                      {a.note ? <span style={{ color: C.text3 }}> · {a.note}</span> : null}
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

// ── one pending case: the investigator miss-dialog ──
function CaseCard({ c, expanded, onToggle, onDecide, onCompare, similar, flash }: {
  c: Case; expanded: boolean; flash?: string
  onToggle: () => void
  onDecide: (id: string, action: string) => void
  onCompare: (id: string) => void
  similar?: Similar[]
}) {
  return (
    <div style={{ border: `1px solid ${C.border}`, borderRadius: 9, padding: 12, marginBottom: 11, background: C.raised }}>
      {/* miss banner */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 8 }}>
        <ShieldAlert size={13} color={C.red} />
        <span style={{ fontSize: 10.5, fontWeight: 800, color: C.red }}>Blue Team failed to detect this fraud</span>
        <span style={{ marginLeft: 'auto', fontSize: 9, color: C.text3 }}>{c.created_iso}</span>
      </div>

      {/* identity row */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 7 }}>
        <span style={{ fontWeight: 800, fontSize: 11 }}>{c.case_id}</span>
        <span style={{ padding: '0 6px', borderRadius: 3, fontSize: 9, background: C.redDim, color: C.red, fontWeight: 700 }}>MISSED</span>
        <span style={{ fontSize: 10, color: C.text2 }}>{c.fraud_type}</span>
      </div>

      {/* metrics grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr auto 1fr', gap: '3px 8px', fontSize: 9.5, marginBottom: 8 }}>
        <span style={{ color: C.text3 }}>Red conf.</span><Pct v={c.red_confidence} c={C.red} />
        <span style={{ color: C.text3 }}>Blue conf.</span><Pct v={c.blue_confidence} c={C.cyan} />
        <span style={{ color: C.text3 }}>Risk</span><Pct v={c.risk_score} c={C.amber} />
        <span style={{ color: C.text3 }}>Size</span><span style={{ color: C.text2 }}>{c.nodes_total}n · {c.edges_total}e</span>
      </div>

      {/* techniques */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 7 }}>
        {c.techniques.map((t, i) => (
          <span key={i} style={{ fontSize: 8.5, padding: '1px 6px', borderRadius: 3, background: C.cyanDim, color: C.cyan }}>{t.replace(/_/g, ' ')}</span>
        ))}
      </div>

      {/* why blue missed */}
      <div style={{ fontSize: 9.5, color: C.text2, lineHeight: 1.5, marginBottom: 9, fontStyle: 'italic' }}>
        {c.explanation}
      </div>

      {/* Review Graph (expandable) + Compare */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 9 }}>
        <button onClick={onToggle} style={ghostBtn}><Eye size={11} /> {expanded ? 'Hide' : 'Review'} Graph</button>
        <button onClick={() => onCompare(c.case_id)} style={ghostBtn}><GitCompare size={11} /> Compare Similar</button>
      </div>
      {expanded && <div style={{ marginBottom: 9 }}><MiniGraph g={c.graph} /></div>}
      {similar && (
        <div style={{ marginBottom: 9, fontSize: 9, color: C.text2 }}>
          {similar.length === 0 ? <span style={{ color: C.text3 }}>no similar cases — this is a novel pattern</span> : (
            <>
              <div style={{ color: C.text3, marginBottom: 3 }}>SIMILAR CASES</div>
              {similar.map(s => (
                <div key={s.case_id} style={{ display: 'flex', gap: 6 }}>
                  <span style={{ fontWeight: 700 }}>{s.case_id}</span>
                  <span style={{ color: s.match === 'exact' ? C.red : C.amber }}>{s.match}</span>
                  <span style={{ color: C.text3 }}>· {Math.round(s.technique_overlap * 100)}% overlap · {s.status}</span>
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {flash ? (
        <div style={{ fontSize: 10, color: C.green, fontWeight: 700, padding: '4px 0' }}>✓ {flash}</div>
      ) : (
        <>
          {/* the required investigator miss-dialog */}
          <div style={{ fontSize: 9.5, color: C.text2, marginBottom: 6 }}>Use this case to improve the Blue Team?</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <button onClick={() => onDecide(c.case_id, 'learn')} style={{ ...actionBtn, background: C.green, color: '#fff' }}>
              <Check size={12} /> Learn from this Case
            </button>
            <button onClick={() => onDecide(c.case_id, 'ignore')} style={{ ...actionBtn, background: 'transparent', color: C.text2, border: `1px solid ${C.border}` }}>
              <Ban size={12} /> Ignore
            </button>
            <button onClick={() => onDecide(c.case_id, 'review')} style={{ ...actionBtn, background: 'transparent', color: C.cyan, border: `1px solid ${C.cyan}55` }}>
              <Eye size={12} /> Review First
            </button>
            <button onClick={() => onDecide(c.case_id, 'reject')} style={{ ...actionBtn, background: 'transparent', color: C.red, border: `1px solid ${C.red}55` }} title="false positive — discard">
              <Ban size={12} /> Reject
            </button>
            <button onClick={() => onDecide(c.case_id, 'archive')} style={{ ...actionBtn, background: 'transparent', color: C.text3, border: `1px solid ${C.border}` }}>
              <Archive size={12} /> Archive
            </button>
          </div>
        </>
      )}
    </div>
  )
}

const iconBtn: React.CSSProperties = { background: 'transparent', border: 'none', cursor: 'pointer', padding: 3, display: 'flex' }
const ghostBtn: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 4, padding: '3px 8px', borderRadius: 5,
  background: 'transparent', border: `1px solid ${C.border}`, color: C.text2, cursor: 'pointer', fontSize: 9, fontFamily: MONO,
}
const actionBtn: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 5, padding: '5px 10px', borderRadius: 6,
  border: 'none', cursor: 'pointer', fontSize: 9.5, fontWeight: 700, fontFamily: MONO,
}
