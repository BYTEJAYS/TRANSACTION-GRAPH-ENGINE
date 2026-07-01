import { AnimatePresence, motion } from 'framer-motion'
import { HoloPanel } from './HoloPanel'
import { PALETTE } from '../shaders/palette'
import type { LiveTransaction } from '../../types'

interface Props {
  transactions: LiveTransaction[]
  fraudNodeIds: ReadonlySet<string>
}

function fmtAmount(n: number): string {
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)}Cr`
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)}L`
  if (n >= 1e3) return `₹${(n / 1e3).toFixed(1)}K`
  return `₹${n.toFixed(0)}`
}

// Realtime transaction feed — cinematic ticker, top entries enter from above.
export function LiveFeed({ transactions, fraudNodeIds }: Props) {
  const recent = transactions.slice(0, 8)
  return (
    <HoloPanel
      glowColor="rgba(0,245,255,0.14)"
      borderColor="rgba(0,245,255,0.18)"
      style={{ width: 340, padding: '12px 14px' }}
    >
      <Header />
      <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 4 }}>
        <AnimatePresence initial={false}>
          {recent.map(t => {
            const fraud = t.is_flagged || fraudNodeIds.has(t.from_account) || fraudNodeIds.has(t.to_account)
            const color = fraud ? PALETTE.critical : PALETTE.safe
            return (
              <motion.div
                key={t.id}
                layout
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.25 }}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '6px 70px 1fr 70px',
                  alignItems: 'center', gap: 8,
                  padding: '5px 0',
                  borderBottom: '1px solid rgba(255,255,255,0.03)',
                  fontSize: 10,
                }}
              >
                <motion.div
                  animate={fraud ? { opacity: [1, 0.3, 1] } : {}}
                  transition={{ repeat: Infinity, duration: 0.9 }}
                  style={{
                    width: 6, height: 6, borderRadius: '50%',
                    background: color, boxShadow: `0 0 6px ${color}`,
                  }}
                />
                <span style={{ color: '#88aabb', fontFamily: 'monospace' }}>
                  {t.payment_rail}
                </span>
                <span style={{
                  color: fraud ? color : '#aac0d0',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  fontFamily: 'monospace',
                }}>
                  {t.from_account} → {t.to_account}
                </span>
                <span style={{
                  color, fontWeight: 700, textAlign: 'right',
                  textShadow: fraud ? `0 0 8px ${color}` : 'none',
                  fontFamily: '"Orbitron", monospace',
                }}>
                  {fmtAmount(t.amount)}
                </span>
              </motion.div>
            )
          })}
        </AnimatePresence>
        {recent.length === 0 && (
          <div style={{ padding: '14px 0', fontSize: 9, color: '#3a5060', letterSpacing: '.18em' }}>
            AWAITING STREAM · STANDBY
          </div>
        )}
      </div>
    </HoloPanel>
  )
}

function Header() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <motion.div
          animate={{ opacity: [1, 0.35, 1] }}
          transition={{ repeat: Infinity, duration: 1.4 }}
          style={{
            width: 7, height: 7, borderRadius: '50%',
            background: '#00ff88', boxShadow: '0 0 10px #00ff88',
          }}
        />
        <div style={{
          fontSize: 10, letterSpacing: '.22em', color: '#bef0ff', fontWeight: 700,
        }}>LIVE INGESTION</div>
      </div>
      <div style={{ fontSize: 8, color: '#3a5060', letterSpacing: '.15em' }}>
        KAFKA · BLUE TEAM
      </div>
    </div>
  )
}
