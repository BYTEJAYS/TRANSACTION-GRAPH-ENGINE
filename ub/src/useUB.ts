// ──────────────────────────────────────────────────────────────────────────────
// useUB — wake-word listener and intent dispatcher for UB.
//
// Voice pipeline: Browser-native SpeechSynthesis via voiceService.
// Speech recognition: Web Speech API (Chrome/Edge/Brave).
// ──────────────────────────────────────────────────────────────────────────────
import { useCallback, useEffect, useRef, useState } from 'react'
import type { VoiceState } from './useVoiceAssistant'
import { UB, matchIntent, stripWake, containsWake, type IntentId } from '../ai/ub'
import * as VoiceService from '../services/voiceService'

// ── Minimal Web Speech API typings ───────────────────────────────────────────
interface SRResult { 0: { transcript: string }; isFinal: boolean }
interface SREvent  { resultIndex: number; results: ArrayLike<SRResult> }
interface SR {
  continuous: boolean; interimResults: boolean; lang: string
  onresult: ((e: SREvent) => void) | null
  onend:    (() => void) | null
  onerror:  ((e: { error: string }) => void) | null
  onstart:  (() => void) | null
  start(): void; stop(): void; abort(): void
}
type SRCtor = new () => SR
function getSpeechRecognition(): SRCtor | null {
  const w = window as unknown as { SpeechRecognition?: SRCtor; webkitSpeechRecognition?: SRCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export type UBHandlers = Partial<Record<IntentId, (transcript: string) => void>>

interface Options {
  handlers:    UBHandlers
  onUnknown?:  (transcript: string) => void
  /** Fires when a FRESH wake ("UB") is detected — not on auto re-arm after UB speaks. */
  onWake?:     () => void
  muted?:      boolean
}

// ── Main hook ──────────────────────────────────────────────────────────────────
export function useUB({ handlers, onUnknown, onWake, muted = false }: Options) {
  const [voiceState,  setVoiceState]  = useState<VoiceState>('idle')
  const [wakeEnabled, setWakeEnabled] = useState(false)
  const [transcript,  setTranscript]  = useState('')
  const [supported,   setSupported]   = useState(true)
  const [armedForCmd, setArmedForCmd] = useState(false)
  const [lastError,   setLastError]   = useState<string | null>(null)

  const srRef          = useRef<SR | null>(null)
  const mutedRef       = useRef(muted)
  const handlersRef    = useRef(handlers)
  const onUnknownRef   = useRef(onUnknown)
  const onWakeRef      = useRef(onWake)
  const armedRef       = useRef(false)
  // True from wake until the command is processed (or silence times out). Keeps
  // the recognizer re-arming after the "Listening" ack so the assistant does
  // NOT shut down right after the wake word — it waits for the actual command.
  const keepListeningRef = useRef(false)
  const armTimerRef    = useRef<ReturnType<typeof setTimeout> | null>(null)
  const wakeEnabledRef = useRef(false)
  const speakingRef    = useRef(false)

  useEffect(() => { mutedRef.current     = muted },     [muted])
  useEffect(() => { handlersRef.current  = handlers },  [handlers])
  useEffect(() => { onUnknownRef.current = onUnknown }, [onUnknown])
  useEffect(() => { onWakeRef.current     = onWake },   [onWake])
  useEffect(() => { wakeEnabledRef.current = wakeEnabled }, [wakeEnabled])
  useEffect(() => { armedRef.current     = armedForCmd }, [armedForCmd])

  // ── Core speak ───────────────────────────────────────────────────────────────
  const speak = useCallback((text: string, onEnd?: () => void) => {
    console.log('[useUB] speak() called, muted=', mutedRef.current, 'text=', text.slice(0, 40))
    if (!text.trim()) { onEnd?.(); return }
    if (mutedRef.current) { console.warn('[useUB] muted — skipping'); onEnd?.(); return }

    // Stop any in-flight speech first
    VoiceService.stopSpeaking()

    // Pause SR while UB speaks
    speakingRef.current = true
    try { srRef.current?.stop() } catch { /* noop */ }

    setVoiceState('processing')

    VoiceService.speak(
      text,
      () => { setVoiceState('speaking') },
      () => {
        speakingRef.current = false

        // After UB finishes speaking, resume ACTIVE_LISTENING for the command
        // whenever we're mid-session (keepListening) or continuous wake is on.
        // This is what stops the "wake → greet → dead" behavior.
        if (wakeEnabledRef.current || keepListeningRef.current) {
          armedRef.current = true
          setArmedForCmd(true)
          setVoiceState('listening')
          try { srRef.current?.start() } catch { /* already running */ }
          if (armTimerRef.current) clearTimeout(armTimerRef.current)
          armTimerRef.current = setTimeout(() => {
            armedRef.current = false
            keepListeningRef.current = false
            setArmedForCmd(false)
            setVoiceState(v => (v === 'listening' ? 'idle' : v))
          }, 10000)
        } else {
          setVoiceState('idle')
        }

        onEnd?.()
      },
    )
  }, [])

  const stop = useCallback(() => {
    VoiceService.stopSpeaking()
    speakingRef.current = false
    setVoiceState(v => (v === 'speaking' || v === 'processing' ? 'idle' : v))
  }, [])

  // ── Intent dispatch ──────────────────────────────────────────────────────────
  const handleUtterance = useCallback((raw: string) => {
    const text = stripWake(raw).trim()
    if (!text) return
    // A real command ends the active session — after responding we return to
    // passive wake-word listening rather than looping the command window.
    keepListeningRef.current = false
    setVoiceState('processing')
    setTranscript(text)
    const id = matchIntent(text)
    const h  = id ? handlersRef.current[id] : undefined
    window.setTimeout(() => {
      if (h) h(text)
      else onUnknownRef.current?.(text)
      setVoiceState(v => (v === 'processing' ? 'idle' : v))
    }, 180)
  }, [])

  // ── SpeechRecognition session ────────────────────────────────────────────────
  const ensureRecognizer = useCallback((): SR | null => {
    if (srRef.current) return srRef.current
    const Ctor = getSpeechRecognition()
    if (!Ctor) { setSupported(false); return null }
    const sr = new Ctor()
    sr.continuous     = true
    sr.interimResults = true
    sr.lang           = 'en-US'

    sr.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res  = e.results[i]
        const text = (res[0].transcript ?? '').trim()
        if (!text) continue

        if (!res.isFinal) {
          if (!armedRef.current && containsWake(text)) {
            armedRef.current = true
            keepListeningRef.current = true
            setArmedForCmd(true)
            setVoiceState('listening')
            onWakeRef.current?.()
            if (armTimerRef.current) clearTimeout(armTimerRef.current)
            armTimerRef.current = setTimeout(() => {
              armedRef.current = false
              keepListeningRef.current = false
              setArmedForCmd(false)
              setVoiceState(v => (v === 'listening' ? 'idle' : v))
            }, 10000)
          }
          continue
        }

        if (armedRef.current) {
          armedRef.current = false
          setArmedForCmd(false)
          if (armTimerRef.current) { clearTimeout(armTimerRef.current); armTimerRef.current = null }
          handleUtterance(text)
        } else if (containsWake(text)) {
          const after = stripWake(text)
          if (after && matchIntent(after)) {
            handleUtterance(text)
          } else {
            armedRef.current = true
            keepListeningRef.current = true
            setArmedForCmd(true)
            setVoiceState('listening')
            onWakeRef.current?.()
            if (armTimerRef.current) clearTimeout(armTimerRef.current)
            armTimerRef.current = setTimeout(() => {
              armedRef.current = false
              keepListeningRef.current = false
              setArmedForCmd(false)
              setVoiceState(v => (v === 'listening' ? 'idle' : v))
            }, 10000)
          }
        }
      }
    }

    sr.onend = () => {
      console.log('[UB] SR onend — speaking=', speakingRef.current, 'wakeEnabled=', wakeEnabledRef.current)
      if (speakingRef.current) return
      if (wakeEnabledRef.current) {
        try { sr.start() } catch { /* already running */ }
      } else {
        setVoiceState(v => (v === 'listening' ? 'idle' : v))
      }
    }

    sr.onerror = (e) => {
      console.warn(`[UB] sr.onerror: ${e.error}`)
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        // Permission not granted yet — keep `supported` true so a later gesture can
        // still recover; drop wake state and surface a hint.
        setWakeEnabled(false); wakeEnabledRef.current = false
        setLastError('Microphone permission needed — allow it for this site (address-bar lock), then click the page.')
      } else if (e.error === 'audio-capture') {
        setWakeEnabled(false); wakeEnabledRef.current = false
        setLastError('No microphone available — check it is connected and allowed for your browser (macOS: System Settings → Privacy & Security → Microphone).')
      } else if (e.error === 'network') {
        setLastError('Speech recognition network error. Check your connection.')
      }
    }

    sr.onstart = () => { console.log('[UB] SR onstart — listening'); setLastError(null) }

    srRef.current = sr
    return sr
  }, [handleUtterance])

  const ensureMicPermission = useCallback(async (): Promise<'granted' | 'denied'> => {
    try {
      const perms = (navigator as any).permissions
      if (perms?.query) {
        const status = await perms.query({ name: 'microphone' })
        if (status.state === 'granted') return 'granted'
      }
    } catch { /* ignore */ }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      stream.getTracks().forEach(t => t.stop())
      return 'granted'
    } catch {
      return 'denied'
    }
  }, [])

  const enableWake = useCallback(async () => {
    console.log('[UB] enableWake() called')
    // getUserMedia is only a best-effort permission probe/nudge. SpeechRecognition
    // manages its OWN microphone, so we ALWAYS start it regardless of the probe —
    // some setups return NotFoundError from getUserMedia yet SR still captures audio.
    // If SR genuinely can't get the mic it fires sr.onerror ('audio-capture' /
    // 'not-allowed'), which surfaces a precise hint. (Gating on getUserMedia here is
    // what made a flaky/absent getUserMedia silently block the wake word.)
    const status = await ensureMicPermission().catch(() => 'denied' as const)
    console.log('[UB] mic probe:', status)
    const sr = ensureRecognizer()
    if (!sr) { setLastError('Speech recognition needs Chrome, Edge, or Brave.'); return }
    setLastError(null)
    setWakeEnabled(true); wakeEnabledRef.current = true
    try { sr.start() } catch { /* already running */ }
  }, [ensureRecognizer, ensureMicPermission])

  const disableWake = useCallback(() => {
    setWakeEnabled(false); wakeEnabledRef.current = false
    armedRef.current = false; setArmedForCmd(false)
    try { srRef.current?.stop() } catch { /* not running */ }
  }, [])

  const armOnce = useCallback(() => {
    // Instant feedback ALWAYS — chime + greeting + panel open fire immediately,
    // before (and independent of) microphone availability. A click never does
    // "nothing": even if speech recognition is unsupported or denied, UB still
    // wakes, opens, and speaks. Listening is best-effort on top of that.
    onWakeRef.current?.()
    const sr = ensureRecognizer()
    if (!sr) { setSupported(false); return }
    armedRef.current = true; keepListeningRef.current = true
    setArmedForCmd(true); setVoiceState('listening')
    try { sr.start() } catch { /* already running */ }
    if (armTimerRef.current) clearTimeout(armTimerRef.current)
    armTimerRef.current = setTimeout(() => {
      armedRef.current = false; keepListeningRef.current = false; setArmedForCmd(false)
      setVoiceState(v => (v === 'listening' ? 'idle' : v))
    }, 6000)
  }, [ensureRecognizer])

  const runCommand = useCallback((text: string) => {
    handleUtterance(text)
  }, [handleUtterance])

  // DevTools test helpers
  useEffect(() => {
    (window as any).__ubSpeak = (t: string) => speak(t)
    ;(window as any).__ubTest  = (t: string) => speak(t)
    return () => {
      delete (window as any).__ubSpeak
      delete (window as any).__ubTest
    }
  }, [speak])

  // Cleanup on unmount
  useEffect(() => () => {
    if (armTimerRef.current) clearTimeout(armTimerRef.current)
    try { srRef.current?.abort() } catch { /* noop */ }
    VoiceService.stopSpeaking()
  }, [])

  // React to browser permission flips
  useEffect(() => {
    if (!navigator.permissions?.query) return
    let cancelled = false
    let status: PermissionStatus | null = null
    let handler: (() => void) | null = null
    navigator.permissions.query({ name: 'microphone' as PermissionName }).then(s => {
      if (cancelled) return
      status = s
      handler = () => {
        if (s.state === 'granted' && !wakeEnabledRef.current) enableWake()
        else if (s.state === 'denied') {
          setWakeEnabled(false); wakeEnabledRef.current = false
          setLastError('Microphone blocked — enable it from the address-bar lock icon.')
        }
      }
      s.addEventListener('change', handler)
    }).catch(() => { /* ignore */ })
    return () => {
      cancelled = true
      if (status && handler) status.removeEventListener('change', handler)
    }
  }, [enableWake])

  const setFraudMode = useCallback((on: boolean) => {
    setVoiceState(v => (on ? 'fraud' : (v === 'fraud' ? 'idle' : v)))
  }, [])

  return {
    voiceState, wakeEnabled, armedForCmd, supported, transcript, lastError,
    speak, stop, enableWake, disableWake, armOnce, runCommand, setFraudMode,
  }
}
