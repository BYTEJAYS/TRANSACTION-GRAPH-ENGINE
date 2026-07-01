import { useState } from 'react'
import { motion } from 'framer-motion'
import { HoloPanel } from './HoloPanel'
import { PALETTE } from '../shaders/palette'
import type { SimulationState } from '../../types/transaction'

interface Props {
  simulationState: SimulationState
  currentStep: number
  totalSteps: number
  onRun: (json: string) => void
  onClear: () => void
  isClearing?: boolean
}

const PRESETS: { label: string; json: string }[] = [
  {
    label: 'CIRCULAR · 4-HOP',
    json: JSON.stringify([
      { from_account: 'FRAUD_A', to_account: 'FRAUD_B', amount: 50000, payment_rail: 'UPI',  timestamp: '2024-01-15T10:00:00' },
      { from_account: 'FRAUD_B', to_account: 'FRAUD_C', amount: 47500, payment_rail: 'UPI',  timestamp: '2024-01-15T10:05:00' },
      { from_account: 'FRAUD_C', to_account: 'FRAUD_D', amount: 45000, payment_rail: 'IMPS', timestamp: '2024-01-15T10:10:00' },
      { from_account: 'FRAUD_D', to_account: 'FRAUD_A', amount: 42500, payment_rail: 'UPI',  timestamp: '2024-01-15T10:15:00' },
    ], null, 2),
  },
  {
    label: 'MULE FAN-OUT',
    json: JSON.stringify([
      { from_account: 'MULE_HUB', to_account: 'MULE_1', amount: 25000, payment_rail: 'UPI',  timestamp: '2024-01-15T02:00:00' },
      { from_account: 'MULE_HUB', to_account: 'MULE_2', amount: 24000, payment_rail: 'UPI',  timestamp: '2024-01-15T02:01:00' },
      { from_account: 'MULE_HUB', to_account: 'MULE_3', amount: 23000, payment_rail: 'UPI',  timestamp: '2024-01-15T02:02:00' },
      { from_account: 'MULE_HUB', to_account: 'MULE_4', amount: 22000, payment_rail: 'IMPS', timestamp: '2024-01-15T02:03:00' },
      { from_account: 'MULE_HUB', to_account: 'MULE_5', amount: 21000, payment_rail: 'UPI',  timestamp: '2024-01-15T02:04:00' },
    ], null, 2),
  },
]

// Left-side command rail — paste-JSON ingest + preset scenarios + clear.
export function CommandRail({ simulationState, currentStep, totalSteps, onRun, onClear, isClearing = false }: Props) {
  const [text, setText] = useState('')
  const running = simulationState === 'running'

  return (
    <HoloPanel
      glowColor="rgba(0,245,255,0.16)"
      borderColor="rgba(0,245,255,0.22)"
      style={{ width: 340, padding: '14px 16px' }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <motion.div
          animate={running ? { opacity: [1, 0.3, 1] } : {}}
          transition={{ repeat: Infinity, duration: 1.0 }}
          style={{
            width: 8, height: 8, borderRadius: '50%',
            background: running ? PALETTE.moderate : PALETTE.safe,
            boxShadow: `0 0 10px ${running ? PALETTE.moderate : PALETTE.safe}`,
          }}
        />
        <div style={{
          fontSize: 10, letterSpacing: '.22em', color: PALETTE.holoText, fontWeight: 700,
        }}>COMMAND INGEST</div>
      </div>

      <div style={{ marginTop: 10, display: 'flex', gap: 6 }}>
        {PRESETS.map(p => (
          <button
            key={p.label}
            onClick={() => setText(p.json)}
            style={{
              flex: 1, padding: '5px 8px', fontSize: 9, letterSpacing: '.12em',
              background: 'rgba(0,245,255,0.06)',
              color: PALETTE.safe,
              border: '1px solid rgba(0,245,255,0.22)',
              borderRadius: 5, cursor: 'pointer',
              fontFamily: 'monospace',
            }}
          >{p.label}</button>
        ))}
      </div>

      <textarea
        value={text}
        onChange={e => setText(e.target.value)}
        placeholder='[{"from_account":"A","to_account":"B","amount":1000,"payment_rail":"UPI"}]'
        style={{
          marginTop: 8, width: '100%', height: 140, resize: 'vertical',
          padding: 10, fontSize: 10, lineHeight: 1.4,
          background: 'rgba(0,0,0,0.45)', color: PALETTE.holoText,
          border: '1px solid rgba(0,245,255,0.14)', borderRadius: 6,
          fontFamily: 'monospace', outline: 'none',
        }}
      />

      <div style={{ marginTop: 10, display: 'flex', gap: 6 }}>
        <button
          onClick={() => onRun(text)}
          disabled={running || !text.trim()}
          style={{
            flex: 1, padding: '7px 10px', fontSize: 10, letterSpacing: '.20em', fontWeight: 700,
            background: running ? 'rgba(245,158,11,0.10)' : 'rgba(0,245,255,0.12)',
            color:      running ? PALETTE.moderate          : PALETTE.safe,
            border:     `1px solid ${running ? 'rgba(245,158,11,0.32)' : 'rgba(0,245,255,0.32)'}`,
            borderRadius: 5,
            cursor: running || !text.trim() ? 'not-allowed' : 'pointer',
            fontFamily: 'monospace',
          }}
        >
          {running ? `RUNNING ${currentStep}/${totalSteps}` : 'EXECUTE'}
        </button>
        <motion.button
          onClick={() => { if (!isClearing && !running) onClear() }}
          disabled={isClearing || running}
          animate={isClearing ? { opacity: [1, 0.4, 1] } : {}}
          transition={{ repeat: Infinity, duration: 0.9 }}
          style={{
            padding: '7px 14px', fontSize: 10, letterSpacing: '.18em',
            background: isClearing ? 'rgba(255,51,102,0.03)' : 'rgba(255,51,102,0.06)',
            color: isClearing ? 'rgba(255,51,102,0.4)' : PALETTE.critical,
            border: `1px solid ${isClearing ? 'rgba(255,51,102,0.10)' : 'rgba(255,51,102,0.22)'}`,
            borderRadius: 5,
            cursor: isClearing || running ? 'not-allowed' : 'pointer',
            fontFamily: 'monospace',
            transition: 'color 0.2s, background 0.2s, border-color 0.2s',
          }}
        >{isClearing ? '···' : 'CLEAR'}</motion.button>
      </div>

      {running && (
        <div style={{
          marginTop: 8, height: 2, borderRadius: 1,
          background: 'rgba(255,255,255,0.05)', overflow: 'hidden',
        }}>
          <motion.div
            animate={{ width: `${totalSteps ? (currentStep / totalSteps) * 100 : 0}%` }}
            transition={{ duration: 0.3 }}
            style={{
              height: '100%',
              background: PALETTE.moderate,
              boxShadow: `0 0 8px ${PALETTE.moderate}`,
            }}
          />
        </div>
      )}
    </HoloPanel>
  )
}
