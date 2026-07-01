import { motion, AnimatePresence } from 'framer-motion'
import { ArrowRight, Zap } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import type { Transaction, RiskLevel } from '../types/transaction'

interface Props {
  transactions: Transaction[]
}

const RISK_COLORS: Record<RiskLevel, string> = {
  safe: '#00ff88',
  moderate: '#ffd700',
  high: '#ff7733',
  critical: '#ff3366',
}

const RAIL_COLORS = {
  UPI: '#00f5ff',
  IMPS: '#7fffaa',
  NEFT: '#a78bfa',
  RTGS: '#ff7733',
}

function getRiskLevel(score: number): RiskLevel {
  if (score < 0.3) return 'safe'
  if (score < 0.6) return 'moderate'
  if (score < 0.8) return 'high'
  return 'critical'
}

function formatAmount(v: number): string {
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)}L`
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(1)}K`
  return `₹${v.toFixed(0)}`
}

function TxnRow({ txn }: { txn: Transaction }) {
  const level = getRiskLevel(txn.risk_score)
  const riskColor = RISK_COLORS[level]
  const railColor = RAIL_COLORS[txn.payment_rail] || '#c8d8f0'

  const timeAgo = (() => {
    try {
      return formatDistanceToNow(new Date(txn.timestamp), { addSuffix: false })
    } catch {
      return 'now'
    }
  })()

  return (
    <motion.div
      layout
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      className="border-b border-cyber-border/30 py-2 px-1 hover:bg-cyber-panel/50 transition-colors"
      style={{ borderLeftColor: riskColor }}
    >
      <div className="flex items-center gap-1.5 text-[9px]">
        {/* Risk indicator */}
        <div
          className="w-1.5 h-1.5 rounded-full shrink-0"
          style={{ background: riskColor, boxShadow: `0 0 4px ${riskColor}` }}
        />

        {/* Accounts */}
        <span className="text-cyber-cyan font-mono truncate max-w-[70px]" title={txn.from_account}>
          {txn.from_account.slice(0, 10)}
        </span>
        <ArrowRight size={8} className="text-cyber-text-dim shrink-0" />
        <span className="text-cyber-text font-mono truncate max-w-[70px]" title={txn.to_account}>
          {txn.to_account.slice(0, 10)}
        </span>

        {/* Amount */}
        <span className="font-bold ml-auto shrink-0" style={{ color: riskColor }}>
          {formatAmount(txn.amount)}
        </span>

        {/* Rail */}
        <span
          className="px-1 py-0.5 rounded text-[8px] shrink-0"
          style={{ background: `${railColor}15`, color: railColor }}
        >
          {txn.payment_rail}
        </span>
      </div>

      {/* Metadata row */}
      <div className="flex items-center gap-2 mt-0.5 pl-3 text-[8px] text-cyber-text-dim">
        <span className="truncate">{txn.transaction_id.slice(0, 14)}</span>
        <span className="ml-auto shrink-0">{timeAgo}</span>
        {txn.fraud_pattern !== 'normal' && (
          <span className="text-cyber-red shrink-0">⚠ {txn.fraud_pattern.replace('_', ' ')}</span>
        )}
      </div>
    </motion.div>
  )
}

export function TransactionFeed({ transactions }: Props) {
  const recent = [...transactions].reverse().slice(0, 60)

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-2 shrink-0">
        <div className="flex items-center gap-2">
          <Zap size={12} className="text-cyber-gold" style={{ filter: 'drop-shadow(0 0 4px #ffd700)' }} />
          <span className="text-[10px] uppercase tracking-widest text-cyber-text-dim">Live Transaction Feed</span>
        </div>
        <motion.div
          animate={{ opacity: [1, 0.3, 1] }}
          transition={{ repeat: Infinity, duration: 1 }}
          className="text-[9px] text-cyber-green"
        >
          ● LIVE
        </motion.div>
      </div>

      {/* Column headers */}
      <div className="grid text-[8px] text-cyber-text-dim px-1 pb-1 border-b border-cyber-border shrink-0"
        style={{ gridTemplateColumns: '1fr auto' }}>
        <span>FROM → TO</span>
        <span>AMOUNT</span>
      </div>

      {/* Feed */}
      <div className="flex-1 overflow-y-auto">
        <AnimatePresence mode="popLayout">
          {recent.length === 0 ? (
            <div className="flex items-center justify-center h-16 text-[11px] text-cyber-text-dim">
              Awaiting transactions…
            </div>
          ) : (
            recent.map(txn => (
              <TxnRow key={txn.transaction_id} txn={txn} />
            ))
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
