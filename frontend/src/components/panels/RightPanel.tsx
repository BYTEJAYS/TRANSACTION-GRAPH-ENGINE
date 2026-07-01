import { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronLeft, Volume2, VolumeX, Square } from 'lucide-react'
import { OrbWaveform } from '../ai/AIOrb'
import { OrbCharacter } from '../ai/OrbCharacter'
import type { VoiceState } from '../../hooks/useVoiceAssistant'
import type { Thought } from '../../hooks/useThoughtStream'
import type { BlueTeamMultiResult, GraphComponentResult } from '../../types'
import { riskPct, riskValue } from '../../utils/percent'

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
  cyan:    '#79c0ff',
  warn:    '#d29922',
  danger:  '#f85149',
  success: '#3fb950',
} as const

const PANEL_W = 320
const STRIP_W = 44

const MONO = '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace'

// ── Command catalogue — each chip dispatches a real UB intent phrase, so the
// response is computed live from the graph, never canned. ──────────────────────
interface Cmd { label: string; phrase: string; danger?: boolean }
const CMD_GROUPS: Array<{ title: string; cmds: Cmd[] }> = [
  {
    title: 'Topology',
    cmds: [
      { label: 'Summarize graph',   phrase: 'summarize graph' },
      { label: 'Analyze fan-out',   phrase: 'analyze fan out' },
      { label: 'Central account',   phrase: 'find central account' },
      { label: 'Circular movement', phrase: 'find circular movement', danger: true },
      { label: 'Detect laundering', phrase: 'detect laundering pattern', danger: true },
      { label: 'Find mules',        phrase: 'find mule accounts', danger: true },
      { label: 'Hidden loops',      phrase: 'show hidden loops', danger: true },
      { label: 'Risky accounts',    phrase: 'show risky accounts', danger: true },
    ],
  },
  {
    title: 'ML Model',
    cmds: [
      { label: 'Run anomaly detection', phrase: 'run anomaly detection' },
      { label: 'Rank anomalies',        phrase: 'rank anomalies' },
      { label: 'Explain this node',     phrase: 'explain this node' },
    ],
  },
  {
    title: 'Camera',
    cmds: [
      { label: 'Show all',     phrase: 'show entire graph' },
      { label: 'Zoom in',      phrase: 'zoom in' },
      { label: 'Zoom out',     phrase: 'zoom out' },
      { label: 'Reset',        phrase: 'reset camera' },
      { label: 'Track node',   phrase: 'track this node' },
      { label: 'This cluster', phrase: 'explain this cluster' },
    ],
  },
  {
    title: 'Report',
    cmds: [
      { label: 'Evidence package', phrase: 'give me evidence' },
      { label: 'Repeat analysis',  phrase: 'repeat analysis' },
      { label: 'Speak slower',     phrase: 'speak slower' },
      { label: 'Speak faster',     phrase: 'speak faster' },
    ],
  },
]

// ── Thought-kind styling ───────────────────────────────────────────────────────
const KIND_COLOR: Record<Thought['kind'], string> = {
  scan:   C.cyan,
  alert:  C.danger,
  metric: C.accent,
  info:   C.text3,
}

// ── Props ────────────────────────────────────────────────────────────────────
interface Props {
  isOpen: boolean
  onToggle: () => void
  voiceState: VoiceState
  onSpeak: (text: string) => void
  onStop: () => void
  onGreet: () => void
  /** Run a UB intent by free-form text — the only path that yields live analysis. */
  onCommand: (text: string) => void
  blueTeamResult: BlueTeamMultiResult
  isFraudDetected: boolean
  isMuted: boolean
  onToggleMute: () => void
  /** Live investigation feed. */
  thoughts: Thought[]
  monitoring: boolean
  nodeCount: number
  linkCount: number
  flaggedNodes: number
  /** Whether a node is currently selected (drives context-aware suggestions). */
  hasSelection: boolean
}

// Context-aware next-step suggestions — adapt to what the analyst is looking at.
function suggestionsFor(hasSelection: boolean, hasFraud: boolean, nodeCount: number): Cmd[] {
  if (hasSelection) return [
    { label: 'Explain this node',   phrase: 'explain this node' },
    { label: 'Track node',          phrase: 'track this node' },
    { label: 'Connected accounts',  phrase: 'connected accounts' },
    { label: 'Explain this cluster',phrase: 'explain this cluster' },
  ]
  if (hasFraud) return [
    { label: 'Detect laundering', phrase: 'detect laundering pattern', danger: true },
    { label: 'Find mules',        phrase: 'find mule accounts', danger: true },
    { label: 'Run model',         phrase: 'run anomaly detection' },
    { label: 'Evidence package',  phrase: 'give me evidence' },
  ]
  if (nodeCount > 0) return [
    { label: 'Summarize graph',       phrase: 'summarize graph' },
    { label: 'Run anomaly detection', phrase: 'run anomaly detection' },
    { label: 'Central account',       phrase: 'find central account' },
  ]
  return [{ label: 'System status', phrase: 'system status' }]
}

// ── Fraud cluster insight card ──────────────────────────────────────────────────
function InsightCard({ graph }: { graph: GraphComponentResult }) {
  const isFraud = graph.flagged
  return (
    <div style={{
      padding: '8px 10px', borderRadius: 5, marginBottom: 6,
      background: isFraud ? 'rgba(248,81,73,0.05)' : 'rgba(255,255,255,0.02)',
      border: `1px solid ${isFraud ? 'rgba(248,81,73,0.15)' : C.borderS}`,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: 10, fontFamily: MONO, fontWeight: 500, color: isFraud ? C.danger : C.text2 }}>
          {graph.graph_id}
        </span>
        <span style={{
          fontSize: 9, padding: '1px 6px', borderRadius: 3,
          background: isFraud ? 'rgba(248,81,73,0.08)' : 'rgba(63,185,80,0.08)',
          border: `1px solid ${isFraud ? 'rgba(248,81,73,0.20)' : 'rgba(63,185,80,0.15)'}`,
          color: isFraud ? C.danger : C.success, fontWeight: 600,
        }}>
          {graph.verdict ?? 'PENDING'}
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ flex: 1, height: 2, background: 'rgba(255,255,255,0.05)', borderRadius: 1, overflow: 'hidden' }}>
          <div style={{
            height: '100%', width: `${riskValue(graph) * 100}%`,
            background: isFraud ? C.danger : C.success, borderRadius: 1, opacity: 0.75,
          }} />
        </div>
        <span style={{ fontSize: 10, color: isFraud ? C.danger : C.text3, fontVariantNumeric: 'tabular-nums' }}>
          {riskPct(graph)}
        </span>
      </div>
      {graph.suspicious_reason && (
        <p style={{ margin: '5px 0 0', fontSize: 9, color: C.text3, fontFamily: MONO, lineHeight: 1.5 }}>
          {graph.suspicious_reason.replace(/_/g, ' ')}
        </p>
      )}
    </div>
  )
}

// ── Speech-activity ring around the orb ─────────────────────────────────────────
function ActivityRings({ voiceState }: { voiceState: VoiceState }) {
  const active = voiceState === 'speaking' || voiceState === 'fraud' || voiceState === 'listening'
  const color  = voiceState === 'fraud' ? C.danger : voiceState === 'listening' ? C.cyan : C.accent
  return (
    <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', pointerEvents: 'none' }}>
      {[0, 1, 2].map(i => (
        <motion.div
          key={i}
          style={{
            position: 'absolute', width: 150, height: 150, borderRadius: '50%',
            border: `1px solid ${color}`,
          }}
          animate={active
            ? { scale: [1, 1.35 + i * 0.12], opacity: [0.28, 0] }
            : { scale: 1, opacity: 0.05 }}
          transition={active
            ? { repeat: Infinity, duration: voiceState === 'fraud' ? 1.1 : 1.7, delay: i * 0.4, ease: 'easeOut' }
            : { duration: 0.4 }}
        />
      ))}
    </div>
  )
}

// ── State label ──────────────────────────────────────────────────────────────
function stateMeta(v: VoiceState): { label: string; color: string } {
  switch (v) {
    case 'fraud':      return { label: 'ALERT',      color: C.danger }
    case 'speaking':   return { label: 'ANALYZING',  color: C.cyan }
    case 'processing': return { label: 'THINKING',   color: C.accent }
    case 'listening':  return { label: 'LISTENING',  color: C.cyan }
    default:           return { label: 'MONITORING', color: C.success }
  }
}

// ── Command chip ────────────────────────────────────────────────────────────────
function Chip({ cmd, onClick }: { cmd: Cmd; onClick: () => void }) {
  const col = cmd.danger ? C.danger : C.text2
  return (
    <motion.button
      whileHover={{ background: cmd.danger ? 'rgba(248,81,73,0.10)' : 'rgba(68,147,248,0.10)', borderColor: cmd.danger ? 'rgba(248,81,73,0.3)' : 'rgba(68,147,248,0.3)' }}
      whileTap={{ scale: 0.96 }}
      onClick={onClick}
      style={{
        padding: '5px 9px', borderRadius: 4, cursor: 'pointer',
        background: 'rgba(255,255,255,0.025)', border: `1px solid ${C.borderS}`,
        fontSize: 10, color: col, fontFamily: MONO, whiteSpace: 'nowrap',
      }}
    >
      {cmd.label}
    </motion.button>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export function RightPanel({
  isOpen, onToggle,
  voiceState, onStop, onGreet, onCommand,
  blueTeamResult, isMuted, onToggleMute,
  thoughts, monitoring, nodeCount, linkCount, flaggedNodes, hasSelection,
}: Props) {
  const feedRef = useRef<HTMLDivElement>(null)

  // Auto-scroll the thought feed.
  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight
  }, [thoughts.length])

  const { graphs } = blueTeamResult
  const hasFraud    = graphs.some(g => g.flagged)
  const fraudGraphs = graphs.filter(g => g.flagged)
  const meta = stateMeta(voiceState)
  const isBusy = voiceState === 'speaking' || voiceState === 'fraud'

  return (
    <motion.div
      animate={{ width: isOpen ? PANEL_W : STRIP_W }}
      transition={{ type: 'spring', stiffness: 300, damping: 34 }}
      style={{
        position: 'absolute', top: 44, right: 0, bottom: 44, zIndex: 40,
        overflow: 'hidden', display: 'flex', flexDirection: 'column',
      }}
    >
      {/* ── Backdrop ──────────────────────────────────────────────── */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{
              position: 'absolute', inset: 0,
              background: hasFraud ? 'rgba(12,10,14,0.96)' : 'rgba(13,17,23,0.94)',
              borderLeft: `1px solid ${hasFraud ? 'rgba(248,81,73,0.14)' : C.border}`,
              backdropFilter: 'blur(22px)', pointerEvents: 'none', transition: 'all 0.5s',
            }}
          />
        )}
      </AnimatePresence>

      {/* ── Collapsed strip ───────────────────────────────────────── */}
      <div
        style={{
          position: 'absolute', left: 0, top: 0, bottom: 0, width: STRIP_W, zIndex: 2,
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8,
          cursor: 'pointer',
        }}
        onClick={onToggle}
      >
        {!isOpen && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
            <motion.div
              animate={{
                backgroundColor: hasFraud ? 'rgba(248,81,73,0.4)' : 'rgba(68,147,248,0.25)',
                scale: [1, 1.05, 1],
              }}
              transition={{ repeat: Infinity, duration: hasFraud ? 0.9 : 2.5 }}
              style={{
                width: 14, height: 14, borderRadius: '50%',
                background: hasFraud ? 'rgba(248,81,73,0.3)' : 'rgba(68,147,248,0.2)',
                border: `1px solid ${hasFraud ? 'rgba(248,81,73,0.5)' : 'rgba(68,147,248,0.4)'}`,
              }}
            />
            {hasFraud && (
              <motion.div
                animate={{ opacity: [1, 0.2, 1] }} transition={{ repeat: Infinity, duration: 0.8 }}
                style={{ width: 3, height: 3, borderRadius: '50%', background: C.danger }}
              />
            )}
          </div>
        )}
        <motion.div
          animate={{ rotate: isOpen ? 0 : 180, x: isOpen ? 10 : 0 }}
          transition={{ type: 'spring', stiffness: 300, damping: 28 }}
          style={{ display: 'flex', color: C.text3 }}
        >
          <ChevronLeft size={14} />
        </motion.div>
      </div>

      {/* ── Panel content ─────────────────────────────────────────── */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.18, delay: 0.06 }}
            style={{
              position: 'absolute', inset: 0, left: 0, width: PANEL_W, zIndex: 1,
              display: 'flex', flexDirection: 'column', overflow: 'hidden',
            }}
          >
            {/* ── Header ─────────────────────────────────────────── */}
            <div style={{
              padding: '11px 16px 9px', borderBottom: `1px solid ${C.borderS}`,
              display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <motion.div
                  animate={{ opacity: [1, 0.35, 1] }}
                  transition={{ repeat: Infinity, duration: hasFraud ? 0.9 : 2.2 }}
                  style={{ width: 6, height: 6, borderRadius: '50%', background: meta.color, boxShadow: `0 0 8px ${meta.color}` }}
                />
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: C.text1, letterSpacing: '.06em', fontFamily: MONO }}>
                    UB · INTELLIGENCE CORE
                  </div>
                  <div style={{ fontSize: 9, color: meta.color, letterSpacing: '.1em', fontFamily: MONO }}>
                    {meta.label}
                  </div>
                </div>
              </div>
              <button
                onClick={onToggleMute}
                title={isMuted ? 'Unmute' : 'Mute'}
                style={{
                  width: 26, height: 26, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  borderRadius: 4, cursor: 'pointer', background: 'transparent',
                  border: `1px solid ${C.border}`, color: isMuted ? C.danger : C.text2,
                }}
              >
                {isMuted ? <VolumeX size={12} /> : <Volume2 size={12} />}
              </button>
            </div>

            {/* ── Orb + activity rings + waveform ─────────────────── */}
            <div style={{
              position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center',
              padding: '16px 16px 10px', borderBottom: `1px solid ${C.borderS}`, flexShrink: 0,
            }}>
              <div style={{ position: 'relative', width: 168, height: 168, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
                   onClick={onGreet}>
                <ActivityRings voiceState={voiceState} />
                <OrbCharacter voiceState={voiceState} size={156} />
              </div>
              <div style={{ marginTop: 4, width: '100%' }}>
                <OrbWaveform voiceState={voiceState} width={272} height={26} />
              </div>
            </div>

            {/* ── Live status bar ─────────────────────────────────── */}
            <div style={{
              padding: '7px 16px', borderBottom: `1px solid ${C.borderS}`, flexShrink: 0,
              display: 'flex', alignItems: 'center', gap: 12,
              fontFamily: MONO, fontSize: 9.5,
            }}>
              <span style={{ color: C.text3 }}>NODES <b style={{ color: C.text1, fontWeight: 600 }}>{nodeCount}</b></span>
              <span style={{ color: C.text3 }}>EDGES <b style={{ color: C.text1, fontWeight: 600 }}>{linkCount}</b></span>
              <span style={{ color: C.text3 }}>FLAGGED <b style={{ color: flaggedNodes > 0 ? C.danger : C.text1, fontWeight: 600 }}>{flaggedNodes}</b></span>
              <div style={{ flex: 1 }} />
              <span style={{ color: monitoring ? C.success : C.warn, letterSpacing: '.06em' }}>
                {monitoring ? 'LIVE' : 'PAUSED'}
              </span>
            </div>

            {/* ── Context-aware suggestions ───────────────────────── */}
            <div style={{ padding: '8px 14px 4px', borderBottom: `1px solid ${C.borderS}`, flexShrink: 0 }}>
              <div style={{ fontSize: 8.5, color: C.cyan, letterSpacing: '.14em', fontFamily: MONO, marginBottom: 5, display: 'flex', alignItems: 'center', gap: 5 }}>
                <motion.span
                  animate={{ opacity: [1, 0.4, 1] }} transition={{ repeat: Infinity, duration: 2 }}
                  style={{ width: 4, height: 4, borderRadius: '50%', background: C.cyan, display: 'inline-block' }}
                />
                SUGGESTED {hasSelection ? '· NODE SELECTED' : hasFraud ? '· FRAUD ACTIVE' : ''}
              </div>
              <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginBottom: 6 }}>
                {suggestionsFor(hasSelection, hasFraud, nodeCount).map(cmd => (
                  <motion.button
                    key={cmd.phrase}
                    whileHover={{ background: cmd.danger ? 'rgba(248,81,73,0.14)' : 'rgba(121,192,255,0.14)' }}
                    whileTap={{ scale: 0.96 }}
                    onClick={() => onCommand(cmd.phrase)}
                    style={{
                      padding: '5px 9px', borderRadius: 4, cursor: 'pointer',
                      background: cmd.danger ? 'rgba(248,81,73,0.06)' : 'rgba(121,192,255,0.06)',
                      border: `1px solid ${cmd.danger ? 'rgba(248,81,73,0.2)' : 'rgba(121,192,255,0.2)'}`,
                      fontSize: 10, color: cmd.danger ? C.danger : C.cyan, fontFamily: MONO, whiteSpace: 'nowrap',
                    }}
                  >
                    {cmd.label}
                  </motion.button>
                ))}
              </div>
            </div>

            {/* ── Command grid ────────────────────────────────────── */}
            <div style={{
              padding: '8px 14px 10px', borderBottom: `1px solid ${C.borderS}`, flexShrink: 0,
              maxHeight: 150, overflowY: 'auto',
            }}>
              {CMD_GROUPS.map(group => (
                <div key={group.title} style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 8.5, color: C.text3, letterSpacing: '.14em', fontFamily: MONO, marginBottom: 5 }}>
                    {group.title.toUpperCase()}
                  </div>
                  <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                    {group.cmds.map(cmd => (
                      <Chip key={cmd.phrase} cmd={cmd} onClick={() => onCommand(cmd.phrase)} />
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* ── Active fraud clusters ───────────────────────────── */}
            {hasFraud && (
              <div style={{ padding: '9px 16px', borderBottom: `1px solid ${C.borderS}`, flexShrink: 0 }}>
                <div style={{ fontSize: 8.5, color: C.danger, fontWeight: 600, marginBottom: 7, letterSpacing: '.12em', fontFamily: MONO }}>
                  ▲ ACTIVE FRAUD CLUSTERS
                </div>
                <div style={{ maxHeight: 120, overflowY: 'auto' }}>
                  {fraudGraphs.map(g => <InsightCard key={g.graph_id} graph={g} />)}
                </div>
              </div>
            )}

            {/* ── Live thought / investigation feed ───────────────── */}
            <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
              <div style={{
                padding: '8px 16px 4px', fontSize: 8.5, color: C.text3,
                letterSpacing: '.14em', fontFamily: MONO, flexShrink: 0,
              }}>
                THOUGHT STREAM
              </div>
              <div ref={feedRef} style={{ flex: 1, overflowY: 'auto', padding: '0 16px 10px' }}>
                <AnimatePresence initial={false}>
                  {thoughts.map(t => (
                    <motion.div
                      key={t.id}
                      initial={{ opacity: 0, x: -6 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.2 }}
                      style={{
                        display: 'flex', gap: 7, padding: '4px 0', alignItems: 'flex-start',
                        borderBottom: `1px solid rgba(255,255,255,0.02)`,
                      }}
                    >
                      <div style={{
                        width: 2, alignSelf: 'stretch', flexShrink: 0, borderRadius: 1,
                        background: KIND_COLOR[t.kind], opacity: 0.7, minHeight: 14,
                      }} />
                      <span style={{
                        fontSize: 10, lineHeight: 1.5, fontFamily: MONO,
                        color: t.kind === 'alert' ? '#d98080' : t.kind === 'info' ? C.text3 : C.text2,
                      }}>
                        {t.text}
                      </span>
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>
            </div>

            {/* ── Stop / engage control ───────────────────────────── */}
            <div style={{
              padding: '9px 16px', borderTop: `1px solid ${C.borderS}`, flexShrink: 0,
              display: 'flex', gap: 6, alignItems: 'center',
            }}>
              {isBusy ? (
                <motion.button
                  whileTap={{ scale: 0.96 }} onClick={onStop}
                  style={{
                    flex: 1, padding: '7px', borderRadius: 4, cursor: 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                    background: 'rgba(248,81,73,0.10)', border: '1px solid rgba(248,81,73,0.25)',
                    color: C.danger, fontSize: 11, fontFamily: MONO, letterSpacing: '.06em',
                  }}
                >
                  <Square size={10} /> HALT SPEECH
                </motion.button>
              ) : (
                <motion.button
                  whileTap={{ scale: 0.96 }} onClick={() => onCommand('summarize graph')}
                  style={{
                    flex: 1, padding: '7px', borderRadius: 4, cursor: 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                    background: 'rgba(68,147,248,0.08)', border: '1px solid rgba(68,147,248,0.22)',
                    color: C.accent, fontSize: 11, fontFamily: MONO, letterSpacing: '.06em',
                  }}
                >
                  RUN TOPOLOGY SCAN
                </motion.button>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
