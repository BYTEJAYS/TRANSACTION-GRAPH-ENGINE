// ──────────────────────────────────────────────────────────────────────────────
// EvidenceBlockchainPanel — appears when a fraud-evidence package is ready.
//
// Lets the investigator DOWNLOAD the evidence PDF and/or ANCHOR it to the blockchain
// (BELS — the Blockchain Evidence Ledger). Anchoring uploads the actual PDF to BELS,
// which hashes it (SHA-256), stores it off-chain and writes an immutable ledger record
// — returning the evidence ID, block index and transaction hash as cryptographic proof
// that the evidence existed at this time and has not been altered.
// ──────────────────────────────────────────────────────────────────────────────
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Download, ShieldCheck, Link2, Loader2, CheckCircle2, AlertTriangle, Copy, X, Blocks,
} from 'lucide-react'
import { belsUrl } from '../../config'

const C = {
  glass:  'rgba(13,17,23,0.92)',
  raised: 'rgba(28,33,40,0.9)',
  border: 'rgba(255,255,255,0.08)',
  text1:  '#e6edf3',
  text2:  '#8b949e',
  text3:  '#5b6573',
  accent: '#4493f8',
  cyan:   '#79c0ff',
  gold:   '#e3c04a',
  ok:     '#3fb950',
  bad:    '#f85149',
} as const

export interface EvidencePackage {
  blobUrl: string
  filename: string
  caseRef: string
}

interface AnchorResult {
  evidence_id: string
  case_id: string
  file_hash: string
  status: string
  block_index: number
  block_hash: string
  anchor_tx_id: string
}

type Phase = 'idle' | 'anchoring' | 'anchored' | 'error'

interface Props {
  evidence: EvidencePackage
  owner?: string
  onClose: () => void
}

export function EvidenceBlockchainPanel({ evidence, owner = 'investigator', onClose }: Props) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [result, setResult] = useState<AnchorResult | null>(null)
  const [error, setError] = useState<string>('')
  const [copied, setCopied] = useState(false)

  async function anchor() {
    setPhase('anchoring')
    setError('')
    try {
      // Pull the generated PDF back out of the object URL as real bytes.
      const blob = await (await fetch(evidence.blobUrl)).blob()
      const file = new File([blob], evidence.filename, { type: 'application/pdf' })

      const fd = new FormData()
      fd.append('file', file)
      fd.append('case_id', evidence.caseRef)
      fd.append('owner', owner)
      fd.append('role', 'investigator')
      fd.append('evidence_type', 'report')

      const res = await fetch(belsUrl('/evidence/upload'), { method: 'POST', body: fd })
      if (!res.ok) throw new Error(`Ledger responded ${res.status}: ${await res.text()}`)
      const data: AnchorResult = await res.json()
      setResult(data)
      setPhase('anchored')
    } catch (e: any) {
      // Most common cause: the BELS service isn't running on :8200.
      const msg = String(e?.message || e)
      setError(
        msg.includes('Failed to fetch')
          ? 'Could not reach the Blockchain Evidence Ledger. Start it with: python3 -m bels.main'
          : msg,
      )
      setPhase('error')
    }
  }

  function copyProof() {
    if (!result) return
    const proof = [
      `BELS Evidence Anchor Proof`,
      `Evidence ID: ${result.evidence_id}`,
      `Case: ${result.case_id}`,
      `SHA-256: ${result.file_hash}`,
      `Block: #${result.block_index}  ${result.block_hash}`,
      `Tx: ${result.anchor_tx_id}`,
    ].join('\n')
    navigator.clipboard?.writeText(proof)
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  const short = (h: string) => (h ? `${h.slice(0, 10)}…${h.slice(-8)}` : '—')

  return (
    <motion.div
      key={evidence.caseRef}
      initial={{ opacity: 0, y: 14, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 14, scale: 0.96 }}
      transition={{ type: 'spring', stiffness: 300, damping: 28 }}
      style={{
        position: 'absolute', right: 60, bottom: 56, zIndex: 80,
        width: 320, borderRadius: 12,
        background: C.glass,
        border: `1px solid ${phase === 'anchored' ? 'rgba(63,185,80,0.34)' : 'rgba(121,192,255,0.20)'}`,
        backdropFilter: 'blur(22px) saturate(140%)',
        WebkitBackdropFilter: 'blur(22px) saturate(140%)',
        boxShadow: '0 10px 40px rgba(0,0,0,0.6)',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '11px 12px', borderBottom: `1px solid ${C.border}`,
      }}>
        <Blocks size={14} color={C.gold} />
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '.12em', color: C.text2, flex: 1 }}>
          EVIDENCE · BLOCKCHAIN
        </span>
        <button onClick={onClose} aria-label="Dismiss" style={{
          all: 'unset', cursor: 'pointer', display: 'flex', color: C.text3,
        }}>
          <X size={14} />
        </button>
      </div>

      <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* Case reference */}
        <div>
          <div style={{ fontSize: 9, color: C.text3, letterSpacing: '.12em' }}>CASE REFERENCE</div>
          <div style={{
            fontSize: 12, fontWeight: 600, color: C.cyan, marginTop: 3,
            fontFamily: 'ui-monospace, SF Mono, Menlo, monospace',
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {evidence.caseRef}
          </div>
          <div style={{ fontSize: 9.5, color: C.text3, marginTop: 2 }}>{evidence.filename}</div>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: 8 }}>
          <a
            href={evidence.blobUrl}
            download={evidence.filename}
            style={{
              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              padding: '8px 10px', borderRadius: 7,
              background: 'rgba(255,255,255,0.04)', border: `1px solid ${C.border}`,
              color: C.text2, fontSize: 11, fontWeight: 600, textDecoration: 'none',
            }}
          >
            <Download size={12} /> Download
          </a>

          {phase !== 'anchored' && (
            <button
              onClick={anchor}
              disabled={phase === 'anchoring'}
              style={{
                flex: 1.4, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                padding: '8px 10px', borderRadius: 7, cursor: phase === 'anchoring' ? 'default' : 'pointer',
                background: 'rgba(227,192,74,0.14)', border: '1px solid rgba(227,192,74,0.36)',
                color: C.gold, fontSize: 11, fontWeight: 700,
              }}
            >
              {phase === 'anchoring'
                ? (<><Loader2 size={12} className="bels-spin" /> Anchoring…</>)
                : (<><ShieldCheck size={12} /> Anchor to Blockchain</>)}
            </button>
          )}
        </div>

        {/* Result / error */}
        <AnimatePresence mode="wait">
          {phase === 'anchored' && result && (
            <motion.div
              key="ok"
              initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}
              style={{
                background: C.raised, border: '1px solid rgba(63,185,80,0.24)', borderRadius: 8,
                padding: '10px 11px', display: 'flex', flexDirection: 'column', gap: 7,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                <CheckCircle2 size={13} color={C.ok} />
                <span style={{ fontSize: 10.5, fontWeight: 700, color: C.ok, letterSpacing: '.04em' }}>
                  ANCHORED · IMMUTABLE
                </span>
              </div>
              <Field label="Evidence ID" value={result.evidence_id} mono />
              <Field label="SHA-256" value={short(result.file_hash)} mono title={result.file_hash} />
              <Field label="Block" value={`#${result.block_index} · ${short(result.block_hash)}`} mono />
              <Field label="Transaction" value={short(result.anchor_tx_id)} mono title={result.anchor_tx_id} />
              <button
                onClick={copyProof}
                style={{
                  marginTop: 2, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                  padding: '6px 10px', borderRadius: 6, cursor: 'pointer',
                  background: 'rgba(255,255,255,0.04)', border: `1px solid ${C.border}`,
                  color: copied ? C.ok : C.text2, fontSize: 10.5, fontWeight: 600,
                }}
              >
                {copied ? <CheckCircle2 size={11} /> : <Copy size={11} />}
                {copied ? 'Proof copied' : 'Copy proof'}
              </button>
            </motion.div>
          )}

          {phase === 'error' && (
            <motion.div
              key="err"
              initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}
              style={{
                background: 'rgba(248,81,73,0.08)', border: '1px solid rgba(248,81,73,0.26)',
                borderRadius: 8, padding: '10px 11px', display: 'flex', gap: 8,
              }}
            >
              <AlertTriangle size={13} color={C.bad} style={{ flexShrink: 0, marginTop: 1 }} />
              <span style={{ fontSize: 10, lineHeight: 1.45, color: C.text2 }}>{error}</span>
            </motion.div>
          )}
        </AnimatePresence>

        {phase === 'idle' && (
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 9, color: C.text3 }}>
            <Link2 size={10} />
            Anchoring writes a tamper-evident SHA-256 record to the evidence ledger.
          </div>
        )}
      </div>

      <style>{`@keyframes bels-spin{to{transform:rotate(360deg)}}.bels-spin{animation:bels-spin 0.8s linear infinite}`}</style>
    </motion.div>
  )
}

function Field({ label, value, mono, title }: { label: string; value: string; mono?: boolean; title?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
      <span style={{ fontSize: 8.5, color: C.text3, letterSpacing: '.08em', textTransform: 'uppercase', width: 74, flexShrink: 0 }}>
        {label}
      </span>
      <span
        title={title}
        style={{
          fontSize: 10, color: C.text1, fontWeight: 600,
          fontFamily: mono ? 'ui-monospace, SF Mono, Menlo, monospace' : 'inherit',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}
      >
        {value}
      </span>
    </div>
  )
}
