// ──────────────────────────────────────────────────────────────────────────────
// Evidence package generator. Renders a dark-themed, intelligence-agency style
// PDF report from the current fraud state and returns a downloadable Blob URL.
// Triggered by UB's "Give me evidence" command.
// ──────────────────────────────────────────────────────────────────────────────
import jsPDF from 'jspdf'
import type { GraphComponentResult, GraphData, GraphNode } from '../types'
import { riskPct } from '../utils/percent'
import { classifyCluster, fmtDur, type ClusterIntel } from './graphClassifier'
import { roleLabel, type NodeIntel } from './riskPropagation'

// ── Palette — clean, professional forensic-report theme (light paper) ────────
// A credible financial-intelligence document reads as black ink on white stock
// with a restrained navy masthead and reserved accent colors, NOT a dark
// terminal. All colors are tuned for contrast and legibility in print.
const P = {
  bg:        '#ffffff',   // page stock
  panel:     '#f1f5f9',   // slate-100 — card fill
  raised:    '#f8fafc',   // slate-50  — subtle row fill
  border:    '#d8e0ea',   // slate-200 — hairlines
  navy:      '#16233b',   // deep slate-navy — masthead band
  onDark:    '#f8fafc',   // text on the navy band
  text1:     '#0f172a',   // slate-900 — primary ink
  text2:     '#475569',   // slate-600 — body copy
  text3:     '#64748b',   // slate-500 — labels / muted
  accent:    '#1d4ed8',   // blue-700  — primary accent
  cyan:      '#0369a1',   // sky-700   — info / references
  warn:      '#b45309',   // amber-700 — caution
  danger:    '#be123c',   // rose-700  — risk / fraud
  success:   '#15803d',   // green-700 — clean
} as const

const PAGE_W = 595.28   // A4 portrait pt
const PAGE_H = 841.89
const M      = 40       // page margin

export interface EvidenceInput {
  graphs:        GraphComponentResult[]   // all analyzed graphs
  graphData:     GraphData                // full node/link snapshot
  fraudNodeIds:  ReadonlySet<string>
  /** Computed per-node intelligence (real propagated risk + role). */
  riskByNode?:   Map<string, NodeIntel>
  caseRef?:      string                   // optional override
  investigator?: string
  notes?:        string
}

export interface EvidenceResult {
  blobUrl:  string
  filename: string
  caseRef:  string
}

// ── Utilities ────────────────────────────────────────────────────────────────
// NOTE: jsPDF's built-in fonts (Helvetica/Courier) have no ₹ (U+20B9) glyph and
// render it as garbage, so the PDF uses the "INR" code instead. sanitize()
// scrubs any ₹ that arrives inside classifier-generated prose.
function fmtCurrency(v: number): string {
  if (v >= 1e7) return `INR ${(v / 1e7).toFixed(2)} Cr`
  if (v >= 1e5) return `INR ${(v / 1e5).toFixed(2)} L`
  if (v >= 1e3) return `INR ${(v / 1e3).toFixed(1)} K`
  return `INR ${Math.floor(v)}`
}

// Scrub glyphs the built-in PDF fonts can't render (₹, arrows, bullets).
function sanitize(s: string): string {
  return s
    .replace(/₹\s*/g, 'INR ')
    .replace(/\s*[→➔➜]\s*/g, ' -> ')
    .replace(/\s*←\s*/g, ' <- ')
    .replace(/•/g, '-')
}

function fmtDate(d = new Date()): string {
  return d.toISOString().replace('T', ' ').slice(0, 19) + ' UTC'
}

function severityFromScore(s: number): string {
  if (s >= 0.85) return 'CRITICAL'
  if (s >= 0.70) return 'HIGH'
  if (s >= 0.50) return 'MODERATE'
  return 'LOW'
}

function makeCaseRef(): string {
  const d = new Date()
  const pad = (n: number) => `${n}`.padStart(2, '0')
  const rand = Math.random().toString(36).slice(2, 6).toUpperCase()
  return `TGIE-${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${rand}`
}

function explanation(reason?: string | null): string {
  if (!reason) return 'Cluster exhibits anomalous behavioral signatures inconsistent with baseline transaction patterns.'
  const r = reason.toLowerCase()
  if (r.includes('fan'))      return 'Funds rapidly disperse from a single source to multiple recipient accounts — a hallmark of fan-out structuring used to obscure beneficiary identity and complicate forensic tracing.'
  if (r.includes('layer'))    return 'Transaction chain shows deliberate obfuscation through repeated intermediate transfers, a pattern consistent with layering during the placement-layering-integration cycle of money laundering.'
  if (r.includes('cycle')    ||
      r.includes('circular')) return 'A closed transaction cycle was detected: funds traverse a ring of connected accounts and return to (or near) the origin, indicating fictitious flow designed to manufacture transactional history.'
  if (r.includes('smurf')    ||
      r.includes('structur')) return 'Multiple transactions cluster near regulatory reporting thresholds, indicating deliberate structuring (smurfing) to avoid Currency Transaction Report triggers.'
  if (r.includes('velocity')) return 'Transaction frequency materially exceeds expected behavioral bounds for the account class, suggesting automated or coordinated activity.'
  if (r.includes('ensemble')) return 'Ensemble model consensus across multiple detectors flags this cluster: behavioral, structural, and velocity features all deviate from baseline.'
  return `Detection signal: ${reason.replace(/_/g, ' ')}. Manual investigation recommended.`
}

// ── Synthetic cluster diagram (drawn on an offscreen canvas, embedded as PNG) ─
function renderClusterImage(
  cluster: GraphComponentResult,
  graphData: GraphData,
  fraudNodeIds: ReadonlySet<string>,
  w = 720, h = 380,
): string {
  const canvas = document.createElement('canvas')
  canvas.width = w; canvas.height = h
  const ctx = canvas.getContext('2d')!

  // Background
  ctx.fillStyle = P.bg
  ctx.fillRect(0, 0, w, h)
  ctx.strokeStyle = P.border
  ctx.lineWidth = 1
  ctx.strokeRect(0.5, 0.5, w - 1, h - 1)

  // Subtle grid
  ctx.strokeStyle = 'rgba(15,23,42,0.05)'
  ctx.lineWidth = 1
  for (let x = 40; x < w; x += 40) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke()
  }
  for (let y = 40; y < h; y += 40) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke()
  }

  const clusterSet = new Set(cluster.nodes)
  const nodes = graphData.nodes.filter(n => clusterSet.has(n.id))
  if (!nodes.length) {
    ctx.fillStyle = P.text3
    ctx.font = '13px ui-monospace, Menlo, monospace'
    ctx.fillText('Cluster data unavailable.', 16, 28)
    return canvas.toDataURL('image/png')
  }

  // Circle layout
  const cx = w / 2, cy = h / 2
  const radius = Math.min(w, h) * 0.36
  const pos = new Map<string, { x: number; y: number }>()
  nodes.forEach((n, i) => {
    const a = (i / nodes.length) * Math.PI * 2 - Math.PI / 2
    pos.set(n.id, { x: cx + Math.cos(a) * radius, y: cy + Math.sin(a) * radius })
  })

  // Edges within the cluster
  ctx.lineWidth = 1
  for (const l of graphData.links) {
    const src = typeof l.source === 'string' ? l.source : (l.source as { id: string }).id
    const tgt = typeof l.target === 'string' ? l.target : (l.target as { id: string }).id
    const a = pos.get(src), b = pos.get(tgt)
    if (!a || !b) continue
    const flagged = l.is_flagged || (fraudNodeIds.has(src) && fraudNodeIds.has(tgt))
    ctx.strokeStyle = flagged ? 'rgba(190,18,60,0.45)' : 'rgba(29,78,216,0.22)'
    ctx.lineWidth = flagged ? 1.4 : 1
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke()
  }

  // Nodes
  for (const n of nodes) {
    const p = pos.get(n.id)!
    const flagged = fraudNodeIds.has(n.id) || n.is_flagged
    const r = 7 + Math.min(8, n.risk_score * 12)
    // Soft halo
    const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, r * 2.6)
    g.addColorStop(0, flagged ? 'rgba(190,18,60,0.18)' : 'rgba(29,78,216,0.13)')
    g.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = g
    ctx.fillRect(p.x - r * 3, p.y - r * 3, r * 6, r * 6)
    // Fill + crisp ring for definition on white
    ctx.fillStyle = flagged ? P.danger : P.accent
    ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2); ctx.fill()
    ctx.lineWidth = 1.5
    ctx.strokeStyle = flagged ? 'rgba(136,12,43,0.9)' : 'rgba(23,52,153,0.85)'
    ctx.stroke()
    // Label
    ctx.fillStyle = P.text1
    ctx.font = '9px ui-monospace, Menlo, monospace'
    ctx.textAlign = 'center'
    ctx.fillText(n.id.slice(0, 8), p.x, p.y + r + 11)
  }
  ctx.textAlign = 'start'

  // Legend
  ctx.fillStyle = P.text3
  ctx.font = '9px ui-sans-serif, system-ui'
  ctx.fillText(`${cluster.graph_id}  ·  ${nodes.length} nodes  ·  generated ${fmtDate()}`, 14, h - 12)

  return canvas.toDataURL('image/png')
}

// ── PDF primitives ───────────────────────────────────────────────────────────
class PDFBuilder {
  doc: jsPDF
  y = M
  constructor() {
    this.doc = new jsPDF({ unit: 'pt', format: 'a4', compress: true })
    this.paintBackground()
  }

  paintBackground() {
    this.doc.setFillColor(P.bg)
    this.doc.rect(0, 0, PAGE_W, PAGE_H, 'F')
  }

  newPage() {
    this.doc.addPage()
    this.paintBackground()
    this.y = M
  }

  ensure(h: number) {
    if (this.y + h > PAGE_H - M) this.newPage()
  }

  rule(color = P.border) {
    this.doc.setDrawColor(color)
    this.doc.setLineWidth(0.5)
    this.doc.line(M, this.y, PAGE_W - M, this.y)
    this.y += 12
  }

  hexRGB(hex: string): [number, number, number] {
    const h = hex.replace('#', '')
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]
  }

  text(s: string, opts: {
    size?: number; color?: string; bold?: boolean; mono?: boolean;
    indent?: number; gap?: number; align?: 'left' | 'right' | 'center';
  } = {}) {
    const { size = 10, color = P.text2, bold = false, mono = false, indent = 0, gap = 4, align = 'left' } = opts
    this.doc.setFont(mono ? 'courier' : 'helvetica', bold ? 'bold' : 'normal')
    this.doc.setFontSize(size)
    const [r, g, b] = this.hexRGB(color)
    this.doc.setTextColor(r, g, b)
    const maxW = PAGE_W - 2 * M - indent
    const lines = this.doc.splitTextToSize(s, maxW) as string[]
    for (const line of lines) {
      this.ensure(size + 4)
      const x = align === 'right'  ? PAGE_W - M
              : align === 'center' ? PAGE_W / 2
              : M + indent
      this.doc.text(line, x, this.y + size, { align })
      this.y += size + 2
    }
    this.y += gap
  }

  panel(h: number, fill = P.panel, border = P.border) {
    this.ensure(h)
    this.doc.setFillColor(fill); this.doc.setDrawColor(border); this.doc.setLineWidth(0.5)
    this.doc.roundedRect(M, this.y, PAGE_W - 2 * M, h, 4, 4, 'FD')
  }

  sectionHeader(idx: number, title: string) {
    this.ensure(34)
    const x = M
    const w = PAGE_W - 2 * M
    // Accent stripe
    this.doc.setFillColor(P.accent)
    this.doc.rect(x, this.y, 2, 18, 'F')
    // Number
    this.doc.setFont('helvetica', 'bold'); this.doc.setFontSize(8)
    const [r, g, b] = this.hexRGB(P.text3)
    this.doc.setTextColor(r, g, b)
    this.doc.text(`SECTION ${String(idx).padStart(2, '0')}`, x + 10, this.y + 7)
    // Title
    this.doc.setFontSize(13)
    const [r2, g2, b2] = this.hexRGB(P.text1)
    this.doc.setTextColor(r2, g2, b2)
    this.doc.text(title.toUpperCase(), x + 10, this.y + 20)
    // Underline
    this.y += 26
    this.doc.setDrawColor(P.border); this.doc.setLineWidth(0.4)
    this.doc.line(x, this.y, x + w, this.y)
    this.y += 10
  }

  kv(rows: Array<[string, string, string?]>) {
    const labelW = 130
    for (const [k, v, color] of rows) {
      this.ensure(15)
      this.doc.setFont('helvetica', 'normal'); this.doc.setFontSize(9)
      const [r, g, b] = this.hexRGB(P.text3)
      this.doc.setTextColor(r, g, b)
      this.doc.text(k.toUpperCase(), M, this.y + 8)
      this.doc.setFont('courier', 'normal'); this.doc.setFontSize(10)
      const [r2, g2, b2] = this.hexRGB(color ?? P.text1)
      this.doc.setTextColor(r2, g2, b2)
      this.doc.text(v, M + labelW, this.y + 8)
      this.y += 14
    }
    this.y += 6
  }

  image(dataUrl: string, w: number, h: number) {
    this.ensure(h + 6)
    const x = (PAGE_W - w) / 2
    this.doc.addImage(dataUrl, 'PNG', x, this.y, w, h, undefined, 'FAST')
    this.y += h + 10
  }

  output(): { blobUrl: string } {
    const blob = this.doc.output('blob')
    return { blobUrl: URL.createObjectURL(blob) }
  }
}

// ── Main entry ───────────────────────────────────────────────────────────────
export function generateEvidencePDF(input: EvidenceInput): EvidenceResult {
  const { graphs, graphData, fraudNodeIds, riskByNode, investigator = 'TGIE Analyst', notes } = input
  // Real per-node risk (the propagated score the whole app uses); falls back to
  // the backend score only when intelligence wasn't supplied.
  const riskOf = (id: string, fallback = 0): number =>
    riskByNode?.get(id)?.propagatedRisk ?? fallback
  const caseRef = input.caseRef ?? makeCaseRef()
  const ts      = fmtDate()
  const flagged = graphs.filter(g => g.flagged)
  const worst   = [...flagged].sort((a, b) => b.risk_score - a.risk_score)[0]

  // Classify every flagged cluster up front — the named pattern, confidence,
  // source/sink, volume, timeline and narrative all feed the report below.
  const intelByGraph = new Map<string, ClusterIntel>()
  for (const g of flagged) intelByGraph.set(g.graph_id, classifyCluster(g, graphData))
  const worstIntel = worst ? intelByGraph.get(worst.graph_id) ?? null : null
  const totalExposure = flagged.reduce((sum, g) => {
    const it = intelByGraph.get(g.graph_id)
    return sum + (it?.volume ?? 0)
  }, 0)

  const b = new PDFBuilder()

  // ── Cover masthead — navy letterhead band ──────────────────────────────────
  const BAND = 80
  b.doc.setFillColor(P.navy); b.doc.rect(0, 0, PAGE_W, BAND, 'F')
  // accent rule under the band
  b.doc.setFillColor(P.accent); b.doc.rect(0, BAND, PAGE_W, 2.4, 'F')
  // kicker
  b.doc.setFont('helvetica', 'bold'); b.doc.setFontSize(8)
  let [r, g, bl] = b.hexRGB('#93b4ff'); b.doc.setTextColor(r, g, bl)
  b.doc.text('TGIE · TRANSACTION GRAPH INTELLIGENCE ENGINE', M, 30)
  // title
  b.doc.setFontSize(20); [r, g, bl] = b.hexRGB(P.onDark); b.doc.setTextColor(r, g, bl)
  b.doc.text('Evidence Package', M, 56)
  // right-side metadata
  b.doc.setFont('courier', 'normal'); b.doc.setFontSize(8.5)
  ;[r, g, bl] = b.hexRGB('#cbd5e1'); b.doc.setTextColor(r, g, bl)
  b.doc.text(caseRef, PAGE_W - M, 28, { align: 'right' })
  b.doc.text(ts,       PAGE_W - M, 42, { align: 'right' })
  b.doc.setFont('helvetica', 'bold'); b.doc.setFontSize(7.5)
  ;[r, g, bl] = b.hexRGB('#fca5b9'); b.doc.setTextColor(r, g, bl)
  b.doc.text('CLASSIFICATION · RESTRICTED — INTERNAL USE', PAGE_W - M, 58, { align: 'right' })
  b.y = BAND + 22

  // ── 1. Fraud summary ───────────────────────────────────────────────────────
  b.sectionHeader(1, 'Executive Summary')
  b.kv([
    ['Case reference',  caseRef],
    ['Generated',       ts,                                  P.text2],
    ['Graphs analyzed', String(graphs.length)],
    ['Clusters flagged', String(flagged.length),             flagged.length ? P.danger : P.success],
    ['Verdict',          flagged.length ? 'FRAUD'   : 'CLEAN',
                         flagged.length ? P.danger  : P.success],
    ['Pattern type',     worstIntel ? worstIntel.typeLabel : 'N/A',
                         worstIntel ? P.cyan : P.text2],
    ['Confidence',       worstIntel ? `${Math.round(worstIntel.confidence * 100)}%` : 'N/A',
                         worstIntel ? P.warn : P.text2],
    ['Total exposure',   totalExposure ? fmtCurrency(totalExposure) : '₹0',
                         totalExposure ? P.danger : P.text2],
    ['Highest severity', worst ? severityFromScore(worst.risk_score) : 'N/A',
                         worst ? P.danger : P.text2],
    ['Recommendation',   worstIntel ? worstIntel.recommendation : 'No action',
                         worstIntel && (worstIntel.recommendation === 'Freeze' || worstIntel.recommendation === 'SAR Filing') ? P.danger : P.warn],
  ])
  b.text(
    flagged.length
      ? `Network analysis identified ${flagged.length} suspicious cluster${flagged.length > 1 ? 's' : ''}. ` +
        `The highest-risk cluster (${worst?.graph_id ?? 'unknown'}) scored ${Math.round((worst?.risk_score ?? 0) * 100)}% confidence ` +
        `against multiple detection signatures. Manual review and SAR consideration recommended.`
      : 'No clusters were flagged by the active detection ensemble. Network behavior is within baseline parameters.',
    { size: 10, color: P.text2, gap: 12 },
  )

  // ── 2. Suspicious nodes ────────────────────────────────────────────────────
  b.sectionHeader(2, 'Suspicious Nodes')
  if (!fraudNodeIds.size) {
    b.text('No nodes currently flagged.', { color: P.text3, gap: 12 })
  } else {
    const flaggedNodes: GraphNode[] = graphData.nodes
      .filter(n => fraudNodeIds.has(n.id) || riskOf(n.id) >= 0.5)
      .sort((a, b) => riskOf(b.id, b.risk_score) - riskOf(a.id, a.risk_score))
      .slice(0, 12)
    for (const n of flaggedNodes) {
      const intel = riskByNode?.get(n.id)
      const rowH = 30
      b.ensure(rowH + 6)
      // card
      b.doc.setFillColor(P.raised); b.doc.setDrawColor(P.border); b.doc.setLineWidth(0.6)
      b.doc.roundedRect(M, b.y, PAGE_W - 2 * M, rowH, 3, 3, 'FD')
      const pct = Math.round(riskOf(n.id, n.risk_score) * 100)
      const rc = pct >= 70 ? P.danger : pct >= 45 ? P.warn : P.cyan
      // risk stripe
      b.doc.setFillColor(rc); b.doc.rect(M, b.y, 3, rowH, 'F')
      // id + role
      b.doc.setFont('courier', 'bold'); b.doc.setFontSize(10.5)
      let [r, g, bl] = b.hexRGB(P.text1); b.doc.setTextColor(r, g, bl)
      b.doc.text(n.id, M + 12, b.y + 13)
      if (intel?.role) {
        const idW = b.doc.getTextWidth(n.id)
        b.doc.setFont('helvetica', 'bold'); b.doc.setFontSize(7)
        ;[r, g, bl] = b.hexRGB(P.accent); b.doc.setTextColor(r, g, bl)
        b.doc.text(roleLabel(intel.role).toUpperCase(), M + 12 + idW + 8, b.y + 12)
      }
      // meta line below the id (own row — no collision)
      b.doc.setFont('helvetica', 'normal'); b.doc.setFontSize(8)
      ;[r, g, bl] = b.hexRGB(P.text3); b.doc.setTextColor(r, g, bl)
      b.doc.text(`sent ${fmtCurrency(n.total_sent)}   ·   rcvd ${fmtCurrency(n.total_received)}   ·   ${n.transaction_count} tx   ·   ${intel ? intel.degree : (n.incoming_count + n.outgoing_count)} links`,
        M + 12, b.y + 24)
      // right-side risk readout
      b.doc.setFont('helvetica', 'bold'); b.doc.setFontSize(6.5)
      ;[r, g, bl] = b.hexRGB(P.text3); b.doc.setTextColor(r, g, bl)
      b.doc.text('RISK', PAGE_W - M - 12, b.y + 10, { align: 'right' })
      b.doc.setFont('helvetica', 'bold'); b.doc.setFontSize(14)
      ;[r, g, bl] = b.hexRGB(rc); b.doc.setTextColor(r, g, bl)
      b.doc.text(`${pct}%`, PAGE_W - M - 12, b.y + 23, { align: 'right' })
      b.y += rowH + 6
    }
    b.y += 4
  }

  // ── 3. Transaction paths ──────────────────────────────────────────────────
  b.sectionHeader(3, 'Transaction Paths')
  if (!flagged.length) {
    b.text('No suspicious paths recorded.', { color: P.text3, gap: 10 })
  } else {
    for (const g of flagged.slice(0, 4)) {
      b.ensure(40)
      b.text(`${g.graph_id} · ${g.nodes.length} nodes`, { size: 10, color: P.cyan, bold: true })
      const path = g.nodes.slice(0, 6).join('  ->  ')
      b.text(path + (g.nodes.length > 6 ? `  ->  +${g.nodes.length - 6} more` : ''),
        { size: 9, mono: true, color: P.text2, gap: 8 })
    }
  }

  // ── 4. Risk score ──────────────────────────────────────────────────────────
  b.sectionHeader(4, 'Risk Score')
  if (worst) {
    const pct = Math.round(worst.risk_score * 100)
    b.kv([
      ['Cluster',     worst.graph_id],
      ['Confidence', `${pct}%`,                    P.danger],
      ['Severity',    severityFromScore(worst.risk_score), P.danger],
      ['Verdict',     worst.verdict ?? 'FRAUD',    P.danger],
    ])
    // bar
    b.ensure(16)
    const barW = PAGE_W - 2 * M
    b.doc.setFillColor('#e6ebf2'); b.doc.roundedRect(M, b.y, barW, 7, 2, 2, 'F')
    b.doc.setFillColor(P.danger);  b.doc.roundedRect(M, b.y, Math.max(4, barW * worst.risk_score), 7, 2, 2, 'F')
    b.y += 16
  } else {
    b.text('No active risk score.', { color: P.text3, gap: 10 })
  }

  // ── 5. Timestamp ───────────────────────────────────────────────────────────
  b.sectionHeader(5, 'Timestamp')
  b.kv([
    ['Generated (UTC)',  ts],
    ['Local time',       new Date().toString()],
    ['Investigator',     investigator],
  ])

  // ── 6. Fraud classification ────────────────────────────────────────────────
  b.sectionHeader(6, 'Pattern Classification')
  if (flagged.length) {
    for (const g of flagged.slice(0, 6)) {
      const it = intelByGraph.get(g.graph_id)
      b.ensure(28)
      b.text(`${g.graph_id}  —  ${it ? it.typeLabel : (g.suspicious_reason ?? 'unspecified')}`,
        { size: 10, color: P.text1, bold: true, gap: 2 })
      b.text(
        it
          ? `Confidence ${Math.round(it.confidence * 100)}%  ·  ${it.accounts} accounts  ·  ${it.transactions} tx  ·  ` +
            `${fmtCurrency(it.volume)} over ${fmtDur(it.durationMin)}  ·  source ${it.primarySource ?? '—'} → sink ${it.primarySink ?? '—'}`
          : `Verdict: ${g.verdict ?? 'FRAUD'}  ·  Risk ${riskPct(g)}`,
        { size: 8.5, mono: true, color: P.text3, gap: 8 })
    }
  } else {
    b.text('No classifications produced.', { color: P.text3, gap: 10 })
  }

  // ── 7. Key anomalies ───────────────────────────────────────────────────────
  b.sectionHeader(7, 'Key Anomalies')
  const reasons = Array.from(new Set(flagged.map(g => g.suspicious_reason).filter(Boolean))) as string[]
  if (reasons.length) {
    for (const r of reasons) {
      b.text(`• ${r.replace(/_/g, ' ')}`, { color: P.text2, indent: 4, gap: 4 })
    }
    b.y += 6
  } else {
    b.text('No anomalous signatures detected.', { color: P.text3, gap: 10 })
  }

  // ── 8. Graph snapshot ─────────────────────────────────────────────────────
  b.sectionHeader(8, 'Graph Snapshot')
  if (worst) {
    const w = PAGE_W - 2 * M
    const h = w * 0.52
    const png = renderClusterImage(worst, graphData, fraudNodeIds, 900, Math.round(900 * 0.52))
    b.image(png, w, h)
  } else {
    b.text('No cluster available for snapshot.', { color: P.text3, gap: 10 })
  }

  // ── 9. AI-generated explanation ───────────────────────────────────────────
  b.sectionHeader(9, 'AI Findings')
  if (worst) {
    b.text(`${worstIntel ? worstIntel.typeLabel : 'Cluster'} ${worst.graph_id} — confidence ${Math.round((worstIntel?.confidence ?? worst.risk_score) * 100)}%.`,
      { size: 10, bold: true, color: P.text1, gap: 4 })
    // Prefer the classifier's data-driven narrative; fall back to the reason map.
    b.text(sanitize(worstIntel ? worstIntel.summary : explanation(worst.suspicious_reason)),
      { size: 10.5, color: P.text2, gap: 10 })

    // Reconstructed fraud timeline.
    if (worstIntel?.timeline.length) {
      b.text('TRANSACTION TIMELINE', { size: 9, bold: true, color: P.cyan, gap: 6 })
      for (const ev of worstIntel.timeline) {
        b.ensure(14)
        // time chip
        b.doc.setFont('courier', 'bold'); b.doc.setFontSize(9)
        let [r, g, bl] = b.hexRGB(P.accent); b.doc.setTextColor(r, g, bl)
        b.doc.text(ev.at, M + 4, b.y + 8)
        // title + detail
        b.doc.setFont('helvetica', 'bold'); b.doc.setFontSize(9)
        ;[r, g, bl] = b.hexRGB(P.text1); b.doc.setTextColor(r, g, bl)
        b.doc.text(ev.title, M + 56, b.y + 8)
        const tw = b.doc.getTextWidth(ev.title)   // measured in the title's own font
        b.doc.setFont('helvetica', 'normal'); b.doc.setFontSize(8.5)
        ;[r, g, bl] = b.hexRGB(P.text3); b.doc.setTextColor(r, g, bl)
        b.doc.text(sanitize(ev.detail), M + 56 + tw + 12, b.y + 8)
        b.y += 14
      }
      b.y += 8
    }

    if (flagged.length > 1) {
      b.text(`A further ${flagged.length - 1} cluster${flagged.length - 1 > 1 ? 's' : ''} were flagged in the same analysis pass. ` +
             `Cross-cluster review is advised to identify shared counterparties or relay accounts.`,
        { size: 10, color: P.text2, gap: 8 })
    }
  } else {
    b.text('No clusters require analytical narrative.', { color: P.text3, gap: 10 })
  }

  // ── 10. Investigation notes ────────────────────────────────────────────────
  b.sectionHeader(10, 'Investigation Notes')
  b.panel(110)
  const noteY = b.y + 12
  b.doc.setFont('helvetica', 'normal'); b.doc.setFontSize(9)
  const [r2, g2, bl2] = b.hexRGB(P.text2); b.doc.setTextColor(r2, g2, bl2)
  const noteText = notes && notes.trim()
    ? notes
    : 'Recommended actions:\n' +
      '  1. Verify counterparty identities for all flagged nodes.\n' +
      '  2. Place 72-hour transactional hold on the highest-risk cluster pending review.\n' +
      '  3. Cross-reference flagged accounts against internal watchlists and prior SARs.\n' +
      '  4. Capture full transaction history for forensic preservation.'
  const noteLines = b.doc.splitTextToSize(noteText, PAGE_W - 2 * M - 24) as string[]
  noteLines.forEach((line, i) => { b.doc.text(line, M + 12, noteY + i * 12) })
  b.y += 122

  // ── Footer (last page) ─────────────────────────────────────────────────────
  const total = b.doc.getNumberOfPages()
  for (let i = 1; i <= total; i++) {
    b.doc.setPage(i)
    b.doc.setFont('helvetica', 'normal'); b.doc.setFontSize(8)
    const [r, g, bl] = b.hexRGB(P.text3); b.doc.setTextColor(r, g, bl)
    b.doc.text(`UB · ${caseRef}`, M, PAGE_H - 18)
    b.doc.text(`${i} / ${total}`, PAGE_W - M, PAGE_H - 18, { align: 'right' })
  }

  const { blobUrl } = b.output()
  const filename = `${caseRef}.pdf`
  return { blobUrl, filename, caseRef }
}
