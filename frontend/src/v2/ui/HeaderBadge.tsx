import { motion } from 'framer-motion'
import { PALETTE } from '../shaders/palette'

interface Props {
  connected: boolean
}

// Top-left product badge — the "Stark Industries header" of the dashboard.
export function HeaderBadge({ connected }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.6 }}
      style={{
        display: 'flex', alignItems: 'center', gap: 14, userSelect: 'none',
      }}
    >
      <div style={{
        position: 'relative',
        width: 44, height: 44, borderRadius: 10,
        background: 'linear-gradient(135deg, rgba(0,245,255,0.18), rgba(168,85,247,0.10))',
        border: '1px solid rgba(0,245,255,0.32)',
        boxShadow: '0 0 24px rgba(0,245,255,0.22), inset 0 0 14px rgba(0,245,255,0.10)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, duration: 18, ease: 'linear' }}
          style={{
            position: 'absolute', inset: 3, borderRadius: 8,
            border: '1px dashed rgba(0,245,255,0.35)',
          }}
        />
        <svg width="20" height="20" viewBox="0 0 16 16" fill="none">
          <circle cx="8" cy="8" r="2.5" fill={PALETTE.safe} opacity="1"/>
          <circle cx="2" cy="4" r="1.4" fill={PALETTE.safe} opacity="0.7"/>
          <circle cx="14" cy="4" r="1.4" fill={PALETTE.critical} opacity="0.85"/>
          <circle cx="2" cy="12" r="1.4" fill={PALETTE.moderate} opacity="0.8"/>
          <circle cx="14" cy="12" r="1.4" fill={PALETTE.high} opacity="0.85"/>
          <line x1="8" y1="8" x2="2" y2="4" stroke={PALETTE.safe} strokeWidth="0.8" opacity="0.55"/>
          <line x1="8" y1="8" x2="14" y2="4" stroke={PALETTE.critical} strokeWidth="0.8" opacity="0.55"/>
          <line x1="8" y1="8" x2="2" y2="12" stroke={PALETTE.moderate} strokeWidth="0.8" opacity="0.4"/>
          <line x1="8" y1="8" x2="14" y2="12" stroke={PALETTE.high} strokeWidth="0.8" opacity="0.55"/>
        </svg>
      </div>
      <div>
        <div style={{
          fontSize: 15, fontWeight: 900, letterSpacing: '.32em', color: PALETTE.safe,
          fontFamily: '"Orbitron", monospace',
          textShadow: `0 0 18px ${PALETTE.safe}88`,
        }}>
          TGIE / V2
        </div>
        <div style={{
          fontSize: 8, color: '#5a7a8a', letterSpacing: '.20em', textTransform: 'uppercase',
          marginTop: 2,
        }}>
          Transaction Graph Intelligence · Cinematic
        </div>
      </div>

      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        marginLeft: 6, paddingLeft: 12, borderLeft: '1px solid rgba(255,255,255,0.06)',
      }}>
        <motion.div
          animate={{ opacity: connected ? [1, 0.35, 1] : 1 }}
          transition={{ repeat: Infinity, duration: 1.4 }}
          style={{
            width: 6, height: 6, borderRadius: '50%',
            background: connected ? '#00ff88' : PALETTE.critical,
            boxShadow: `0 0 8px ${connected ? '#00ff88' : PALETTE.critical}`,
          }}
        />
        <span style={{ fontSize: 9, color: '#88aabb', letterSpacing: '.18em' }}>
          {connected ? 'WS · LIVE' : 'WS · DOWN'}
        </span>
      </div>
    </motion.div>
  )
}
