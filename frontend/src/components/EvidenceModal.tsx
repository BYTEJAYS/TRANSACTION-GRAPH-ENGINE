import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { apiUrl } from '../config'
import type { GraphComponentResult, EvidenceResult } from '../types'
import { riskPct, riskValue } from '../utils/percent'

const C = {
  bg:      '#0d1117',
  surface: '#161b22',
  raised:  '#1c2128',
  border:  'rgba(255,255,255,0.08)',
  borderS: 'rgba(255,255,255,0.05)',
  text1:   '#e6edf3',
  text2:   '#8b949e',
  text3:   '#484f58',
  accent:  '#4493f8',
  danger:  '#f85149',
  success: '#3fb950',
} as const

interface Props {
  fraudGraphs: GraphComponentResult[]
  onDismiss: () => void
}

type ModalState = 'prompt' | 'generating' | 'ready' | 'error'

function fmt(n: number): string {
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)} L`
  return `₹${n.toLocaleString('en-IN')}`
}

function Spinner() {
  return (
    <motion.div
      animate={{ rotate: 360 }}
      transition={{ repeat: Infinity, duration: 1.1, ease: 'linear' }}
      style={{
        width: 18, height: 18, borderRadius: '50%',
        border: `2px solid rgba(255,255,255,0.07)`,
        borderTopColor: C.accent,
        flexShrink: 0,
      }}
    />
  )
}

export function EvidenceModal({ fraudGraphs, onDismiss }: Props) {
  const [modalState, setModalState] = useState<ModalState>('prompt')
  const [results, setResults]       = useState<EvidenceResult[]>([])
  const [errorMsg, setErrorMsg]     = useState<string | null>(null)

  const worstGraph = [...fraudGraphs].sort((a, b) => riskValue(b) - riskValue(a))[0]

  const handleYes = async () => {
    setModalState('generating')
    setErrorMsg(null)
    try {
      const generated: EvidenceResult[] = []
      for (const g of fraudGraphs) {
        const res = await fetch(apiUrl('/api/evidence/generate'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ graph_id: g.graph_id }),
        })
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Server error' }))
          throw new Error(err.detail || `Failed for ${g.graph_id}`)
        }
        generated.push(await res.json())
      }
      setResults(generated)
      setModalState('ready')
    } catch (e: any) {
      setErrorMsg(e.message || 'Evidence generation failed')
      setModalState('error')
    }
  }

  const handleDownload = (url: string, filename: string) => {
    const a = document.createElement('a')
    a.href = apiUrl(url)
    a.download = filename
    a.click()
  }

  return (
    <AnimatePresence>
      <motion.div
        key="evidence-backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        style={{
          position: 'fixed', inset: 0, zIndex: 200,
          background: 'rgba(0,0,0,0.65)',
          backdropFilter: 'blur(8px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
        onClick={e => { if (e.target === e.currentTarget) onDismiss() }}
      >
        <motion.div
          key="evidence-panel"
          initial={{ opacity: 0, scale: 0.96, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 12 }}
          transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
          style={{
            width: 440,
            background: '#0d1117',
            border: `1px solid rgba(248,81,73,0.22)`,
            borderRadius: 10,
            boxShadow: '0 24px 64px rgba(0,0,0,0.7)',
            overflow: 'hidden',
          }}
        >
          {/* ── Header ─────────────────────────────────────────────────── */}
          <div style={{
            padding: '14px 18px',
            borderBottom: `1px solid rgba(248,81,73,0.10)`,
            background: 'rgba(248,81,73,0.04)',
            display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <div style={{
              width: 28, height: 28, borderRadius: 6, flexShrink: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'rgba(248,81,73,0.08)',
              border: `1px solid rgba(248,81,73,0.20)`,
            }}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M7 1L2 3.2v3.5c0 3.22 2.5 6.23 5 6.8 2.5-.57 5-3.58 5-6.8V3.2L7 1z"
                  fill="none" stroke={C.danger} strokeWidth="1" opacity="0.9"/>
                <path d="M4.5 7l1.8 1.8L9.5 5.5" stroke={C.danger} strokeWidth="1" strokeLinecap="round"/>
              </svg>
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: C.danger }}>
                Fraud cluster detected
              </div>
              <div style={{ fontSize: 10, color: C.text3 }}>
                Blue Team · Evidence Generation
              </div>
            </div>
            <button
              onClick={onDismiss}
              style={{
                width: 24, height: 24, borderRadius: 4,
                border: `1px solid ${C.border}`,
                background: 'transparent', cursor: 'pointer',
                color: C.text3, fontSize: 16, lineHeight: 1,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'border-color 0.15s, color 0.15s',
              }}
              onMouseEnter={e => {
                (e.currentTarget as HTMLButtonElement).style.color = C.text2
                ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(255,255,255,0.14)'
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLButtonElement).style.color = C.text3
                ;(e.currentTarget as HTMLButtonElement).style.borderColor = C.border
              }}
            >
              ×
            </button>
          </div>

          {/* ── Body ───────────────────────────────────────────────────── */}
          <div style={{ padding: '16px 18px' }}>
            <AnimatePresence mode="wait">

              {/* PROMPT */}
              {modalState === 'prompt' && (
                <motion.div key="prompt" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
                    {fraudGraphs.map(g => (
                      <div key={g.graph_id} style={{
                        padding: '10px 12px', borderRadius: 6,
                        background: 'rgba(248,81,73,0.05)',
                        border: '1px solid rgba(248,81,73,0.14)',
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                            <motion.div
                              animate={{ opacity: [1, 0.25, 1] }}
                              transition={{ repeat: Infinity, duration: 1.1 }}
                              style={{ width: 5, height: 5, borderRadius: '50%', background: C.danger }}
                            />
                            <span style={{
                              fontSize: 11, fontWeight: 500,
                              fontFamily: 'ui-monospace, SF Mono, Menlo, monospace',
                              color: C.danger,
                            }}>
                              {g.graph_id}
                            </span>
                          </div>
                          <span style={{
                            fontSize: 10, fontWeight: 600, color: C.danger,
                            padding: '1px 7px', borderRadius: 3,
                            background: 'rgba(248,81,73,0.08)',
                            border: '1px solid rgba(248,81,73,0.18)',
                          }}>
                            FRAUD
                          </span>
                        </div>
                        <div style={{ display: 'flex', gap: 16 }}>
                          <div>
                            <div style={{ fontSize: 9, color: C.text3, marginBottom: 2 }}>Risk score</div>
                            <div style={{ fontSize: 14, fontWeight: 600, color: C.danger, fontFamily: 'ui-monospace, monospace', fontVariantNumeric: 'tabular-nums' }}>
                              {riskPct(g)}
                            </div>
                          </div>
                          {g.flagged_nodes.length > 0 && (
                            <div>
                              <div style={{ fontSize: 9, color: C.text3, marginBottom: 2 }}>Flagged accounts</div>
                              <div style={{ fontSize: 10, color: C.text3, fontFamily: 'ui-monospace, monospace' }}>
                                {g.flagged_nodes.slice(0, 3).join(', ')}
                                {g.flagged_nodes.length > 3 && ` +${g.flagged_nodes.length - 3}`}
                              </div>
                            </div>
                          )}
                        </div>
                        {g.suspicious_reason && (
                          <div style={{
                            marginTop: 8, fontSize: 10, color: C.text3,
                            fontFamily: 'ui-monospace, monospace',
                            padding: '5px 8px', borderRadius: 4,
                            background: 'rgba(255,255,255,0.02)',
                            border: `1px solid ${C.borderS}`,
                          }}>
                            {g.suspicious_reason}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  <p style={{ margin: '0 0 14px', fontSize: 11, color: C.text3, lineHeight: 1.6 }}>
                    Generate a forensic evidence file with fraud metadata, transaction paths,
                    account details, and risk explanation — downloadable as JSON and PDF.
                  </p>

                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      onClick={handleYes}
                      style={{
                        flex: 1, padding: '9px 0', borderRadius: 5, cursor: 'pointer',
                        background: 'rgba(248,81,73,0.12)',
                        border: `1px solid rgba(248,81,73,0.30)`,
                        color: C.danger, fontSize: 11, fontWeight: 500,
                        transition: 'background 0.15s',
                      }}
                      onMouseEnter={e => (e.currentTarget as HTMLButtonElement).style.background = 'rgba(248,81,73,0.20)'}
                      onMouseLeave={e => (e.currentTarget as HTMLButtonElement).style.background = 'rgba(248,81,73,0.12)'}
                    >
                      Generate evidence
                    </button>
                    <button
                      onClick={onDismiss}
                      style={{
                        flex: 1, padding: '9px 0', borderRadius: 5, cursor: 'pointer',
                        background: 'transparent',
                        border: `1px solid ${C.border}`,
                        color: C.text3, fontSize: 11,
                        transition: 'border-color 0.15s',
                      }}
                      onMouseEnter={e => (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(255,255,255,0.14)'}
                      onMouseLeave={e => (e.currentTarget as HTMLButtonElement).style.borderColor = C.border}
                    >
                      Skip
                    </button>
                  </div>
                </motion.div>
              )}

              {/* GENERATING */}
              {modalState === 'generating' && (
                <motion.div
                  key="generating"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14, padding: '28px 0' }}
                >
                  <Spinner />
                  <div style={{ fontSize: 11, color: C.text2, textAlign: 'center', lineHeight: 1.7 }}>
                    Extracting fraud metadata · Building transaction path<br/>
                    Compiling risk explanation · Rendering PDF report
                  </div>
                </motion.div>
              )}

              {/* ERROR */}
              {modalState === 'error' && (
                <motion.div key="error" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                  style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div style={{
                    padding: '10px 12px', borderRadius: 5,
                    background: 'rgba(248,81,73,0.06)', border: '1px solid rgba(248,81,73,0.18)',
                    fontSize: 11, color: C.danger, fontFamily: 'ui-monospace, monospace',
                  }}>
                    {errorMsg}
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button onClick={handleYes} style={{
                      flex: 1, padding: '8px 0', borderRadius: 5, cursor: 'pointer',
                      background: 'rgba(248,81,73,0.08)', border: '1px solid rgba(248,81,73,0.22)',
                      color: C.danger, fontSize: 11,
                    }}>Retry</button>
                    <button onClick={onDismiss} style={{
                      flex: 1, padding: '8px 0', borderRadius: 5, cursor: 'pointer',
                      background: 'transparent', border: `1px solid ${C.border}`,
                      color: C.text3, fontSize: 11,
                    }}>Dismiss</button>
                  </div>
                </motion.div>
              )}

              {/* READY */}
              {modalState === 'ready' && (
                <motion.div key="ready" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                  style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '9px 12px', borderRadius: 5,
                    background: 'rgba(63,185,80,0.05)', border: '1px solid rgba(63,185,80,0.14)',
                  }}>
                    <div style={{
                      width: 18, height: 18, borderRadius: '50%',
                      background: 'rgba(63,185,80,0.10)', border: '1px solid rgba(63,185,80,0.22)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                    }}>
                      <svg width="9" height="9" viewBox="0 0 9 9" fill="none">
                        <path d="M1.5 4.5l2 2L7.5 2" stroke={C.success} strokeWidth="1.2" strokeLinecap="round"/>
                      </svg>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, fontWeight: 500, color: C.success }}>Evidence generated</div>
                      <div style={{ fontSize: 10, color: C.text3 }}>
                        {results.length} package{results.length > 1 ? 's' : ''} ready
                      </div>
                    </div>
                  </div>

                  {results.map(r => (
                    <div key={r.graph_id} style={{
                      padding: '10px 12px', borderRadius: 5,
                      background: 'rgba(255,255,255,0.02)', border: `1px solid ${C.borderS}`,
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                        <span style={{ fontSize: 11, color: C.danger, fontFamily: 'ui-monospace, monospace', fontWeight: 500 }}>{r.graph_id}</span>
                        <span style={{ fontSize: 10, color: C.text3, fontFamily: 'monospace' }}>{r.summary.case_id}</span>
                      </div>
                      <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginBottom: 10 }}>
                        {[r.summary.fraud_type, fmt(r.summary.total_amount), `${r.summary.accounts_count} accounts`].map(tag => (
                          <span key={tag} style={{
                            fontSize: 9, padding: '2px 7px', borderRadius: 3,
                            background: 'rgba(255,255,255,0.03)',
                            border: `1px solid ${C.borderS}`,
                            color: C.text2,
                          }}>{tag}</span>
                        ))}
                      </div>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button
                          onClick={() => handleDownload(r.json_url, r.json_filename)}
                          style={{
                            flex: 1, padding: '7px 0', borderRadius: 4, cursor: 'pointer',
                            background: 'rgba(68,147,248,0.07)', border: '1px solid rgba(68,147,248,0.18)',
                            color: C.accent, fontSize: 10,
                            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
                            transition: 'background 0.15s',
                          }}
                          onMouseEnter={e => (e.currentTarget as HTMLButtonElement).style.background = 'rgba(68,147,248,0.14)'}
                          onMouseLeave={e => (e.currentTarget as HTMLButtonElement).style.background = 'rgba(68,147,248,0.07)'}
                        >
                          ↓ JSON
                        </button>
                        {r.pdf_available && r.pdf_url && r.pdf_filename && (
                          <button
                            onClick={() => handleDownload(r.pdf_url!, r.pdf_filename!)}
                            style={{
                              flex: 1, padding: '7px 0', borderRadius: 4, cursor: 'pointer',
                              background: 'rgba(248,81,73,0.07)', border: '1px solid rgba(248,81,73,0.18)',
                              color: C.danger, fontSize: 10,
                              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
                              transition: 'background 0.15s',
                            }}
                            onMouseEnter={e => (e.currentTarget as HTMLButtonElement).style.background = 'rgba(248,81,73,0.14)'}
                            onMouseLeave={e => (e.currentTarget as HTMLButtonElement).style.background = 'rgba(248,81,73,0.07)'}
                          >
                            ↓ PDF
                          </button>
                        )}
                      </div>
                    </div>
                  ))}

                  <button
                    onClick={onDismiss}
                    style={{
                      width: '100%', padding: '9px 0', borderRadius: 5, cursor: 'pointer',
                      background: 'transparent', border: `1px solid ${C.border}`,
                      color: C.text3, fontSize: 11, marginTop: 2,
                      transition: 'border-color 0.15s',
                    }}
                    onMouseEnter={e => (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(255,255,255,0.14)'}
                    onMouseLeave={e => (e.currentTarget as HTMLButtonElement).style.borderColor = C.border}
                  >
                    Close
                  </button>
                </motion.div>
              )}

            </AnimatePresence>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
