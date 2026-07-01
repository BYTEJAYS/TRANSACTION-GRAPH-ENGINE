import { useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Play, Trash2, ChevronDown, ChevronUp, Shield, AlertTriangle, Banknote } from 'lucide-react'
import type { SimulationState } from '../types/transaction'

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

// ── Sample scenarios ───────────────────────────────────────────────────────
const NORMAL_SCENARIO = JSON.stringify([
  { from_account: 'ACC_1001', to_account: 'ACC_2001', amount: 15000, payment_rail: 'UPI',  timestamp: '2026-05-15T10:00:00' },
  { from_account: 'ACC_2001', to_account: 'ACC_3001', amount: 8500,  payment_rail: 'IMPS', timestamp: '2026-05-15T10:15:00' },
  { from_account: 'ACC_1001', to_account: 'ACC_4001', amount: 25000, payment_rail: 'RTGS', timestamp: '2026-05-15T10:30:00' },
  { from_account: 'ACC_3001', to_account: 'ACC_5001', amount: 7200,  payment_rail: 'NEFT', timestamp: '2026-05-15T10:45:00' },
], null, 2)

const FRAUD_SCENARIO = JSON.stringify([
  { from_account: 'ACC_ALPHA',   to_account: 'ACC_BETA',    amount: 100000, payment_rail: 'UPI', timestamp: '2026-05-15T09:00:00' },
  { from_account: 'ACC_BETA',    to_account: 'ACC_GAMMA',   amount: 100000, payment_rail: 'UPI', timestamp: '2026-05-15T09:01:00' },
  { from_account: 'ACC_GAMMA',   to_account: 'ACC_DELTA',   amount: 100000, payment_rail: 'UPI', timestamp: '2026-05-15T09:02:00' },
  { from_account: 'ACC_DELTA',   to_account: 'ACC_EPSILON', amount: 100000, payment_rail: 'UPI', timestamp: '2026-05-15T09:03:00' },
  { from_account: 'ACC_EPSILON', to_account: 'ACC_ALPHA',   amount: 100000, payment_rail: 'UPI', timestamp: '2026-05-15T09:04:00' },
], null, 2)

const CASH_SCENARIO = JSON.stringify([
  { from_account: 'CASH_SOURCE', to_account: 'ACC_1001',   amount: 500000, payment_rail: 'CASH', timestamp: '2026-05-15T08:00:00' },
  { from_account: 'ACC_1001',    to_account: 'ACC_2001',   amount: 300000, payment_rail: 'UPI',  timestamp: '2026-05-15T08:30:00' },
  { from_account: 'ACC_2001',    to_account: 'ACC_3001',   amount: 200000, payment_rail: 'IMPS', timestamp: '2026-05-15T09:00:00' },
  { from_account: 'ACC_3001',    to_account: 'CASH_EXIT',  amount: 150000, payment_rail: 'CASH', timestamp: '2026-05-15T09:30:00' },
  { from_account: 'CASH_SOURCE', to_account: 'ACC_2001',   amount: 250000, payment_rail: 'CASH', timestamp: '2026-05-15T10:00:00' },
], null, 2)

// ── Legend items ───────────────────────────────────────────────────────────
const LEGEND = [
  { color: C.accent,  label: 'Safe' },
  { color: C.warn,    label: 'Medium risk' },
  { color: '#e3683e', label: 'High risk' },
  { color: C.danger,  label: 'Critical / Fraud' },
  { color: '#d4a11e', label: 'Cash inflow' },
  { color: '#a371f7', label: 'Cash outflow' },
]

const SCENARIOS = [
  { key: 'normal', label: 'Normal',   icon: Shield,        json: NORMAL_SCENARIO },
  { key: 'fraud',  label: 'Fraud',    icon: AlertTriangle, json: FRAUD_SCENARIO  },
  { key: 'cash',   label: 'Cash AML', icon: Banknote,      json: CASH_SCENARIO   },
]

interface Props {
  simulationState: SimulationState
  currentStep: number
  totalSteps: number
  onRunSimulation: (json: string) => Promise<void>
  onClearGraph: () => void
}

export function TransactionInputPanel({
  simulationState,
  currentStep,
  totalSteps,
  onRunSimulation,
  onClearGraph,
}: Props) {
  const [json, setJson]         = useState(NORMAL_SCENARIO)
  const [error, setError]       = useState<string | null>(null)
  const [collapsed, setCollapsed] = useState(false)
  const [activeScenario, setActiveScenario] = useState('normal')
  const isRunning = simulationState === 'running'

  const validate = useCallback((text: string): boolean => {
    try {
      const parsed = JSON.parse(text)
      if (!Array.isArray(parsed)) {
        setError('Expected a JSON array of transactions')
        return false
      }
      for (const t of parsed) {
        if (!t.from_account || !t.to_account || t.amount === undefined) {
          setError('Each transaction needs from_account, to_account, and amount')
          return false
        }
      }
      setError(null)
      return true
    } catch (e: any) {
      setError(e.message ?? 'Invalid JSON')
      return false
    }
  }, [])

  const handleRun = useCallback(async () => {
    if (!validate(json)) return
    await onRunSimulation(json)
  }, [json, validate, onRunSimulation])

  const handleClear = useCallback(() => {
    setError(null)
    onClearGraph()
  }, [onClearGraph])

  const progress = totalSteps > 0 ? (currentStep / totalSteps) * 100 : 0

  return (
    <motion.div
      initial={{ x: -16, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.3, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
      style={{
        position: 'absolute',
        top: 44,
        left: 0,
        bottom: 0,
        width: 256,
        zIndex: 40,
        display: 'flex',
        flexDirection: 'column',
        background: 'rgba(13,17,23,0.88)',
        borderRight: `1px solid ${C.border}`,
        backdropFilter: 'blur(20px)',
      }}
    >
      {/* ── Section header ──────────────────────────────────────────────── */}
      <button
        onClick={() => setCollapsed(c => !c)}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 16px',
          background: 'none', border: 'none', borderBottom: `1px solid ${C.borderS}`,
          cursor: 'pointer', width: '100%', textAlign: 'left',
        }}
      >
        <span style={{ fontSize: 11, fontWeight: 600, color: C.text2, letterSpacing: '.04em' }}>
          Simulation
        </span>
        {collapsed
          ? <ChevronDown size={12} color={C.text3} />
          : <ChevronUp   size={12} color={C.text3} />
        }
      </button>

      <AnimatePresence initial={false}>
        {!collapsed && (
          <motion.div
            key="sim-body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: 'hidden', flexShrink: 0 }}
          >
            <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>

              {/* Scenario selector */}
              <div style={{ display: 'flex', gap: 4 }}>
                {SCENARIOS.map(({ key, label, icon: Icon, json: j }) => (
                  <button
                    key={key}
                    onClick={() => { setJson(j); setError(null); setActiveScenario(key) }}
                    style={{
                      flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
                      gap: 3, padding: '6px 4px', borderRadius: 5, cursor: 'pointer',
                      background: activeScenario === key ? C.raised : 'transparent',
                      border: `1px solid ${activeScenario === key ? C.border : C.borderS}`,
                      transition: 'background 0.15s, border-color 0.15s',
                    }}
                  >
                    <Icon size={10} color={activeScenario === key ? C.text2 : C.text3} />
                    <span style={{
                      fontSize: 9, fontWeight: 500,
                      color: activeScenario === key ? C.text2 : C.text3,
                      letterSpacing: '.03em',
                    }}>
                      {label}
                    </span>
                  </button>
                ))}
              </div>

              {/* JSON editor */}
              <textarea
                value={json}
                onChange={e => { setJson(e.target.value); setError(null) }}
                spellCheck={false}
                style={{
                  width: '100%',
                  height: 200,
                  resize: 'none',
                  padding: '10px',
                  borderRadius: 5,
                  fontSize: 10,
                  lineHeight: 1.55,
                  fontFamily: 'ui-monospace, SF Mono, Menlo, Consolas, monospace',
                  background: C.bg,
                  border: `1px solid ${error ? 'rgba(248,81,73,0.35)' : C.border}`,
                  color: C.text2,
                  caretColor: C.accent,
                  outline: 'none',
                  transition: 'border-color 0.15s',
                }}
              />

              {error && (
                <p style={{ margin: 0, fontSize: 10, color: C.danger, lineHeight: 1.4 }}>
                  {error}
                </p>
              )}

              {/* Progress */}
              {isRunning && totalSteps > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 10, color: C.text3 }}>Processing</span>
                    <span style={{
                      fontSize: 10, color: C.text2,
                      fontFamily: 'ui-monospace, monospace',
                      fontVariantNumeric: 'tabular-nums',
                    }}>
                      {currentStep} / {totalSteps}
                    </span>
                  </div>
                  <div style={{ height: 1, background: C.border, borderRadius: 1, overflow: 'hidden' }}>
                    <motion.div
                      style={{ height: '100%', background: C.accent, borderRadius: 1 }}
                      initial={{ width: 0 }}
                      animate={{ width: `${progress}%` }}
                      transition={{ duration: 0.35, ease: 'easeOut' }}
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
                    gap: 6, padding: '7px 12px', borderRadius: 5,
                    fontSize: 11, fontWeight: 500,
                    background: isRunning ? C.raised : C.accent,
                    border: `1px solid ${isRunning ? C.border : 'transparent'}`,
                    color: isRunning ? C.text3 : '#fff',
                    cursor: isRunning ? 'not-allowed' : 'pointer',
                    transition: 'all 0.15s',
                  }}
                >
                  {isRunning ? (
                    <>
                      <motion.span
                        animate={{ rotate: 360 }}
                        transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
                        style={{
                          display: 'inline-block', width: 10, height: 10,
                          border: `1.5px solid ${C.text3}`,
                          borderTopColor: 'transparent', borderRadius: '50%',
                        }}
                      />
                      Running…
                    </>
                  ) : (
                    <>
                      <Play size={11} />
                      Run Simulation
                    </>
                  )}
                </button>

                <button
                  onClick={handleClear}
                  title="Clear graph"
                  style={{
                    width: 34, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    borderRadius: 5, cursor: 'pointer',
                    background: 'transparent',
                    border: `1px solid ${C.border}`,
                    color: C.text3,
                    transition: 'border-color 0.15s, color 0.15s',
                  }}
                  onMouseEnter={e => {
                    (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(248,81,73,0.35)'
                    ;(e.currentTarget as HTMLButtonElement).style.color = C.danger
                  }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLButtonElement).style.borderColor = C.border
                    ;(e.currentTarget as HTMLButtonElement).style.color = C.text3
                  }}
                >
                  <Trash2 size={12} />
                </button>
              </div>

              {/* Field hint */}
              <p style={{ margin: 0, fontSize: 9, color: C.text3, lineHeight: 1.5 }}>
                Required: <span style={{ color: C.text2, fontFamily: 'monospace' }}>from_account</span>,{' '}
                <span style={{ color: C.text2, fontFamily: 'monospace' }}>to_account</span>,{' '}
                <span style={{ color: C.text2, fontFamily: 'monospace' }}>amount</span>
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Spacer — pushes legend to bottom ───────────────────────────── */}
      <div style={{ flex: 1 }} />

      {/* ── Graph legend ────────────────────────────────────────────────── */}
      <div style={{
        padding: '12px 16px',
        borderTop: `1px solid ${C.borderS}`,
        display: 'flex', flexDirection: 'column', gap: 6,
      }}>
        <span style={{ fontSize: 9, color: C.text3, letterSpacing: '.06em', textTransform: 'uppercase' }}>
          Risk Scale
        </span>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 8px' }}>
          {LEGEND.map(({ color, label }) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: color, flexShrink: 0 }} />
              <span style={{ fontSize: 9, color: C.text3 }}>{label}</span>
            </div>
          ))}
        </div>

        {/* Payment rail legend */}
        <div style={{ height: 1, background: C.borderS, margin: '4px 0' }} />
        <span style={{ fontSize: 9, color: C.text3, letterSpacing: '.06em', textTransform: 'uppercase' }}>
          Payment Rails
        </span>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 8px' }}>
          {[
            { color: '#4493f8', label: 'UPI'  },
            { color: '#3fb950', label: 'IMPS' },
            { color: '#d29922', label: 'RTGS' },
            { color: '#a371f7', label: 'NEFT' },
          ].map(({ color, label }) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 14, height: 1.5, background: color, borderRadius: 1, flexShrink: 0 }} />
              <span style={{ fontSize: 9, color: C.text3 }}>{label}</span>
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  )
}
