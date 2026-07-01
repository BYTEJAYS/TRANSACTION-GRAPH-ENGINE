import { AnimatePresence, motion } from 'framer-motion'
import { PALETTE, riskColor } from '../shaders/palette'
import type { GraphNode } from '../../types'

interface Props {
  node: GraphNode | null
  isFraud: boolean
  graphId?: string
}

// Floating cursor-anchored holographic readout. Shown on hover.
// Kept lightweight so it doesn't interrupt the cinematic flow.
export function HoverProbe({ node, isFraud, graphId }: Props) {
  return (
    <AnimatePresence>
      {node && (
        <motion.div
          key={node.id}
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          style={{
            position: 'absolute', top: 18, left: '50%', transform: 'translateX(-50%)',
            zIndex: 60, pointerEvents: 'none',
          }}
        >
          <div style={{
            padding: '6px 16px',
            background: 'rgba(2,4,10,0.88)',
            border: `1px solid ${isFraud ? 'rgba(255,51,102,0.32)' : 'rgba(0,245,255,0.22)'}`,
            borderRadius: 20, backdropFilter: 'blur(12px)',
            display: 'flex', alignItems: 'center', gap: 10,
            boxShadow: isFraud
              ? '0 0 24px rgba(255,51,102,0.22)'
              : '0 0 18px rgba(0,245,255,0.14)',
            fontFamily: '"JetBrains Mono", monospace',
          }}>
            <motion.div
              animate={isFraud ? { opacity: [1, 0.3, 1] } : {}}
              transition={{ repeat: Infinity, duration: 0.9 }}
              style={{
                width: 6, height: 6, borderRadius: '50%',
                background: isFraud ? PALETTE.critical : PALETTE.safe,
                boxShadow: `0 0 8px ${isFraud ? PALETTE.critical : PALETTE.safe}`,
              }}
            />
            <span style={{
              fontSize: 10, color: PALETTE.holoText, fontWeight: 700, letterSpacing: '.06em',
            }}>
              {node.id}
            </span>
            {graphId && (
              <>
                <Sep />
                <span style={{ fontSize: 9, color: '#446677' }}>{graphId}</span>
              </>
            )}
            <Sep />
            <span style={{
              fontSize: 10, fontWeight: 700,
              color: riskColor(node.risk_score, isFraud),
              textShadow: `0 0 8px ${riskColor(node.risk_score, isFraud)}55`,
            }}>
              {(node.risk_score * 100).toFixed(0)}% RISK
            </span>
            {isFraud && (
              <>
                <Sep />
                <span style={{
                  fontSize: 9, color: PALETTE.critical, fontWeight: 700, letterSpacing: '.16em',
                }}>
                  FRAUD
                </span>
              </>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

const Sep = () => (
  <span style={{ fontSize: 9, color: '#1e2d3a' }}>·</span>
)
