// ── Recovery Probability Engine API client ───────────────────────────────────
import { apiRequest } from '../auth/api'
import { T } from '../theme'

export interface CriticalAccount {
  account: string; held_amount: number; freeze_impact: number; freeze_success: number; risk: number
}
export interface KillNode { account: string; disruption_pct: number; degree: number; risk: number | null }
export interface DecayPoint { hours: number; recovery: number }

export interface RecoveryFactor {
  key: string; name: string; score: number; label: string; detail: string
  // optional per-factor extras
  age_hours?: number; hops?: number; recipients?: number
  still_in_fraction?: number; withdrawn_fraction?: number
  critical_accounts?: CriticalAccount[]; routing_hubs?: number
  matches?: { case_id: string; title: string; similarity: number; status: string; recovery_proxy: number }[]
  window_seconds?: number; decay_curve?: DecayPoint[]
  beneficiaries?: number; avg_risk?: number; kill_node?: KillNode | null
}

export interface RecoveryAction {
  priority: number; action: string; target: string | null; type: string
  impact: string; expected_recovery_increase: number; rationale: string
}

export interface RecoveryFunnel {
  fraud_amount: number; still_traceable: number; recoverable: number; likely_recoverable: number
  cashed_out: number; exited_network: number
}

// Explainability surfaces — every item is derived from the flow-of-funds model.
export interface RecoveryReason { polarity: 'positive' | 'negative'; text: string }
export interface RecoveryObstacle { obstacle: string; severity: string; detail: string }
export interface TraceAccount {
  account: string; incoming: number; outgoing: number; traceable_balance: number
  retained: number; dispersed: number; cashed_out: number; status: string
  risk: number; recovery_importance: number
}
export interface RecoveryPath {
  path: string[]; terminal: string; recoverable_amount: number; hops: number; risk: number; priority: number
}
export interface FundFlow {
  originated: number; in_network: number; cashed_out: number; exited: number
  still_in_fraction: number; withdrawn_fraction: number
}

export interface RecoveryAnalysis {
  case_id: string; title: string; category: string; status: string
  insufficient_evidence?: boolean; evidence_message?: string
  recovery_probability: number; band: string; confidence: number
  estimated_loss: number; expected_recoverable: number; headline_action: string
  funnel: RecoveryFunnel
  factors: RecoveryFactor[]
  weights: Record<string, number>
  critical_accounts: CriticalAccount[]
  kill_node: KillNode | null
  decay_curve: DecayPoint[]
  window_seconds: number
  actions: RecoveryAction[]
  reasons?: RecoveryReason[]
  obstacles?: RecoveryObstacle[]
  traceability?: TraceAccount[]
  recovery_paths?: RecoveryPath[]
  flow?: FundFlow
  generated_at: number
}

export interface RecoverySimulation {
  case_id: string; scenario: string; account: string | null; delay_hours: number
  baseline_probability: number; simulated_probability: number; delta: number
  baseline_recoverable: number; simulated_recoverable: number; recoverable_delta: number
  note: string
}

export interface DashboardCase {
  case_id: string; title: string; category: string; status: string; priority: string
  recovery_probability: number; band: string; expected_recoverable: number; estimated_loss: number
  headline_action: string; window_seconds: number; urgent: boolean; is_open: boolean
}
export interface RecoveryDashboard {
  total_recoverable: number; potential_loss_exposure: number
  avg_recovery_probability: number; cases_requiring_action: number; case_count: number
  cases: DashboardCase[]
}

export const recoveryApi = {
  analyze(case_id: string, force = false) {
    return apiRequest<RecoveryAnalysis>('/api/recovery/analyze', { method: 'POST', body: JSON.stringify({ case_id, force }) })
  },
  forCase(case_id: string) { return apiRequest<RecoveryAnalysis>(`/api/recovery/case/${encodeURIComponent(case_id)}`) },
  dashboard() { return apiRequest<RecoveryDashboard>('/api/recovery/dashboard') },
  actions(case_id: string) { return apiRequest<{ case_id: string; actions: RecoveryAction[] }>(`/api/recovery/actions?case_id=${encodeURIComponent(case_id)}`) },
  simulate(case_id: string, scenario: string, account?: string, delay_hours = 24) {
    const p = new URLSearchParams({ case_id, scenario, delay_hours: String(delay_hours) })
    if (account) p.set('account', account)
    return apiRequest<RecoverySimulation>(`/api/recovery/simulation?${p.toString()}`)
  },
  explain(case_id: string, question?: string) {
    return apiRequest<{ case_id: string; answer: string; source: 'ub' | 'heuristic'; model: string | null }>(
      '/api/recovery/explain', { method: 'POST', body: JSON.stringify({ case_id, question }) })
  },
}

// Recovery-probability band → colour (muted, executive — not neon).
export function recoveryColor(score: number): string {
  if (score >= 81) return T.success     // very high
  if (score >= 61) return '#5fa86b'     // high (muted green)
  if (score >= 41) return T.warn        // moderate (amber)
  if (score >= 21) return '#f0883e'     // difficult (orange)
  return T.danger                        // extremely unlikely (red)
}

export function impactColor(impact: string): string {
  switch (impact) {
    case 'Very High': return T.danger
    case 'High': return '#f0883e'
    case 'Medium': return T.warn
    default: return T.text3
  }
}

// ── Derived executive attributes (no new backend data — pure presentation) ─────

// One-line recovery classification for the hero ring.
export function recoveryClass(score: number): string {
  if (score >= 81) return 'VERY HIGH RECOVERY POTENTIAL'
  if (score >= 61) return 'HIGH RECOVERY POTENTIAL'
  if (score >= 41) return 'MODERATE RECOVERY POTENTIAL'
  if (score >= 21) return 'DIFFICULT RECOVERY'
  return 'FUNDS CRITICALLY AT RISK'
}

// Case criticality — low recovery odds against a large exposure is the worst case.
export function caseCriticality(prob: number, loss: number): { label: string; color: string } {
  const big = loss >= 5e5
  if (prob < 35) return { label: 'Critical', color: T.danger }
  if (prob < 55 || (prob < 70 && big)) return { label: 'High', color: '#f0883e' }
  if (prob < 75) return { label: 'Elevated', color: T.warn }
  return { label: 'Contained', color: T.success }
}

// How fast must this action be taken — drives the urgency chip on a decision card.
export function actionUrgency(type: string): { label: string; color: string } {
  switch (type) {
    case 'freeze':
    case 'recall':   return { label: 'Immediate', color: T.danger }
    case 'isolate':  return { label: 'Hours', color: '#f0883e' }
    case 'escalate': return { label: 'Today', color: T.warn }
    default:         return { label: 'Ongoing', color: T.text2 }
  }
}

// Execution difficulty — freeze ease scales with the target account's freeze success.
export function actionDifficulty(type: string, freezeSuccess?: number): { label: string; color: string } {
  if (type === 'freeze') {
    if ((freezeSuccess ?? 60) >= 75) return { label: 'Low', color: T.success }
    if ((freezeSuccess ?? 60) >= 50) return { label: 'Moderate', color: T.warn }
    return { label: 'Hard', color: '#f0883e' }
  }
  switch (type) {
    case 'escalate':
    case 'monitor':  return { label: 'Low', color: T.success }
    case 'recall':   return { label: 'Hard', color: '#f0883e' }
    case 'isolate':  return { label: 'Moderate', color: T.warn }
    default:         return { label: 'Moderate', color: T.warn }
  }
}

// Read the projected recovery probability at an arbitrary hour off the decay curve.
export function recoveryAtHour(curve: DecayPoint[], hours: number): number {
  if (!curve.length) return 0
  if (hours <= curve[0].hours) return curve[0].recovery
  const last = curve[curve.length - 1]
  if (hours >= last.hours) return last.recovery
  for (let i = 1; i < curve.length; i++) {
    const a = curve[i - 1], b = curve[i]
    if (hours <= b.hours) {
      const t = (hours - a.hours) / (b.hours - a.hours || 1)
      return Math.round(a.recovery + t * (b.recovery - a.recovery))
    }
  }
  return last.recovery
}
