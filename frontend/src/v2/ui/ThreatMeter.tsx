import { motion } from 'framer-motion'
import { HoloPanel } from './HoloPanel'
import { PALETTE } from '../shaders/palette'

interface Props {
  fraudRate: number       // 0..1
  flaggedNodes: number
  isFraudDetected: boolean
}

function levelInfo(rate: number, fraud: boolean) {
  if (fraud || rate > 0.6)  return { label: 'CRITICAL', color: PALETTE.critical, bar: 95 }
  if (rate > 0.35)          return { label: 'ELEVATED', color: PALETTE.high,     bar: 70 }
  if (rate > 0.15)          return { label: 'GUARDED',  color: PALETTE.moderate, bar: 45 }
  return                          { label: 'NOMINAL',  color: PALETTE.safe,     bar: 20 }
}

// Cyberpunk threat-level dial. Top-center anchor.
export function ThreatMeter({ fraudRate, flaggedNodes, isFraudDetected }: Props) {
  const { label, color, bar } = levelInfo(fraudRate, isFraudDetected)
  const glow = `${color}22`

  return (
    <HoloPanel
      glowColor={isFraudDetected ? 'rgba(255,51,102,0.32)' : glow}
      borderColor={isFraudDetected ? 'rgba(255,51,102,0.34)' : `${color}55`}
      intense={isFraudDetected}
      style={{ padding: '12px 18px', minWidth: 280 }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <motion.div
          animate={isFraudDetected ? { scale: [1, 1.18, 1], opacity: [1, 0.6, 1] } : {}}
          transition={{ repeat: Infinity, duration: 1.1 }}
          style={{
            width: 10, height: 10, borderRadius: '50%',
            background: color,
            boxShadow: `0 0 14px ${color}, 0 0 32px ${color}`,
          }}
        />
        <div style={{ flex: 1 }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
            fontSize: 10, letterSpacing: '.22em', color: '#88aabb',
          }}>
            <span>THREAT LEVEL</span>
            <span style={{ color, fontWeight: 700, fontSize: 13, textShadow: `0 0 10px ${color}` }}>
              {label}
            </span>
          </div>
          <div style={{
            marginTop: 7, height: 4, borderRadius: 2,
            background: 'rgba(255,255,255,0.06)', overflow: 'hidden',
          }}>
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${bar}%` }}
              transition={{ duration: 0.7, ease: 'easeOut' }}
              style={{
                height: '100%',
                background: `linear-gradient(90deg, ${color}, ${color}cc)`,
                boxShadow: `0 0 12px ${color}`,
              }}
            />
          </div>
          <div style={{
            marginTop: 6, fontSize: 9, color: '#566677', letterSpacing: '.10em',
            display: 'flex', justifyContent: 'space-between',
          }}>
            <span>FLAGGED · {flaggedNodes}</span>
            <span>RATE · {(fraudRate * 100).toFixed(1)}%</span>
          </div>
        </div>
      </div>
    </HoloPanel>
  )
}
