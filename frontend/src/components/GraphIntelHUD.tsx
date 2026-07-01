// ──────────────────────────────────────────────────────────────────────────────
// GraphIntelHUD — the prominent "what is this graph" intelligence card.
//
// Surfaces the live classifier output in depth: the named GRAPH TYPE with its
// confidence provenance (structural vs verdict), the recommended action and its
// rationale, the network facts, the DETECTION SIGNALS that fired (with strength),
// the ranked PATTERN MATCH breakdown, the KEY ACCOUNTS by role + risk, the
// quantitative NETWORK METRICS, the RISK FACTORS, a human-readable summary, and
// the reconstructed fraud timeline.
//
// Non-intrusive: docks to the left edge under the header, collapsible to a slim
// rail, and only appears when a fraud cluster is present. Lets the analyst
// understand WHAT happened, WHY it is suspicious, WHO is involved and HOW money
// moved — without inspecting raw nodes.
// ──────────────────────────────────────────────────────────────────────────────
import { useState } from 'react'
import { motion } from 'framer-motion'
import {
  ChevronLeft, ChevronRight, Crosshair, FileText, Search, AlertTriangle, Clock,
  Activity, Radar, GitBranch, Users, ShieldAlert,
} from 'lucide-react'
import type { ClusterIntel, Severity, KeyAccount } from '../ai/graphClassifier'
import { fmtDur } from '../ai/graphClassifier'

// Cream / dull-white palette — warm off-white surfaces, dark warm text, muted accents.
const C = {
  glass:   'rgba(237,231,218,0.94)',  // dull cream panel
  raised:  'rgba(70,58,38,0.05)',     // subtly recessed block over cream
  border:  'rgba(70,58,38,0.16)',     // warm muted border
  text1:   '#33302a',                 // primary (warm near-black)
  text2:   '#6b6458',                 // secondary
  text3:   '#9c9486',                 // tertiary / dim
  accent:  '#4a6fa5',                 // muted slate-blue
  cyan:    '#3f7d8c',                 // muted teal
  warn:    '#b8860b',                 // deep amber (readable on cream)
  danger:  '#c0392b',                 // deep red
  success: '#2e7d32',                 // deep green
  magenta: '#a23ba8',                 // muted magenta
} as const

function sevColor(s: Severity): string {
  return s === 'CRITICAL' || s === 'HIGH' ? C.danger : s === 'MODERATE' ? C.warn : C.cyan
}

function money(v: number): string {
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)}Cr`
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)}L`
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(0)}K`
  return `₹${Math.round(v)}`
}

interface Props {
  intel:         ClusterIntel | null
  clusterCount:  number
  clusterIndex:  number          // 0-based, which flagged cluster is shown
  onCycle:       () => void      // step to the next flagged cluster
  onFocus:       () => void      // frame this cluster in the 3D scene
  onInvestigate: () => void      // UB live investigation
  onEvidence:    () => void      // build evidence package
}

function Fact({ label, value, color = C.text1 }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={{ fontSize: 8.5, color: C.text3, letterSpacing: '.10em', textTransform: 'uppercase' }}>{label}</span>
      <span style={{ fontSize: 11.5, fontWeight: 600, color, fontFamily: '"JetBrains Mono", ui-monospace, monospace' }}>{value}</span>
    </div>
  )
}

function pct(v: number): string { return `${Math.round(v * 100)}%` }

// Section heading with icon — matches the FRAUD TIMELINE label style.
function SectionLabel({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 9 }}>
      {icon}
      <span style={{ fontSize: 9, color: C.text3, letterSpacing: '.14em' }}>{children}</span>
    </div>
  )
}

// A labelled horizontal strength bar (used for signals + pattern scores).
function StrengthRow({ label, detail, value, color }: { label: string; detail?: string; value: number; color: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span style={{ fontSize: 10.5, fontWeight: 600, color: C.text1, flexShrink: 0 }}>{label}</span>
        {detail && <span style={{ fontSize: 9, color: C.text3, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{detail}</span>}
        <span style={{ fontSize: 9.5, fontWeight: 700, color, fontVariantNumeric: 'tabular-nums', marginLeft: 'auto' }}>{pct(value)}</span>
      </div>
      <div style={{ height: 3, background: 'rgba(70,58,38,0.10)', borderRadius: 2, overflow: 'hidden' }}>
        <motion.div
          style={{ height: '100%', background: color, borderRadius: 2 }}
          initial={{ width: 0 }} animate={{ width: `${Math.round(value * 100)}%` }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
        />
      </div>
    </div>
  )
}

// Role → accent colour for the key-accounts list.
function roleColor(role: KeyAccount['role']): string {
  switch (role) {
    case 'source': case 'origin': return C.warn
    case 'sink':                  return C.magenta
    case 'hub':                   return C.accent
    case 'bridge':                return C.danger
    case 'mule': case 'relay':    return C.cyan
    default:                      return C.text2
  }
}

export function GraphIntelHUD({
  intel, clusterCount, clusterIndex, onCycle, onFocus, onInvestigate, onEvidence,
}: Props) {
  const [collapsed, setCollapsed] = useState(false)
  if (!intel) return null

  const sc = sevColor(intel.severity)
  const conf = Math.round(intel.confidence * 100)

  return (
    <motion.div
      initial={{ opacity: 0, x: -16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -16 }}
      transition={{ type: 'spring', stiffness: 280, damping: 30 }}
      style={{
        position: 'absolute', left: 52, top: 56, zIndex: 45,
        width: collapsed ? 44 : 344,
        maxHeight: 'calc(100vh - 120px)',
        display: 'flex', flexDirection: 'column',
        background: C.glass,
        border: `1px solid ${intel.severity === 'CRITICAL' ? 'rgba(192,57,43,0.42)' : C.border}`,
        borderRadius: 10,
        backdropFilter: 'blur(22px) saturate(140%)',
        WebkitBackdropFilter: 'blur(22px) saturate(140%)',
        boxShadow: intel.severity === 'CRITICAL'
          ? '0 8px 34px rgba(192,57,43,0.20), 0 0 0 1px rgba(192,57,43,0.14) inset'
          : '0 8px 26px rgba(60,50,30,0.22)',
        overflow: 'hidden', userSelect: 'none',
      }}
    >
      {/* ── Collapsed rail ─────────────────────────────────────────────── */}
      {collapsed ? (
        <button
          onClick={() => setCollapsed(false)}
          title="Graph intelligence"
          style={{
            all: 'unset', cursor: 'pointer', height: 120,
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8,
          }}
        >
          <AlertTriangle size={14} color={sc} />
          <span style={{
            writingMode: 'vertical-rl', fontSize: 9, fontWeight: 700, letterSpacing: '.14em',
            color: C.text2, textTransform: 'uppercase',
          }}>
            Intel
          </span>
          <ChevronRight size={13} color={C.text3} />
        </button>
      ) : (
        <>
          {/* ── Header ──────────────────────────────────────────────────── */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '9px 10px 9px 12px', borderBottom: `1px solid ${C.border}`,
          }}>
            <motion.div
              style={{ width: 6, height: 6, borderRadius: '50%', background: sc, flexShrink: 0, boxShadow: `0 0 8px ${sc}` }}
              animate={{ opacity: [1, 0.3, 1] }}
              transition={{ repeat: Infinity, duration: 1.2 }}
            />
            <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.14em', color: C.text2, flex: 1 }}>
              GRAPH INTELLIGENCE
            </span>
            {clusterCount > 1 && (
              <button
                onClick={onCycle}
                title="Next flagged cluster"
                style={{
                  all: 'unset', cursor: 'pointer', fontSize: 9, color: C.cyan,
                  padding: '2px 6px', borderRadius: 4, border: `1px solid ${C.border}`,
                  fontFamily: 'ui-monospace, monospace',
                }}
              >
                {clusterIndex + 1}/{clusterCount} ›
              </button>
            )}
            <button onClick={() => setCollapsed(true)} title="Collapse" style={{ all: 'unset', cursor: 'pointer', display: 'flex' }}>
              <ChevronLeft size={14} color={C.text3} />
            </button>
          </div>

          {/* ── Scroll body ─────────────────────────────────────────────── */}
          <div style={{ overflowY: 'auto', padding: '12px', display: 'flex', flexDirection: 'column', gap: 14 }}>

            {/* GRAPH TYPE — the prominent classification */}
            <div>
              <div style={{ fontSize: 9, color: C.text3, letterSpacing: '.16em', marginBottom: 4 }}>GRAPH TYPE</div>
              <div style={{
                fontSize: 19, fontWeight: 700, color: C.text1, lineHeight: 1.1, letterSpacing: '-0.01em',
              }}>
                {intel.typeLabel}
              </div>
              {/* Confidence bar */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
                <div style={{ flex: 1, height: 4, background: 'rgba(70,58,38,0.12)', borderRadius: 2, overflow: 'hidden' }}>
                  <motion.div
                    style={{ height: '100%', background: sc, borderRadius: 2 }}
                    initial={{ width: 0 }}
                    animate={{ width: `${conf}%` }}
                    transition={{ duration: 0.6, ease: 'easeOut' }}
                  />
                </div>
                <span style={{ fontSize: 11, fontWeight: 700, color: sc, fontVariantNumeric: 'tabular-nums' }}>{conf}%</span>
              </div>
              {/* Confidence provenance — structural evidence vs backend verdict */}
              <div style={{ display: 'flex', gap: 10, marginTop: 6, fontSize: 8.5, color: C.text3 }}>
                <span>Structural <b style={{ color: C.text2, fontWeight: 700 }}>{pct(intel.confidenceBreakdown.structural)}</b></span>
                <span>Verdict <b style={{ color: C.text2, fontWeight: 700 }}>{pct(intel.confidenceBreakdown.verdict)}</b></span>
              </div>
              {intel.alsoMatched.length > 0 && (
                <div style={{ fontSize: 8.5, color: C.text3, marginTop: 5 }}>
                  Also matched: {intel.alsoMatched.map(t => t.replace(/_/g, ' ')).join(', ')}
                </div>
              )}
            </div>

            {/* Severity + recommendation pills */}
            <div style={{ display: 'flex', gap: 6 }}>
              <span style={{
                fontSize: 9, fontWeight: 700, letterSpacing: '.06em', color: sc,
                padding: '3px 8px', borderRadius: 4, background: `${sc}1a`, border: `1px solid ${sc}3a`,
              }}>
                {intel.severity}
              </span>
              <span style={{
                fontSize: 9, fontWeight: 600, color: C.cyan,
                padding: '3px 8px', borderRadius: 4, background: 'rgba(63,125,140,0.12)', border: `1px solid rgba(63,125,140,0.30)`,
              }}>
                {intel.recommendation}
              </span>
            </div>

            {/* Why this action */}
            <div style={{ fontSize: 9.5, lineHeight: 1.5, color: C.text3, marginTop: -6 }}>
              {intel.actionRationale}
            </div>

            {/* Network facts grid */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '11px 12px' }}>
              <Fact label="Accounts" value={String(intel.accounts)} />
              <Fact label="Transactions" value={String(intel.transactions)} />
              <Fact label="Volume" value={money(intel.volume)} color={C.cyan} />
              <Fact label="Duration" value={fmtDur(intel.durationMin)} />
              <Fact label="Primary Source" value={intel.primarySource ?? '—'} color={C.warn} />
              <Fact label="Primary Sink" value={intel.primarySink ?? '—'} color={C.magenta} />
            </div>

            {/* Detection signals — the structural evidence behind the verdict */}
            {intel.indicators.length > 0 && (
              <div>
                <SectionLabel icon={<Radar size={11} color={C.text3} />}>DETECTION SIGNALS</SectionLabel>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                  {intel.indicators.slice(0, 6).map(ind => (
                    <StrengthRow
                      key={ind.key}
                      label={ind.label}
                      detail={ind.detail}
                      value={ind.strength}
                      color={ind.strength >= 0.66 ? C.danger : ind.strength >= 0.4 ? C.warn : C.cyan}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Pattern-match breakdown — how the candidate patterns ranked */}
            {intel.patternScores.length > 1 && (
              <div>
                <SectionLabel icon={<GitBranch size={11} color={C.text3} />}>PATTERN MATCH</SectionLabel>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {intel.patternScores.map((p, i) => (
                    <StrengthRow
                      key={p.type}
                      label={p.label}
                      value={p.score}
                      color={i === 0 ? sc : C.text2}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Key accounts — who matters, by role and risk */}
            {intel.keyAccounts.length > 0 && (
              <div>
                <SectionLabel icon={<Users size={11} color={C.text3} />}>KEY ACCOUNTS</SectionLabel>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                  {intel.keyAccounts.map(a => {
                    const rc = roleColor(a.role)
                    return (
                      <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ width: 6, height: 6, borderRadius: '50%', background: rc, flexShrink: 0 }} />
                        <span style={{ fontSize: 10.5, fontWeight: 600, color: C.text1, fontFamily: 'ui-monospace, monospace' }}>{a.id}</span>
                        <span style={{
                          fontSize: 8.5, fontWeight: 600, color: rc, letterSpacing: '.03em',
                          padding: '1px 6px', borderRadius: 3, background: `${rc}18`, border: `1px solid ${rc}33`,
                        }}>
                          {a.roleLabel}
                        </span>
                        <span style={{ marginLeft: 'auto', fontSize: 9, color: a.netFlow >= 0 ? C.warn : C.magenta, fontFamily: 'ui-monospace, monospace' }}>
                          {a.netFlow >= 0 ? '+' : '−'}{money(Math.abs(a.netFlow))}
                        </span>
                        <span style={{ fontSize: 9, fontWeight: 700, color: a.risk >= 0.7 ? C.danger : a.risk >= 0.4 ? C.warn : C.text2, fontVariantNumeric: 'tabular-nums', width: 30, textAlign: 'right' }}>
                          {pct(a.risk)}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Quantitative network metrics */}
            <div>
              <SectionLabel icon={<Activity size={11} color={C.text3} />}>NETWORK METRICS</SectionLabel>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '11px 12px' }}>
                <Fact label="Velocity" value={intel.metrics.velocityTxPerMin > 0 ? `${intel.metrics.velocityTxPerMin.toFixed(1)}/min` : '—'} color={intel.metrics.velocityTxPerMin >= 2 ? C.warn : C.text1} />
                <Fact label="Avg Transfer" value={intel.metrics.avgTx > 0 ? money(intel.metrics.avgTx) : '—'} />
                <Fact label="Largest" value={intel.metrics.largestTx > 0 ? money(intel.metrics.largestTx) : '—'} color={C.cyan} />
                <Fact label="Density" value={pct(intel.metrics.density)} />
                <Fact label="Concentration" value={pct(intel.metrics.concentration)} color={intel.metrics.concentration >= 0.6 ? C.warn : C.text1} />
                <Fact label="Retention" value={pct(intel.metrics.retention)} color={intel.metrics.retention <= 0.15 ? C.danger : C.text1} />
                {intel.metrics.rails.length > 0 && (
                  <div style={{ gridColumn: '1 / -1' }}>
                    <Fact label="Payment Rails" value={intel.metrics.rails.join(' · ')} color={intel.metrics.rails.length >= 3 ? C.warn : C.text1} />
                  </div>
                )}
              </div>
            </div>

            {/* Risk factors — the "why flagged" bullets */}
            {intel.riskFactors.length > 0 && (
              <div>
                <SectionLabel icon={<ShieldAlert size={11} color={C.text3} />}>RISK FACTORS</SectionLabel>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {intel.riskFactors.map((f, i) => (
                    <div key={i} style={{ display: 'flex', gap: 7 }}>
                      <span style={{ color: sc, fontSize: 11, lineHeight: 1.4, flexShrink: 0 }}>›</span>
                      <span style={{ fontSize: 10, lineHeight: 1.45, color: C.text2 }}>{f}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Human-readable summary */}
            <div style={{
              fontSize: 11, lineHeight: 1.55, color: C.text2,
              padding: '10px 11px', background: C.raised, borderRadius: 7,
              border: `1px solid ${C.border}`,
            }}>
              {intel.summary}
            </div>

            {/* Fraud timeline */}
            {intel.timeline.length > 0 && (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                  <Clock size={11} color={C.text3} />
                  <span style={{ fontSize: 9, color: C.text3, letterSpacing: '.14em' }}>FRAUD TIMELINE</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 0, position: 'relative' }}>
                  {intel.timeline.map((ev, i) => (
                    <div key={i} style={{ display: 'flex', gap: 9, paddingBottom: i === intel.timeline.length - 1 ? 0 : 12, position: 'relative' }}>
                      {/* rail */}
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
                        <div style={{ width: 7, height: 7, borderRadius: '50%', background: sc, boxShadow: `0 0 6px ${sc}`, marginTop: 2 }} />
                        {i < intel.timeline.length - 1 && (
                          <div style={{ width: 1, flex: 1, background: C.border, marginTop: 2 }} />
                        )}
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
                          <span style={{ fontSize: 10, fontWeight: 700, color: C.cyan, fontFamily: 'ui-monospace, monospace' }}>{ev.at}</span>
                          <span style={{ fontSize: 10.5, fontWeight: 600, color: C.text1 }}>{ev.title}</span>
                        </div>
                        <div style={{ fontSize: 9.5, color: C.text3, lineHeight: 1.4, marginTop: 1 }}>{ev.detail}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* ── Action bar ──────────────────────────────────────────────── */}
          <div style={{ display: 'flex', gap: 6, padding: '9px 10px', borderTop: `1px solid ${C.border}` }}>
            <HudBtn icon={<Crosshair size={12} />} label="Focus" onClick={onFocus} />
            <HudBtn icon={<Search size={12} />} label="Investigate" onClick={onInvestigate} primary />
            <HudBtn icon={<FileText size={12} />} label="Evidence" onClick={onEvidence} />
          </div>
        </>
      )}
    </motion.div>
  )
}

function HudBtn({ icon, label, onClick, primary = false }: { icon: React.ReactNode; label: string; onClick: () => void; primary?: boolean }) {
  return (
    <button
      onClick={onClick}
      style={{
        all: 'unset', cursor: 'pointer', flex: 1,
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
        padding: '7px 4px', borderRadius: 6,
        background: primary ? 'rgba(74,111,165,0.16)' : 'rgba(70,58,38,0.05)',
        border: `1px solid ${primary ? 'rgba(74,111,165,0.40)' : C.border}`,
        color: primary ? C.accent : C.text2,
        fontSize: 10, fontWeight: 600,
      }}
    >
      {icon}{label}
    </button>
  )
}
