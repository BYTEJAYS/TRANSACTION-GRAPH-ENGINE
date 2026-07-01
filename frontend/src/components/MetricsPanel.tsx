import { motion } from 'framer-motion'
import { Activity, AlertTriangle, Network, Zap, TrendingUp, Shield } from 'lucide-react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import type { DashboardStats } from '../types/transaction'

interface Props {
  stats: DashboardStats
  connected: boolean
}

const RISK_PIE_COLORS = ['#00ff88', '#ffd700', '#ff7733', '#ff3366']

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  color,
  glow,
}: {
  icon: typeof Activity
  label: string
  value: string | number
  sub?: string
  color: string
  glow?: string
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-cyber-panel border border-cyber-border rounded-xl p-4 flex flex-col gap-2 relative overflow-hidden"
      style={{ boxShadow: glow ? `0 0 20px ${glow}20` : undefined }}
    >
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest text-cyber-text-dim">{label}</span>
        <Icon size={14} style={{ color }} />
      </div>
      <div className="text-2xl font-display font-bold" style={{ color }}>
        {value}
      </div>
      {sub && <div className="text-[10px] text-cyber-text-dim">{sub}</div>}
      {/* Corner accent */}
      <div
        className="absolute top-0 right-0 w-12 h-12 opacity-10"
        style={{
          background: `radial-gradient(circle at top right, ${color}, transparent)`,
        }}
      />
    </motion.div>
  )
}

function formatAmount(v: number): string {
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(1)}Cr`
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)}L`
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(1)}K`
  return `₹${v.toFixed(0)}`
}

function formatCount(v: number): string {
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`
  return String(v)
}

export function MetricsPanel({ stats, connected }: Props) {
  const riskPieData = [
    { name: 'Safe', value: stats.riskDistribution.safe },
    { name: 'Moderate', value: stats.riskDistribution.moderate },
    { name: 'High', value: stats.riskDistribution.high },
    { name: 'Critical', value: stats.riskDistribution.critical },
  ].filter(d => d.value > 0)

  const flagRatio =
    stats.activeNodes > 0
      ? ((stats.flaggedNodes / stats.activeNodes) * 100).toFixed(1)
      : '0.0'

  return (
    <div className="flex flex-col gap-3 h-full overflow-y-auto pr-1">
      {/* Connection status */}
      <div className="flex items-center gap-2 px-1">
        <div
          className={`w-2 h-2 rounded-full ${connected ? 'bg-cyber-green animate-pulse' : 'bg-cyber-red'}`}
          style={{ boxShadow: connected ? '0 0 6px #00ff88' : '0 0 6px #ff3366' }}
        />
        <span className="text-[10px] text-cyber-text-dim">
          {connected ? 'LIVE — Real-time stream active' : 'DISCONNECTED — Reconnecting…'}
        </span>
      </div>

      {/* Primary metrics grid */}
      <div className="grid grid-cols-2 gap-2">
        <StatCard
          icon={Activity}
          label="Total Transactions"
          value={formatCount(stats.totalTransactions)}
          sub="all rails"
          color="#00f5ff"
          glow="#00f5ff"
        />
        <StatCard
          icon={TrendingUp}
          label="Total Volume"
          value={formatAmount(stats.totalVolume)}
          color="#7fffaa"
          glow="#7fffaa"
        />
        <StatCard
          icon={Network}
          label="Active Accounts"
          value={formatCount(stats.activeNodes)}
          sub={`${stats.flaggedNodes} flagged`}
          color="#a78bfa"
          glow="#a78bfa"
        />
        <StatCard
          icon={Zap}
          label="Throughput"
          value={`${stats.throughput}/s`}
          sub="transactions"
          color="#ffd700"
          glow="#ffd700"
        />
      </div>

      {/* Fraud alerts */}
      <motion.div
        animate={{ boxShadow: stats.fraudAlerts > 0 ? ['0 0 10px #ff336630', '0 0 20px #ff336660', '0 0 10px #ff336630'] : [] }}
        transition={{ repeat: Infinity, duration: 2 }}
        className="bg-cyber-panel border border-cyber-border rounded-xl p-4 flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <AlertTriangle size={20} className="text-cyber-red" style={{ filter: 'drop-shadow(0 0 6px #ff3366)' }} />
          <div>
            <div className="text-[10px] text-cyber-text-dim uppercase tracking-widest">Fraud Alerts</div>
            <div className="text-2xl font-display font-bold text-cyber-red">{stats.fraudAlerts}</div>
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] text-cyber-text-dim">Flagged Rate</div>
          <div className="text-lg font-mono text-cyber-red">{flagRatio}%</div>
        </div>
      </motion.div>

      {/* Risk distribution chart */}
      <div className="bg-cyber-panel border border-cyber-border rounded-xl p-4">
        <div className="text-[10px] uppercase tracking-widest text-cyber-text-dim mb-3 flex items-center gap-2">
          <Shield size={12} />
          Risk Distribution
        </div>
        {riskPieData.length > 0 ? (
          <div className="flex items-center gap-4">
            <ResponsiveContainer width={90} height={90}>
              <PieChart>
                <Pie
                  data={riskPieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={24}
                  outerRadius={42}
                  paddingAngle={2}
                  dataKey="value"
                  strokeWidth={0}
                >
                  {riskPieData.map((_, i) => (
                    <Cell key={i} fill={RISK_PIE_COLORS[i]} opacity={0.9} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: '#0d1420',
                    border: '1px solid #1a2540',
                    borderRadius: 8,
                    fontSize: 10,
                    color: '#c8d8f0',
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="flex flex-col gap-1.5 text-[10px]">
              {['Safe', 'Moderate', 'High', 'Critical'].map((label, i) => {
                const val = [
                  stats.riskDistribution.safe,
                  stats.riskDistribution.moderate,
                  stats.riskDistribution.high,
                  stats.riskDistribution.critical,
                ][i]
                const total = stats.activeNodes || 1
                const pct = ((val / total) * 100).toFixed(0)
                return (
                  <div key={label} className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full" style={{ background: RISK_PIE_COLORS[i] }} />
                    <span style={{ color: RISK_PIE_COLORS[i] }}>{label}</span>
                    <span className="text-cyber-text-dim ml-auto">{pct}%</span>
                  </div>
                )
              })}
            </div>
          </div>
        ) : (
          <div className="text-[11px] text-cyber-text-dim text-center py-4">
            Awaiting transactions…
          </div>
        )}
      </div>

      {/* Rail distribution bars */}
      <div className="bg-cyber-panel border border-cyber-border rounded-xl p-4">
        <div className="text-[10px] uppercase tracking-widest text-cyber-text-dim mb-3">Payment Rails</div>
        {[
          { label: 'UPI', color: '#00f5ff', pct: 55 },
          { label: 'IMPS', color: '#7fffaa', pct: 25 },
          { label: 'NEFT', color: '#a78bfa', pct: 12 },
          { label: 'RTGS', color: '#ff7733', pct: 8 },
        ].map(({ label, color, pct }) => (
          <div key={label} className="flex items-center gap-2 mb-2">
            <span className="text-[10px] w-8" style={{ color }}>{label}</span>
            <div className="flex-1 h-1.5 bg-cyber-bg rounded-full overflow-hidden">
              <motion.div
                className="h-full rounded-full"
                style={{ background: color, width: `${pct}%` }}
                initial={{ width: 0 }}
                animate={{ width: `${pct}%` }}
                transition={{ duration: 1, ease: 'easeOut' }}
              />
            </div>
            <span className="text-[10px] text-cyber-text-dim w-6">{pct}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}
