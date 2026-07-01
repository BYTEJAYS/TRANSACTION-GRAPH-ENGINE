import { motion, AnimatePresence } from 'framer-motion'
import type { BlueTeamMultiResult, BlueTeamVerdict, GraphComponentResult } from '../types'
import { riskPct, riskValue } from '../utils/percent'

// ── Design tokens ──────────────────────────────────────────────────────────
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

interface Props {
  result: BlueTeamMultiResult
  onFocusGraph?: (graphId: string, nodeIds: string[]) => void
}

function verdictColor(verdict?: BlueTeamVerdict): string {
  if (verdict === 'FRAUD')      return C.danger
  if (verdict === 'SUSPICIOUS') return C.warn
  if (verdict === 'LOGGED')     return '#a371f7'
  if (verdict === 'CLEAN')      return C.success
  return C.text2
}

function verdictLabel(g: GraphComponentResult): string {
  if (g.status === 'no_data') return 'Empty'
  if (!g.verdict)              return 'Pending'
  if (g.verdict === 'FRAUD')      return 'Fraud'
  if (g.verdict === 'SUSPICIOUS') return 'Suspicious'
  if (g.verdict === 'LOGGED')     return 'Logged'
  return 'Clean'
}

function GraphRow({ graph, onFocus }: { graph: GraphComponentResult; onFocus?: () => void }) {
  const vc      = verdictColor(graph.verdict)
  const label   = verdictLabel(graph)
  const pct     = riskValue(graph) * 100   // bar width only (0 when N/A)
  const isFraud = graph.flagged
  const isWarn  = graph.verdict === 'SUSPICIOUS'

  return (
    <motion.button
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      onClick={onFocus}
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        width: '100%', padding: '6px 8px', borderRadius: 4,
        background: isFraud
          ? 'rgba(248,81,73,0.05)'
          : isWarn ? 'rgba(210,153,34,0.04)'
          : 'transparent',
        border: `1px solid ${isFraud
          ? 'rgba(248,81,73,0.14)'
          : isWarn ? 'rgba(210,153,34,0.10)'
          : 'transparent'}`,
        cursor: 'pointer', textAlign: 'left',
        transition: 'background 0.15s',
      }}
      whileHover={{
        background: isFraud
          ? 'rgba(248,81,73,0.09)'
          : isWarn ? 'rgba(210,153,34,0.08)'
          : 'rgba(255,255,255,0.03)',
      }}
    >
      {/* Status dot */}
      <div style={{
        width: 5, height: 5, borderRadius: '50%', flexShrink: 0,
        background: vc, opacity: isFraud ? 1 : 0.7,
      }}>
        {isFraud && (
          <motion.div
            animate={{ opacity: [1, 0.2, 1] }}
            transition={{ repeat: Infinity, duration: 1.2 }}
            style={{ width: '100%', height: '100%', borderRadius: '50%', background: vc }}
          />
        )}
      </div>

      {/* Graph ID */}
      <span style={{
        fontSize: 10, fontFamily: 'ui-monospace, SF Mono, Menlo, monospace',
        color: C.text3, flexShrink: 0, width: 72, overflow: 'hidden', textOverflow: 'ellipsis',
      }}>
        {graph.graph_id}
      </span>

      {/* Verdict */}
      <span style={{
        fontSize: 10, fontWeight: 500, color: vc,
        flexShrink: 0, width: 68,
      }}>
        {label}
      </span>

      {/* Risk bar */}
      <div style={{
        flex: 1, height: 1.5,
        background: 'rgba(255,255,255,0.05)',
        borderRadius: 1, overflow: 'hidden',
      }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
          style={{
            height: '100%', borderRadius: 1,
            background: vc,
            opacity: 0.75,
          }}
        />
      </div>

      {/* Score */}
      <span style={{
        fontSize: 10, fontFamily: 'ui-monospace, monospace',
        color: vc, flexShrink: 0, width: 32, textAlign: 'right',
        fontVariantNumeric: 'tabular-nums',
      }}>
        {riskPct(graph)}
      </span>

      {/* Arrow */}
      <span style={{ fontSize: 10, color: C.text3, flexShrink: 0 }}>›</span>
    </motion.button>
  )
}

function SpinnerRow() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0' }}>
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ repeat: Infinity, duration: 1.2, ease: 'linear' }}
        style={{
          width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
          border: `1.5px solid rgba(255,255,255,0.08)`,
          borderTopColor: C.accent,
        }}
      />
      <span style={{ fontSize: 10, color: C.text3 }}>
        Running pipeline…
      </span>
    </div>
  )
}

export function BlueTeamPanel({ result, onFocusGraph }: Props) {
  const { status, graphs } = result
  const isIdle      = status === 'idle'
  const isAnalyzing = status === 'analyzing'
  const isDone      = status === 'analyzed'
  const hasFraud    = graphs.some(g => g.flagged)
  const hasWarn     = graphs.some(g => g.verdict === 'SUSPICIOUS')

  const statusColor = hasFraud ? C.danger : hasWarn ? C.warn : isDone ? C.success : C.text3
  const statusLabel = isIdle ? 'Idle' : isAnalyzing ? 'Analyzing' : hasFraud ? 'Fraud detected' : 'Clear'

  const worstGraph = isDone && graphs.length > 0
    ? [...graphs].sort((a, b) => b.risk_score - a.risk_score)[0]
    : null

  return (
    <motion.div
      initial={{ x: 16, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.3, delay: 0.15, ease: [0.16, 1, 0.3, 1] }}
      style={{
        position: 'absolute',
        top: 44,
        right: 0,
        bottom: 0,
        width: 288,
        zIndex: 50,
        display: 'flex',
        flexDirection: 'column',
        background: 'rgba(13,17,23,0.88)',
        borderLeft: `1px solid rgba(255,255,255,0.08)`,
        backdropFilter: 'blur(20px)',
        transition: 'border-color 0.5s',
      }}
    >
      {/* ── Panel header ────────────────────────────────────────────────── */}
      <div style={{
        padding: '12px 16px',
        borderBottom: `1px solid rgba(255,255,255,0.05)`,
        display: 'flex', alignItems: 'center', gap: 10,
        flexShrink: 0,
      }}>
        <div style={{
          width: 26, height: 26, borderRadius: 5,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: hasFraud ? 'rgba(248,81,73,0.08)' : 'rgba(255,255,255,0.04)',
          border: `1px solid ${hasFraud ? 'rgba(248,81,73,0.18)' : 'rgba(255,255,255,0.08)'}`,
          flexShrink: 0,
          transition: 'all 0.4s',
        }}>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path
              d="M6 1L1 3v3c0 2.76 2.14 5.35 5 6 2.86-.65 5-3.24 5-6V3L6 1z"
              stroke={hasFraud ? C.danger : '#484f58'}
              strokeWidth="0.9"
              fill="none"
            />
          </svg>
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: '#8b949e' }}>
            Blue Team
          </div>
          <div style={{ fontSize: 9, color: '#484f58' }}>
            Per-graph analysis
          </div>
        </div>

        <div style={{
          display: 'flex', alignItems: 'center', gap: 5,
          padding: '2px 8px', borderRadius: 4,
          background: hasFraud
            ? 'rgba(248,81,73,0.08)'
            : isDone ? 'rgba(63,185,80,0.07)'
            : 'rgba(255,255,255,0.04)',
          border: `1px solid ${hasFraud
            ? 'rgba(248,81,73,0.18)'
            : isDone ? 'rgba(63,185,80,0.15)'
            : 'rgba(255,255,255,0.06)'}`,
        }}>
          {isAnalyzing && (
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ repeat: Infinity, duration: 1.2, ease: 'linear' }}
              style={{
                width: 6, height: 6, borderRadius: '50%',
                border: `1px solid ${C.text3}`, borderTopColor: C.accent,
              }}
            />
          )}
          {!isAnalyzing && (
            <div style={{ width: 5, height: 5, borderRadius: '50%', background: statusColor, opacity: 0.85 }} />
          )}
          <span style={{ fontSize: 10, fontWeight: 500, color: statusColor }}>
            {statusLabel}
          </span>
        </div>
      </div>

      {/* ── Panel body ──────────────────────────────────────────────────── */}
      <div style={{
        flex: 1, overflowY: 'auto', padding: '10px 12px',
        display: 'flex', flexDirection: 'column', gap: 6,
      }}>

        <AnimatePresence mode="wait">
          {isIdle && (
            <motion.div key="idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <p style={{ margin: 0, fontSize: 11, color: C.text3, lineHeight: 1.6 }}>
                Submit transactions to begin analysis.
              </p>
            </motion.div>
          )}

          {isAnalyzing && (
            <motion.div key="analyzing" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <SpinnerRow />
              <p style={{ margin: '4px 0 0', fontSize: 10, color: C.text3, lineHeight: 1.5 }}>
                Gate checks → cycle detection → risk scoring
              </p>
            </motion.div>
          )}

          {isDone && graphs.length === 0 && (
            <motion.div key="nodata" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <p style={{ margin: 0, fontSize: 11, color: C.text3 }}>No transactions in graph.</p>
            </motion.div>
          )}

          {isDone && graphs.length > 0 && (
            <motion.div
              key="graphs"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              style={{ display: 'flex', flexDirection: 'column', gap: 3 }}
            >
              {/* Column headers */}
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '0 8px', marginBottom: 2,
              }}>
                <div style={{ width: 5, flexShrink: 0 }} />
                <span style={{ fontSize: 9, color: C.text3, width: 72 }}>Graph</span>
                <span style={{ fontSize: 9, color: C.text3, width: 68 }}>Verdict</span>
                <span style={{ fontSize: 9, color: C.text3, flex: 1 }}>Risk</span>
                <span style={{ fontSize: 9, color: C.text3, width: 32, textAlign: 'right' }}>Score</span>
                <span style={{ width: 14 }} />
              </div>

              {graphs.map(g => (
                <GraphRow
                  key={g.graph_id}
                  graph={g}
                  onFocus={() => onFocusGraph?.(g.graph_id, g.nodes)}
                />
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Summary footer ──────────────────────────────────────────────── */}
      {isDone && graphs.length > 0 && (
        <div style={{
          padding: '10px 16px',
          borderTop: `1px solid rgba(255,255,255,0.05)`,
          display: 'flex', flexDirection: 'column', gap: 6,
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 10, color: C.text3 }}>
              {graphs.length} graph{graphs.length !== 1 ? 's' : ''} analyzed
            </span>
            <span style={{
              fontSize: 10, fontWeight: 500,
              color: hasFraud ? C.danger : C.success,
            }}>
              {graphs.filter(g => g.flagged).length} flagged
            </span>
          </div>

          {worstGraph?.suspicious_reason && (
            <div style={{
              padding: '7px 10px', borderRadius: 4,
              background: 'rgba(255,255,255,0.02)',
              border: `1px solid rgba(255,255,255,0.05)`,
            }}>
              <div style={{ fontSize: 9, color: C.text3, marginBottom: 3 }}>Top signal</div>
              <div style={{
                fontSize: 10, color: C.text2, lineHeight: 1.5,
                fontFamily: 'ui-monospace, SF Mono, Menlo, monospace',
              }}>
                {worstGraph.suspicious_reason}
              </div>
            </div>
          )}
        </div>
      )}
    </motion.div>
  )
}
