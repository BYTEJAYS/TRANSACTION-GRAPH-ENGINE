import { forwardRef, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { LiveTransaction } from '../types'

// ── Design tokens ──────────────────────────────────────────────────────────
const C = {
  bg:      '#0d1117',
  surface: '#161b22',
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

const RAIL_COLORS: Record<string, string> = {
  UPI:  C.accent,
  IMPS: C.success,
  NEFT: '#a371f7',
  RTGS: C.warn,
}

interface Props {
  transactions: LiveTransaction[]
  isFraudDetected?: boolean
  fraudNodeIds?: ReadonlySet<string>
}

function fmtAmt(v: number): string {
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)}L`
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(1)}K`
  return `₹${v.toFixed(0)}`
}

function fmtTime(ts: string): string {
  try {
    const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000)
    if (diff < 60)   return `${diff}s`
    if (diff < 3600) return `${Math.floor(diff / 60)}m`
    return `${Math.floor(diff / 3600)}h`
  } catch { return '' }
}

// forwardRef so framer-motion's popLayout can attach a ref to each child
// (AnimatePresence mode="popLayout" passes a ref through PopChild).
const TickerItem = forwardRef<HTMLDivElement, { txn: LiveTransaction; inFraudGraph?: boolean }>(
  function TickerItem({ txn, inFraudGraph }, ref) {
  const flagged  = txn.is_flagged || (inFraudGraph ?? false)
  const railColor = RAIL_COLORS[txn.payment_rail] ?? C.text3

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.18 }}
      style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '4px 10px', borderRadius: 4, flexShrink: 0,
        background: flagged ? 'rgba(248,81,73,0.06)' : 'rgba(255,255,255,0.02)',
        border: `1px solid ${flagged ? 'rgba(248,81,73,0.16)' : C.borderS}`,
        whiteSpace: 'nowrap',
      }}
    >
      {/* Flagged indicator */}
      {flagged && (
        <motion.div
          style={{ width: 3, height: 3, borderRadius: '50%', background: C.danger, flexShrink: 0 }}
          animate={{ opacity: [1, 0.2, 1] }}
          transition={{ repeat: Infinity, duration: 0.9 }}
        />
      )}

      {/* From → To */}
      <span style={{
        fontSize: 10, fontFamily: 'ui-monospace, SF Mono, Menlo, monospace',
        color: flagged ? '#c07070' : C.text3,
      }}>
        {txn.from_account.slice(-6)}
      </span>
      <span style={{ fontSize: 9, color: C.text3 }}>→</span>
      <span style={{
        fontSize: 10, fontFamily: 'ui-monospace, SF Mono, Menlo, monospace',
        color: flagged ? '#c07070' : C.text3,
      }}>
        {txn.to_account.slice(-6)}
      </span>

      <span style={{ width: 1, height: 10, background: C.borderS, flexShrink: 0 }} />

      {/* Amount */}
      <span style={{
        fontSize: 10, fontWeight: 600,
        fontFamily: 'ui-monospace, monospace',
        fontVariantNumeric: 'tabular-nums',
        color: flagged ? C.danger : C.text2,
      }}>
        {fmtAmt(txn.amount)}
      </span>

      {/* Rail */}
      <span style={{
        fontSize: 8, padding: '1px 5px', borderRadius: 3,
        background: `${railColor}10`,
        border: `1px solid ${railColor}22`,
        color: railColor,
        fontFamily: 'ui-monospace, monospace',
        letterSpacing: '.02em',
      }}>
        {txn.payment_rail}
      </span>

      {/* Time */}
      <span style={{ fontSize: 9, color: C.text3 }}>{fmtTime(txn.timestamp)}</span>
    </motion.div>
  )
})

export function TransactionTicker({ transactions, isFraudDetected, fraudNodeIds }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [paused, setPaused] = useState(false)

  if (transactions.length === 0) return null

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.5, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      style={{
        position: 'absolute',
        bottom: 0,
        left: 44,
        right: 44,
        height: 44,
        zIndex: 50,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        padding: '0 16px',
        background: 'rgba(13,17,23,0.88)',
        borderTop: `1px solid ${isFraudDetected ? 'rgba(248,81,73,0.14)' : 'rgba(255,255,255,0.06)'}`,
        backdropFilter: 'blur(20px)',
        transition: 'border-color 0.4s',
      }}
    >
      <div
        ref={scrollRef}
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          overflowX: 'auto', overflowY: 'hidden',
          scrollbarWidth: 'none',
        }}
      >
        {/* Label */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 5,
          flexShrink: 0, marginRight: 4,
        }}>
          <motion.div
            style={{
              width: 4, height: 4, borderRadius: '50%',
              background: isFraudDetected ? C.danger : C.success,
            }}
            animate={{ opacity: [1, 0.3, 1] }}
            transition={{ repeat: Infinity, duration: isFraudDetected ? 0.8 : 2 }}
          />
          <span style={{ fontSize: 9, color: C.text3, letterSpacing: '.04em', whiteSpace: 'nowrap' }}>
            Live
          </span>
          <span style={{
            fontSize: 9, padding: '0px 5px', borderRadius: 3,
            background: 'rgba(255,255,255,0.04)',
            border: `1px solid ${C.borderS}`,
            color: C.text3,
          }}>
            {transactions.length}
          </span>
          {isFraudDetected && (
            <span style={{
              fontSize: 9, fontWeight: 600, color: C.danger,
              padding: '0px 6px', borderRadius: 3,
              background: 'rgba(248,81,73,0.07)',
              border: '1px solid rgba(248,81,73,0.16)',
              whiteSpace: 'nowrap',
            }}>
              FRAUD
            </span>
          )}
        </div>

        <div style={{ width: 1, height: 14, background: C.borderS, flexShrink: 0 }} />

        <AnimatePresence mode="popLayout" initial={false}>
          {transactions.slice(0, 24).map((txn, i) => {
            const inFraudGraph = fraudNodeIds
              ? (fraudNodeIds.has(txn.from_account) || fraudNodeIds.has(txn.to_account))
              : false
            // ids can collide across live/mock feeds — suffix with index to keep keys unique
            return (
              <TickerItem key={`${txn.id}-${i}`} txn={txn} inFraudGraph={inFraudGraph} />
            )
          })}
        </AnimatePresence>
      </div>
    </motion.div>
  )
}
