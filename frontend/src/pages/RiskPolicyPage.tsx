import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, SlidersHorizontal, Save, RotateCcw, ShieldAlert } from 'lucide-react'
import { Page } from '../components/nav/AppLayout'
import { riskApi, type RiskConfig } from '../cases/api'
import { T } from '../theme'

// Administrator panel to tune the Risk Engine — thresholds & weights, no code edits.
export default function RiskPolicyPage() {
  const navigate = useNavigate()
  const [cfg, setCfg] = useState<RiskConfig | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { riskApi.getConfig().then(setCfg).catch(e => setErr(e.message)) }, [])

  const save = async () => {
    if (!cfg) return
    setBusy(true); setMsg(null); setErr(null)
    try { const next = await riskApi.updateConfig(cfg); setCfg(next); setMsg('Risk policy saved.') }
    catch (e) { setErr(e instanceof Error ? e.message : 'Save failed (managers/admins only)') }
    finally { setBusy(false) }
  }
  const reset = async () => {
    setBusy(true); setMsg(null); setErr(null)
    try { const next = await riskApi.resetConfig(); setCfg(next); setMsg('Reset to defaults.') }
    catch (e) { setErr(e instanceof Error ? e.message : 'Reset failed') }
    finally { setBusy(false) }
  }

  if (!cfg) return <Page><button onClick={() => navigate(-1)} style={backBtn}><ArrowLeft size={15} /> Back</button>
    <div style={{ marginTop: 24, color: err ? T.danger : T.text3, fontSize: 13 }}>{err ?? 'Loading risk policy…'}</div></Page>

  const setThreshold = (k: keyof RiskConfig['thresholds'], v: number) =>
    setCfg({ ...cfg, thresholds: { ...cfg.thresholds, [k]: v }, ...(k === 'high_risk' ? { investigation_threshold: v } : {}) })

  return (
    <Page>
      <button onClick={() => navigate(-1)} style={backBtn}><ArrowLeft size={15} /> Back</button>
      <div style={{ display: 'flex', alignItems: 'center', gap: 11, marginTop: 12 }}>
        <SlidersHorizontal size={19} color={T.gold} />
        <h1 style={{ fontSize: 19, fontWeight: 700, margin: 0 }}>Risk Policy — Threshold & Weight Tuning</h1>
      </div>
      <p style={{ color: T.text2, fontSize: 13, margin: '8px 0 20px' }}>
        Configure how TGIE scores fraud and when it opens cases. Changes apply to the next detection — no code edits.
      </p>

      {/* thresholds */}
      <div style={card}>
        <div style={hdr}><ShieldAlert size={16} color={T.gold} /> Risk-level thresholds (0–100)</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px,1fr))', gap: 14 }}>
          <Num label="Monitor ≥" value={cfg.thresholds.monitor} onChange={v => setThreshold('monitor', v)} />
          <Num label="Suspicious ≥" value={cfg.thresholds.suspicious} onChange={v => setThreshold('suspicious', v)} />
          <Num label="High Risk ≥ (opens case)" value={cfg.thresholds.high_risk} onChange={v => setThreshold('high_risk', v)} accent />
          <Num label="Critical ≥" value={cfg.thresholds.critical} onChange={v => setThreshold('critical', v)} />
        </div>
        <div style={{ display: 'flex', gap: 20, marginTop: 16, flexWrap: 'wrap', alignItems: 'center' }}>
          <Num label="Velocity window (s)" value={cfg.velocity_window_seconds} onChange={v => setCfg({ ...cfg, velocity_window_seconds: v })} />
          <Num label="Velocity txn target" value={cfg.velocity_txn_target} onChange={v => setCfg({ ...cfg, velocity_txn_target: v })} />
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: T.text2, cursor: 'pointer' }}>
            <input type="checkbox" checked={cfg.suppress_false_positives} onChange={e => setCfg({ ...cfg, suppress_false_positives: e.target.checked })} />
            Suppress false positives (cap benign simple transfers)
          </label>
        </div>
      </div>

      {/* weights */}
      <div style={{ ...card, marginTop: 14 }}>
        <div style={hdr}><SlidersHorizontal size={16} color={T.gold} /> Factor weights (max points each can contribute)</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px,1fr))', gap: 14 }}>
          {Object.entries(cfg.weights).map(([k, v]) => (
            <Num key={k} label={k.replace(/_/g, ' ')} value={v}
              onChange={nv => setCfg({ ...cfg, weights: { ...cfg.weights, [k]: nv } })} />
          ))}
        </div>
      </div>

      {(msg || err) && <div style={{ marginTop: 14, fontSize: 12.5, color: err ? T.danger : T.success }}>{err ?? msg}</div>}

      <div style={{ display: 'flex', gap: 10, marginTop: 18 }}>
        <button onClick={save} disabled={busy} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '10px 16px', borderRadius: 9, border: 'none', background: T.gold, color: T.textOn, fontWeight: 700, fontSize: 12.5, cursor: 'pointer', fontFamily: T.font }}><Save size={15} /> Save policy</button>
        <button onClick={reset} disabled={busy} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '10px 16px', borderRadius: 9, border: `1px solid ${T.border}`, background: T.raised, color: T.text2, fontSize: 12.5, cursor: 'pointer', fontFamily: T.font }}><RotateCcw size={15} /> Reset defaults</button>
      </div>
    </Page>
  )
}

const card: React.CSSProperties = { background: T.panel, border: `1px solid ${T.border}`, borderRadius: 12, padding: 16 }
const hdr: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 9, marginBottom: 14, fontSize: 13.5, fontWeight: 600 }
const backBtn: React.CSSProperties = { display: 'inline-flex', alignItems: 'center', gap: 7, background: 'none', border: 'none', color: T.text2, fontSize: 12.5, cursor: 'pointer', padding: 0, fontFamily: T.font }

function Num({ label, value, onChange, accent }: { label: string; value: number; onChange: (v: number) => void; accent?: boolean }) {
  return (
    <label style={{ display: 'block' }}>
      <div style={{ fontSize: 9.5, color: accent ? T.gold : T.text3, letterSpacing: '.05em', marginBottom: 6, textTransform: 'capitalize', fontWeight: accent ? 700 : 400 }}>{label}</div>
      <input type="number" value={value} onChange={e => onChange(Number(e.target.value))}
        style={{ width: '100%', boxSizing: 'border-box', padding: '8px 10px', background: T.bg2, border: `1px solid ${accent ? T.goldLine : T.border}`, borderRadius: 8, color: T.text, fontSize: 13, outline: 'none', fontFamily: T.mono }} />
    </label>
  )
}
