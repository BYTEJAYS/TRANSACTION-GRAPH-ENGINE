// ── Recovery factor grid ─────────────────────────────────────────────────────
// The ten intelligence factors behind the score, each with its weighted bar.
// Higher score = better recovery prospects.
import { motion } from 'framer-motion'
import {
  Clock, Layers, Split, Banknote, Snowflake, ShieldHalf,
  Dna, Timer, UserX, Network,
} from 'lucide-react'
import { T } from '../../theme'
import { recoveryColor, type RecoveryFactor } from '../api'

const ICONS: Record<string, any> = {
  age: Clock, depth: Layers, dispersion: Split, withdrawal: Banknote, freeze: Snowflake,
  containment: ShieldHalf, dna: Dna, timeline: Timer, beneficiary: UserX, disruption: Network,
}

export function FactorGrid({ factors, weights }: { factors: RecoveryFactor[]; weights: Record<string, number> }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(232px, 1fr))', gap: 12 }}>
      {factors.map((f, i) => {
        const Icon = ICONS[f.key] || Clock
        const col = recoveryColor(f.score)
        const w = Math.round((weights[f.key] || 0) * 100)
        return (
          <motion.div key={f.key}
            initial={{ opacity: 0, y: 10 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.03 }}
            style={{ background: 'rgba(20,22,27,0.72)', border: `1px solid ${T.border}`, borderRadius: 12, padding: '13px 14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 9 }}>
              <div style={{ width: 28, height: 28, borderRadius: 8, display: 'grid', placeItems: 'center', background: `${col}1a`, border: `1px solid ${col}44` }}>
                <Icon size={14} color={col} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</div>
                <div style={{ fontSize: 9, color: T.text3 }}>weight {w}%</div>
              </div>
              <span style={{ fontSize: 18, fontWeight: 700, color: col, fontFamily: T.mono }}>{f.score}</span>
            </div>
            <div style={{ height: 5, background: T.bg2, borderRadius: 3, overflow: 'hidden', marginBottom: 8 }}>
              <motion.div initial={{ width: 0 }} whileInView={{ width: `${f.score}%` }} viewport={{ once: true }} transition={{ duration: 0.7 }} style={{ height: '100%', background: col, borderRadius: 3 }} />
            </div>
            <div style={{ fontSize: 11, color: T.text2, fontWeight: 500 }}>{f.label}</div>
            <div style={{ fontSize: 10.5, color: T.text3, marginTop: 2 }}>{f.detail}</div>
          </motion.div>
        )
      })}
    </div>
  )
}
