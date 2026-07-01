export type PaymentRail = 'UPI' | 'IMPS' | 'RTGS' | 'NEFT'
export type RiskLevel = 'safe' | 'moderate' | 'high' | 'critical'
export type ClassificationStatus = 'normal' | 'fraud'
export type SimulationState = 'idle' | 'running' | 'completed'

export type FraudPattern =
  | 'normal'
  | 'circular_transfer'
  | 'fan_out'
  | 'layering'
  | 'rapid_microtransaction'
  | 'mule_chain'
  | 'burst_transfer'
  | 'structuring'

// ── Manual ingestion ──────────────────────────────────────────────────────────

export interface ManualTransactionInput {
  from_account: string
  to_account: string
  amount: number
  payment_rail: string
  timestamp?: string
}

// ── Force-graph node/link shapes ──────────────────────────────────────────────

export interface ForceNode {
  id: string
  // structural
  transaction_count: number
  total_sent: number
  total_received: number
  risk_level: RiskLevel
  risk_score: number
  account_type: string
  detected_patterns: string[]
  geo_locations: string[]
  is_flagged: boolean
  // derived display helpers (set by graphStore)
  incoming_count: number
  outgoing_count: number
  connected_accounts: string[]
  last_activity: string
  // visual (written by store, read by GraphScene nodeThreeObject)
  nodeColor?: string
  nodeSize?: number
}

export interface ForceLink {
  id: string
  source: string | ForceNode
  target: string | ForceNode
  amount: number
  payment_rail: string
  timestamp: string
  risk_score: number
  is_flagged: boolean
}

export interface ForceGraphData {
  nodes: ForceNode[]
  links: ForceLink[]
}

// ── Websocket message shapes ──────────────────────────────────────────────────

export interface ManualGraphUpdate {
  nodes: any[]
  edges: any[]
  stats?: Record<string, any>
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
}

// ── Legacy types kept for NodeInspector compatibility ─────────────────────────

export interface GraphNode {
  id: string
  label: string
  risk_score: number
  risk_level: RiskLevel
  account_type: 'normal' | 'mule' | 'high_value' | 'merchant' | 'cash'
  transaction_count: number
  total_sent: number
  total_received: number
  is_flagged: boolean
  detected_patterns: FraudPattern[]
  geo_locations: string[]
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  amount: number
  payment_rail: PaymentRail
  risk_score: number
  timestamp: string
  fraud_pattern: FraudPattern
  is_flagged: boolean
}

export interface GraphStats {
  total_transactions: number
  total_volume: number
  total_nodes: number
  total_edges: number
  flagged_nodes: number
  flagged_transactions: number
}

export interface GraphState {
  nodes: GraphNode[]
  edges: GraphEdge[]
  stats: GraphStats
}

// ── Legacy types (kept for backward compat with unused components) ────────────

export interface Transaction {
  transaction_id: string
  from_account: string
  to_account: string
  amount: number
  timestamp: string
  payment_rail: PaymentRail
  device_id: string
  ip_address: string
  geo_location: string
  risk_score: number
  fraud_pattern: FraudPattern
  metadata: Record<string, unknown>
}

export interface DashboardStats {
  totalTransactions: number
  totalVolume: number
  activeNodes: number
  flaggedNodes: number
  fraudAlerts: number
  throughput: number
  riskDistribution: { safe: number; moderate: number; high: number; critical: number }
}

export interface FraudAlert {
  alert_id: string
  alert_type: FraudPattern
  severity: RiskLevel
  timestamp: string
  accounts_involved: string[]
  transaction_ids: string[]
  description: string
  risk_score: number
  shap_explanation: Record<string, number>
  propagation_path: string[]
  total_amount: number
}
