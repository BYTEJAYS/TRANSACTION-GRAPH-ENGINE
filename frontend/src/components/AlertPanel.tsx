import { motion, AnimatePresence } from 'framer-motion'
import { AlertTriangle, Zap, GitBranch, Repeat, Layers, Users, TrendingDown } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import type { FraudAlert, FraudPattern, RiskLevel } from '../types/transaction'

interface Props {
  alerts: FraudAlert[]
  onAlertClick: (alert: FraudAlert) => void
}

const PATTERN_META: Record<FraudPattern, { icon: typeof AlertTriangle; label: string; color: string }> = {
  normal: { icon: TrendingDown, label: 'Normal', color: '#00ff88' },
  circular_transfer: { icon: Repeat, label: 'Circular', color: '#ff3366' },
  fan_out: { icon: GitBranch, label: 'Fan-Out', color: '#ff7733' },
  layering: { icon: Layers, label: 'Layering', color: '#9d00ff' },
  rapid_microtransaction: { icon: Zap, label: 'Rapid Micro', color: '#ffd700' },
  mule_chain: { icon: Users, label: 'Mule Chain', color: '#ff3366' },
  burst_transfer: { icon: Zap, label: 'Burst', color: '#ffd700' },
  structuring: { icon: TrendingDown, label: 'Structuring', color: '#ff7733' },
}

const SEVERITY_COLORS: Record<RiskLevel, string> = {
  safe: '#00ff88',
  moderate: '#ffd700',
  high: '#ff7733',
  critical: '#ff3366',
}

function AlertCard({ alert, onClick }: { alert: FraudAlert; onClick: () => void }) {
  const meta = PATTERN_META[alert.alert_type] || PATTERN_META.normal
  const Icon = meta.icon
  const color = SEVERITY_COLORS[alert.severity] || meta.color

  const timeAgo = (() => {
    try {
      return formatDistanceToNow(new Date(alert.timestamp), { addSuffix: true })
    } catch {
      return 'just now'
    }
  })()

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: 20, scale: 0.95 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: -20, scale: 0.95 }}
      onClick={onClick}
      className="bg-cyber-bg border rounded-lg p-3 cursor-pointer hover:bg-cyber-panel transition-colors group"
      style={{
        borderColor: `${color}50`,
        boxShadow: `0 0 8px ${color}15`,
      }}
    >
      <div className="flex items-start gap-2.5">
        {/* Icon */}
        <div
          className="mt-0.5 p-1.5 rounded-lg shrink-0"
          style={{ background: `${color}15`, color }}
        >
          <Icon size={12} style={{ filter: `drop-shadow(0 0 3px ${color})` }} />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className="text-[10px] font-bold uppercase tracking-wider"
              style={{ color }}
            >
              {meta.label}
            </span>
            <span
              className="text-[9px] px-1.5 py-0.5 rounded-full uppercase font-bold"
              style={{ background: `${color}20`, color }}
            >
              {alert.severity}
            </span>
          </div>

          <p className="text-[10px] text-cyber-text leading-relaxed line-clamp-2 mb-1.5">
            {alert.description}
          </p>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-[9px] text-cyber-text-dim">
              <span>{alert.accounts_involved.length} accts</span>
              {alert.total_amount > 0 && (
                <>
                  <span className="text-cyber-border">•</span>
                  <span style={{ color }}>
                    ₹{alert.total_amount >= 1e5
                      ? `${(alert.total_amount / 1e5).toFixed(1)}L`
                      : alert.total_amount.toFixed(0)}
                  </span>
                </>
              )}
            </div>
            <span className="text-[9px] text-cyber-text-dim">{timeAgo}</span>
          </div>

          {/* Risk score bar */}
          <div className="mt-2 h-0.5 bg-cyber-border rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${alert.risk_score * 100}%`, background: color }}
            />
          </div>
        </div>
      </div>
    </motion.div>
  )
}

export function AlertPanel({ alerts, onAlertClick }: Props) {
  const recentAlerts = [...alerts].reverse().slice(0, 50)

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-3 shrink-0">
        <div className="flex items-center gap-2">
          <AlertTriangle size={14} className="text-cyber-red" style={{ filter: 'drop-shadow(0 0 4px #ff3366)' }} />
          <span className="text-[11px] uppercase tracking-widest text-cyber-text-dim">Fraud Intelligence</span>
        </div>
        <div className="flex items-center gap-2">
          {alerts.length > 0 && (
            <motion.div
              animate={{ opacity: [1, 0.3, 1] }}
              transition={{ repeat: Infinity, duration: 1.5 }}
              className="text-[10px] text-cyber-red font-bold"
            >
              {alerts.length} ALERT{alerts.length !== 1 ? 'S' : ''}
            </motion.div>
          )}
        </div>
      </div>

      {/* Alert feed */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        <AnimatePresence mode="popLayout">
          {recentAlerts.length === 0 ? (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex flex-col items-center justify-center py-12 text-cyber-text-dim"
            >
              <Shield className="w-8 h-8 mb-3 opacity-30" />
              <p className="text-[11px]">No alerts detected</p>
              <p className="text-[10px] mt-1 opacity-60">Monitoring for suspicious patterns…</p>
            </motion.div>
          ) : (
            recentAlerts.map(alert => (
              <AlertCard
                key={alert.alert_id}
                alert={alert}
                onClick={() => onAlertClick(alert)}
              />
            ))
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

// Placeholder shield icon used in empty state
function Shield({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  )
}
