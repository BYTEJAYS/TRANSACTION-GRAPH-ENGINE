// ── Collaboration panels for the Investigation Workspace (Phase 2) ────────────
import { useState } from 'react'
import {
  Users, UserPlus, UserCheck, Crown, X, ArrowRightLeft, ShieldCheck,
  MessageSquare, Send, Reply, Pencil, Archive, CheckCircle2, Circle, Plus,
} from 'lucide-react'
import { T } from '../theme'
import { collabApi, type CaseDetail, type CaseComment, type CaseParticipant, type CaseTask, type PresentUser } from './api'
import type { Investigator } from '../auth/api'

export interface CollabProps {
  c: CaseDetail
  caps: string[]
  me: Investigator | null
  busy: boolean
  run: (fn: () => Promise<CaseDetail>) => void
  onErr: (m: string) => void
}

const ADD_ROLES = ['Supporting Investigator', 'Digital Forensics Analyst', 'Recovery Specialist', 'Observer']

function initials(name?: string): string {
  const parts = (name || '?').split(' ').filter(Boolean)
  return ((parts[0]?.[0] ?? '?') + (parts[1]?.[0] ?? '')).toUpperCase()
}
function ago(ts: number): string {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts))
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return new Date(ts * 1000).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
}
function Avatar({ name, color = T.gold, size = 26 }: { name?: string; color?: string; size?: number }) {
  return (
    <span style={{
      width: size, height: size, borderRadius: '50%', flexShrink: 0, display: 'grid', placeItems: 'center',
      background: `${color}22`, color, border: `1px solid ${color}55`, fontSize: size * 0.4, fontWeight: 700,
    }}>{initials(name)}</span>
  )
}
function renderText(text: string) {
  return text.split(/(@[A-Za-z0-9][A-Za-z0-9\-_]{2,31})/g).map((p, i) =>
    p.startsWith('@')
      ? <span key={i} style={{ color: T.gold, fontWeight: 600 }}>{p}</span>
      : <span key={i}>{p}</span>)
}
const card: React.CSSProperties = { background: T.panel, border: `1px solid ${T.border}`, borderRadius: 12, padding: 16 }
const inputStyle: React.CSSProperties = {
  background: T.raised, border: `1px solid ${T.border}`, borderRadius: 9, color: T.text,
  fontSize: 13, padding: '9px 11px', outline: 'none', fontFamily: T.font, boxSizing: 'border-box',
}
function Btn({ onClick, disabled, icon: Icon, label, primary, danger, small }: {
  onClick: () => void; disabled?: boolean; icon?: any; label: string; primary?: boolean; danger?: boolean; small?: boolean
}) {
  const color = danger ? T.danger : primary ? T.gold : T.text2
  return (
    <button onClick={onClick} disabled={disabled} style={{
      display: 'inline-flex', alignItems: 'center', gap: 6, cursor: disabled ? 'default' : 'pointer',
      background: primary ? T.gold : 'transparent', color: primary ? T.textOn : color,
      border: `1px solid ${primary ? T.gold : danger ? `${T.danger}55` : T.border}`,
      borderRadius: 8, padding: small ? '5px 10px' : '8px 13px', fontSize: small ? 11.5 : 12.5,
      fontWeight: 600, fontFamily: T.font, opacity: disabled ? 0.5 : 1,
    }}>{Icon && <Icon size={small ? 12 : 14} />}{label}</button>
  )
}

// ── Live presence row ─────────────────────────────────────────────────────────
export function PresenceBar({ present, connected }: { present: PresentUser[]; connected: boolean }) {
  if (!present.length) {
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, color: T.text3 }}>
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: connected ? T.success : T.text3 }} />
        {connected ? 'Live' : 'Connecting…'}
      </span>
    )
  }
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: T.success }} />
      <div style={{ display: 'flex' }}>
        {present.slice(0, 6).map((p, i) => (
          <span key={(p.investigator_id || '') + i} title={`${p.name} — ${p.activity}`}
            style={{ marginLeft: i ? -7 : 0, borderRadius: '50%', boxShadow: `0 0 0 2px ${T.bg}` }}>
            <Avatar name={p.name} size={24} color={p.activity?.includes('edit') ? T.warn : T.success} />
          </span>
        ))}
      </div>
      <span style={{ fontSize: 11.5, color: T.text2 }}>
        {present.length === 1 ? `${present[0].name} is ${present[0].activity}` : `${present.length} viewing this case`}
      </span>
    </div>
  )
}

// ── Team / participants / assignment ──────────────────────────────────────────
export function TeamPanel({ c, caps, me, busy, run }: CollabProps) {
  const [pid, setPid] = useState('')
  const [prole, setProle] = useState(ADD_ROLES[0])
  const [toId, setToId] = useState('')
  const [hnote, setHnote] = useState('')
  const parts = c.participants ?? []
  const isClosed = ['Resolved', 'Closed', 'False Positive', 'Archived'].includes(c.status)
  const iAmOwner = !!me && c.assigned_to === me.investigator_id
  const canManage = caps.includes('assign_others')

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {/* claim / ownership banner */}
      {!c.assigned_to && caps.includes('claim') && !isClosed && (
        <div style={{ ...card, display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderColor: T.goldLine }}>
          <div>
            <div style={{ fontSize: 13.5, fontWeight: 600 }}>This case is unassigned</div>
            <div style={{ fontSize: 12, color: T.text2, marginTop: 2 }}>Claim it to become the primary investigator.</div>
          </div>
          <Btn onClick={() => run(() => collabApi.claim(c.case_id))} disabled={busy} icon={UserCheck} label="Claim case" primary />
        </div>
      )}

      <div style={card}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <Users size={16} color={T.gold} />
          <span style={{ fontSize: 14, fontWeight: 600 }}>Investigation Team · {parts.length}</span>
        </div>
        {parts.length === 0 && <div style={{ fontSize: 13, color: T.text3 }}>No investigators assigned yet.</div>}
        <div style={{ display: 'grid', gap: 8 }}>
          {parts.map(p => (
            <ParticipantRow key={p.investigator_id} p={p} me={me} canManage={canManage} busy={busy}
              onRemove={() => run(() => collabApi.removeParticipant(c.case_id, p.investigator_id))} />
          ))}
        </div>
      </div>

      {/* add a colleague */}
      {caps.includes('comment') && !isClosed && (
        <div style={card}>
          <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 7 }}>
            <UserPlus size={14} color={T.gold} /> Add a colleague to this case
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <input value={pid} onChange={e => setPid(e.target.value)} placeholder="Investigator ID (e.g. INV-2026)"
              style={{ ...inputStyle, flex: 1, minWidth: 180 }} />
            <select value={prole} onChange={e => setProle(e.target.value)} style={{ ...inputStyle, cursor: 'pointer' }}>
              {ADD_ROLES.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
            <Btn label="Add" icon={Plus} disabled={busy || !pid.trim()}
              onClick={() => { if (!pid.trim()) return; run(() => collabApi.addParticipant(c.case_id, pid.trim().toUpperCase(), prole)); setPid('') }} />
          </div>
        </div>
      )}

      {/* handover */}
      {caps.includes('handover') && (iAmOwner || canManage) && c.assigned_to && !isClosed && (
        <div style={card}>
          <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 7 }}>
            <ArrowRightLeft size={14} color={T.gold} /> Hand over (shift change)
          </div>
          <div style={{ fontSize: 11.5, color: T.text3, marginBottom: 10 }}>
            Transfers primary ownership. {c.assigned_name} stays on the case as a supporting investigator — nothing is lost.
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <input value={toId} onChange={e => setToId(e.target.value)} placeholder="New owner Investigator ID"
              style={{ ...inputStyle, flex: 1, minWidth: 170 }} />
            <input value={hnote} onChange={e => setHnote(e.target.value)} placeholder="Handover note (optional)"
              style={{ ...inputStyle, flex: 1, minWidth: 170 }} />
            <Btn label="Hand over" icon={ArrowRightLeft} disabled={busy || !toId.trim()}
              onClick={() => { if (!toId.trim()) return; run(() => collabApi.handover(c.case_id, toId.trim().toUpperCase(), hnote || undefined)); setToId(''); setHnote('') }} />
          </div>
        </div>
      )}

      {/* request manager review */}
      {caps.includes('comment') && c.status !== 'Pending Approval' && !isClosed && (
        <div style={{ ...card, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 12.5, color: T.text2 }}>Investigation ready for sign-off?</span>
          <Btn label="Request manager review" icon={ShieldCheck} disabled={busy}
            onClick={() => run(() => collabApi.requestApproval(c.case_id))} />
        </div>
      )}
    </div>
  )
}

function ParticipantRow({ p, me, canManage, busy, onRemove }: {
  p: CaseParticipant; me: Investigator | null; canManage: boolean; busy: boolean; onRemove: () => void
}) {
  const isSelf = me?.investigator_id === p.investigator_id
  const canRemove = !p.is_primary && (canManage || isSelf)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '9px 12px', background: T.raised, borderRadius: 9 }}>
      <Avatar name={p.name} color={p.is_primary ? T.gold : T.info} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 7 }}>
          {p.name} {isSelf && <span style={{ fontSize: 10, color: T.text3 }}>(you)</span>}
          {p.is_primary && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 10, color: T.gold, background: T.goldDim, border: `1px solid ${T.goldLine}`, padding: '1px 7px', borderRadius: 999 }}><Crown size={10} /> Primary</span>}
        </div>
        <div style={{ fontSize: 11.5, color: T.text3 }}>{p.role_on_case} · <span style={{ fontFamily: T.mono }}>{p.investigator_id}</span></div>
      </div>
      {canRemove && (
        <button onClick={onRemove} disabled={busy} title="Remove from case"
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.text3, padding: 4 }}>
          <X size={15} />
        </button>
      )}
    </div>
  )
}

// ── Comments thread ───────────────────────────────────────────────────────────
export function CommentsPanel({ c, caps, me, busy, run, onErr }: CollabProps) {
  const [text, setText] = useState('')
  const canComment = caps.includes('comment')
  const all = c.comments ?? []
  const roots = all.filter(x => !x.parent_id)
  const repliesOf = (id: string) => all.filter(x => x.parent_id === id)

  return (
    <div style={card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
        <MessageSquare size={16} color={T.gold} />
        <span style={{ fontSize: 14, fontWeight: 600 }}>Discussion · {all.filter(x => !x.archived).length}</span>
      </div>

      {canComment && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 18 }}>
          <textarea value={text} onChange={e => setText(e.target.value)} rows={2}
            placeholder="Add a comment…  use @INV-ID to mention a colleague"
            style={{ ...inputStyle, flex: 1, resize: 'vertical', minHeight: 38 }} />
          <Btn label="Send" icon={Send} primary disabled={busy || !text.trim()}
            onClick={() => { if (!text.trim()) return; run(() => collabApi.addComment(c.case_id, text)); setText('') }} />
        </div>
      )}

      {roots.length === 0 && <div style={{ fontSize: 13, color: T.text3, padding: '14px 0' }}>No discussion yet. Start the thread.</div>}
      <div style={{ display: 'grid', gap: 14 }}>
        {roots.map(cm => (
          <div key={cm.id}>
            <CommentRow cm={cm} c={c} caps={caps} me={me} busy={busy} run={run} onErr={onErr} />
            {repliesOf(cm.id).length > 0 && (
              <div style={{ marginLeft: 30, marginTop: 10, display: 'grid', gap: 10, borderLeft: `1px solid ${T.border}`, paddingLeft: 14 }}>
                {repliesOf(cm.id).map(r => (
                  <CommentRow key={r.id} cm={r} c={c} caps={caps} me={me} busy={busy} run={run} onErr={onErr} isReply />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function CommentRow({ cm, c, caps, me, busy, run, isReply }: CollabProps & { cm: CaseComment; isReply?: boolean }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(cm.text)
  const [replying, setReplying] = useState(false)
  const [reply, setReply] = useState('')
  const isAuthor = me?.investigator_id === cm.author
  const canMod = isAuthor || caps.includes('approve')

  if (cm.archived) {
    return (
      <div style={{ display: 'flex', gap: 10, opacity: 0.55 }}>
        <Avatar name={cm.author_name} size={26} color={T.text3} />
        <div style={{ fontSize: 12.5, color: T.text3, fontStyle: 'italic', paddingTop: 3 }}>
          Comment by {cm.author_name} archived{cm.archived_by ? ` by ${cm.archived_by}` : ''} · not deleted (audit-preserved)
        </div>
      </div>
    )
  }
  return (
    <div style={{ display: 'flex', gap: 10 }}>
      <Avatar name={cm.author_name} size={26} color={isReply ? T.info : T.gold} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
          <span style={{ fontSize: 12.5, fontWeight: 600 }}>{cm.author_name}</span>
          <span style={{ fontSize: 11, color: T.text3 }}>{ago(cm.created_at)}</span>
          {cm.edited_at && <span style={{ fontSize: 10.5, color: T.text3 }}>· edited{cm.edit_history.length ? ` (${cm.edit_history.length})` : ''}</span>}
        </div>
        {editing ? (
          <div style={{ display: 'flex', gap: 6 }}>
            <textarea value={draft} onChange={e => setDraft(e.target.value)} rows={2} style={{ ...inputStyle, flex: 1 }} />
            <div style={{ display: 'grid', gap: 6 }}>
              <Btn small label="Save" primary disabled={busy || !draft.trim()}
                onClick={() => { run(() => collabApi.editComment(c.case_id, cm.id, draft)); setEditing(false) }} />
              <Btn small label="Cancel" onClick={() => { setEditing(false); setDraft(cm.text) }} />
            </div>
          </div>
        ) : (
          <div style={{ fontSize: 13, color: T.text, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{renderText(cm.text)}</div>
        )}
        <div style={{ display: 'flex', gap: 12, marginTop: 6 }}>
          {!isReply && caps.includes('comment') && (
            <Mini icon={Reply} label="Reply" onClick={() => setReplying(v => !v)} />
          )}
          {isAuthor && !editing && <Mini icon={Pencil} label="Edit" onClick={() => setEditing(true)} />}
          {canMod && <Mini icon={Archive} label="Archive" onClick={() => run(() => collabApi.archiveComment(c.case_id, cm.id))} />}
        </div>
        {replying && (
          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
            <input value={reply} onChange={e => setReply(e.target.value)} placeholder="Reply…" style={{ ...inputStyle, flex: 1 }} />
            <Btn small label="Reply" primary disabled={busy || !reply.trim()}
              onClick={() => { if (!reply.trim()) return; run(() => collabApi.addComment(c.case_id, reply, cm.id)); setReply(''); setReplying(false) }} />
          </div>
        )}
      </div>
    </div>
  )
}

function Mini({ icon: Icon, label, onClick }: { icon: any; label: string; onClick: () => void }) {
  return (
    <button onClick={onClick} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, background: 'none', border: 'none', cursor: 'pointer', color: T.text3, fontSize: 11.5, fontFamily: T.font, padding: 0 }}>
      <Icon size={12} /> {label}
    </button>
  )
}

// ── Tasks / checklist ─────────────────────────────────────────────────────────
export function TasksPanel({ c, caps, me, busy, run }: CollabProps) {
  const [label, setLabel] = useState('')
  const tasks = c.tasks ?? []
  const done = tasks.filter(t => t.done).length
  const pct = tasks.length ? Math.round((done / tasks.length) * 100) : 0
  const canTask = caps.includes('task')

  return (
    <div style={card}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <CheckCircle2 size={16} color={T.gold} />
          <span style={{ fontSize: 14, fontWeight: 600 }}>Investigation Checklist</span>
        </div>
        <span style={{ fontSize: 12, color: T.text2 }}>{done}/{tasks.length} done</span>
      </div>
      <div style={{ height: 6, background: T.raised, borderRadius: 999, overflow: 'hidden', marginBottom: 16 }}>
        <div style={{ width: `${pct}%`, height: '100%', background: pct === 100 ? T.success : T.gold, transition: 'width .3s' }} />
      </div>

      <div style={{ display: 'grid', gap: 6 }}>
        {tasks.map(t => (
          <TaskRow key={t.id} t={t} me={me} canTask={canTask} busy={busy}
            onToggle={() => run(() => collabApi.updateTask(c.case_id, t.id, { done: !t.done }))}
            onAssignMe={() => me && run(() => collabApi.updateTask(c.case_id, t.id, { set_assignee: true, assignee: me.investigator_id, assignee_name: me.name }))} />
        ))}
      </div>

      {canTask && (
        <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
          <input value={label} onChange={e => setLabel(e.target.value)} placeholder="Add a checklist item…"
            style={{ ...inputStyle, flex: 1 }} onKeyDown={e => { if (e.key === 'Enter' && label.trim()) { run(() => collabApi.addTask(c.case_id, label.trim())); setLabel('') } }} />
          <Btn label="Add" icon={Plus} disabled={busy || !label.trim()}
            onClick={() => { if (!label.trim()) return; run(() => collabApi.addTask(c.case_id, label.trim())); setLabel('') }} />
        </div>
      )}
    </div>
  )
}

function TaskRow({ t, me, canTask, busy, onToggle, onAssignMe }: {
  t: CaseTask; me: Investigator | null; canTask: boolean; busy: boolean; onToggle: () => void; onAssignMe: () => void
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '9px 11px', background: T.raised, borderRadius: 9 }}>
      <button onClick={onToggle} disabled={!canTask || busy} style={{ background: 'none', border: 'none', cursor: canTask ? 'pointer' : 'default', padding: 0, display: 'grid', placeItems: 'center', color: t.done ? T.success : T.text3 }}>
        {t.done ? <CheckCircle2 size={18} /> : <Circle size={18} />}
      </button>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, color: t.done ? T.text3 : T.text, textDecoration: t.done ? 'line-through' : 'none' }}>{t.label}</div>
        <div style={{ fontSize: 11, color: T.text3, marginTop: 1 }}>
          {t.assignee_name ? `Assigned to ${t.assignee_name}` : 'Unassigned'}
          {t.done && t.done_by ? ` · done by ${t.done_by}` : ''}
        </div>
      </div>
      {!t.assignee && canTask && me && (
        <button onClick={onAssignMe} disabled={busy} title="Assign to me"
          style={{ background: 'none', border: `1px solid ${T.border}`, borderRadius: 7, cursor: 'pointer', color: T.text3, fontSize: 11, padding: '3px 8px', fontFamily: T.font }}>
          Take
        </button>
      )}
    </div>
  )
}
