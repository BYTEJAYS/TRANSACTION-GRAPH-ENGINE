import { motion } from 'framer-motion'
import { CSSProperties, ReactNode } from 'react'

interface Props {
  label: string
  value: ReactNode
  accent?: string
  trail?: ReactNode
  style?: CSSProperties
}

// Minimal numeric tile — small holographic value with label + optional sparkline slot.
export function StatTile({ label, value, accent = '#00f5ff', trail, style }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        padding: '8px 12px',
        borderRight: '1px solid rgba(255,255,255,0.04)',
        minWidth: 110,
        ...style,
      }}
    >
      <div style={{
        fontSize: 8, letterSpacing: '.18em', color: '#5a7a8a',
        textTransform: 'uppercase',
      }}>{label}</div>
      <div style={{
        marginTop: 3,
        fontSize: 17, fontWeight: 700, color: accent,
        textShadow: `0 0 12px ${accent}55`,
        fontFamily: '"Orbitron", "JetBrains Mono", monospace',
        letterSpacing: '.02em',
      }}>
        {value}
      </div>
      {trail && (
        <div style={{ marginTop: 2, fontSize: 8, color: '#3a5060', letterSpacing: '.05em' }}>
          {trail}
        </div>
      )}
    </motion.div>
  )
}
