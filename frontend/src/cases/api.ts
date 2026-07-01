// ── Case Management API client ───────────────────────────────────────────────
import { apiRequest, tokenStore } from '../auth/api'
import { apiUrl } from '../config'

export interface CaseSummary {
  case_id: string
  title: string
  category: string
  status: string
  priority: string
  risk_score: number
  fraud_confidence: number
  assigned_to: string | null
  assigned_name: string | null
  created_at: number
  updated_at: number
  account_count: number
  primary_account: string | null
  is_open: boolean
  // collaboration counts (Phase 2)
  participant_count?: number
  comment_count?: number
  open_tasks?: number
  task_total?: number
  is_locked?: boolean
}

export interface CaseTransaction {
  txn_id: string; amount: number; date: number
  from_account: string; to_account: string; rail: string; reason: string
}
export interface CaseEvidence {
  evidence_id: string; type: string; description?: string
  hash: string; anchored: boolean; added_at: number; added_by: string
  // present on real uploaded files (Phase 2)
  name?: string; uploader?: string; timestamp?: number; sha256?: string
  size_bytes?: number; remarks?: string; verification_status?: string; has_file?: boolean
}

// ── Baked analysis sections (Phase 1 single source of truth) ──────────────────
export interface AccountRole {
  account: string; role: string; risk: number; transactions: number
  incoming: number; outgoing: number; status: string
}
export interface CaseRecovery {
  probability: number; band: string | null; confidence: number
  estimated_loss: number; expected_recoverable: number; timeline: string
  window_seconds: number; accounts_to_freeze: string[]
  critical_accounts: { account: string; held_amount: number; freeze_impact: number; freeze_success: number; risk: number }[]
  most_recoverable_branch: string | null; least_recoverable_branch: string | null
  headline_action: string | null; recommended_priority: string | null
}
export interface RiskFactor { key: string; label: string; points: number; max: number; detail: string }
export interface RiskAssessment {
  score: number
  level: 'Safe' | 'Monitor' | 'Suspicious' | 'High Risk' | 'Critical'
  action: string
  priority: string
  confidence: number
  factors: RiskFactor[]
  top_indicators: string[]
  suppressed: boolean
  suppression_reason: string | null
  explanation: string
  should_create_case: boolean
  investigation_threshold: number
  metrics: Record<string, unknown>
  scored_at: string
}

export interface CaseBlockchain {
  status: string; verified: boolean; provider: string; hash: string | null
  evidence_id: string | null; txid: string | null
  block_index: number | null; block_hash: string | null
  certificate: Record<string, unknown> | null
  anchored_at: number | null; verified_at: number | null
  items: { component: string; hash: string }[]
}
export interface CaseNote {
  id: string; ts: number; author: string; author_name: string; text: string
}
export interface CaseTimelineEvent {
  id: string; ts: number; event: string; actor: string; detail: string
}
export interface CaseRiskPoint { ts: number; score: number; reason: string }
export interface GraphSnapshot {
  // seeded snapshots use {id,risk,role}+{from,to}; captured (verbatim) snapshots
  // use positioned nodes {id,x,y,z,…}+{source,target} plus a camera.
  nodes: Array<{ id: string; risk?: number; role?: string; x?: number; y?: number; z?: number } & Record<string, unknown>>
  edges: Array<({ from?: string; to?: string; source?: string; target?: string }) & Record<string, unknown>>
  indicators: string[]
  camera?: { position: { x: number; y: number; z: number }; target: { x: number; y: number; z: number } } | null
  captured?: boolean
  captured_at?: number
}

// ── Collaboration (Phase 2) ───────────────────────────────────────────────────
export interface CaseParticipant {
  investigator_id: string; name: string; role_on_case: string
  is_primary: boolean; added_by: string; added_at: number
}
export interface CaseComment {
  id: string; author: string; author_name: string; text: string
  parent_id: string | null; mentions: string[]; attachments: unknown[]
  created_at: number; edited_at: number | null
  edit_history: { ts: number; previous_text: string; editor: string }[]
  archived: boolean; archived_by: string | null; archived_at: number | null
}
export interface CaseTask {
  id: string; label: string; done: boolean
  assignee: string | null; assignee_name: string | null
  done_by: string | null; done_at: number | null
  created_by: string; created_at: number
}
export interface MyCapabilities { role: string; tier: string; capabilities: string[] }
export interface OpsMetrics {
  total_cases: number; open: number; critical: number; unassigned: number
  waiting_assignment: number; waiting_approval: number; escalated: number; resolved: number
  potential_loss: number; recovered_amount: number; evidence_today: number
  blockchain_verifications: number; active_investigators: number
}
export interface WorkloadRow {
  investigator_id: string; name: string; role: string | null
  active: number; critical: number; pending: number; overloaded: boolean; idle: boolean
}
export interface Workload {
  investigators: WorkloadRow[]; overloaded: string[]; idle: string[]
  recommendations: string[]; unassigned_open: number
}
export interface MyDashboard {
  assigned: number; open: number; completed: number; critical: number
  pending_reviews: number; participating: number; today_activity: number
  recent_cases: CaseSummary[]; unread_comments: number
}
export interface PresentUser { investigator_id: string | null; name: string; avatar: string | null; activity: string }

export interface CaseDetail extends Omit<CaseSummary, 'account_count' | 'is_open'> {
  detection_reason: string
  supervisor: string | null
  department: string | null
  due_date: string | null
  accounts: string[]
  transactions: CaseTransaction[]
  evidence: CaseEvidence[]
  notes: CaseNote[]
  timeline: CaseTimelineEvent[]
  risk_history: CaseRiskPoint[]
  graph_snapshot: GraphSnapshot
  ub_analysis: string
  // Phase 1 baked sections (optional → tolerant of pre-enrichment cases)
  recovery?: CaseRecovery
  account_roles?: AccountRole[]
  roles?: { primary_suspects: string[]; victims: string[]; intermediaries: string[]; destinations: string[] }
  payment_rails?: string[]
  graph_metrics?: Record<string, unknown>
  financials?: { total_amount: number; estimated_recoverable: number; estimated_loss: number; recovery_probability: number; recovery_timeline: string }
  blockchain?: CaseBlockchain
  risk_assessment?: RiskAssessment | null
  // Cross-Bank Intelligence (metadata only; present when there is a cross-bank signal).
  cross_bank?: {
    risk: number; band: string; banks_involved: string[]
    linked_banks: number; linked_accounts: number
    shared_devices: number; shared_phones: number
    known_suspicious_entities: number; patterns: string[]
  } | null
  last_updated?: number
  // collaboration (Phase 2)
  participants?: CaseParticipant[]
  comments?: CaseComment[]
  tasks?: CaseTask[]
  locks?: Record<string, { holder_id: string; holder_name: string; ts: number }>
}

// ── Risk Engine config (admin) + preview ──────────────────────────────────────
export interface RiskConfig {
  thresholds: { monitor: number; suspicious: number; high_risk: number; critical: number }
  investigation_threshold: number
  weights: Record<string, number>
  velocity_window_seconds: number
  velocity_txn_target: number
  suppress_false_positives: boolean
}

export const riskApi = {
  getConfig() { return apiRequest<RiskConfig>('/api/risk/config') },
  updateConfig(patch: Partial<RiskConfig>) {
    return apiRequest<RiskConfig>('/api/risk/config', { method: 'PUT', body: JSON.stringify(patch) })
  },
  resetConfig() { return apiRequest<RiskConfig>('/api/risk/config/reset', { method: 'POST', body: '{}' }) },
  classify(score: number) {
    return apiRequest<{ score: number; level: string; action: string; priority: string }>(`/api/risk/classify?score=${score}`)
  },
}

export interface SearchHit extends CaseSummary { matched_on: string }

export interface CaseStats {
  total: number; open: number; critical: number
  assigned_to_me: number; resolved: number; escalated: number
}

export interface CaseMeta { statuses: string[]; priorities: string[]; categories: string[] }

export const caseApi = {
  list(scope?: string, status?: string, priority?: string) {
    const p = new URLSearchParams()
    if (scope) p.set('scope', scope)
    if (status) p.set('status', status)
    if (priority) p.set('priority', priority)
    const qs = p.toString()
    return apiRequest<{ cases: CaseSummary[]; meta: CaseMeta }>(`/api/cases${qs ? '?' + qs : ''}`)
  },
  stats() { return apiRequest<CaseStats>('/api/cases/stats') },
  notifications() {
    return apiRequest<{ notifications: { case_id: string; title: string; event: string; detail: string; ts: number }[] }>('/api/cases/notifications')
  },
  get(id: string) { return apiRequest<CaseDetail>(`/api/cases/${encodeURIComponent(id)}`) },
  byAccount(account: string) {
    return apiRequest<{ cases: CaseSummary[] }>(`/api/cases/by-account/${encodeURIComponent(account)}`)
  },
  create(body: Record<string, unknown>) {
    return apiRequest<CaseDetail>('/api/cases/create', { method: 'POST', body: JSON.stringify(body) })
  },
  update(id: string, body: Record<string, unknown>) {
    return apiRequest<CaseDetail>(`/api/cases/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(body) })
  },
  addNote(id: string, text: string) {
    return apiRequest<CaseDetail>(`/api/cases/${encodeURIComponent(id)}/notes`, { method: 'POST', body: JSON.stringify({ text }) })
  },
  addEvidence(id: string, body: { type: string; description?: string; reference?: string }) {
    return apiRequest<CaseDetail>(`/api/cases/${encodeURIComponent(id)}/evidence`, { method: 'POST', body: JSON.stringify(body) })
  },
  assign(id: string, body: Record<string, unknown>) {
    return apiRequest<CaseDetail>(`/api/cases/${encodeURIComponent(id)}/assign`, { method: 'POST', body: JSON.stringify(body) })
  },
  close(id: string, resolution: string, summary?: string) {
    return apiRequest<CaseDetail>(`/api/cases/${encodeURIComponent(id)}/close`, { method: 'POST', body: JSON.stringify({ resolution, summary }) })
  },

  // ── Phase 2: evidence files, blockchain, bundle, search ────────────────────
  async uploadEvidence(id: string, file: File, type = '', remarks = ''): Promise<CaseDetail> {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('type', type)
    fd.append('remarks', remarks)
    // NB: do NOT set Content-Type — the browser must add the multipart boundary.
    const res = await fetch(apiUrl(`/api/cases/${encodeURIComponent(id)}/evidence/upload`), {
      method: 'POST',
      headers: tokenStore.access ? { Authorization: `Bearer ${tokenStore.access}` } : {},
      body: fd,
    })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? 'Upload failed')
    return res.json()
  },
  downloadEvidence(id: string, evidenceId: string) {
    return authedDownload(`/api/cases/${encodeURIComponent(id)}/evidence/${encodeURIComponent(evidenceId)}/download`)
  },
  downloadBundle(id: string) {
    return authedDownload(`/api/cases/${encodeURIComponent(id)}/bundle`, `${id}-case-bundle.zip`)
  },
  downloadReceipt(id: string) {
    return authedDownload(`/api/cases/${encodeURIComponent(id)}/blockchain/receipt`, `${id}-blockchain-receipt.json`)
  },
  anchorBlockchain(id: string) {
    return apiRequest<CaseDetail>(`/api/cases/${encodeURIComponent(id)}/blockchain/anchor`, { method: 'POST', body: '{}' })
  },
  verifyBlockchain(id: string) {
    return apiRequest<{ verified: boolean; tampered: boolean; current_hash: string; anchored_hash: string; provider: string; blockchain: CaseBlockchain }>(
      `/api/cases/${encodeURIComponent(id)}/blockchain/verify`)
  },
  search(q: string) {
    return apiRequest<{ query: string; results: SearchHit[] }>(`/api/cases/search?q=${encodeURIComponent(q)}`)
  },
  saveGraphSnapshot(id: string, snap: { nodes: unknown[]; edges: unknown[]; camera?: unknown; indicators?: string[] }) {
    return apiRequest<CaseDetail>(`/api/cases/${encodeURIComponent(id)}/graph-snapshot`, { method: 'POST', body: JSON.stringify(snap) })
  },
}

// ── Collaboration API client (Phase 2) ────────────────────────────────────────
const eid = encodeURIComponent

export const collabApi = {
  capabilities() { return apiRequest<MyCapabilities>('/api/cases/me/capabilities') },
  myDashboard() { return apiRequest<MyDashboard>('/api/cases/my/dashboard') },
  opsMetrics() { return apiRequest<OpsMetrics>('/api/cases/ops/metrics') },
  workload() { return apiRequest<Workload>('/api/cases/ops/workload') },

  claim(id: string) {
    return apiRequest<CaseDetail>(`/api/cases/${eid(id)}/claim`, { method: 'POST', body: '{}' })
  },
  addParticipant(id: string, investigator_id: string, role_on_case: string, name?: string) {
    return apiRequest<CaseDetail>(`/api/cases/${eid(id)}/participants`,
      { method: 'POST', body: JSON.stringify({ investigator_id, role_on_case, name }) })
  },
  removeParticipant(id: string, investigatorId: string) {
    return apiRequest<CaseDetail>(`/api/cases/${eid(id)}/participants/${eid(investigatorId)}`, { method: 'DELETE' })
  },
  handover(id: string, to_investigator_id: string, note?: string, to_name?: string) {
    return apiRequest<CaseDetail>(`/api/cases/${eid(id)}/handover`,
      { method: 'POST', body: JSON.stringify({ to_investigator_id, note, to_name }) })
  },
  requestApproval(id: string, note?: string) {
    return apiRequest<CaseDetail>(`/api/cases/${eid(id)}/request-approval`,
      { method: 'POST', body: JSON.stringify({ note }) })
  },

  addComment(id: string, text: string, parent_id?: string | null) {
    return apiRequest<CaseDetail>(`/api/cases/${eid(id)}/comments`,
      { method: 'POST', body: JSON.stringify({ text, parent_id: parent_id ?? null }) })
  },
  editComment(id: string, commentId: string, text: string) {
    return apiRequest<CaseDetail>(`/api/cases/${eid(id)}/comments/${eid(commentId)}`,
      { method: 'PUT', body: JSON.stringify({ text }) })
  },
  archiveComment(id: string, commentId: string) {
    return apiRequest<CaseDetail>(`/api/cases/${eid(id)}/comments/${eid(commentId)}/archive`,
      { method: 'POST', body: '{}' })
  },

  addTask(id: string, label: string, assignee?: string, assignee_name?: string) {
    return apiRequest<CaseDetail>(`/api/cases/${eid(id)}/tasks`,
      { method: 'POST', body: JSON.stringify({ label, assignee, assignee_name }) })
  },
  updateTask(id: string, taskId: string,
             body: { done?: boolean; set_assignee?: boolean; assignee?: string | null; assignee_name?: string | null }) {
    return apiRequest<CaseDetail>(`/api/cases/${eid(id)}/tasks/${eid(taskId)}`,
      { method: 'PUT', body: JSON.stringify(body) })
  },

  lock(id: string, resource = 'notes') {
    return apiRequest<{ locked: boolean; resource: string; holder_name: string }>(
      `/api/cases/${eid(id)}/lock`, { method: 'POST', body: JSON.stringify({ resource }) })
  },
  unlock(id: string, resource = 'notes') {
    return apiRequest<{ released: boolean }>(`/api/cases/${eid(id)}/lock?resource=${eid(resource)}`, { method: 'DELETE' })
  },
}

// Authenticated blob download → saves via a transient object URL. Honours the
// Content-Disposition filename when the server provides one.
async function authedDownload(path: string, fallbackName?: string): Promise<void> {
  const res = await fetch(apiUrl(path), {
    headers: tokenStore.access ? { Authorization: `Bearer ${tokenStore.access}` } : {},
  })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? 'Download failed')
  const cd = res.headers.get('Content-Disposition') ?? ''
  const m = /filename="?([^"]+)"?/.exec(cd)
  const name = m?.[1] ?? fallbackName ?? path.split('/').pop() ?? 'download'
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = name
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 4000)
}

// ── shared helpers ────────────────────────────────────────────────────────────
export function priorityColor(p: string): string {
  switch (p) {
    case 'Critical': return '#e5484d'
    case 'High': return '#f0883e'
    case 'Medium': return '#d9a23a'
    default: return '#46a758'
  }
}

export function caseStatusColor(s: string): string {
  const x = s.toLowerCase()
  if (x.includes('escalat')) return '#e5484d'
  if (x.includes('active') || x.includes('evidence')) return '#f0883e'
  if (x.includes('review') || x.includes('new') || x.includes('pending')) return '#5b8def'
  if (x.includes('resolved')) return '#46a758'
  if (x.includes('false')) return '#7a7360'
  if (x.includes('closed') || x.includes('archiv')) return '#7a7360'
  return '#9aa3af'
}
