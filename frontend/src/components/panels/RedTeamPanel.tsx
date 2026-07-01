// ──────────────────────────────────────────────────────────────────────────────
// RedTeamPanel — LOCALHOST-only adversarial review queue.
//
// The Red Team evolves an attack per archetype and FEEDS its graph here. For each, the
// panel shows: the actual attack graph, the per-generation evolution that produced it
// (detection-risk dropping as it learns to evade), the deployed-vs-hardened verdicts, and
// a GARBAGE flag (broken-objective / partition-dependent artifacts). A human then clicks
// YES (feed the Blue Team) or NO (reject) — so the Blue Team only ever trains on real,
// on-graph evasions, never on garbage. Backed by /api/redteam/{attacks,review,reset}.
// ──────────────────────────────────────────────────────────────────────────────
import { useEffect, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Swords, RefreshCw, Check, Ban, TriangleAlert, CircleCheck, ShieldCheck } from 'lucide-react'
import { apiUrl } from '../../config'

// Dulled cream / greige palette (soft light theme — no bright white).
const C = {
  glass: 'rgba(234,229,219,0.96)', glassHi: 'rgba(225,219,207,0.97)', raised: 'rgba(243,239,231,0.82)',
  border: 'rgba(70,60,48,0.16)', text1: '#352f27', text2: '#6b6052', text3: '#9d9180',
  red: '#bd4040', redDim: 'rgba(189,64,64,0.10)', green: '#4a8a52', greenDim: 'rgba(74,138,82,0.13)',
  amber: '#b07d22', amberDim: 'rgba(176,125,34,0.14)', cyan: '#3f7ab5',
} as const
const MONO = '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace'
const PANEL_W = 480

type Verdict = 'CLEAN' | 'LOGGED' | 'SUSPICIOUS' | 'FRAUD'
interface GNode { id: string; role: 'source' | 'sink' | 'relay' }
interface GEdge { source: string; target: string; amount: number }
type Outcome = 'trained' | 'blue_catches' | 'garbage' | 'rejected'
interface Cand {
  id: string; archetype: string; techniques: string[]
  graph: { nodes: GNode[]; edges: GEdge[]; shown_edges: number }
  nodes_total: number; edges_total: number; components: number
  evolution: { gen: number; detection: number; evaded: boolean }[]
  native: { verdict: Verdict; risk: number; evaded: boolean }
  hardened: { verdict: Verdict; risk: number; caught: boolean; signal: string }
  feasibility: { objective_ok: boolean; on_graph: boolean }
  garbage: boolean; reason: string; decision: boolean | null
  blue_catches: boolean; trainable: boolean
  novel: boolean; complexity: number
  outcome?: Outcome; feedback?: string   // set after the human reviews
}
interface Tally { approved: number; rejected: number; reviewed: number; blue_corpus: number; red_must_improve: number }
interface Escalation { level: number; max_techniques: number; generations: number; evaded: number; total: number; mean_detection: number; novel: number }
interface Data { seed: number; took_ms: number; escalation: Escalation; ladder: { layer: string; context: string; probe: string }[]; candidates: Cand[]; tally: Tally }
interface Eval { fragments: number; reflag: number; benign_fp: number; quality: number }
interface ReviewRes { tally: Tally; outcome: Outcome; message: string; blue: { verdict: Verdict; risk: number; signal: string | null } | null }
interface TrainRes { ok: boolean; msg: string; approved?: number; real?: number; caught?: number; garbage?: number; current?: Eval | null; clean?: Eval | null; delta?: { benign_fp: number; quality: number } | null }

const vColor = (v: Verdict) => v === 'FRAUD' ? C.red : v === 'SUSPICIOUS' ? C.amber : v === 'LOGGED' ? C.cyan : C.text3
const roleColor = (r: GNode['role']) => r === 'source' ? C.red : r === 'sink' ? C.amber : C.cyan

// ── tiny role-layered graph viz ──
function MiniGraph({ g }: { g: Cand['graph'] }) {
  const W = 432, H = 150, pad = 14
  const cols: Record<string, GNode[]> = { source: [], relay: [], sink: [] }
  g.nodes.forEach(n => cols[n.role].push(n))
  const xOf = { source: pad + 8, relay: W / 2, sink: W - pad - 8 } as Record<string, number>
  const pos: Record<string, { x: number; y: number }> = {}
  ;(['source', 'relay', 'sink'] as const).forEach(role => {
    const arr = cols[role]
    arr.forEach((n, i) => {
      // relays wrap into 3 sub-columns so a fat middle doesn't overflow
      const sub = role === 'relay' ? (i % 3) - 1 : 0
      pos[n.id] = { x: xOf[role] + sub * 52, y: pad + ((H - 2 * pad) * (Math.floor(role === 'relay' ? i / 3 : i) + 1)) / ((role === 'relay' ? Math.ceil(arr.length / 3) : arr.length) + 1) }
    })
  })
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: H, display: 'block' }}>
      {g.edges.map((e, i) => {
        const a = pos[e.source], b = pos[e.target]
        if (!a || !b) return null
        return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="rgba(60,50,40,0.22)" strokeWidth={0.7} />
      })}
      {g.nodes.map(n => {
        const p = pos[n.id]; if (!p) return null
        return <circle key={n.id} cx={p.x} cy={p.y} r={n.role === 'relay' ? 2.6 : 4}
          fill={roleColor(n.role)} fillOpacity={n.role === 'relay' ? 0.75 : 1} />
      })}
    </svg>
  )
}

// ── evolution sparkline (animated draw): detection-risk dropping over generations ──
function Evolution({ evo }: { evo: Cand['evolution'] }) {
  if (!evo.length) return <div style={{ fontSize: 9.5, color: C.text3, fontStyle: 'italic' }}>curated attack — no evolution</div>
  const W = 200, H = 38
  const xs = (i: number) => (W * i) / Math.max(1, evo.length - 1)
  const ys = (d: number) => H - 3 - (H - 6) * d         // detection 1→top, 0→bottom
  const path = evo.map((p, i) => `${i ? 'L' : 'M'}${xs(i).toFixed(1)},${ys(p.detection).toFixed(1)}`).join(' ')
  const last = evo[evo.length - 1]
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: W, height: H }}>
        <line x1={0} y1={ys(0.62)} x2={W} y2={ys(0.62)} stroke={C.amber} strokeOpacity={0.3} strokeDasharray="3 3" strokeWidth={0.6} />
        <motion.path d={path} fill="none" stroke={last.evaded ? C.red : C.cyan} strokeWidth={1.6}
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.1, ease: 'easeInOut' }} />
        {evo.map((p, i) => (
          <motion.circle key={i} cx={xs(i)} cy={ys(p.detection)} r={1.8} fill={last.evaded ? C.red : C.cyan}
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 + i * (1.0 / evo.length) }} />
        ))}
      </svg>
      <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.text2, lineHeight: 1.3 }}>
        <div>risk {evo[0].detection.toFixed(2)} → <b style={{ color: last.evaded ? C.red : C.cyan }}>{last.detection.toFixed(2)}</b></div>
        <div style={{ color: C.text3 }}>{evo.length} generations</div>
      </div>
    </div>
  )
}

function EvalRow({ label, ev, hi }: { label: string; ev: Eval; hi?: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', fontFamily: MONO, fontSize: 10.5, padding: '2px 0' }}>
      <span style={{ flex: 1, color: hi ? C.text1 : C.text2 }}>{label}</span>
      <span style={{ width: 78, textAlign: 'right', color: C.cyan }}>{Math.round(ev.reflag * 100)}%</span>
      <span style={{ width: 70, textAlign: 'right', color: ev.benign_fp > 0.1 ? C.red : C.green, fontWeight: 700 }}>{Math.round(ev.benign_fp * 100)}%</span>
      <span style={{ width: 62, textAlign: 'right', color: ev.quality >= 0 ? C.green : C.red, fontWeight: 700 }}>{ev.quality >= 0 ? '+' : ''}{ev.quality.toFixed(2)}</span>
    </div>
  )
}

interface Props { isOpen: boolean; onClose: () => void }

export function RedTeamPanel({ isOpen, onClose }: Props) {
  const [data, setData] = useState<Data | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [seed, setSeed] = useState(0)
  const [train, setTrain] = useState<TrainRes | null>(null)
  const [training, setTraining] = useState(false)

  const load = useCallback(async (s: number) => {
    setLoading(true); setErr(null)
    try {
      const r = await fetch(apiUrl(`/api/redteam/attacks?seed=${s}`))
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setData(await r.json())
    } catch (e: any) {
      setErr(e?.message || 'failed — start the local backend with ENABLE_REDTEAM_PANEL=1')
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { if (isOpen && !data) load(0) }, [isOpen, data, load])

  const review = useCallback(async (id: string, approved: boolean) => {
    try {
      const r = await fetch(apiUrl('/api/redteam/review'), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, approved }),
      })
      const res: ReviewRes = await r.json()
      setData(d => d && ({ ...d, tally: res.tally,
        candidates: d.candidates.map(c => c.id === id
          ? { ...c, decision: approved, outcome: res.outcome, feedback: res.message } : c) }))
    } catch { /* ignore */ }
  }, [])

  const reset = useCallback(async () => {
    try { await fetch(apiUrl('/api/redteam/reset'), { method: 'POST' }) } catch {}
    setTrain(null); load(seed)
  }, [load, seed])

  const autoReject = useCallback(async () => {
    try {
      const r = await fetch(apiUrl(`/api/redteam/auto_reject?seed=${seed}`), { method: 'POST' })
      const res = await r.json()
      setData(d => d && ({ ...d, tally: res.tally,
        candidates: d.candidates.map(c => (c.garbage && c.decision == null) ? { ...c, decision: false } : c) }))
    } catch { /* ignore */ }
  }, [seed])

  const trainBlue = useCallback(async () => {
    setTraining(true)
    try {
      const r = await fetch(apiUrl('/api/redteam/train'), { method: 'POST' })
      setTrain(await r.json())
    } catch { setTrain({ ok: false, msg: 'train failed' }) }
    finally { setTraining(false) }
  }, [])

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.aside
          initial={{ x: PANEL_W + 20 }} animate={{ x: 0 }} exit={{ x: PANEL_W + 20 }}
          transition={{ type: 'spring', stiffness: 320, damping: 34 }}
          style={{
            position: 'fixed', top: 0, right: 0, bottom: 0, width: PANEL_W, zIndex: 60,
            background: C.glass, backdropFilter: 'blur(18px)', WebkitBackdropFilter: 'blur(18px)',
            borderLeft: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column',
            boxShadow: '-20px 0 50px rgba(60,50,40,0.20)',
          }}>
          {/* header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '13px 16px', borderBottom: `1px solid ${C.border}`, background: C.glassHi }}>
            <Swords size={16} color={C.red} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: C.text1, letterSpacing: '.04em' }}>RED TEAM · review queue</div>
              <div style={{ fontSize: 9.5, color: C.text3 }}>each escalation: new, more complex, harder-to-detect attacks</div>
            </div>
            <button onClick={() => { const s = seed + 1; setSeed(s); load(s) }} disabled={loading} title="escalate — evolve a new, harder generation of attacks"
              style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: loading ? 'default' : 'pointer', padding: '5px 9px', borderRadius: 5, background: C.redDim, border: `1px solid ${C.red}40`, color: C.red, fontSize: 10, fontWeight: 600, opacity: loading ? 0.5 : 1 }}>
              <RefreshCw size={11} className={loading ? 'spin' : ''} /> {loading ? 'evolving…' : 'escalate'}
            </button>
            <button onClick={onClose} style={{ cursor: 'pointer', background: 'transparent', border: 'none', color: C.text2, padding: 4 }}><X size={16} /></button>
          </div>

          {/* escalation status — grows every "escalate" */}
          {data && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 16px', borderBottom: `1px solid ${C.border}`, background: 'rgba(207,58,58,0.06)', fontFamily: MONO, fontSize: 10 }}>
              <span style={{ fontWeight: 700, color: C.red, letterSpacing: '.04em' }}>⚡ ESCALATION Lv.{data.escalation.level}</span>
              <span style={{ color: C.text3 }}>·</span>
              <span style={{ color: C.text2 }} title="max chained techniques · GA generations">≤{data.escalation.max_techniques} tech · {data.escalation.generations} gens</span>
              <span style={{ flex: 1 }} />
              <span style={{ color: C.red }} title="attacks that evade the deployed Blue">evades {data.escalation.evaded}/{data.escalation.total}</span>
              <span style={{ color: C.text3 }}>det {data.escalation.mean_detection.toFixed(2)}</span>
            </div>
          )}

          {/* tally + actions */}
          {data && (
            <div style={{ borderBottom: `1px solid ${C.border}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 16px 6px', fontSize: 11, fontFamily: MONO }}>
                <span style={{ color: C.green }}>Blue corpus <b>{data.tally.blue_corpus}</b></span>
                {data.tally.red_must_improve > 0 &&
                  <span style={{ color: C.amber }} title="you approved these but Blue already catches them — Red must improve">↻ Red {data.tally.red_must_improve}</span>}
                <span style={{ color: C.red }}>✗ {data.tally.rejected}</span>
                <span style={{ flex: 1 }} />
                <button onClick={reset} style={{ cursor: 'pointer', background: 'transparent', border: `1px solid ${C.border}`, borderRadius: 4, color: C.text3, fontSize: 9.5, padding: '2px 7px' }}>reset</button>
              </div>
              <div style={{ display: 'flex', gap: 8, padding: '0 16px 9px' }}>
                <button onClick={autoReject} title="reject every garbage candidate"
                  style={{ flex: 1, cursor: 'pointer', background: C.amberDim, border: `1px solid ${C.amber}44`, borderRadius: 5, color: C.amber, fontSize: 10, fontWeight: 600, padding: '5px' }}>
                  ⚠ auto-reject garbage
                </button>
                <button onClick={trainBlue} disabled={training} title="re-fit the Blue detector on the approved corpus only"
                  style={{ flex: 1.4, cursor: training ? 'default' : 'pointer', background: C.greenDim, border: `1px solid ${C.green}55`, borderRadius: 5, color: C.green, fontSize: 10, fontWeight: 700, padding: '5px', opacity: training ? 0.5 : 1 }}>
                  {training ? 'training…' : '⚙ Train Blue on approved corpus'}
                </button>
              </div>
              {/* train result — before/after curation delta */}
              {train && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}
                  style={{ padding: '9px 16px 11px', borderTop: `1px solid ${C.border}`, background: 'rgba(60,50,40,0.05)' }}>
                  {!train.ok || !train.current ? (
                    <div style={{ fontSize: 10.5, color: C.amber, fontFamily: MONO }}>{train.msg}</div>
                  ) : (
                    <>
                      <div style={{ fontSize: 9, color: C.text3, letterSpacing: '.08em', marginBottom: 6 }}>BLUE CALIBRATION (evaluated, not deployed)</div>
                      {/* header row */}
                      <div style={{ display: 'flex', fontFamily: MONO, fontSize: 9, color: C.text3, marginBottom: 3 }}>
                        <span style={{ flex: 1 }} /><span style={{ width: 78, textAlign: 'right' }}>catch fraud</span><span style={{ width: 70, textAlign: 'right' }}>benign FP</span><span style={{ width: 62, textAlign: 'right' }}>quality</span>
                      </div>
                      <EvalRow label={`train on all ${train.approved} approved`} ev={train.current} />
                      {train.clean && ((train.caught || 0) + (train.garbage || 0) > 0) ? (
                        <EvalRow label={`train on ${train.real} Blue-missed only`} ev={train.clean} hi />
                      ) : null}
                      {train.delta && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6, fontFamily: MONO, fontSize: 10 }}>
                          <span style={{ color: C.green, fontWeight: 700 }}>Δ curation</span>
                          <span style={{ color: train.delta.benign_fp <= 0 ? C.green : C.red }}>
                            FP {train.delta.benign_fp <= 0 ? '' : '+'}{Math.round(train.delta.benign_fp * 100)}pts
                          </span>
                          <span style={{ color: train.delta.quality >= 0 ? C.green : C.red }}>
                            quality {train.delta.quality >= 0 ? '+' : ''}{train.delta.quality.toFixed(2)}
                          </span>
                        </div>
                      )}
                      <div style={{ fontSize: 9.5, color: train.garbage ? C.amber : C.green, fontStyle: 'italic', marginTop: 6 }}>{train.msg}</div>
                    </>
                  )}
                </motion.div>
              )}
            </div>
          )}

          <div style={{ flex: 1, overflowY: 'auto', padding: 14 }}>
            {err && <div style={{ color: C.red, fontSize: 11, fontFamily: MONO, lineHeight: 1.5 }}>{err}</div>}
            {loading && !data && <div style={{ color: C.text2, fontSize: 12 }}>evolving attacks…</div>}

            {data && data.candidates.map((c, i) => (
              <motion.div key={c.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}
                style={{ marginBottom: 14, borderRadius: 9, background: C.raised, border: `1px solid ${c.blue_catches ? C.red + '40' : c.garbage ? C.amber + '44' : C.border}`, overflow: 'hidden' }}>
                {/* card header */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px', borderBottom: `1px solid ${C.border}` }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: C.text1, textTransform: 'capitalize' }}>{c.archetype}</span>
                  {c.novel && <span title="a technique combination the Red Team has never produced before" style={{ fontFamily: MONO, fontSize: 8, fontWeight: 700, color: C.cyan, background: 'rgba(47,124,201,0.10)', border: '1px solid rgba(47,124,201,0.32)', borderRadius: 3, padding: '0 4px' }}>NEW</span>}
                  <span style={{ fontFamily: MONO, fontSize: 8.5, color: C.text3 }} title="chained attack techniques">×{c.complexity}</span>
                  <span style={{ flex: 1 }} />
                  {c.blue_catches
                    ? <span title="the deployed Blue Team already flags this — Red must improve" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 9.5, fontWeight: 700, color: C.red }}><ShieldCheck size={12} /> BLUE CATCHES</span>
                    : c.garbage
                      ? <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 9.5, fontWeight: 700, color: C.amber }}><TriangleAlert size={12} /> GARBAGE</span>
                      : <span title="a real on-graph evasion the deployed Blue couldn't catch — gold training data" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 9.5, fontWeight: 700, color: C.green }}><CircleCheck size={12} /> BLUE MISSED</span>}
                </div>

                {/* graph */}
                <div style={{ background: 'rgba(60,50,40,0.04)' }}><MiniGraph g={c.graph} /></div>
                <div style={{ display: 'flex', gap: 10, padding: '6px 12px', fontSize: 9, color: C.text3, fontFamily: MONO }}>
                  <span style={{ color: C.red }}>● source</span><span style={{ color: C.amber }}>● sink</span><span style={{ color: C.cyan }}>● relay/mule</span>
                  <span style={{ flex: 1 }} />
                  <span>{c.nodes_total}n · {c.edges_total}e · {c.components} parts</span>
                </div>

                {/* evolution + verdicts */}
                <div style={{ padding: '4px 12px 10px' }}>
                  <Evolution evo={c.evolution} />
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, margin: '9px 0 7px' }}>
                    {c.techniques.slice(0, 5).map((t, ti) => (
                      <span key={`${t}-${ti}`} style={{ fontFamily: MONO, fontSize: 9, color: C.cyan, background: 'rgba(47,124,201,0.08)', border: '1px solid rgba(47,124,201,0.22)', borderRadius: 3, padding: '1px 5px' }}>{t}</span>
                    ))}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontFamily: MONO, fontSize: 10 }}>
                    <span style={{ color: vColor(c.native.verdict) }}>{c.native.verdict} {c.native.risk.toFixed(2)}</span>
                    {c.native.evaded && <span style={{ color: C.red, fontSize: 8.5, fontWeight: 700 }}>EVADED</span>}
                    <span style={{ color: C.text3 }}>→</span>
                    <span style={{ color: vColor(c.hardened.verdict) }}>{c.hardened.verdict} {c.hardened.risk.toFixed(2)}</span>
                    <span style={{ color: C.text3, fontSize: 9 }}>via {c.hardened.signal}</span>
                  </div>
                  <div style={{ fontSize: 9.5, color: c.garbage ? C.amber : C.text3, marginTop: 6, fontStyle: 'italic' }}>{c.reason}</div>
                </div>

                {/* YES / NO gate */}
                <div style={{ padding: '0 12px 12px' }}>
                  {c.decision == null ? (
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button onClick={() => review(c.id, true)}
                        style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, cursor: 'pointer', padding: '7px', borderRadius: 6, background: C.greenDim, border: `1px solid ${C.green}55`, color: C.green, fontSize: 11, fontWeight: 700 }}>
                        <Check size={13} /> YES — feed Blue
                      </button>
                      <button onClick={() => review(c.id, false)}
                        style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, cursor: 'pointer', padding: '7px', borderRadius: 6, background: C.redDim, border: `1px solid ${C.red}55`, color: C.red, fontSize: 11, fontWeight: 700 }}>
                        <Ban size={13} /> NO — reject
                      </button>
                    </div>
                  ) : (() => {
                    // outcome decides what actually happened to the YES
                    const o = c.outcome ?? (c.decision ? 'trained' : 'rejected')
                    const m: Record<Outcome, { col: string; label: string }> = {
                      trained: { col: C.green, label: '✓ fed to Blue corpus' },
                      blue_catches: { col: C.red, label: '↻ Blue catches — Red must improve' },
                      garbage: { col: C.amber, label: '✗ not added — garbage' },
                      rejected: { col: C.red, label: '✗ rejected' },
                    }
                    const st = m[o]
                    return (
                      <div style={{ borderRadius: 6, background: `${st.col}14`, border: `1px solid ${st.col}44`, padding: '7px 10px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', fontSize: 11, fontWeight: 700, color: st.col }}>
                          <span style={{ flex: 1 }}>{st.label}</span>
                          <button onClick={() => review(c.id, !c.decision)} style={{ cursor: 'pointer', background: 'transparent', border: 'none', color: C.text3, fontSize: 9.5, textDecoration: 'underline' }}>undo</button>
                        </div>
                        {o === 'blue_catches' && (
                          <div style={{ marginTop: 5, fontSize: 9.5, fontFamily: MONO, color: C.text2, lineHeight: 1.4 }}>
                            Blue flagged <b style={{ color: vColor(c.native.verdict) }}>{c.native.verdict} {c.native.risk.toFixed(2)}</b> — not trained. Improve the attack so Blue can't see it.
                          </div>
                        )}
                      </div>
                    )
                  })()}
                </div>
              </motion.div>
            ))}

            {/* defense ladder */}
            {data && (
              <div style={{ marginTop: 4 }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: C.text2, letterSpacing: '.08em', marginBottom: 6 }}>DEFENSE LADDER</div>
                {data.ladder.map((l, i) => (
                  <div key={l.layer} style={{ display: 'flex', gap: 8, padding: '5px 0', borderBottom: i < data.ladder.length - 1 ? `1px solid ${C.border}` : 'none' }}>
                    <span style={{ fontFamily: MONO, fontSize: 9.5, color: i === 0 ? C.text3 : C.green, minWidth: 86, fontWeight: 600 }}>{l.layer}</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 10, color: C.text1 }}>{l.context}</div>
                      <div style={{ fontSize: 9, color: C.text3, fontStyle: 'italic' }}>↳ {l.probe}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  )
}
