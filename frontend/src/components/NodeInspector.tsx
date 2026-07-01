import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X, AlertTriangle, ShieldCheck, Brain,
  Zap, ArrowUpRight, ArrowDownLeft, MapPin,
  Banknote, Network, Activity, Crosshair, GitBranch, Scale,
} from 'lucide-react'
import type { GraphNode, ClassificationStatus, GraphComponentResult, CashNodeType } from '../types'
import { riskPct, pctValue } from '../utils/percent'
import { exposureLabel, roleLabel, type NodeIntel } from '../ai/riskPropagation'
import { apiUrl, sessionHeaders } from '../config'

// ── Design tokens ─────────────────────────────────────────────────────────────
const C = {
  bg:          'rgba(7,9,15,0.98)',
  surface:     'rgba(255,255,255,0.028)',
  surfaceHover:'rgba(255,255,255,0.045)',
  border:      'rgba(255,255,255,0.07)',
  borderS:     'rgba(255,255,255,0.04)',
  text1:       '#e8eef7',
  text2:       '#8d97ad',
  text3:       '#414855',
  accent:      '#3d8ef5',
  accentGlow:  'rgba(61,142,245,0.14)',
  warn:        '#d4970e',
  warnGlow:    'rgba(212,151,14,0.12)',
  danger:      '#ef4444',
  dangerGlow:  'rgba(239,68,68,0.12)',
  orange:      '#e3683e',
  orangeGlow:  'rgba(227,104,62,0.12)',
  success:     '#22c55e',
  successGlow: 'rgba(34,197,94,0.10)',
  purple:      '#a855f7',
  gold:        '#d4a11e',
} as const

// ── Risk palette ──────────────────────────────────────────────────────────────
function riskColor(score: number, isFraud: boolean): string {
  if (isFraud)   return C.danger
  if (score > 0.7) return C.orange
  if (score > 0.45) return C.warn
  return C.accent
}

function riskGlow(score: number, isFraud: boolean): string {
  if (isFraud)   return C.dangerGlow
  if (score > 0.7) return C.orangeGlow
  if (score > 0.45) return C.warnGlow
  return C.accentGlow
}

function riskLabel(score: number, isFraud: boolean): string {
  if (isFraud)    return 'FRAUD FLAGGED'
  if (score > 0.7) return 'HIGH RISK'
  if (score > 0.45) return 'MODERATE'
  if (score > 0.2) return 'LOW RISK'
  return 'NORMAL'
}

// ── Helper ────────────────────────────────────────────────────────────────────
function fmt(v: number): string {
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)}Cr`
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(2)}L`
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(1)}K`
  return `₹${Math.floor(v)}`
}

function computeRole(node: GraphNode): { label: string; color: string } {
  const hasIn  = (node.incoming_count ?? 0) > 0
  const hasOut = (node.outgoing_count ?? 0) > 0
  const ratio  = (node.total_sent ?? 0) / ((node.total_received ?? 0) || 1)
  if (!hasIn && hasOut)  return { label: 'Origin / Source', color: C.warn }
  if (hasIn && !hasOut)  return { label: 'Sink / Terminal', color: C.purple }
  if (hasIn && hasOut) {
    if (node.account_type === 'mule' || ratio > 0.85)
      return { label: 'Mule / Relay', color: C.orange }
    return { label: 'Intermediary', color: C.accent }
  }
  return { label: 'Isolated', color: C.text3 }
}

function generateAI(
  node: GraphNode, isFraud: boolean, comp: GraphComponentResult | null,
  effectiveRisk: number, exposure: string, isInherited: boolean,
): string {
  const isHub = (node.connected_accounts?.length ?? 0) > 4
  const pct   = Math.round(effectiveRisk * 100)
  if (isInherited) {
    const reason = (comp?.suspicious_reason ?? 'fraudulent activity').replace(/_/g, ' ')
    return `Inherits ${pct}% risk via ${exposure.toLowerCase()} to fraud cluster ${comp?.graph_id ?? ''} (${reason}). This account is implicated by proximity to a confirmed fraud hub even though its own transactions are not individually flagged. Recommend tracing its links into the cluster.`
  }
  if (isFraud) {
    const reason = (comp?.suspicious_reason ?? 'anomalous activity').replace(/_/g, ' ')
    const hops = node.connected_accounts?.length ?? 0
    return `Confirmed fraud signal at ${pct}% confidence. ${reason.charAt(0).toUpperCase() + reason.slice(1)} pattern detected across ${hops} linked entities. Rapid hop velocity consistent with layering-phase money movement.`
  }
  if (effectiveRisk > 0.6) {
    return `Elevated activity detected. Account exhibits ${isHub ? 'hub-and-spoke' : 'sequential'} disbursement with above-threshold velocity. Recommend enhanced monitoring and 30-day retrospective review.`
  }
  if (effectiveRisk > 0.3) {
    return `Moderate transaction velocity. Behavior deviates from baseline within acceptable range. Scheduled for periodic compliance review under standard protocol.`
  }
  return `${isHub ? `Multi-connection hub (${node.connected_accounts?.length ?? 0} peers) with` : 'Account shows'} balanced in-out flow distribution. Behavior within normal parameters. No laundering sequences detected.`
}

// ── Types ─────────────────────────────────────────────────────────────────────
interface Props {
  node: (GraphNode & { isCashNode?: boolean; cashType?: CashNodeType; amount?: number; parentAccount?: string }) | null
  classification: ClassificationStatus
  onClose: () => void
  fraudNodeIds?: ReadonlySet<string>
  nodeToGraphId?: Map<string, string>
  graphComponents?: GraphComponentResult[]
  /** Unified propagated-risk intel for this node (source of truth). */
  nodeIntel?: NodeIntel | null
}

// ── Micro-components ──────────────────────────────────────────────────────────

function RiskArc({ score, color }: { score: number; color: string }) {
  const r = 34
  const size = 88
  const cx = size / 2
  const cy = size / 2
  const circumference = 2 * Math.PI * r
  const dashOffset = circumference * (1 - Math.min(1, Math.max(0, score)))
  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ position: 'absolute', inset: 0 }}>
        {/* Outer ambient ring */}
        <circle cx={cx} cy={cy} r={r + 5} fill="none" stroke={color} strokeWidth="1" opacity="0.07" />
        {/* Track */}
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="2.5" />
        {/* Progress */}
        <motion.circle
          cx={cx} cy={cy} r={r}
          fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: dashOffset }}
          transition={{ duration: 1.5, ease: [0.16, 1, 0.3, 1] }}
          transform={`rotate(-90 ${cx} ${cy})`}
        />
        {/* Glow end cap */}
        <motion.circle
          cx={cx} cy={cy} r={r}
          fill="none" stroke={color} strokeWidth="6" strokeLinecap="round"
          strokeDasharray={`0 ${circumference}`}
          initial={{ strokeDashoffset: 0, opacity: 0 }}
          animate={{ opacity: [0, 0.3, 0] }}
          transition={{ duration: 1.5, ease: 'easeOut' }}
          transform={`rotate(-90 ${cx} ${cy})`}
          style={{ filter: `blur(4px)` }}
        />
      </svg>
      <div style={{
        position: 'absolute', inset: 0,
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      }}>
        <motion.span
          initial={{ opacity: 0, scale: 0.75 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.35, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          style={{
            fontSize: 17, fontWeight: 800, lineHeight: 1,
            fontFamily: 'ui-monospace, monospace', fontVariantNumeric: 'tabular-nums', color,
          }}
        >
          {(score * 100).toFixed(0)}
        </motion.span>
        <span style={{ fontSize: 7, color: 'rgba(255,255,255,0.22)', letterSpacing: '.08em', marginTop: 2 }}>%</span>
      </div>
    </div>
  )
}

function Typewriter({ text, startDelay = 200, speed = 16 }: { text: string; startDelay?: number; speed?: number }) {
  const [chars, setChars] = useState(0)
  useEffect(() => {
    setChars(0)
    const init = setTimeout(() => {
      const id = setInterval(() => {
        setChars(n => {
          if (n >= text.length) { clearInterval(id); return n }
          return n + 1
        })
      }, speed)
      return () => clearInterval(id)
    }, startDelay)
    return () => clearTimeout(init)
  }, [text, startDelay, speed])
  const done = chars >= text.length
  return (
    <span>
      {text.slice(0, chars)}
      {!done && (
        <motion.span
          animate={{ opacity: [1, 0] }}
          transition={{ repeat: Infinity, duration: 0.55 }}
          style={{ display: 'inline-block', width: 1.5, height: '0.85em', background: C.accent, verticalAlign: 'middle', marginLeft: 2 }}
        />
      )}
    </span>
  )
}

function ConnectionChip({ id, isFraud }: { id: string; isFraud: boolean }) {
  const [hov, setHov] = useState(false)
  return (
    <span
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        fontSize: 9, padding: '3px 7px', borderRadius: 4,
        fontFamily: 'ui-monospace, monospace',
        transition: 'all 0.18s',
        cursor: 'default',
        background: hov
          ? (isFraud ? 'rgba(239,68,68,0.10)' : 'rgba(61,142,245,0.08)')
          : 'rgba(255,255,255,0.03)',
        border: `1px solid ${hov
          ? (isFraud ? 'rgba(239,68,68,0.35)' : 'rgba(61,142,245,0.25)')
          : C.borderS}`,
        color: isFraud ? (hov ? C.danger : '#a06060') : (hov ? C.text2 : C.text3),
        boxShadow: (hov && isFraud) ? `0 0 10px rgba(239,68,68,0.18)` : undefined,
      }}
    >
      {id.length > 12 ? id.slice(-8) : id}
    </span>
  )
}

// Section header with thin rule
function SectionHead({ label, count, icon }: { label: string; count?: number; icon?: React.ReactNode }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      marginBottom: 10, paddingBottom: 7,
      borderBottom: `1px solid ${C.borderS}`,
    }}>
      {icon && <span style={{ color: C.text3, lineHeight: 0, flexShrink: 0 }}>{icon}</span>}
      <span style={{ fontSize: 9, fontWeight: 600, color: C.text3, letterSpacing: '.10em', textTransform: 'uppercase' }}>
        {label}
      </span>
      {count !== undefined && (
        <span style={{
          fontSize: 8, padding: '1px 5px', borderRadius: 3,
          background: 'rgba(255,255,255,0.04)', color: C.text3, fontFamily: 'monospace',
        }}>
          {count}
        </span>
      )}
    </div>
  )
}

// Key/value row
function InfoRow({ label, value, color, mono = true }: { label: string; value: string; color?: string; mono?: boolean }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '5px 0', borderBottom: `1px solid ${C.borderS}`,
    }}>
      <span style={{ fontSize: 10, color: C.text3 }}>{label}</span>
      <span style={{
        fontSize: 11, fontWeight: 500, color: color ?? C.text2,
        fontFamily: mono ? 'ui-monospace, monospace' : 'inherit',
      }}>
        {value}
      </span>
    </div>
  )
}

// ── Customer Profile card (Profile Intelligence demonstration) ────────────────
// Compact, professional. Shows the inferred customer profile, expected vs current
// behaviour, and the profile-driven risk adjustment — so an investigator sees WHY
// the same behaviour is normal for one customer and suspicious for another.
function CustomerProfileCard({ intel }: { intel: import('../types').AccountProfileIntel }) {
  const adj = intel.adjustment_pct
  const raised = adj > 0
  const adjColor = raised ? C.danger : adj < 0 ? C.success : C.text2
  const adjText = `${adj > 0 ? '+' : ''}${adj}%`
  return (
    <div style={{
      marginTop: 10, padding: '9px 11px', borderRadius: 7,
      background: 'rgba(61,142,245,0.04)', border: `1px solid rgba(61,142,245,0.16)`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontSize: 9, letterSpacing: '.06em', color: C.text3, textTransform: 'uppercase' }}>
          Customer Profile
        </span>
        <span style={{
          fontSize: 9, padding: '1px 6px', borderRadius: 10, fontWeight: 600,
          background: `${adjColor}14`, border: `1px solid ${adjColor}30`, color: adjColor,
        }}>
          Risk {raised ? '↑' : adj < 0 ? '↓' : '·'} {adjText}
        </span>
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, color: C.text1, marginBottom: 6 }}>{intel.label}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        <div style={{ display: 'flex', gap: 6 }}>
          <span style={{ fontSize: 9, color: C.text3, width: 58, flexShrink: 0 }}>Expected</span>
          <span style={{ fontSize: 10, color: C.text2 }}>{intel.expected}</span>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <span style={{ fontSize: 9, color: C.text3, width: 58, flexShrink: 0 }}>Current</span>
          <span style={{ fontSize: 10, color: C.text2 }}>{intel.current}</span>
        </div>
      </div>
      {intel.reasons.length > 0 && (
        <div style={{ marginTop: 6, paddingTop: 6, borderTop: `1px solid ${C.borderS}` }}>
          {intel.reasons.slice(0, 3).map((r, i) => (
            <div key={i} style={{ fontSize: 9.5, color: raised ? '#c98a8a' : C.text2, lineHeight: 1.45 }}>
              {raised ? '• ' : '✓ '}{r}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Cross-Bank Intelligence — "has this entity behaved suspiciously at OTHER banks?".
// Metadata only; rendered when the component carries a cross-bank report for this node.
function CrossBankCard({ intel, banks }: {
  intel: import('../types').CrossBankAccountIntel
  banks?: string[]
}) {
  const risk = intel.cross_bank_risk
  const accent = risk >= 70 ? C.danger : risk >= 45 ? '#d4a11e' : C.text2
  const seen = (intel.banks_seen && intel.banks_seen.length ? intel.banks_seen : banks) ?? []
  return (
    <div style={{
      marginTop: 10, padding: '9px 11px', borderRadius: 7,
      background: `${accent}0a`, border: `1px solid ${accent}28`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontSize: 9, letterSpacing: '.06em', color: C.text3, textTransform: 'uppercase' }}>
          Cross-Bank Intelligence
        </span>
        <span style={{
          fontSize: 9, padding: '1px 6px', borderRadius: 10, fontWeight: 700,
          background: `${accent}14`, border: `1px solid ${accent}30`, color: accent,
        }}>
          {risk} / 100
        </span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        <div style={{ display: 'flex', gap: 6 }}>
          <span style={{ fontSize: 9, color: C.text3, width: 92, flexShrink: 0 }}>Banks seen</span>
          <span style={{ fontSize: 10, color: C.text2 }}>{intel.linked_banks}{seen.length ? ` · ${seen.slice(0, 5).join(', ')}` : ''}</span>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <span style={{ fontSize: 9, color: C.text3, width: 92, flexShrink: 0 }}>Linked accounts</span>
          <span style={{ fontSize: 10, color: C.text2 }}>{intel.linked_accounts}</span>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <span style={{ fontSize: 9, color: C.text3, width: 92, flexShrink: 0 }}>Shared devices</span>
          <span style={{ fontSize: 10, color: C.text2 }}>{intel.shared_devices}</span>
        </div>
        {intel.known_suspicious && (
          <div style={{ fontSize: 9.5, color: C.danger, marginTop: 2, fontWeight: 600 }}>
            ⚑ Known to other banks
          </div>
        )}
      </div>
      {intel.reasons?.length > 0 && (
        <div style={{ marginTop: 6, paddingTop: 6, borderTop: `1px solid ${C.borderS}` }}>
          {intel.reasons.slice(0, 3).map((r, i) => (
            <div key={i} style={{ fontSize: 9.5, color: C.text2, lineHeight: 1.45 }}>• {r}</div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Panel shared layout ───────────────────────────────────────────────────────
const PANEL_STYLE: React.CSSProperties = {
  position: 'absolute',
  top: 44, right: 44, bottom: 44,
  zIndex: 55,
  width: 300,
  display: 'flex', flexDirection: 'column',
  background: C.bg,
  borderLeft: '1px solid rgba(255,255,255,0.08)',
  backdropFilter: 'blur(28px) saturate(140%)',
  overflow: 'hidden',
}

// Framer variants for staggered section reveal
const BODY_VARIANTS = {
  initial: {},
  animate: { transition: { staggerChildren: 0.045, delayChildren: 0.12 } },
}
const SECTION_VARIANTS = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.16, 1, 0.3, 1] } },
}

// ── CashNode inspector ────────────────────────────────────────────────────────
function CashNodeInspector({
  id, cashType, amount, parentAccount, onClose, firstClass = false, channel,
}: { id: string; cashType: CashNodeType; amount: number; parentAccount: string
     onClose: () => void; firstClass?: boolean; channel?: string }) {
  const isCashIn = cashType === 'CASH_IN'
  // Emerald for cash-IN (entry), gold for cash-OUT (exit) — identity colour that
  // fraud never overrides (matches the graph node fill in graphStore).
  const accent = isCashIn ? '#00b368' : '#d4a11e'

  return (
    <AnimatePresence>
      <motion.div
        key={id}
        initial={{ x: 20, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: 20, opacity: 0 }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
        style={PANEL_STYLE}
      >
        {/* Header */}
        <div style={{
          padding: '14px 16px 12px',
          borderBottom: `1px solid ${C.borderS}`,
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 6 }}>
                <motion.div
                  style={{ width: 6, height: 6, borderRadius: '50%', background: accent, flexShrink: 0 }}
                  animate={{ opacity: [0.9, 0.4, 0.9] }}
                  transition={{ repeat: Infinity, duration: 2.4 }}
                />
                <span style={{ fontSize: 9, fontWeight: 600, color: accent, letterSpacing: '.10em' }}>
                  {isCashIn ? 'CASH INFLOW' : 'CASH OUTFLOW'}
                </span>
              </div>
              <div style={{ fontSize: 13, fontWeight: 700, fontFamily: 'ui-monospace, monospace', color: C.text1 }}>
                {isCashIn ? 'Cash Deposit Event' : 'Cash Withdrawal Event'}
              </div>
              <div style={{ fontSize: 10, color: C.text3, marginTop: 2 }}>
                {firstClass
                  ? (isCashIn ? 'Funds entered banking system' : 'Funds exited banking system')
                  : 'Off-graph physical rail'}
              </div>
            </div>
            <CloseBtn onClose={onClose} />
          </div>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{
            padding: '14px', borderRadius: 8,
            background: `rgba(212,161,30,0.06)`,
            border: `1px solid rgba(212,161,30,0.18)`,
          }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: accent, fontFamily: 'ui-monospace, monospace', marginBottom: 4 }}>
              {fmt(amount)}
            </div>
            <div style={{ fontSize: 10, color: C.text3 }}>Transaction amount</div>
          </div>
          <section>
            <SectionHead label={isCashIn ? 'Cash Deposit' : 'Cash Withdrawal'} icon={<Banknote size={10} />} />
            <InfoRow label="Node type"      value={isCashIn ? 'Cash Deposit Event' : 'Cash Withdrawal Event'} color={accent} />
            <InfoRow label={isCashIn ? 'Into account' : 'Source account'} value={parentAccount || '—'} color={C.accent} />
            {channel ? <InfoRow label="Channel" value={channel} color={C.text3} /> : null}
            <InfoRow label="Rail type"      value={firstClass ? cashType : 'CASH (physical)'} color={C.text3} />
            <InfoRow label="Status"         value={isCashIn ? 'Entered banking system' : 'Exited banking system'} color={accent} />
          </section>
          <div style={{
            padding: '10px 12px', borderRadius: 6,
            background: C.surface, border: `1px solid ${C.borderS}`,
          }}>
            <p style={{ margin: 0, fontSize: 10, color: C.text3, lineHeight: 1.65 }}>
              {isCashIn
                ? 'Money entering the banking system as physical cash. This is an entry event, not a customer account.'
                : 'Money leaving the banking system as physical cash. This is a terminal exit event, not a customer account — it reduces recovery probability.'}
            </p>
          </div>
        </div>

        <PanelFooter tag={isCashIn ? 'CASH IN' : 'CASH OUT'} accentColor={accent} />
      </motion.div>
    </AnimatePresence>
  )
}

function CloseBtn({ onClose }: { onClose: () => void }) {
  const [hov, setHov] = useState(false)
  return (
    <button
      onClick={onClose}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        width: 26, height: 26, borderRadius: 5, flexShrink: 0,
        background: hov ? 'rgba(255,255,255,0.06)' : 'transparent',
        border: `1px solid ${hov ? 'rgba(255,255,255,0.14)' : C.border}`,
        cursor: 'pointer', color: hov ? C.text2 : C.text3,
        transition: 'all 0.15s',
      }}
    >
      <X size={12} />
    </button>
  )
}

function PanelFooter({ tag, accentColor }: { tag: string; accentColor: string }) {
  return (
    <div style={{
      padding: '8px 16px', borderTop: `1px solid ${C.borderS}`,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      flexShrink: 0,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <div style={{ width: 4, height: 4, borderRadius: '50%', background: C.text3, opacity: 0.4 }} />
        <span style={{ fontSize: 8, color: C.text3, letterSpacing: '.08em', fontFamily: 'monospace' }}>
          TGIE · NODE ANALYSIS
        </span>
      </div>
      <span style={{
        fontSize: 8, fontWeight: 700, letterSpacing: '.08em', fontFamily: 'monospace',
        padding: '2px 7px', borderRadius: 3,
        background: `${accentColor}14`, border: `1px solid ${accentColor}28`, color: accentColor,
      }}>
        {tag}
      </span>
    </div>
  )
}

// ── Backend Investigation Intelligence (additive) ──────────────────────────────
// Fetches the server-computed Blue Team V2 analysis for the selected account and
// renders the richer fields (explainable risk factors, centrality, money trail,
// evidence) the live graph payload can't carry. Pure visualisation of backend
// output — all logic stays server-side. Renders nothing until data arrives, so
// it never disturbs the existing panel.
interface NodeIntelResponse {
  available: boolean
  graph_id?: string
  role?: string
  node_risk_pct?: number
  confidence?: number
  risk_factors?: { factor: string; share: number }[]
  centrality?: { degree: number; betweenness: number; closeness: number; bridge_importance: number }
  metrics?: Record<string, number | boolean>
  patterns?: string[]
  evidence?: { pattern: string; title: string; description: string; severity: number; confidence: number }[]
  cluster?: { verdict: string; cluster_risk: number; primary_classification: string; narrative?: string; node_count: number }
  flow?: {
    direct_inflows: { account: string; amount: number; transfers: number }[]
    direct_outflows: { account: string; amount: number; transfers: number }[]
    upstream_sources: string[]
    downstream_beneficiaries: string[]
    upstream_count: number
    downstream_count: number
  }
  connected_suspicious?: string[]
}

function FactorBar({ label, share }: { label: string; share: number }) {
  const pct = Math.round(share * 100)
  return (
    <div style={{ marginBottom: 7 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
        <span style={{ fontSize: 9.5, color: C.text2 }}>{label}</span>
        <span style={{ fontSize: 9.5, color: C.text2, fontFamily: 'monospace' }}>{pct}%</span>
      </div>
      <div style={{ height: 3, background: 'rgba(255,255,255,0.05)', borderRadius: 2, overflow: 'hidden' }}>
        <motion.div
          style={{ height: '100%', borderRadius: 2, background: C.accent }}
          initial={{ width: 0 }} animate={{ width: `${pct}%` }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
        />
      </div>
    </div>
  )
}

function verdictColor(v?: string): string {
  if (v === 'FRAUD') return C.danger
  if (v === 'SUSPICIOUS') return C.warn
  if (v === 'LOGGED') return C.accent
  return C.success
}

function BackendIntelligence({ accountId }: { accountId: string }) {
  const [data, setData] = useState<NodeIntelResponse | null>(null)

  useEffect(() => {
    let alive = true
    setData(null)
    fetch(apiUrl(`/api/graph/node/${encodeURIComponent(accountId)}/intelligence`), {
      headers: sessionHeaders(),
    })
      .then(r => (r.ok ? r.json() : null))
      .then(j => { if (alive) setData(j) })
      .catch(() => { if (alive) setData(null) })
    return () => { alive = false }
  }, [accountId])

  if (!data || !data.available) return null
  const { role, node_risk_pct, confidence, risk_factors, centrality, cluster, flow, evidence } = data

  return (
    <>
      {/* ── Investigation Intelligence ─────────────────────────── */}
      <motion.section variants={SECTION_VARIANTS}>
        <SectionHead label="Investigation Intelligence" icon={<Crosshair size={9} />} />
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 12px' }}>
          {role && <InfoRow label="Structural role" value={role.replace(/_/g, ' ')} color={C.text1} mono={false} />}
          {node_risk_pct != null && <InfoRow label="Node risk" value={`${node_risk_pct}%`} color={node_risk_pct >= 62 ? C.danger : node_risk_pct >= 38 ? C.warn : C.accent} />}
          {confidence != null && <InfoRow label="Confidence" value={`${Math.round(confidence * 100)}%`} color={C.text2} />}
          {cluster && <InfoRow label="Cluster verdict" value={cluster.verdict} color={verdictColor(cluster.verdict)} mono={false} />}
        </div>
        {cluster?.primary_classification && (
          <InfoRow label="Classification" value={cluster.primary_classification} color={C.text2} mono={false} />
        )}
        {cluster?.narrative && (
          <div style={{
            marginTop: 8, padding: '10px 12px', borderRadius: 6,
            background: C.surface, border: `1px solid ${C.borderS}`,
            fontSize: 10, color: C.text2, lineHeight: 1.65,
          }}>
            {cluster.narrative}
          </div>
        )}
      </motion.section>

      {/* ── Why — explainable risk factors ─────────────────────── */}
      {risk_factors && risk_factors.length > 0 && (
        <motion.section variants={SECTION_VARIANTS}>
          <SectionHead label="Why — Risk Factors" icon={<Scale size={9} />} count={risk_factors.length} />
          {risk_factors.slice(0, 7).map(f => <FactorBar key={f.factor} label={f.factor} share={f.share} />)}
        </motion.section>
      )}

      {/* ── Centrality / influence ─────────────────────────────── */}
      {centrality && (
        <motion.section variants={SECTION_VARIANTS}>
          <SectionHead label="Centrality & Influence" icon={<Network size={9} />} />
          <InfoRow label="Degree" value={centrality.degree.toFixed(3)} color={C.text2} />
          <InfoRow label="Betweenness" value={centrality.betweenness.toFixed(3)} color={centrality.betweenness > 0.2 ? C.orange : C.text2} />
          <InfoRow label="Closeness" value={centrality.closeness.toFixed(3)} color={C.text2} />
          <InfoRow label="Bridge importance" value={centrality.bridge_importance.toFixed(3)} color={centrality.bridge_importance > 0.2 ? '#d946ef' : C.text2} />
        </motion.section>
      )}

      {/* ── Money trail (origin → destination) ─────────────────── */}
      {flow && (
        <motion.section variants={SECTION_VARIANTS}>
          <SectionHead label="Money Trail" icon={<GitBranch size={9} />} />
          <InfoRow label="Upstream reach" value={`${flow.upstream_count} accounts`} color={C.text2} />
          <InfoRow label="Downstream reach" value={`${flow.downstream_count} accounts`} color={C.text2} />
          {flow.upstream_sources.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 9, color: C.text3, marginBottom: 5 }}>Money origin (upstream sources)</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {flow.upstream_sources.slice(0, 10).map(a => <ConnectionChip key={a} id={a} isFraud />)}
              </div>
            </div>
          )}
          {flow.downstream_beneficiaries.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 9, color: C.text3, marginBottom: 5 }}>Money destination (beneficiaries)</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {flow.downstream_beneficiaries.slice(0, 10).map(a => <ConnectionChip key={a} id={a} isFraud />)}
              </div>
            </div>
          )}
        </motion.section>
      )}

      {/* ── Detected evidence ──────────────────────────────────── */}
      {evidence && evidence.length > 0 && (
        <motion.section variants={SECTION_VARIANTS}>
          <SectionHead label="Detection Evidence" icon={<AlertTriangle size={9} />} count={evidence.length} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            {evidence.slice(0, 5).map((e, i) => (
              <div key={`${e.pattern}-${i}`} style={{
                padding: '9px 11px', borderRadius: 6,
                background: 'rgba(239,68,68,0.04)', border: '1px solid rgba(239,68,68,0.14)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 3 }}>
                  <span style={{ fontSize: 10, fontWeight: 600, color: '#d08585' }}>{e.title}</span>
                  <span style={{ fontSize: 8.5, color: C.text3, fontFamily: 'monospace' }}>{Math.round(e.severity * 100)}%</span>
                </div>
                <div style={{ fontSize: 9.5, color: C.text3, lineHeight: 1.55 }}>{e.description}</div>
              </div>
            ))}
          </div>
        </motion.section>
      )}
    </>
  )
}

// ── Main export ───────────────────────────────────────────────────────────────
export function NodeInspector({
  node, classification, onClose,
  fraudNodeIds = new Set<string>(),
  nodeToGraphId = new Map<string, string>(),
  graphComponents = [],
  nodeIntel = null,
}: Props) {
  if (!node) return null

  if ((node as any).isCashNode) {
    return (
      <CashNodeInspector
        id={node.id}
        cashType={(node as any).cashType as CashNodeType}
        amount={(node as any).amount as number}
        parentAccount={(node as any).parentAccount as string}
        onClose={onClose}
      />
    )
  }

  // First-class cash EVENT node (rail-driven, in the main graph). A cash event is
  // NOT a bank account — show the cash-event panel, never the account/customer
  // profile. cash_kind comes from the backend; fall back to flow direction.
  if (node.is_cash_event || node.account_type === 'cash') {
    const kind: CashNodeType = node.cash_kind
      ?? ((node.total_sent ?? 0) >= (node.total_received ?? 0) ? 'CASH_IN' : 'CASH_OUT')
    const amount = kind === 'CASH_IN' ? (node.total_sent || node.total_received) : (node.total_received || node.total_sent)
    return (
      <CashNodeInspector
        id={node.id}
        cashType={kind}
        amount={amount}
        parentAccount={node.connected_accounts?.[0] ?? '—'}
        firstClass
        onClose={onClose}
      />
    )
  }

  const graphId        = nodeToGraphId.get(node.id) ?? null
  const graphComp      = graphId ? graphComponents.find(g => g.graph_id === graphId) ?? null : null
  const isGraphFraud   = graphComp?.flagged ?? false
  const isDirectFraud  = node.is_flagged
  const isClusterFraud = isGraphFraud || fraudNodeIds.has(node.id)
  const isFraud        = isDirectFraud || isClusterFraud

  // Propagated risk (graded by topology distance) is the source of truth when
  // available; falls back to the flat max for safety.
  const directRisk    = node.risk_score
  const inheritedRisk = nodeIntel?.clusterFlagged
    ? nodeIntel.propagatedRisk
    : (isClusterFraud ? (graphComp?.risk_score ?? 0) : 0)
  const effectiveRisk = nodeIntel ? nodeIntel.propagatedRisk : Math.max(directRisk, inheritedRisk)
  const exposure      = nodeIntel ? exposureLabel(nodeIntel.exposure) : (isClusterFraud ? 'Direct Exposure' : 'None')
  const suspicion     = nodeIntel?.suspicion ?? (effectiveRisk >= 0.6 ? 'HIGH' : effectiveRisk >= 0.35 ? 'MODERATE' : 'LOW')
  const isInherited   = (nodeIntel?.clusterFlagged ?? isClusterFraud) && (nodeIntel?.exposure ?? 'direct') !== 'origin'

  const accent = riskColor(effectiveRisk, isFraud)
  const glow   = riskGlow(effectiveRisk, isFraud)
  const status = riskLabel(effectiveRisk, isFraud)

  const role          = computeRole(node)
  const aiText        = generateAI(node, isFraud, graphComp, effectiveRisk, exposure, isInherited)
  const netFlow       = (node.total_received ?? 0) - (node.total_sent ?? 0)
  const fraudTags     = [...(node.detected_patterns?.filter(p => p !== 'normal') ?? [])]
  if (graphComp?.suspicious_reason && !fraudTags.includes(graphComp.suspicious_reason))
    fraudTags.push(graphComp.suspicious_reason)

  const lastActive = (() => {
    try { return new Date(node.last_activity).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' }) }
    catch { return '—' }
  })()

  const aiConfidence = Math.round(82 + effectiveRisk * 14)

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={node.id}
        initial={{ x: 20, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: 20, opacity: 0 }}
        transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
        style={PANEL_STYLE}
      >

        {/* ── HEADER ─────────────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
          style={{
            padding: '13px 16px 11px',
            borderBottom: `1px solid ${C.borderS}`,
            flexShrink: 0,
            background: isFraud ? 'rgba(239,68,68,0.04)' : 'transparent',
          }}
        >
          {/* Status line */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 9 }}>
            <motion.div
              style={{
                width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                background: accent,
                boxShadow: `0 0 ${isFraud ? 10 : 6}px ${accent}`,
              }}
              animate={isFraud
                ? { opacity: [1, 0.2, 1], scale: [1, 0.75, 1] }
                : { opacity: [0.85, 0.4, 0.85] }}
              transition={{ repeat: Infinity, duration: isFraud ? 1.1 : 2.8 }}
            />
            <span style={{ fontSize: 9, fontWeight: 700, color: accent, letterSpacing: '.12em', flex: 1 }}>
              {status}
            </span>
            {isFraud && (
              <motion.span
                initial={{ opacity: 0, x: 4 }}
                animate={{ opacity: 1, x: 0 }}
                style={{
                  fontSize: 8, fontWeight: 700, letterSpacing: '.08em',
                  color: C.danger, padding: '2px 6px', borderRadius: 3,
                  background: 'rgba(239,68,68,0.10)',
                  border: '1px solid rgba(239,68,68,0.22)',
                }}
              >
                ALERT
              </motion.span>
            )}
          </div>

          {/* ID + close */}
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontSize: 13, fontWeight: 700, color: C.text1, lineHeight: 1.3,
                fontFamily: 'ui-monospace, SF Mono, Menlo, monospace',
                letterSpacing: '.01em', wordBreak: 'break-all',
              }}>
                {node.id}
              </div>
              <div style={{ fontSize: 10, color: C.text3, marginTop: 3 }}>
                {node.account_type === 'cash'
                  ? ((node.total_sent ?? 0) >= (node.total_received ?? 0)
                      ? 'Cash Deposit · cash entered network'
                      : 'Cash Withdrawal · cash exited network')
                  : `${node.account_type} · ${classification} network`}
              </div>
            </div>
            <CloseBtn onClose={onClose} />
          </div>
        </motion.div>

        {/* ── RISK OVERVIEW (pinned) ──────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.08, duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
          style={{
            padding: '12px 16px',
            borderBottom: `1px solid ${C.borderS}`,
            flexShrink: 0,
            background: `linear-gradient(180deg, ${glow} 0%, transparent 100%)`,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <RiskArc score={effectiveRisk} color={accent} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 9, color: C.text3, letterSpacing: '.10em', marginBottom: 7 }}>
                RISK INDEX
              </div>
              {/* Risk level badge */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 8 }}>
                <span style={{
                  fontSize: 10, fontWeight: 600, letterSpacing: '.06em',
                  color: accent, padding: '2px 8px', borderRadius: 3,
                  background: `${accent}12`, border: `1px solid ${accent}28`,
                }}>
                  {status}
                </span>
              </div>
              {/* Thin progress bar */}
              <div style={{ height: 2, background: 'rgba(255,255,255,0.05)', borderRadius: 1, overflow: 'hidden', marginBottom: 6 }}>
                <motion.div
                  style={{ height: '100%', borderRadius: 1, background: accent }}
                  initial={{ width: 0 }}
                  animate={{ width: `${effectiveRisk * 100}%` }}
                  transition={{ duration: 1.2, delay: 0.2, ease: 'easeOut' }}
                />
              </div>
              <div style={{ fontSize: 9, color: C.text3 }}>
                AI confidence{' '}
                <span style={{ color: C.text2, fontFamily: 'monospace', fontWeight: 500 }}>
                  {aiConfidence}%
                </span>
              </div>
            </div>
          </div>

          {/* Cluster-inherited warning */}
          {isClusterFraud && !isDirectFraud && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              transition={{ delay: 0.3, duration: 0.3 }}
              style={{
                marginTop: 10, padding: '7px 10px', borderRadius: 5,
                background: 'rgba(227,104,62,0.07)',
                border: '1px solid rgba(227,104,62,0.20)',
                display: 'flex', gap: 7, alignItems: 'flex-start',
              }}
            >
              <AlertTriangle size={10} color={C.orange} style={{ flexShrink: 0, marginTop: 1 }} />
              <span style={{ fontSize: 9, color: '#b07050', lineHeight: 1.55 }}>
                Cluster member —{' '}
                <span style={{ color: C.orange, fontFamily: 'monospace' }}>{graphId}</span>{' '}
                inherited context applied.
              </span>
            </motion.div>
          )}
        </motion.div>

        {/* ── SCROLLABLE BODY ─────────────────────────────────────────── */}
        <motion.div
          variants={BODY_VARIANTS}
          initial="initial"
          animate="animate"
          style={{
            flex: 1, overflowY: 'auto',
            padding: '14px 16px',
            display: 'flex', flexDirection: 'column', gap: 18,
            scrollbarWidth: 'none',
          }}
        >

          {/* ── Account Intelligence ─────────────────────────────── */}
          <motion.section variants={SECTION_VARIANTS}>
            <SectionHead label="Account Intelligence" icon={<Network size={9} />} />
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 10px' }}>
              {[
                { label: 'Type',   value: node.account_type === 'cash'
                    ? ((node.total_sent ?? 0) >= (node.total_received ?? 0) ? 'Cash Deposit' : 'Cash Withdrawal')
                    : node.account_type,                                   color: C.text2, mono: false },
                { label: 'Role',   value: role.label,                      color: role.color, mono: false },
                { label: 'Txns',   value: String(node.transaction_count),  color: C.text2 },
                { label: 'Active', value: lastActive,                       color: C.text3 },
              ].map(({ label, value, color, mono }) => (
                <div key={label} style={{
                  padding: '8px 10px', borderRadius: 5,
                  background: C.surface, border: `1px solid ${C.borderS}`,
                }}>
                  <div style={{ fontSize: 9, color: C.text3, marginBottom: 3, textTransform: 'uppercase', letterSpacing: '.06em' }}>
                    {label}
                  </div>
                  <div style={{
                    fontSize: 11, fontWeight: 500, color,
                    fontFamily: mono === false ? 'inherit' : 'ui-monospace, monospace',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {value}
                  </div>
                </div>
              ))}
            </div>
            {/* Graph context rows */}
            {(graphId || nodeIntel) && (
              <div style={{ marginTop: 8 }}>
                {nodeIntel && (
                  <InfoRow
                    label="Topology role"
                    value={roleLabel(nodeIntel.role)}
                    color={nodeIntel.isBridge ? '#d946ef'
                         : nodeIntel.role === 'origin' ? C.danger
                         : nodeIntel.role === 'hub' ? C.orange
                         : nodeIntel.role === 'sink' ? C.accent : C.text2}
                  />
                )}
                {graphId && <InfoRow label="Graph cluster"    value={graphId}  color={C.accent} />}
                {graphId && (
                  <InfoRow
                    label="Cluster verdict"
                    value={isGraphFraud ? 'Fraudulent' : graphComp?.verdict === 'SUSPICIOUS' ? 'Suspicious' : graphComp?.verdict ?? 'Unanalyzed'}
                    color={isGraphFraud ? C.danger : graphComp?.verdict === 'SUSPICIOUS' ? C.warn : C.success}
                  />
                )}
                {graphComp && (
                  <InfoRow
                    label="Cluster risk"
                    value={riskPct(graphComp, 1)}
                    color={isGraphFraud ? C.orange : C.accent}
                  />
                )}
                {graphComp?.risk_confidence != null && (
                  <InfoRow
                    label="Risk confidence"
                    value={pctValue(graphComp.risk_confidence)}
                    color={C.text2}
                  />
                )}
                {graphComp?.risk_level && (
                  <InfoRow label="Risk level" value={graphComp.risk_level} color={isGraphFraud ? C.danger : C.text2} />
                )}
                <InfoRow
                  label="Fraud exposure"
                  value={exposure}
                  color={nodeIntel?.exposure === 'origin' || nodeIntel?.exposure === 'direct' ? C.danger
                       : nodeIntel?.exposure === 'secondary' ? C.warn
                       : nodeIntel?.exposure === 'peripheral' ? C.accent : C.text3}
                />
                <InfoRow
                  label="Suspicious degree"
                  value={suspicion}
                  color={suspicion === 'CRITICAL' || suspicion === 'HIGH' ? C.danger
                       : suspicion === 'MODERATE' ? C.warn : C.text2}
                />
                {isInherited && (
                  <InfoRow
                    label="Inherited risk"
                    value={`${Math.round(effectiveRisk * 100)}% (local ${Math.round(directRisk * 100)}%)`}
                    color={C.danger}
                  />
                )}
                {graphComp?.profile_intelligence?.accounts?.[node.id] && (
                  <CustomerProfileCard intel={graphComp.profile_intelligence.accounts[node.id]} />
                )}
                {graphComp?.cross_bank?.accounts?.[node.id] && (
                  <CrossBankCard
                    intel={graphComp.cross_bank.accounts[node.id]}
                    banks={graphComp.cross_bank.banks_involved}
                  />
                )}
                {(() => {
                  // Declared enterprise-format intelligence — shown ONLY when the
                  // backend provides it (Phase 15: surface, don't redesign).
                  const ai = graphComp?.account_intelligence?.[node.id]
                  if (!ai) return null
                  const rows: [string, string, string?][] = []
                  if (ai.kyc_risk)         rows.push(['KYC risk', ai.kyc_risk, ai.kyc_risk === 'high' ? C.danger : ai.kyc_risk === 'medium' ? C.warn : C.success])
                  if (ai.account_category) rows.push(['Account', ai.account_category])
                  if (ai.products?.length) rows.push(['Products', ai.products.join(', ')])
                  if (ai.channels?.length) rows.push(['Channel', ai.channels.join(', ')])
                  if (ai.geo)              rows.push(['Location', ai.geo, ai.geo_anomaly ? C.danger : undefined])
                  if (ai.device_reputation) rows.push(['Device', ai.device_reputation, ai.device_reputation === 'known_bad' ? C.danger : ai.proxy_or_vpn ? C.warn : undefined])
                  if (ai.merchant?.merchant_id) rows.push(['Merchant', String(ai.merchant.merchant_id)])
                  if (rows.length === 0) return null
                  return (
                    <div style={{ marginTop: 8 }}>
                      <div style={{ fontSize: 9, letterSpacing: '.06em', color: C.text3, textTransform: 'uppercase', marginBottom: 2 }}>
                        Declared Intelligence
                      </div>
                      {rows.map(([l, v, col]) => <InfoRow key={l} label={l} value={v} color={col} mono={false} />)}
                    </div>
                  )
                })()}
              </div>
            )}
          </motion.section>

          {/* ── Backend investigation intelligence (server-computed) ─ */}
          <BackendIntelligence accountId={node.id} />

          {/* ── Transaction Flow ──────────────────────────────────── */}
          <motion.section variants={SECTION_VARIANTS}>
            <SectionHead label="Transaction Flow" icon={<Activity size={9} />} />
            {/* IN / OUT cards */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 8 }}>
              <motion.div
                whileHover={{ scale: 1.02 }}
                style={{
                  padding: '11px', borderRadius: 7,
                  background: 'rgba(34,197,94,0.05)',
                  border: '1px solid rgba(34,197,94,0.14)',
                  cursor: 'default',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 6 }}>
                  <ArrowDownLeft size={9} color={C.success} />
                  <span style={{ fontSize: 8, color: C.text3, textTransform: 'uppercase', letterSpacing: '.07em' }}>Received</span>
                </div>
                <div style={{ fontSize: 15, fontWeight: 800, color: C.success, fontFamily: 'ui-monospace, monospace', lineHeight: 1 }}>
                  {fmt(node.total_received)}
                </div>
                <div style={{ fontSize: 9, color: C.text3, marginTop: 4 }}>
                  {node.incoming_count} inbound
                </div>
              </motion.div>
              <motion.div
                whileHover={{ scale: 1.02 }}
                style={{
                  padding: '11px', borderRadius: 7,
                  background: 'rgba(227,104,62,0.05)',
                  border: '1px solid rgba(227,104,62,0.14)',
                  cursor: 'default',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 6 }}>
                  <ArrowUpRight size={9} color={C.orange} />
                  <span style={{ fontSize: 8, color: C.text3, textTransform: 'uppercase', letterSpacing: '.07em' }}>Sent</span>
                </div>
                <div style={{ fontSize: 15, fontWeight: 800, color: C.orange, fontFamily: 'ui-monospace, monospace', lineHeight: 1 }}>
                  {fmt(node.total_sent)}
                </div>
                <div style={{ fontSize: 9, color: C.text3, marginTop: 4 }}>
                  {node.outgoing_count} outbound
                </div>
              </motion.div>
            </div>
            {/* Volume + Net */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 12px' }}>
              <InfoRow
                label="Total volume"
                value={fmt((node.total_received ?? 0) + (node.total_sent ?? 0))}
                color={C.text2}
              />
              <InfoRow
                label="Net flow"
                value={(netFlow >= 0 ? '+' : '') + fmt(Math.abs(netFlow))}
                color={netFlow >= 0 ? C.success : C.orange}
              />
            </div>
          </motion.section>

          {/* ── Cash Exposure ─────────────────────────────────────── */}
          {((node.cash_inflow_count ?? 0) > 0 || (node.cash_outflow_count ?? 0) > 0) && (
            <motion.section variants={SECTION_VARIANTS}>
              <SectionHead label="Cash Exposure" icon={<Banknote size={9} />} />
              <div style={{
                padding: '12px', borderRadius: 7,
                background: 'rgba(212,161,30,0.05)', border: '1px solid rgba(212,161,30,0.16)',
              }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 8 }}>
                  <div>
                    <div style={{ fontSize: 9, color: C.text3, marginBottom: 4 }}>Inflows</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: C.gold, fontFamily: 'monospace' }}>
                      {fmt(node.cash_inflows ?? 0)}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 9, color: C.text3, marginBottom: 4 }}>Outflows</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: C.gold, fontFamily: 'monospace' }}>
                      {fmt(node.cash_outflows ?? 0)}
                    </div>
                  </div>
                </div>
                <div style={{ height: 1, background: 'rgba(212,161,30,0.10)', margin: '0 0 8px' }} />
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 10, color: C.text3 }}>Total exposure</span>
                  <span style={{ fontSize: 12, fontWeight: 700, color: C.gold, fontFamily: 'monospace' }}>
                    {fmt((node.cash_inflows ?? 0) + (node.cash_outflows ?? 0))}
                  </span>
                </div>
              </div>
            </motion.section>
          )}

          {/* ── AI Analysis ───────────────────────────────────────── */}
          <motion.section variants={SECTION_VARIANTS}>
            <SectionHead label="AI Analysis" icon={<Brain size={9} />} />
            <div style={{
              padding: '12px', borderRadius: 7,
              background: C.surface, border: `1px solid ${C.borderS}`,
              position: 'relative', overflow: 'hidden',
            }}>
              {/* Ambient scan line */}
              <motion.div
                style={{
                  position: 'absolute', left: 0, right: 0, top: 0, height: 1,
                  background: `linear-gradient(90deg, transparent, ${C.accent}30, transparent)`,
                }}
                animate={{ y: [0, 56] }}
                transition={{ duration: 1.8, delay: 0.5, ease: 'easeInOut' }}
              />
              <div style={{ display: 'flex', gap: 8 }}>
                <div style={{
                  width: 22, height: 22, borderRadius: 5, flexShrink: 0,
                  background: `rgba(61,142,245,0.10)`, border: `1px solid rgba(61,142,245,0.18)`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <Brain size={11} color={C.accent} />
                </div>
                <div>
                  <div style={{ fontSize: 9, color: C.text3, marginBottom: 5, letterSpacing: '.06em', textTransform: 'uppercase' }}>
                    Pattern Analysis
                  </div>
                  <div style={{ fontSize: 10, color: C.text2, lineHeight: 1.65 }}>
                    <Typewriter text={aiText} startDelay={600} speed={14} />
                  </div>
                </div>
              </div>
              <div style={{
                marginTop: 10, paddingTop: 8, borderTop: `1px solid ${C.borderS}`,
                display: 'flex', alignItems: 'center', gap: 6,
              }}>
                {isFraud ? (
                  <AlertTriangle size={9} color={C.danger} />
                ) : (
                  <ShieldCheck size={9} color={C.success} />
                )}
                <span style={{ fontSize: 9, color: isFraud ? C.danger : C.success }}>
                  {isFraud ? 'HIGH-RISK VERDICT' : 'LOW-RISK VERDICT'}
                </span>
                <span style={{ fontSize: 9, color: C.text3, marginLeft: 'auto' }}>
                  Conf. <span style={{ color: C.text2, fontFamily: 'monospace' }}>{aiConfidence}%</span>
                </span>
              </div>
            </div>
          </motion.section>

          {/* ── Fraud Intelligence ────────────────────────────────── */}
          {isFraud && (
            <motion.section variants={SECTION_VARIANTS}>
              <SectionHead label="Fraud Intelligence" icon={<AlertTriangle size={9} />} />
              {graphComp?.suspicious_reason && (
                <div style={{
                  padding: '10px 12px', borderRadius: 6, marginBottom: 8,
                  background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.16)',
                }}>
                  <div style={{ fontSize: 9, color: C.text3, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.06em' }}>
                    Flagged reason
                  </div>
                  <div style={{ fontSize: 10, color: '#c07070', lineHeight: 1.6, fontFamily: 'ui-monospace, monospace' }}>
                    {graphComp.suspicious_reason.replace(/_/g, ' ')}
                  </div>
                </div>
              )}
              {fraudTags.length > 0 && (
                <>
                  <div style={{ fontSize: 9, color: C.text3, marginBottom: 5 }}>Fraud tags</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 8 }}>
                    {fraudTags.map(tag => (
                      <span key={tag} style={{
                        fontSize: 9, padding: '3px 7px', borderRadius: 3,
                        background: 'rgba(239,68,68,0.07)', border: '1px solid rgba(239,68,68,0.20)',
                        color: '#c07070', fontFamily: 'ui-monospace, monospace', letterSpacing: '.03em',
                      }}>
                        {tag.replace(/_/g, ' ')}
                      </span>
                    ))}
                  </div>
                </>
              )}
              {graphComp && (
                <InfoRow
                  label="Flagged in cluster"
                  value={`${graphComp.flagged_nodes.length} / ${graphComp.nodes.length} nodes`}
                  color={C.danger}
                />
              )}
              {isDirectFraud && (
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 5,
                  marginTop: 6, padding: '6px 10px', borderRadius: 5,
                  background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.14)',
                }}>
                  <AlertTriangle size={9} color={C.danger} />
                  <span style={{ fontSize: 9, color: '#a06060' }}>Node directly flagged by detection engine</span>
                </div>
              )}
            </motion.section>
          )}

          {/* ── Connections ───────────────────────────────────────── */}
          {(node.connected_accounts?.length ?? 0) > 0 && (
            <motion.section variants={SECTION_VARIANTS}>
              <SectionHead label="Connections" icon={<Zap size={9} />} count={node.connected_accounts.length} />
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {node.connected_accounts.slice(0, 14).map(acc => (
                  <ConnectionChip key={acc} id={acc} isFraud={fraudNodeIds.has(acc)} />
                ))}
                {node.connected_accounts.length > 14 && (
                  <span style={{
                    fontSize: 9, padding: '3px 7px', borderRadius: 4,
                    color: C.text3, background: C.surface, border: `1px solid ${C.borderS}`,
                  }}>
                    +{node.connected_accounts.length - 14}
                  </span>
                )}
              </div>
            </motion.section>
          )}

          {/* ── Geo Locations ─────────────────────────────────────── */}
          {(node.geo_locations?.length ?? 0) > 0 && (
            <motion.section variants={SECTION_VARIANTS}>
              <SectionHead label="Geographic Markers" icon={<MapPin size={9} />} />
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {node.geo_locations.map(g => (
                  <span key={g} style={{
                    fontSize: 10, padding: '3px 9px', borderRadius: 4,
                    background: 'rgba(61,142,245,0.05)', border: '1px solid rgba(61,142,245,0.14)',
                    color: '#6699cc', fontFamily: 'ui-monospace, monospace',
                  }}>
                    {g}
                  </span>
                ))}
              </div>
            </motion.section>
          )}

          {/* Bottom spacer */}
          <div style={{ height: 4 }} />
        </motion.div>

        {/* ── FOOTER ─────────────────────────────────────────────────── */}
        <PanelFooter
          tag={isGraphFraud ? 'CLUSTER ALERT' : status}
          accentColor={accent}
        />
      </motion.div>
    </AnimatePresence>
  )
}
