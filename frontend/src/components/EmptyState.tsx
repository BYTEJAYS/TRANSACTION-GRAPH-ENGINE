// ──────────────────────────────────────────────────────────────────────────────
// EmptyState — the dormant, "no graph loaded" overlay.
//
// Shown over the (empty) canvas on first load so the analyst can NEVER mistake
// placeholder data for a live investigation. The graph engine stays dormant
// until real data arrives; this card is the only thing on screen.
// ──────────────────────────────────────────────────────────────────────────────
import { motion } from 'framer-motion'
import { Network, Sparkles, Upload } from 'lucide-react'

const C = {
  text1:  '#e6edf3',
  text2:  '#8b949e',
  text3:  '#5b6675',
  accent: '#4493f8',
  cyan:   '#79c0ff',
} as const

interface Props {
  connected:        boolean
  onGenerateSample: () => void
  onLoadDataset:    () => void
}

export function EmptyState({ connected, onGenerateSample, onLoadDataset }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
      style={{
        position: 'absolute', inset: 0, zIndex: 20,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        pointerEvents: 'none',
      }}
    >
      <motion.div
        initial={{ y: 10, scale: 0.98, opacity: 0 }}
        animate={{ y: 0, scale: 1, opacity: 1 }}
        transition={{ delay: 0.05, duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
        style={{
          pointerEvents: 'auto', textAlign: 'center', userSelect: 'none',
          padding: '34px 40px', borderRadius: 16, maxWidth: 380,
          background: 'rgba(13,17,23,0.55)',
          border: '1px solid rgba(255,255,255,0.07)',
          backdropFilter: 'blur(16px) saturate(120%)',
          WebkitBackdropFilter: 'blur(16px) saturate(120%)',
          boxShadow: '0 16px 60px rgba(0,0,0,0.45)',
        }}
      >
        {/* Pulsing network glyph */}
        <div style={{ position: 'relative', width: 64, height: 64, margin: '0 auto 18px' }}>
          {[0, 1].map(i => (
            <motion.div
              key={i}
              style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: `1px solid ${C.accent}` }}
              animate={{ scale: [1, 1.7], opacity: [0.3, 0] }}
              transition={{ repeat: Infinity, duration: 2.6, delay: i * 1.3, ease: 'easeOut' }}
            />
          ))}
          <div style={{
            position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
            borderRadius: '50%', background: 'rgba(68,147,248,0.08)', border: `1px solid rgba(68,147,248,0.22)`,
          }}>
            <Network size={26} color={C.cyan} strokeWidth={1.5} />
          </div>
        </div>

        <div style={{ fontSize: 15, fontWeight: 700, color: C.text1, letterSpacing: '.01em' }}>
          No transaction graph loaded
        </div>
        <div style={{ fontSize: 12, color: C.text2, marginTop: 7, lineHeight: 1.5 }}>
          Import transactions or generate a simulation<br />to begin fraud analysis.
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: 9, justifyContent: 'center', marginTop: 20 }}>
          <button
            onClick={onGenerateSample}
            style={{
              display: 'flex', alignItems: 'center', gap: 7, cursor: 'pointer',
              padding: '9px 15px', borderRadius: 8, border: '1px solid rgba(68,147,248,0.35)',
              background: 'rgba(68,147,248,0.14)', color: C.accent, fontSize: 12, fontWeight: 600,
            }}
          >
            <Sparkles size={13} /> Generate Sample
          </button>
          <button
            onClick={onLoadDataset}
            style={{
              display: 'flex', alignItems: 'center', gap: 7, cursor: 'pointer',
              padding: '9px 15px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.1)',
              background: 'rgba(255,255,255,0.03)', color: C.text2, fontSize: 12, fontWeight: 600,
            }}
          >
            <Upload size={13} /> Load Dataset
          </button>
        </div>

        <div style={{ fontSize: 9.5, color: C.text3, marginTop: 16, letterSpacing: '.08em' }}>
          {connected ? 'ENGINE READY · WAITING FOR DATA' : 'CONNECTING TO ENGINE…'}
        </div>
      </motion.div>
    </motion.div>
  )
}
