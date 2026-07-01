import { useCallback, useEffect, useState } from 'react'
import * as VoiceService from '../services/voiceService'

export type VoiceState = 'idle' | 'listening' | 'processing' | 'speaking' | 'fraud'

const FRAUD_NARRATIONS: Record<string, string> = {
  fan_out_detected: 'Fan-out fraud detected. Funds are rapidly dispersing across multiple recipient accounts.',
  layering:         'Transaction layering identified. Chain shows deliberate obfuscation behavior.',
  cycling:          'Circular loop detected. Funds cycling through a closed network of connected accounts.',
  smurfing:         'Structuring pattern flagged. Multiple transactions clustered near reporting thresholds.',
  high_velocity:    'Anomalous velocity detected. Transaction frequency exceeds expected behavioral bounds.',
  ML_ensemble:      'Ensemble model consensus: cluster behavior deviates significantly from baseline.',
  cycle_detected:   'Closed transaction cycle identified. Potential circular flow of funds.',
}

export function useVoiceAssistant() {
  const [voiceState, setVoiceState] = useState<VoiceState>('idle')

  useEffect(() => {
    const unsub1 = VoiceService.onSpeakStart(() => setVoiceState('speaking'))
    const unsub2 = VoiceService.onSpeakEnd(() =>
      setVoiceState(s => (s === 'speaking' || s === 'processing' ? 'idle' : s)),
    )
    return () => { unsub1(); unsub2() }
  }, [])

  const speak = useCallback((text: string, onEnd?: () => void) => {
    if (!text) return
    setVoiceState('processing')
    VoiceService.speak(text, undefined, onEnd)
  }, [])

  const stop = useCallback(() => {
    VoiceService.stopSpeaking()
    setVoiceState('idle')
  }, [])

  const narrateFraud = useCallback((score: number, reason?: string | null, graphCount = 1) => {
    setVoiceState('fraud')
    const template = reason
      ? (FRAUD_NARRATIONS[reason] ?? `${reason.replace(/_/g, ' ')}.`)
      : 'Suspicious transaction pattern identified.'
    const lines = [
      'Alert.',
      template,
      `Confidence score: ${Math.round(score * 100)} percent.`,
      graphCount > 1
        ? `${graphCount} separate clusters have been flagged for review.`
        : 'Initiating deep cluster analysis.',
    ]
    setTimeout(() => speak(lines.join(' ')), 600)
  }, [speak])

  const narrateClean = useCallback(() => {
    speak('Analysis complete. No suspicious activity detected. Network behavior within normal parameters.')
  }, [speak])

  const greet = useCallback(() => {
    speak('Transaction Graph Intelligence Engine online. Monitoring financial network for anomalies.')
  }, [speak])

  return { voiceState, speak, stop, narrateFraud, narrateClean, greet }
}
