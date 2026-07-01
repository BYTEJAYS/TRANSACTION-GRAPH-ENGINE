// Temporary developer diagnostic panel for the voice subsystem.
// Enable with ?voicedebug in the URL, or localStorage.setItem('voicedebug','1').
// Surfaces exactly where speech fails so production issues are diagnosable at a glance.
import { useEffect, useState } from 'react'
import * as VoiceService from '../../services/voiceService'

const ROW: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', gap: 12, padding: '2px 0' }
const KEY: React.CSSProperties = { color: '#7a8aa0' }

function val(ok: boolean | null, text: string): React.CSSProperties {
  return { color: ok === null ? '#c9d4e3' : ok ? '#36d399' : '#f87272', fontWeight: 600 }
}

export default function VoiceDebugPanel() {
  const [d, setD] = useState(() => VoiceService.getDiagnostics())

  useEffect(() => {
    const id = setInterval(() => setD(VoiceService.getDiagnostics()), 400)
    return () => clearInterval(id)
  }, [])

  return (
    <div
      style={{
        position: 'fixed', bottom: 12, left: 12, zIndex: 99999,
        width: 280, padding: 12, borderRadius: 10,
        background: 'rgba(8,12,20,0.92)', border: '1px solid #1f2b3d',
        font: '11px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace',
        color: '#c9d4e3', boxShadow: '0 8px 30px rgba(0,0,0,0.5)', backdropFilter: 'blur(6px)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <strong style={{ color: '#5ec2ff', letterSpacing: 0.5 }}>[VOICE] DIAGNOSTICS</strong>
        <span style={{ color: '#566' }}>live</span>
      </div>

      <div style={ROW}><span style={KEY}>Speech Supported</span>
        <span style={val(d.supported, '')}>{d.supported ? 'TRUE' : 'FALSE'}</span></div>

      <div style={ROW}><span style={KEY}>Voices Loaded</span>
        <span style={val(d.voicesLoaded > 0, '')}>{d.voicesLoaded}</span></div>

      <div style={ROW}><span style={KEY}>Selected Voice</span>
        <span style={{ ...val(!!d.selectedVoice, ''), maxWidth: 150, textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {d.selectedVoice ?? '—'}</span></div>

      <div style={ROW}><span style={KEY}>Voice Type</span>
        <span style={{ color: d.selectedVoiceLocal ? '#36d399' : '#f0a02f', fontWeight: 600 }}>
          {d.selectedVoiceLocal === null ? '—' : d.selectedVoiceLocal ? 'local' : 'remote'}</span></div>

      <div style={ROW}><span style={KEY}>Unlocked (gesture)</span>
        <span style={val(d.unlocked, '')}>{d.unlocked ? 'YES' : 'NO — click page'}</span></div>

      <div style={ROW}><span style={KEY}>Speech Queue</span>
        <span style={{ color: '#c9d4e3', fontWeight: 600 }}>
          {d.speaking ? 'active' : d.queued ? 'pending' : 'empty'}</span></div>

      <div style={ROW}><span style={KEY}>Rate</span>
        <span style={{ color: '#c9d4e3' }}>{d.rate.toFixed(2)}</span></div>

      <div style={ROW}><span style={KEY}>Last Event</span>
        <span style={{ color: d.lastEvent === 'error' ? '#f87272' : '#5ec2ff', fontWeight: 600 }}>{d.lastEvent}</span></div>

      {d.lastError && (
        <div style={{ marginTop: 6, color: '#f87272', fontSize: 10 }}>⚠ {d.lastError}</div>
      )}

      <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
        <button
          onClick={() => { VoiceService.unlockSpeech(); VoiceService.speak('Voice diagnostic test. Synthesis is audible.') }}
          style={btn('#1c3a55')}
        >Test speak</button>
        <button onClick={() => VoiceService.stopSpeaking()} style={btn('#3a1c1c')}>Stop</button>
      </div>
    </div>
  )
}

function btn(bg: string): React.CSSProperties {
  return {
    flex: 1, padding: '5px 0', borderRadius: 6, border: '1px solid #2a3a50',
    background: bg, color: '#dbe6f5', cursor: 'pointer', font: 'inherit',
  }
}
