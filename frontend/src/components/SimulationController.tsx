import { motion, AnimatePresence } from 'framer-motion'
import { ShieldAlert, ShieldCheck, Zap, AlertCircle, GitBranch, Repeat, TrendingUp } from 'lucide-react'
import type { ClassificationStatus, SimulationState } from '../types/transaction'

interface Props {
  simulationState: SimulationState
  classification: ClassificationStatus
  rulesTriggered: string[]
  currentStep: number
  totalSteps: number
  nodeCount: number
  linkCount: number
}

const RULE_META: Record<string, { label: string; icon: typeof Zap; color: string }> = {
  chain_depth_exceeded:       { label: 'Chain Depth > 3',        icon: TrendingUp,    color: '#ff7733' },
  repeated_amount_forwarding: { label: 'Repeated Amount ×3+',    icon: Repeat,        color: '#ffd700' },
  circular_path_detected:     { label: 'Circular Path',          icon: Repeat,        color: '#ff3366' },
  fan_out_detected:           { label: 'Fan-Out ≥ 4 Targets',   icon: GitBranch,     color: '#9d00ff' },
}

export function SimulationController({
  simulationState,
  classification,
  rulesTriggered,
  currentStep,
  totalSteps,
  nodeCount,
  linkCount,
}: Props) {
  const isFraud = classification === 'fraud'
  const isActive = simulationState !== 'idle'

  return (
    <AnimatePresence>
      {isActive && (
        <motion.div
          key="sim-hud"
          initial={{ y: 60, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 60, opacity: 0 }}
          transition={{ type: 'spring', stiffness: 220, damping: 26 }}
          className="absolute bottom-6 left-1/2 z-40 -translate-x-1/2 flex flex-col items-center gap-2.5"
        >
          {/* Classification badge */}
          <motion.div
            className="flex items-center gap-3 px-5 py-2.5 rounded-full"
            animate={isFraud ? { boxShadow: ['0 0 12px #ff336640', '0 0 28px #ff336680', '0 0 12px #ff336640'] } : {}}
            transition={{ repeat: Infinity, duration: 1.4 }}
            style={{
              background: isFraud
                ? 'rgba(255,51,102,0.12)'
                : 'rgba(0,255,136,0.10)',
              border: `1px solid ${isFraud ? 'rgba(255,51,102,0.5)' : 'rgba(0,255,136,0.4)'}`,
              backdropFilter: 'blur(10px)',
            }}
          >
            {isFraud ? (
              <motion.div
                animate={{ opacity: [1, 0.4, 1] }}
                transition={{ repeat: Infinity, duration: 0.8 }}
              >
                <ShieldAlert size={16} style={{ color: '#ff3366', filter: 'drop-shadow(0 0 6px #ff3366)' }} />
              </motion.div>
            ) : (
              <ShieldCheck size={16} style={{ color: '#00ff88', filter: 'drop-shadow(0 0 6px #00ff88)' }} />
            )}
            <span
              className="text-[13px] font-bold uppercase tracking-widest font-mono"
              style={{
                color: isFraud ? '#ff3366' : '#00ff88',
                textShadow: `0 0 10px ${isFraud ? '#ff336680' : '#00ff8880'}`,
              }}
            >
              {isFraud ? 'FRAUD DETECTED' : 'NETWORK NORMAL'}
            </span>

            {/* Step counter */}
            {simulationState === 'running' && totalSteps > 0 && (
              <>
                <div className="w-px h-4 bg-current opacity-20" />
                <span className="text-[11px] font-mono opacity-70">
                  {currentStep}/{totalSteps}
                </span>
              </>
            )}

            {simulationState === 'completed' && (
              <>
                <div className="w-px h-4 bg-current opacity-20" />
                <span className="text-[10px] uppercase tracking-wider opacity-60">
                  Complete
                </span>
              </>
            )}
          </motion.div>

          {/* Triggered rules */}
          {rulesTriggered.length > 0 && (
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="flex items-center gap-2 flex-wrap justify-center"
            >
              {rulesTriggered.map(rule => {
                const meta = RULE_META[rule]
                if (!meta) return null
                const Icon = meta.icon
                return (
                  <div
                    key={rule}
                    className="flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider"
                    style={{
                      background: `${meta.color}15`,
                      border: `1px solid ${meta.color}40`,
                      color: meta.color,
                    }}
                  >
                    <Icon size={9} />
                    {meta.label}
                  </div>
                )
              })}
            </motion.div>
          )}

          {/* Graph stats mini bar */}
          <div
            className="flex items-center gap-4 px-4 py-1.5 rounded-full text-[10px] font-mono text-cyber-text-dim"
            style={{
              background: 'rgba(8,12,20,0.7)',
              border: '1px solid rgba(26,37,64,0.6)',
              backdropFilter: 'blur(8px)',
            }}
          >
            <span>
              <span className="text-cyber-cyan">{nodeCount}</span> nodes
            </span>
            <span className="opacity-30">|</span>
            <span>
              <span className="text-cyber-cyan">{linkCount}</span> edges
            </span>
            {simulationState === 'running' && (
              <>
                <span className="opacity-30">|</span>
                <motion.div
                  className="flex items-center gap-1"
                  animate={{ opacity: [1, 0.4, 1] }}
                  transition={{ repeat: Infinity, duration: 1.2 }}
                >
                  <AlertCircle size={9} style={{ color: '#00f5ff' }} />
                  <span className="text-cyber-cyan">Processing</span>
                </motion.div>
              </>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
