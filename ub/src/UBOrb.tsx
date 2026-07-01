import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Mic, MicOff } from 'lucide-react'
import { OrbCharacter } from './OrbCharacter'
import type { VoiceState } from '../../hooks/useVoiceAssistant'

// Tokens reused from app palette (Bloomberg-dark fintech).
const C = {
  glass:    'rgba(13,17,23,0.62)',
  glassH:   'rgba(22,27,34,0.78)',
  border:   'rgba(255,255,255,0.08)',
  borderS:  'rgba(255,255,255,0.05)',
  text1:    '#e6edf3',
  text2:    '#8b949e',
  text3:    '#484f58',
  accent:   '#4493f8',
  cyan:     '#79c0ff',
  warn:     '#d29922',
  danger:   '#f85149',
  success:  '#3fb950',
} as const

interface Props {
  voiceState:   VoiceState
  wakeEnabled:  boolean
  armedForCmd:  boolean
  supported:    boolean
  transcript:   string
  onToggleWake: () => void   // long-press / right-click toggles continuous wake
  onActivate:   () => void   // single click → push-to-talk arm
  onStop:       () => void
}

function stateLabel(s: VoiceState, armed: boolean, wake: boolean): { label: string; color: string } {
  if (s === 'fraud')      return { label: 'Alert',      color: C.danger }
  if (s === 'speaking')   return { label: 'Speaking',   color: C.cyan }
  if (s === 'processing') return { label: 'Thinking',   color: C.accent }
  if (s === 'listening' || armed) return { label: 'Listening', color: C.cyan }
  if (wake)               return { label: 'Standby',    color: C.text2 }
  return { label: 'Idle',     color: C.text3 }
}

export function UBOrb({
  voiceState, wakeEnabled, armedForCmd, supported, transcript,
  onToggleWake, onActivate, onStop,
}: Props) {
  const [hovered, setHovered] = useState(false)
  const { label, color } = stateLabel(voiceState, armedForCmd, wakeEnabled)
  const isActive = voiceState === 'listening' || voiceState === 'speaking' || voiceState === 'processing' || armedForCmd
  const isAlert  = voiceState === 'fraud'

  // Expanded chip when active or hovered.
  const expand = hovered || isActive || isAlert

  return (
    <motion.div
      initial={{ opacity: 0, y: -10, scale: 0.92 }}
      animate={{ opacity: 1, y: 0,   scale: 1 }}
      exit={{    opacity: 0, y: -8,  scale: 0.94 }}
      transition={{ type: 'spring', stiffness: 320, damping: 30 }}
      style={{
        position: 'fixed',
        top: 54, right: 54,
        zIndex: 70,
        userSelect: 'none',
        pointerEvents: 'auto',
        transformOrigin: 'top right',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <motion.div
        layout
        animate={{
          width:    expand ? 240 : 52,
          background: isAlert ? 'rgba(34,12,12,0.78)' : (expand ? C.glassH : C.glass),
          borderColor: isAlert ? 'rgba(248,81,73,0.32)' : (expand ? 'rgba(121,192,255,0.22)' : C.border),
          boxShadow: isAlert
            ? '0 4px 28px rgba(248,81,73,0.18), 0 0 0 1px rgba(248,81,73,0.18) inset'
            : expand
              ? '0 6px 28px rgba(0,0,0,0.55), 0 0 0 1px rgba(121,192,255,0.10) inset'
              : '0 4px 20px rgba(0,0,0,0.45)',
        }}
        transition={{ type: 'spring', stiffness: 320, damping: 32 }}
        style={{
          // row-reverse keeps the orb pinned to the top-right corner while the
          // label + controls expand leftward — Siri-style, no corner drift.
          display: 'flex', flexDirection: 'row-reverse', alignItems: 'center', gap: 10,
          padding: '5px 5px 5px 12px',
          borderRadius: 999,
          border: '1px solid',
          backdropFilter: 'blur(22px) saturate(140%)',
          WebkitBackdropFilter: 'blur(22px) saturate(140%)',
          overflow: 'hidden',
          cursor: 'pointer',
        }}
        onClick={(e) => {
          // Single click — push-to-talk arm.
          if ((e.target as HTMLElement).dataset.role === 'mic') return
          if (voiceState === 'speaking') { onStop(); return }
          onActivate()
        }}
      >
        {/* Orb */}
        <div style={{ width: 42, height: 42, flexShrink: 0, position: 'relative' }}>
          <OrbCharacter
            voiceState={voiceState === 'processing' ? 'speaking' : voiceState}
            size={42}
            interactive={false}
            radiusFactor={0.42}
          />
          {/* Rotating ring during listening */}
          {(voiceState === 'listening' || armedForCmd) && (
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ repeat: Infinity, duration: 3.2, ease: 'linear' }}
              style={{
                position: 'absolute', inset: -3,
                borderRadius: '50%',
                border: '1px dashed rgba(121,192,255,0.45)',
                pointerEvents: 'none',
              }}
            />
          )}
        </div>

        {/* Expanded label */}
        <AnimatePresence initial={false}>
          {expand && (
            <motion.div
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -4 }}
              transition={{ duration: 0.18 }}
              style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{
                  fontSize: 10, fontWeight: 700, letterSpacing: '.14em',
                  color: C.text1,
                }}>
                  UB
                </span>
                <motion.span
                  style={{ width: 4, height: 4, borderRadius: '50%', background: color, flexShrink: 0 }}
                  animate={isActive || isAlert ? { opacity: [1, 0.25, 1] } : { opacity: 0.7 }}
                  transition={{ repeat: Infinity, duration: isAlert ? 0.85 : 1.4 }}
                />
                <span style={{
                  fontSize: 9, letterSpacing: '.10em', color,
                  textTransform: 'uppercase',
                }}>
                  {label}
                </span>
              </div>
              <div style={{
                fontSize: 10, color: C.text3,
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                fontFamily: transcript ? 'ui-monospace, SF Mono, Menlo, monospace' : 'inherit',
              }}>
                {transcript
                  ? `“${transcript}”`
                  : armedForCmd
                    ? 'Yes?'
                    : voiceState === 'speaking'
                      ? 'Responding…'
                      : voiceState === 'processing'
                        ? 'Thinking…'
                        : wakeEnabled
                          ? 'Say “UB” to activate'
                          : 'Click to speak'}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Mic toggle (only when expanded) */}
        <AnimatePresence initial={false}>
          {expand && supported && (
            <motion.button
              data-role="mic"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.16 }}
              onClick={(e) => { e.stopPropagation(); onToggleWake() }}
              title={wakeEnabled ? 'Disable wake word' : 'Enable wake word'}
              style={{
                width: 26, height: 26, flexShrink: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                borderRadius: '50%', cursor: 'pointer',
                background: wakeEnabled ? 'rgba(68,147,248,0.14)' : 'transparent',
                border: `1px solid ${wakeEnabled ? 'rgba(68,147,248,0.30)' : C.border}`,
                color: wakeEnabled ? C.accent : C.text3,
              }}
            >
              {wakeEnabled ? <Mic size={11} /> : <MicOff size={11} />}
            </motion.button>
          )}
        </AnimatePresence>
      </motion.div>
    </motion.div>
  )
}
