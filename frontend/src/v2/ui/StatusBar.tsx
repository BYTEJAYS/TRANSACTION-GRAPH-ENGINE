import { motion } from 'framer-motion'
import { HoloPanel } from './HoloPanel'
import { StatTile } from './StatTile'
import { PALETTE } from '../shaders/palette'
import type { GraphStats } from '../../types'

interface Props {
  stats: GraphStats
  connected: boolean
  fraudIntensity: number
}

function fmt(n: number): string {
  if (n >= 1e9) return `₹${(n / 1e9).toFixed(2)}B`
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)}Cr`
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)}L`
  if (n >= 1e3) return `₹${(n / 1e3).toFixed(1)}K`
  return `₹${n.toFixed(0)}`
}

// Bottom-left status bar — system-wide KPIs in instrument style.
export function StatusBar({ stats, connected, fraudIntensity }: Props) {
  return (
    <HoloPanel
      glowColor={fraudIntensity > 0.4 ? 'rgba(255,51,102,0.18)' : 'rgba(0,245,255,0.12)'}
      borderColor={fraudIntensity > 0.4 ? 'rgba(255,51,102,0.28)' : 'rgba(0,245,255,0.20)'}
      intense={fraudIntensity > 0.6}
      style={{ display: 'flex', alignItems: 'stretch', padding: '6px 4px 6px 16px' }}
    >
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '4px 14px 4px 0',
        borderRight: '1px solid rgba(255,255,255,0.06)',
      }}>
        <motion.div
          animate={{ opacity: connected ? [1, 0.4, 1] : 1, scale: connected ? [1, 1.18, 1] : 1 }}
          transition={{ repeat: Infinity, duration: 1.4 }}
          style={{
            width: 8, height: 8, borderRadius: '50%',
            background: connected ? '#00ff88' : PALETTE.critical,
            boxShadow: `0 0 12px ${connected ? '#00ff88' : PALETTE.critical}`,
          }}
        />
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ fontSize: 8, color: '#5a7a8a', letterSpacing: '.22em' }}>WS LINK</div>
          <div style={{
            fontSize: 10, color: connected ? '#00ff88' : PALETTE.critical,
            fontWeight: 700, letterSpacing: '.14em',
          }}>
            {connected ? 'ONLINE' : 'OFFLINE'}
          </div>
        </div>
      </div>

      <StatTile label="Nodes"     value={stats.nodeCount.toLocaleString()} />
      <StatTile label="Edges"     value={stats.linkCount.toLocaleString()} />
      <StatTile label="Flagged"   value={stats.flaggedNodes.toString()}
                accent={stats.flaggedNodes > 0 ? PALETTE.critical : PALETTE.safe} />
      <StatTile label="Volume"    value={fmt(stats.totalVolume)} />
      <StatTile label="Fraud Rate"
                value={`${(stats.fraudRate * 100).toFixed(1)}%`}
                accent={stats.fraudRate > 0.3 ? PALETTE.critical : stats.fraudRate > 0.1 ? PALETTE.moderate : PALETTE.safe}
                style={{ borderRight: 'none' }} />
    </HoloPanel>
  )
}
