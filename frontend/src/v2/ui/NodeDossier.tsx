import { AnimatePresence, motion } from 'framer-motion'
import { HoloPanel } from './HoloPanel'
import { PALETTE, riskColor } from '../shaders/palette'
import type { GraphNode } from '../../types'

interface Props {
  node: GraphNode | null
  isFraud: boolean
  graphId?: string
  onClose: () => void
}

function fmt(n: number): string {
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)}Cr`
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)}L`
  if (n >= 1e3) return `₹${(n / 1e3).toFixed(1)}K`
  return `₹${n.toFixed(0)}`
}

// Side panel — selected-node intelligence dossier.
// Cinematic readout, not a generic property dump.
export function NodeDossier({ node, isFraud, graphId, onClose }: Props) {
  return (
    <AnimatePresence>
      {node && (
        <motion.div
          key={node.id}
          initial={{ opacity: 0, x: 40 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 40 }}
          transition={{ duration: 0.45, ease: [0.22, 0.61, 0.36, 1] }}
          style={{ position: 'absolute', top: 90, right: 18, zIndex: 50, width: 340 }}
        >
          <HoloPanel
            glowColor={isFraud ? 'rgba(255,51,102,0.32)' : 'rgba(0,245,255,0.18)'}
            borderColor={isFraud ? 'rgba(255,51,102,0.40)' : 'rgba(0,245,255,0.28)'}
            intense={isFraud}
            style={{ padding: '14px 16px' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <div>
                <div style={{ fontSize: 8, letterSpacing: '.22em', color: '#5a7a8a' }}>
                  ENTITY DOSSIER
                </div>
                <div style={{
                  marginTop: 4, fontSize: 16, fontWeight: 700,
                  color: PALETTE.holoText, letterSpacing: '.04em',
                  fontFamily: '"Orbitron", monospace',
                }}>
                  {node.id}
                </div>
              </div>
              <button
                onClick={onClose}
                style={{
                  background: 'transparent', border: '1px solid rgba(255,255,255,0.1)',
                  color: '#88aabb', cursor: 'pointer',
                  fontSize: 9, padding: '3px 8px', borderRadius: 4, letterSpacing: '.14em',
                }}
              >CLOSE</button>
            </div>

            <div style={{
              marginTop: 12, padding: 10, borderRadius: 8,
              border: `1px solid ${isFraud ? 'rgba(255,51,102,0.30)' : 'rgba(0,245,255,0.14)'}`,
              background: isFraud ? 'rgba(255,51,102,0.06)' : 'rgba(0,245,255,0.03)',
            }}>
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }}>
                <span style={{ fontSize: 9, color: '#88aabb', letterSpacing: '.18em' }}>
                  RISK SCORE
                </span>
                <span style={{
                  fontSize: 22, fontWeight: 900,
                  color: riskColor(node.risk_score, isFraud),
                  textShadow: `0 0 14px ${riskColor(node.risk_score, isFraud)}`,
                  fontFamily: '"Orbitron", monospace',
                }}>
                  {(node.risk_score * 100).toFixed(0)}%
                </span>
              </div>
              <div style={{
                marginTop: 8, height: 3, borderRadius: 2,
                background: 'rgba(255,255,255,0.05)', overflow: 'hidden',
              }}>
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.min(100, node.risk_score * 100)}%` }}
                  transition={{ duration: 0.7, ease: 'easeOut' }}
                  style={{
                    height: '100%',
                    background: riskColor(node.risk_score, isFraud),
                    boxShadow: `0 0 10px ${riskColor(node.risk_score, isFraud)}`,
                  }}
                />
              </div>
            </div>

            <Row label="Account Type" value={node.account_type.toUpperCase()} />
            <Row label="Risk Level"   value={node.risk_level.toUpperCase()} accent={riskColor(node.risk_score, isFraud)} />
            <Row label="Transactions" value={node.transaction_count.toString()} />
            <Row label="Inflow"        value={fmt(node.total_received)} />
            <Row label="Outflow"       value={fmt(node.total_sent)} />
            <Row label="Connections"  value={(node.connected_accounts?.length ?? 0).toString()} />
            {graphId && <Row label="Cluster" value={graphId} mono />}

            {(node.detected_patterns?.length ?? 0) > 0 && (
              <div style={{ marginTop: 10 }}>
                <div style={{ fontSize: 8, letterSpacing: '.22em', color: '#5a7a8a', marginBottom: 5 }}>
                  DETECTED PATTERNS
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {node.detected_patterns.map(p => (
                    <span key={p} style={{
                      fontSize: 8, padding: '3px 7px', borderRadius: 4,
                      background: 'rgba(255,51,102,0.10)',
                      color: PALETTE.critical, letterSpacing: '.06em',
                      border: '1px solid rgba(255,51,102,0.20)',
                    }}>{p}</span>
                  ))}
                </div>
              </div>
            )}

            {(node.geo_locations?.length ?? 0) > 0 && (
              <div style={{ marginTop: 10, fontSize: 9, color: '#788d9d', letterSpacing: '.10em' }}>
                <span style={{ color: '#5a7a8a', letterSpacing: '.22em' }}>GEO · </span>
                {node.geo_locations.join(' · ')}
              </div>
            )}
          </HoloPanel>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function Row({ label, value, accent, mono }: { label: string; value: string; accent?: string; mono?: boolean }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
      padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.03)',
    }}>
      <span style={{ fontSize: 9, color: '#5a7a8a', letterSpacing: '.18em' }}>{label}</span>
      <span style={{
        fontSize: 11, color: accent ?? PALETTE.holoText,
        fontFamily: mono ? 'monospace' : '"JetBrains Mono", monospace',
        textShadow: accent ? `0 0 6px ${accent}66` : 'none',
        letterSpacing: '.04em',
      }}>{value}</span>
    </div>
  )
}
