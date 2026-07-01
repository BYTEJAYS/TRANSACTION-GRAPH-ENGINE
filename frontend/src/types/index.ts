export type RiskLevel = 'safe' | 'moderate' | 'high' | 'critical'
export type PaymentRail = 'UPI' | 'IMPS' | 'RTGS' | 'NEFT' | 'CASH'
export type ClassificationStatus = 'normal' | 'fraud'
export type CashNodeType = 'CASH_IN' | 'CASH_OUT'

export interface CashNode {
  id: string
  cashType: CashNodeType
  parentAccount: string
  amount: number
  timestamp: string
}

export interface GraphNode {
  id: string
  transaction_count: number
  total_sent: number
  total_received: number
  risk_level: RiskLevel
  risk_score: number
  account_type: string
  detected_patterns: string[]
  geo_locations: string[]
  is_flagged: boolean
  incoming_count: number
  outgoing_count: number
  connected_accounts: string[]
  last_activity: string
  // Cash exposure fields — populated when account has CASH rail events
  cash_inflows?: number
  cash_outflows?: number
  cash_inflow_count?: number
  cash_outflow_count?: number
  // Cash-EVENT ontology (rail-driven, set by the backend graph builder). A cash
  // event is NOT a bank account — it is a boundary where money entered (CASH_IN) or
  // left (CASH_OUT, terminal) the banking system. account_type === 'cash' when set.
  is_cash_event?: boolean
  cash_kind?: 'CASH_IN' | 'CASH_OUT' | null
  is_account?: boolean
  terminal?: boolean
  // Visual — written by store, read by GraphScene
  nodeColor?: string
  nodeSize?: number
  // Three.js runtime positions — written by force-graph
  x?: number; y?: number; z?: number
  vx?: number; vy?: number; vz?: number
  fx?: number; fy?: number; fz?: number
}

export interface GraphLink {
  id: string
  source: string | GraphNode
  target: string | GraphNode
  amount: number
  payment_rail: PaymentRail
  timestamp: string
  risk_score: number
  is_flagged: boolean
  linkColor?: string
}

export interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
}

export interface LiveTransaction {
  id: string
  from_account: string
  to_account: string
  amount: number
  payment_rail: PaymentRail
  timestamp: string
  risk_score: number
  is_flagged: boolean
  fraud_pattern?: string
}

export interface FraudAlert {
  alert_id: string
  alert_type: string
  severity: RiskLevel
  timestamp: string
  accounts_involved: string[]
  description: string
  risk_score: number
  total_amount: number
}

export interface GraphStats {
  nodeCount: number
  linkCount: number
  flaggedNodes: number
  alertCount: number
  totalVolume: number
  fraudRate: number
}

// WebSocket envelope from backend
export interface WSEnvelope {
  type: string
  data: unknown
  timestamp: string
}

// graph_update data payload
export interface WSGraphUpdate {
  nodes?: any[]
  edges?: any[]
  /** Set by the backend at the start of a new run — clients must wipe state. */
  reset?: boolean
  status?: ClassificationStatus
  rules_triggered?: string[]
  suspicious_nodes?: string[]
  current_transaction?: {
    from_account: string
    to_account: string
    amount: number
    step: number
    total: number
  }
  total_processed?: number
  cash_event?: {
    id: string
    type: CashNodeType
    parent_account: string
    amount: number
    timestamp: string
  }
}

// ── Blue Team integration types ───────────────────────────────────────────────

export type BlueTeamStatus = 'idle' | 'analyzing' | 'analyzed' | 'offline' | 'no_data'
export type BlueTeamVerdict = 'CLEAN' | 'SUSPICIOUS' | 'FRAUD' | 'LOGGED' | 'UNKNOWN'

export interface BlueTeamResult {
  status: BlueTeamStatus
  verdict?: BlueTeamVerdict
  score?: number
  action?: string
  confidence?: number
  flagged_nodes?: string[]
  suspicious_reason?: string | null
  transactions_scored?: number
  reason?: string
}

// Per-graph component result — one entry per disconnected cluster
// Single backend-computed contributing factor behind a risk score (explainability).
export interface RiskContributor {
  key: string
  label: string
  points: number   // contribution to the 0–100 score
  max: number      // weight ceiling for this factor
  detail: string   // human-readable evidence
}

// Per-account customer-profile evaluation (Profile Intelligence). Behaviour judged
// relative to the customer's profile, not absolute thresholds.
export interface AccountProfileIntel {
  profile: string
  label: string
  segment: string
  confidence: number
  expected: string
  current: string
  expected_behaviour: string[]
  deviation: number
  mitigation: number
  adjustment_pct: number   // signed: −ve = risk lowered (consistent), +ve = risk raised
  reasons: string[]
}
export interface ProfileIntelligence {
  available: boolean
  accounts: Record<string, AccountProfileIntel>
  component_deviation: number
  amount_mitigation: number
  top_account: string | null
  explanation: string | null
}

// Cross-Bank Intelligence (plug-in enrichment, metadata only — never alters the graph).
export interface CrossBankAccountIntel {
  account: string
  cross_bank_risk: number       // 0–100
  banks_seen: string[]
  linked_banks: number
  linked_accounts: number
  shared_devices: number
  shared_phones: number
  known_suspicious: boolean
  reasons: string[]
}
export interface CrossBankReport {
  available: boolean
  cross_bank_risk: number       // 0–100 component-level
  band: string
  linked_banks: number
  linked_accounts: number
  shared_devices: number
  shared_phone_numbers: number
  known_suspicious_entities: number
  banks_involved: string[]
  cross_bank_patterns: string[]
  accounts: Record<string, CrossBankAccountIntel>
  explanation: string | null
}

// Declared per-account intelligence from the enterprise event format (all optional).
export interface AccountIntel {
  profile?: string
  segment?: string
  kyc_risk?: string
  account_category?: string
  account_status?: string
  current_balance?: number
  device_reputation?: string
  proxy_or_vpn?: boolean
  geo?: string
  geo_anomaly?: boolean
  products?: string[]
  channels?: string[]
  merchant?: Record<string, unknown>
  recovery?: Record<string, unknown>
}

export interface GraphComponentResult {
  graph_id: string
  status: 'analyzed' | 'offline' | 'no_data'
  verdict?: BlueTeamVerdict
  profile_intelligence?: ProfileIntelligence | null
  account_intelligence?: Record<string, AccountIntel> | null
  cross_bank?: CrossBankReport | null
  // 0–1 FRACTION computed by the backend Risk Engine. `null` when the engine
  // could not score this component — the UI MUST render "N/A", never a number.
  risk_score: number | null
  // Explicit availability flag so consumers never mistake a missing score for 0.
  risk_available?: boolean
  // Explainability — all backend-computed, all 0–100 integer points.
  risk_points?: number            // canonical 0–100 integer (= round(risk_score*100))
  risk_level?: string             // Safe | Monitor | Suspicious | High Risk | Critical
  risk_confidence?: number        // 0–100 model CERTAINTY (distinct from risk)
  risk_factors?: string[]         // top contributing factor labels
  risk_contributors?: RiskContributor[]  // full per-factor breakdown
  risk_explanation?: string       // the "Why?" sentence
  flagged: boolean
  flagged_nodes: string[]
  suspicious_reason?: string | null
  transactions_scored: number
  // Node IDs belonging to this component (for camera focus + coloring)
  nodes: string[]
  mode?: string
  reason?: string
}

// Multi-graph result — replaces single BlueTeamResult in the store
export interface BlueTeamMultiResult {
  status: BlueTeamStatus
  graphs: GraphComponentResult[]
}

// Evidence generation
export interface EvidenceFileSummary {
  case_id: string
  fraud_type: string
  total_amount: number
  accounts_count: number
}

export interface EvidenceResult {
  success: boolean
  graph_id: string
  json_filename: string
  pdf_filename: string | null
  json_url: string
  pdf_url: string | null
  pdf_available: boolean
  summary: EvidenceFileSummary
}
