import { useState, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronRight, Play, Trash2 } from 'lucide-react'
import { UNIFIED_SAMPLE_JSON } from '../../data/sampleDataset'
import type { SimulationState } from '../../types/transaction'
import type { BlueTeamMultiResult, GraphComponentResult, BlueTeamVerdict, LiveTransaction } from '../../types'
import { riskPct } from '../../utils/percent'

// ── Tokens ───────────────────────────────────────────────────────────────────
const C = {
  bg:      '#0d1117',
  surface: '#161b22',
  raised:  '#1c2128',
  border:  'rgba(255,255,255,0.08)',
  borderS: 'rgba(255,255,255,0.05)',
  text1:   '#e6edf3',
  text2:   '#8b949e',
  text3:   '#484f58',
  accent:  '#4493f8',
  warn:    '#d29922',
  danger:  '#f85149',
  success: '#3fb950',
} as const

const PANEL_W  = 280
const STRIP_W  = 44

// ── Unified sample dataset ────────────────────────────────────────────────────
// One simulation feeds every activity type at once (legit + cash AML + fraud
// ring). Editable in the textarea below; defined once in data/sampleDataset.

const RAIL_COLORS: Record<string, string> = {
  UPI:  C.accent, IMPS: C.success, RTGS: C.warn, NEFT: '#a371f7', CASH: '#d4a11e',
}

function verdictColor(v?: BlueTeamVerdict) {
  if (v === 'FRAUD')      return C.danger
  if (v === 'SUSPICIOUS') return C.warn
  if (v === 'LOGGED')     return '#a371f7'
  if (v === 'CLEAN')      return C.success
  return C.text3
}

function fmtAmt(v: number) {
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)}L`
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(1)}K`
  return `₹${v.toFixed(0)}`
}

function fmtTime(ts: string) {
  try {
    const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000)
    if (diff < 60) return `${diff}s`
    if (diff < 3600) return `${Math.floor(diff / 60)}m`
    return `${Math.floor(diff / 3600)}h`
  } catch { return '' }
}

// ── Section wrapper ──────────────────────────────────────────────────────────
function Section({
  title, children, defaultOpen = true,
}: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          width: '100%', padding: '8px 16px',
          background: 'none', border: 'none', borderBottom: `1px solid ${C.borderS}`,
          cursor: 'pointer', textAlign: 'left',
        }}
      >
        <span style={{ fontSize: 10, fontWeight: 500, color: C.text3, letterSpacing: '.06em', textTransform: 'uppercase' }}>
          {title}
        </span>
        <motion.span
          animate={{ rotate: open ? 90 : 0 }}
          transition={{ duration: 0.18 }}
          style={{ display: 'flex', color: C.text3 }}
        >
          <ChevronRight size={11} />
        </motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: 'hidden' }}
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Transaction feed item ────────────────────────────────────────────────────
function TxnItem({ txn, fraudNodeIds }: { txn: LiveTransaction; fraudNodeIds?: ReadonlySet<string> }) {
  const inFraud = (fraudNodeIds?.has(txn.from_account) || fraudNodeIds?.has(txn.to_account)) ?? false
  const flagged = txn.is_flagged || inFraud
  const railColor = RAIL_COLORS[txn.payment_rail] ?? C.text3

  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '1fr auto auto',
      alignItems: 'center', gap: 8,
      padding: '5px 16px',
      borderBottom: `1px solid ${C.borderS}`,
      background: flagged ? 'rgba(248,81,73,0.03)' : 'transparent',
      transition: 'background 0.15s',
    }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 1 }}>
          {flagged && <div style={{ width: 3, height: 3, borderRadius: '50%', background: C.danger, flexShrink: 0 }} />}
          <span style={{
            fontSize: 10, fontFamily: 'ui-monospace, monospace',
            color: flagged ? '#c07070' : C.text3,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {txn.from_account.slice(-6)} → {txn.to_account.slice(-6)}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{
            fontSize: 9, padding: '0 4px', borderRadius: 2,
            background: `${railColor}12`, border: `1px solid ${railColor}20`,
            color: railColor, fontFamily: 'monospace',
          }}>
            {txn.payment_rail}
          </span>
          <span style={{ fontSize: 9, color: C.text3 }}>{fmtTime(txn.timestamp)}</span>
        </div>
      </div>
      <span style={{
        fontSize: 11, fontWeight: 600, fontFamily: 'ui-monospace, monospace',
        fontVariantNumeric: 'tabular-nums',
        color: flagged ? C.danger : C.text2,
      }}>
        {fmtAmt(txn.amount)}
      </span>
    </div>
  )
}

// ── Blue Team row ────────────────────────────────────────────────────────────
function GraphRow({ graph, onFocus }: { graph: GraphComponentResult; onFocus?: () => void }) {
  const vc = verdictColor(graph.verdict)
  return (
    <motion.button
      whileHover={{ background: 'rgba(255,255,255,0.03)' }}
      onClick={onFocus}
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        width: '100%', padding: '5px 16px',
        background: 'transparent', border: 'none',
        borderBottom: `1px solid ${C.borderS}`,
        cursor: 'pointer', textAlign: 'left',
      }}
    >
      {graph.flagged && (
        <motion.div
          animate={{ opacity: [1, 0.2, 1] }}
          transition={{ repeat: Infinity, duration: 1.2 }}
          style={{ width: 4, height: 4, borderRadius: '50%', background: C.danger, flexShrink: 0 }}
        />
      )}
      {!graph.flagged && (
        <div style={{ width: 4, height: 4, borderRadius: '50%', background: vc, opacity: 0.7, flexShrink: 0 }} />
      )}
      <span style={{ fontSize: 10, fontFamily: 'ui-monospace, monospace', color: C.text3, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {graph.graph_id}
      </span>
      <span style={{ fontSize: 10, fontWeight: 500, color: vc, flexShrink: 0 }}>
        {graph.verdict ?? 'Pending'}
      </span>
      <span style={{ fontSize: 10, fontFamily: 'monospace', color: vc, flexShrink: 0, fontVariantNumeric: 'tabular-nums' }}>
        {riskPct(graph)}
      </span>
    </motion.button>
  )
}

// ── Props ────────────────────────────────────────────────────────────────────
interface Props {
  isOpen: boolean
  onToggle: () => void
  simulationState: SimulationState
  currentStep: number
  totalSteps: number
  onRunSimulation: (json: string) => Promise<void>
  onClearGraph: () => void
  isClearingGraph?: boolean
  blueTeamResult: BlueTeamMultiResult
  onFocusGraph: (graphId: string, nodeIds: string[]) => void
  transactions: LiveTransaction[]
  fraudNodeIds: ReadonlySet<string>
}

// ── Main component ───────────────────────────────────────────────────────────
export function LeftPanel({
  isOpen, onToggle,
  simulationState, currentStep, totalSteps,
  onRunSimulation, onClearGraph,
  isClearingGraph = false,
  blueTeamResult, onFocusGraph,
  transactions, fraudNodeIds,
}: Props) {
  const [json, setJson]           = useState(UNIFIED_SAMPLE_JSON)
  const [error, setError]         = useState<string | null>(null)
  const isRunning = simulationState === 'running'
  const feedRef = useRef<HTMLDivElement>(null)

  const validate = useCallback((text: string): boolean => {
    try {
      const parsed = JSON.parse(text)
      if (!Array.isArray(parsed)) { setError('Expected a JSON array'); return false }
      for (const t of parsed) {
        if (!t.from_account || !t.to_account || t.amount === undefined) {
          setError('Each item needs from_account, to_account, amount'); return false
        }
      }
      setError(null); return true
    } catch (e: any) { setError(e.message ?? 'Invalid JSON'); return false }
  }, [])

  const handleRun = useCallback(async () => {
    if (!validate(json)) return
    await onRunSimulation(json)
  }, [json, validate, onRunSimulation])

  const { graphs, status } = blueTeamResult
  const hasFraud = graphs.some(g => g.flagged)
  const progress = totalSteps > 0 ? (currentStep / totalSteps) * 100 : 0

  return (
    <motion.div
      animate={{ width: isOpen ? PANEL_W : STRIP_W }}
      transition={{ type: 'spring', stiffness: 300, damping: 34 }}
      style={{
        position: 'absolute',
        top: 44, left: 0, bottom: 44,
        zIndex: 40,
        overflow: 'hidden',
        display: 'flex', flexDirection: 'column',
      }}
    >
      {/* ── Backdrop ──────────────────────────────────────────────── */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{
              position: 'absolute', inset: 0,
              background: 'rgba(13,17,23,0.93)',
              borderRight: `1px solid ${C.border}`,
              backdropFilter: 'blur(20px)',
              pointerEvents: 'none',
            }}
          />
        )}
      </AnimatePresence>

      {/* ── Collapsed strip ───────────────────────────────────────── */}
      {/* pointerEvents:none when open so the strip doesn't intercept clicks   */}
      {/* on panel content (specifically the trash button which sits under it). */}
      {/* The chevron keeps pointerEvents:auto so toggle-close still works.    */}
      <div
        style={{
          position: 'absolute', right: 0, top: 0, bottom: 0,
          width: STRIP_W, zIndex: 2,
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: 8,
          cursor: isOpen ? 'default' : 'pointer',
          pointerEvents: isOpen ? 'none' : 'auto',
        }}
        onClick={isOpen ? undefined : onToggle}
      >
        {/* Indicator dots when collapsed */}
        {!isOpen && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
            <div style={{ width: 3, height: 3, borderRadius: '50%', background: C.text3 }} />
            <div style={{ width: 3, height: 3, borderRadius: '50%', background: C.text3 }} />
            <div style={{ width: 3, height: 3, borderRadius: '50%', background: hasFraud ? C.danger : C.text3 }} />
          </div>
        )}

        {/* Toggle arrow — always clickable (overrides parent pointerEvents:none) */}
        <motion.div
          animate={{ rotate: isOpen ? 180 : 0, x: isOpen ? -10 : 0 }}
          transition={{ type: 'spring', stiffness: 300, damping: 28 }}
          onClick={(e) => { e.stopPropagation(); onToggle() }}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: 20, height: 20,
            color: C.text3,
            pointerEvents: 'auto',
            cursor: 'pointer',
          }}
        >
          <ChevronRight size={14} />
        </motion.div>
      </div>

      {/* ── Panel content ─────────────────────────────────────────── */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18, delay: 0.06 }}
            style={{
              position: 'absolute', inset: 0, right: 0,
              display: 'flex', flexDirection: 'column',
              overflow: 'hidden', zIndex: 1,
              width: PANEL_W,
            }}
          >
            {/* ── 1. Simulation ──────────────────────────────────── */}
            <Section title="Simulation" defaultOpen>
              <div style={{ padding: '10px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                {/* One unified feed — legit traffic, cash AML and a fraud ring
                    together. Edit freely, or reset to the sample below. */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 9, color: C.text3, letterSpacing: 0.3 }}>
                    TRANSACTION FEED
                  </span>
                  <button
                    onClick={() => { setJson(UNIFIED_SAMPLE_JSON); setError(null) }}
                    style={{
                      fontSize: 9, color: C.text3, background: 'transparent',
                      border: `1px solid ${C.borderS}`, borderRadius: 4,
                      padding: '2px 7px', cursor: 'pointer',
                    }}
                  >
                    Reset sample
                  </button>
                </div>

                {/* Editor */}
                <textarea
                  value={json}
                  onChange={e => { setJson(e.target.value); setError(null) }}
                  spellCheck={false}
                  style={{
                    width: '100%', height: 160, resize: 'none',
                    padding: '8px', borderRadius: 4,
                    fontSize: 9.5, lineHeight: 1.55,
                    fontFamily: 'ui-monospace, SF Mono, Menlo, monospace',
                    background: C.bg, border: `1px solid ${error ? 'rgba(248,81,73,0.35)' : C.border}`,
                    color: C.text2, caretColor: C.accent, outline: 'none',
                  }}
                />
                {error && <p style={{ margin: 0, fontSize: 10, color: C.danger }}>{error}</p>}

                {/* Progress */}
                {isRunning && totalSteps > 0 && (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <span style={{ fontSize: 9, color: C.text3 }}>Processing</span>
                      <span style={{ fontSize: 9, color: C.text2, fontFamily: 'monospace', fontVariantNumeric: 'tabular-nums' }}>
                        {currentStep} / {totalSteps}
                      </span>
                    </div>
                    <div style={{ height: 1, background: C.border, borderRadius: 1, overflow: 'hidden' }}>
                      <motion.div
                        style={{ height: '100%', background: C.accent, borderRadius: 1 }}
                        animate={{ width: `${progress}%` }}
                        transition={{ duration: 0.35 }}
                      />
                    </div>
                  </div>
                )}

                {/* Actions */}
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    onClick={handleRun}
                    disabled={isRunning}
                    style={{
                      flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
                      gap: 5, padding: '7px', borderRadius: 4,
                      fontSize: 11, fontWeight: 500,
                      background: isRunning ? C.raised : C.accent,
                      border: `1px solid ${isRunning ? C.border : 'transparent'}`,
                      color: isRunning ? C.text3 : '#fff',
                      cursor: isRunning ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {isRunning ? (
                      <motion.span
                        animate={{ rotate: 360 }}
                        transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
                        style={{ display: 'inline-block', width: 10, height: 10, border: `1.5px solid ${C.text3}`, borderTopColor: 'transparent', borderRadius: '50%' }}
                      />
                    ) : <Play size={11} />}
                    {isRunning ? 'Running…' : 'Run'}
                  </button>
                  <button
                    onClick={(e) => { e.preventDefault(); e.stopPropagation(); if (!isClearingGraph) { setError(null); onClearGraph() } }}
                    disabled={isClearingGraph}
                    title={isClearingGraph ? 'Clearing…' : 'Clear graph'}
                    style={{
                      width: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
                      borderRadius: 4,
                      cursor: isClearingGraph ? 'not-allowed' : 'pointer',
                      background: 'transparent', border: `1px solid ${C.border}`,
                      color: isClearingGraph ? C.text3 : C.danger,
                      opacity: isClearingGraph ? 0.45 : 1,
                      transition: 'color 0.15s, opacity 0.15s',
                    }}
                  >
                    {isClearingGraph ? (
                      <motion.span
                        animate={{ rotate: 360 }}
                        transition={{ repeat: Infinity, duration: 0.9, ease: 'linear' }}
                        style={{
                          display: 'inline-block', width: 10, height: 10,
                          border: `1.5px solid ${C.text3}`, borderTopColor: 'transparent',
                          borderRadius: '50%',
                        }}
                      />
                    ) : <Trash2 size={11} />}
                  </button>
                </div>
              </div>
            </Section>

            {/* ── 2. Blue Team Analysis ──────────────────────────── */}
            <Section title={`Analysis${hasFraud ? ' · FRAUD' : status === 'analyzed' ? ' · Clear' : ''}`} defaultOpen={false}>
              <div style={{ padding: '6px 0' }}>
                {status === 'idle' && (
                  <p style={{ margin: 0, padding: '8px 16px', fontSize: 10, color: C.text3 }}>
                    Awaiting graph input.
                  </p>
                )}
                {status === 'analyzing' && (
                  <div style={{ padding: '8px 16px', display: 'flex', alignItems: 'center', gap: 8 }}>
                    <motion.div
                      animate={{ rotate: 360 }}
                      transition={{ repeat: Infinity, duration: 1.2, ease: 'linear' }}
                      style={{ width: 10, height: 10, borderRadius: '50%', border: `1.5px solid ${C.text3}`, borderTopColor: C.accent }}
                    />
                    <span style={{ fontSize: 10, color: C.text3 }}>Running pipeline…</span>
                  </div>
                )}
                {status === 'analyzed' && graphs.map(g => (
                  <GraphRow key={g.graph_id} graph={g} onFocus={() => onFocusGraph(g.graph_id, g.nodes)} />
                ))}
                {status === 'analyzed' && graphs.length > 1 && (
                  <div style={{ padding: '6px 16px', display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 9, color: C.text3 }}>{graphs.length} graphs</span>
                    <span style={{ fontSize: 9, fontWeight: 500, color: hasFraud ? C.danger : C.success }}>
                      {graphs.filter(g => g.flagged).length} flagged
                    </span>
                  </div>
                )}
              </div>
            </Section>

            {/* ── 3. Transaction Feed ────────────────────────────── */}
            <Section title={`Feed${transactions.length > 0 ? ` · ${transactions.length}` : ''}`} defaultOpen={false}>
              <div
                ref={feedRef}
                style={{
                  maxHeight: 220, overflowY: 'auto',
                  display: 'flex', flexDirection: 'column',
                }}
              >
                {transactions.length === 0 && (
                  <p style={{ margin: 0, padding: '8px 16px', fontSize: 10, color: C.text3 }}>
                    No transactions yet.
                  </p>
                )}
                {transactions.slice(0, 40).map(txn => (
                  <TxnItem key={txn.id} txn={txn} fraudNodeIds={fraudNodeIds} />
                ))}
              </div>
            </Section>

            {/* ── Spacer ─────────────────────────────────────────── */}
            <div style={{ flex: 1 }} />

            {/* ── Legend ─────────────────────────────────────────── */}
            <div style={{ padding: '10px 16px', borderTop: `1px solid ${C.borderS}` }}>
              {/* Node types — colour conveys MEANING; cash identity outranks fraud */}
              <div style={{ fontSize: 9, color: C.text3, marginBottom: 6, letterSpacing: '.05em', textTransform: 'uppercase' }}>
                Node Types
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '3px 8px', marginBottom: 10 }}>
                {[
                  { color: '#00E676', label: 'Cash In' },
                  { color: '#FFC400', label: 'Cash Out' },
                  { color: C.danger,  label: 'Fraud Account' },
                  { color: C.accent,  label: 'Normal Account' },
                  { color: '#a371f7', label: 'Selected' },
                  { color: '#ffffff', label: 'Investigating' },
                ].map(({ color, label }) => (
                  <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                    <div style={{ width: 5, height: 5, borderRadius: '50%', background: color, flexShrink: 0, boxShadow: `0 0 5px ${color}` }} />
                    <span style={{ fontSize: 9, color: C.text3 }}>{label}</span>
                  </div>
                ))}
              </div>
              <div style={{ fontSize: 9, color: C.text3, marginBottom: 6, letterSpacing: '.05em', textTransform: 'uppercase' }}>
                Risk Scale
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '3px 8px' }}>
                {[
                  { color: C.accent,  label: 'Safe' },
                  { color: C.warn,    label: 'Moderate' },
                  { color: '#e3683e', label: 'High' },
                  { color: C.danger,  label: 'Fraud' },
                ].map(({ color, label }) => (
                  <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                    <div style={{ width: 5, height: 5, borderRadius: '50%', background: color, flexShrink: 0 }} />
                    <span style={{ fontSize: 9, color: C.text3 }}>{label}</span>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
