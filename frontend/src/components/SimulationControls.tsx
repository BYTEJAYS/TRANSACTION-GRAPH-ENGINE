import { useState } from 'react'
import { motion } from 'framer-motion'
import { Play, Zap, Repeat, GitBranch, Layers, Users, AlertTriangle } from 'lucide-react'

interface Props {
  onBurst: () => void
  onInjectFraud: (pattern: string) => void
}

const FRAUD_PATTERNS = [
  { id: 'circular_transfer', label: 'Circular', icon: Repeat, color: '#ff3366' },
  { id: 'fan_out', label: 'Fan-Out', icon: GitBranch, color: '#ff7733' },
  { id: 'layering', label: 'Layering', icon: Layers, color: '#9d00ff' },
  { id: 'mule_chain', label: 'Mule Chain', icon: Users, color: '#ff3366' },
  { id: 'rapid_microtransaction', label: 'Rapid Micro', icon: Zap, color: '#ffd700' },
  { id: 'structuring', label: 'Structuring', icon: AlertTriangle, color: '#ff7733' },
]

export function SimulationControls({ onBurst, onInjectFraud }: Props) {
  const [activePattern, setActivePattern] = useState<string | null>(null)

  const handleInject = async (pattern: string) => {
    setActivePattern(pattern)
    onInjectFraud(pattern)
    setTimeout(() => setActivePattern(null), 2000)
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="text-[10px] uppercase tracking-widest text-cyber-text-dim">Simulation Controls</div>

      {/* Burst button */}
      <motion.button
        whileTap={{ scale: 0.95 }}
        onClick={onBurst}
        className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border border-cyber-gold/40 bg-cyber-gold/10 text-cyber-gold text-[11px] font-bold hover:bg-cyber-gold/20 transition-colors"
        style={{ textShadow: '0 0 8px #ffd700' }}
      >
        <Zap size={13} />
        TRIGGER BURST
      </motion.button>

      {/* Fraud pattern injection */}
      <div className="grid grid-cols-3 gap-1.5">
        {FRAUD_PATTERNS.map(({ id, label, icon: Icon, color }) => (
          <motion.button
            key={id}
            whileTap={{ scale: 0.92 }}
            onClick={() => handleInject(id)}
            className="flex flex-col items-center gap-1 py-2.5 px-1 rounded-lg border transition-colors text-center"
            style={{
              borderColor: activePattern === id ? color : `${color}30`,
              background: activePattern === id ? `${color}20` : `${color}08`,
              color,
            }}
          >
            <Icon size={12} />
            <span className="text-[8px] font-bold leading-tight">{label}</span>
          </motion.button>
        ))}
      </div>

      <p className="text-[9px] text-cyber-text-dim text-center">
        Click patterns to inject fraud scenarios
      </p>
    </div>
  )
}
