// Browser-native SpeechSynthesis voice service
// Singleton — one utterance at a time across the entire app.
// Zero external dependencies, zero API keys, zero latency.
//
// PRODUCTION ROOT CAUSE THIS FILE ADDRESSES
// ─────────────────────────────────────────
// On localhost Chrome applies a lenient autoplay policy, so speech triggered
// from timers / WebSocket callbacks is audible. On a fresh production (Vercel,
// HTTPS) visit the page has zero media-engagement, so the browser blocks audio
// output until a genuine user gesture — utterances fire onstart/onend with NO
// sound ("events fire but nothing is heard"), and the synthesis engine can wedge
// if the first attempt was non-gestured. The fix here:
//   1. A sticky one-time UNLOCK primed on the first real user gesture
//      (warm-up utterance + synthesis.resume()) — see installSpeechUnlock().
//   2. speak() DEFERS any request made before unlock and flushes it afterward,
//      so pre-gesture narration is never attempted silently (and never lost).
//   3. Local voices are preferred over remote (Google/Microsoft Online) voices,
//      which fail silently in production.
//   4. Staged [VOICE] logging + diagnostics for the dev test panel.

type Listener    = () => void
type ErrListener = (message: string) => void

let activeUtterance: SpeechSynthesisUtterance | null = null
let chromePingInterval: ReturnType<typeof setInterval> | null = null
let _speaking = false

const startCbs = new Set<Listener>()
const endCbs   = new Set<Listener>()
const errCbs   = new Set<ErrListener>()

// ── Logging ─────────────────────────────────────────────────────────────────
type VoiceEvent =
  | 'init' | 'voices-loaded' | 'voice-selected' | 'queued' | 'deferred'
  | 'unlocked' | 'started' | 'ended' | 'error' | 'unsupported'
let lastEvent: VoiceEvent = 'init'
let lastErrorMessage: string | null = null

function vlog(msg: string, ...rest: unknown[]): void {
  // Single, greppable channel for the whole speech pipeline.
  console.log(`[VOICE] ${msg}`, ...rest)
}

// ── Support detection ─────────────────────────────────────────────────────────
export function isSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    'speechSynthesis' in window &&
    typeof window.SpeechSynthesisUtterance !== 'undefined'
  )
}

// ── Voice selection ─────────────────────────────────────────────────────────
// The SpeechSynthesis voice list loads asynchronously. We resolve it once, pick
// the best available English voice, and cache it.
//
// IMPORTANT: local voices are preferred over remote/network voices. Remote
// voices ("Google US English", "Microsoft … Online (Natural)") route through a
// server and are a well-known source of SILENT failures in production — they
// fire onstart/onend but emit no audio on a fresh page. Local voices (Samantha,
// Microsoft David, Alex …) are reliable, so they win.
const LOCAL_PREFERENCES = [
  'Samantha',
  'Alex',
  'Daniel',
  'Microsoft David Desktop - English (United States)',
  'Microsoft David',
  'Microsoft Zira Desktop - English (United States)',
  'Microsoft Mark',
]
const REMOTE_PREFERENCES = [
  'Google US English',
  'Microsoft Aria Online (Natural) - English (United States)',
  'Microsoft Guy Online (Natural) - English (United States)',
  'Google UK English Male',
]

let selectedVoice: SpeechSynthesisVoice | null = null
let voicesReady = false
let lastVoiceCount = 0

function matchByName(voices: SpeechSynthesisVoice[], names: string[]): SpeechSynthesisVoice | null {
  for (const n of names) {
    const exact = voices.find(v => v.name === n)
    if (exact) return exact
  }
  for (const n of names) {
    const loose = voices.find(v => v.name.toLowerCase().includes(n.toLowerCase()))
    if (loose) return loose
  }
  return null
}

function pickBestVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  if (!voices.length) return null
  // 1) Named LOCAL preference (most reliable audio).
  const namedLocal = matchByName(voices.filter(v => v.localService), LOCAL_PREFERENCES)
  if (namedLocal) return namedLocal
  // 2) Any local en-US, then any local English.
  const localEnUs = voices.find(v => v.localService && v.lang === 'en-US')
  if (localEnUs) return localEnUs
  const localEn = voices.find(v => v.localService && v.lang?.startsWith('en'))
  if (localEn) return localEn
  // 3) Named REMOTE preference (works, just less reliable on first paint).
  const namedRemote = matchByName(voices, REMOTE_PREFERENCES)
  if (namedRemote) return namedRemote
  // 4) Any en-US, any English, platform default, then anything.
  return voices.find(v => v.lang === 'en-US')
      ?? voices.find(v => v.lang?.startsWith('en'))
      ?? voices.find(v => v.default)
      ?? voices[0]
}

function refreshVoices(): void {
  if (!isSupported()) return
  const voices = window.speechSynthesis.getVoices()
  lastVoiceCount = voices.length
  if (!voices.length) {
    vlog('getVoices() returned 0 — waiting for voiceschanged…')
    return
  }
  voicesReady = true
  lastEvent = 'voices-loaded'
  vlog(`Voices loaded: ${voices.length}`)
  const picked = pickBestVoice(voices)
  if (picked && picked !== selectedVoice) {
    selectedVoice = picked
    lastEvent = 'voice-selected'
    vlog(`Selected voice: ${picked.name} (${picked.lang}) local=${picked.localService}`)
  }
}

if (isSupported()) {
  vlog('Browser supports speech synthesis')
  refreshVoices()
  // Chrome/Edge fire this once the async list is populated.
  window.speechSynthesis.addEventListener?.('voiceschanged', refreshVoices)
  // Some browsers populate lazily even without the event — poll a few times.
  let tries = 0
  const poll = setInterval(() => {
    tries += 1
    if (voicesReady || tries > 20) { clearInterval(poll); return }
    refreshVoices()
  }, 250)
} else if (typeof window !== 'undefined') {
  lastEvent = 'unsupported'
  vlog('SpeechSynthesis NOT supported in this browser')
}

export function getSelectedVoice(): SpeechSynthesisVoice | null { return selectedVoice }
export function voicesAreReady(): boolean { return voicesReady }

// ── User-activation unlock (the production fix) ───────────────────────────────
let unlocked = false
let pendingSpeak: { text: string; onStart?: () => void; onEnd?: () => void } | null = null

export function isUnlocked(): boolean { return unlocked }

/**
 * Warm the synthesis engine inside a real user gesture so subsequent speech —
 * including narration fired from timers / WebSocket callbacks — produces audio
 * in production. Idempotent.
 */
export function unlockSpeech(): void {
  if (unlocked || !isSupported()) return
  try {
    // Clear any wedged/paused state and warm the pipeline with a silent utterance.
    window.speechSynthesis.cancel()
    window.speechSynthesis.resume()
    const warm = new SpeechSynthesisUtterance(' ')
    warm.volume = 0
    warm.rate = 1
    if (selectedVoice) { warm.voice = selectedVoice; warm.lang = selectedVoice.lang }
    window.speechSynthesis.speak(warm)
    unlocked = true
    lastEvent = 'unlocked'
    vlog('Speech unlocked by user gesture (engine warmed)')
    // Ensure the voice list is resolved now that we are interactive.
    if (!voicesReady) refreshVoices()
    // Flush anything that was requested before the gesture.
    if (pendingSpeak) {
      const p = pendingSpeak
      pendingSpeak = null
      vlog('Flushing deferred utterance')
      speak(p.text, p.onStart, p.onEnd)
    }
  } catch (e) {
    vlog('unlockSpeech failed', e)
  }
}

/**
 * Register global, capture-phase listeners that unlock speech on the first real
 * user interaction. Runs in capture phase so it fires on the SAME gesture that
 * also triggers UI handlers (e.g. clicking the orb), warming the engine before
 * that handler's speak() runs. Returns a cleanup function.
 */
export function installSpeechUnlock(): () => void {
  if (typeof window === 'undefined') return () => {}
  if (unlocked) return () => {}
  const handler = () => unlockSpeech()
  const opts: AddEventListenerOptions = { capture: true, passive: true }
  const events: (keyof WindowEventMap)[] = ['pointerdown', 'mousedown', 'touchstart', 'keydown', 'click']
  events.forEach(ev => window.addEventListener(ev, handler, opts))
  vlog('Speech unlock armed — waiting for first user gesture')
  return () => events.forEach(ev => window.removeEventListener(ev, handler, opts))
}

// ── Speech rate (global, user-adjustable via "speak slower / faster") ────────
const RATE_MIN = 0.6
const RATE_MAX = 1.25
let speechRate = 0.96   // default — slightly measured, intelligence-system cadence

export function getRate(): number { return speechRate }
export function setRate(rate: number): number {
  speechRate = Math.min(RATE_MAX, Math.max(RATE_MIN, rate))
  return speechRate
}
/** Step the rate down (slower). Returns a human label for narration. */
export function slowDown(): string {
  setRate(speechRate - 0.15)
  return speechRate <= RATE_MIN + 0.01 ? 'minimum' : 'slower'
}
/** Step the rate up (faster). */
export function speedUp(): string {
  setRate(speechRate + 0.15)
  return speechRate >= RATE_MAX - 0.01 ? 'maximum' : 'faster'
}

// ── Last-utterance memory (for "repeat that") ────────────────────────────────
let lastSpokenText = ''
export function getLastSpoken(): string { return lastSpokenText }

// ── Diagnostics (for the dev test panel) ──────────────────────────────────────
export interface VoiceDiagnostics {
  supported: boolean
  voicesLoaded: number
  voicesReady: boolean
  selectedVoice: string | null
  selectedVoiceLocal: boolean | null
  unlocked: boolean
  speaking: boolean
  queued: boolean
  rate: number
  lastEvent: VoiceEvent
  lastError: string | null
}
export function getDiagnostics(): VoiceDiagnostics {
  return {
    supported: isSupported(),
    voicesLoaded: lastVoiceCount,
    voicesReady,
    selectedVoice: selectedVoice?.name ?? null,
    selectedVoiceLocal: selectedVoice ? selectedVoice.localService : null,
    unlocked,
    speaking: _speaking,
    queued: typeof window !== 'undefined' && !!window.speechSynthesis?.pending,
    rate: speechRate,
    lastEvent,
    lastError: lastErrorMessage,
  }
}

// ── Event subscriptions ───────────────────────────────────────────────────────
export function onSpeakStart(fn: Listener):    () => void { startCbs.add(fn); return () => startCbs.delete(fn) }
export function onSpeakEnd(fn: Listener):      () => void { endCbs.add(fn);   return () => endCbs.delete(fn) }
export function onSpeakError(fn: ErrListener): () => void { errCbs.add(fn);   return () => errCbs.delete(fn) }
export function isSpeaking(): boolean { return _speaking }

function emitStart() { _speaking = true;  startCbs.forEach(f => f()) }
function emitEnd()   { _speaking = false; endCbs.forEach(f => f()) }
function emitError(msg: string) { lastErrorMessage = msg; errCbs.forEach(f => f(msg)) }

function clearChromePing() {
  if (chromePingInterval !== null) {
    clearInterval(chromePingInterval)
    chromePingInterval = null
  }
}

// ── Control API ───────────────────────────────────────────────────────────────
export function stopSpeaking(): void {
  if (!isSupported()) return
  clearChromePing()
  const wasSpeaking = _speaking
  activeUtterance = null
  window.speechSynthesis.cancel()
  if (wasSpeaking) emitEnd()
}

export function pauseSpeaking(): void {
  window.speechSynthesis?.pause()
}

export function resumeSpeaking(): void {
  window.speechSynthesis?.resume()
}

// Aliases matching the broader service API contract
export const stopSpeech   = stopSpeaking
export const pauseSpeech  = pauseSpeaking
export const resumeSpeech = resumeSpeaking
export const cleanupAudio = stopSpeaking

// No-op — browser synth requires no API keys or preloading
export function preloadVoice(): void {}

// ── Core speak() ──────────────────────────────────────────────────────────────
export function speak(
  text: string,
  onStart?: () => void,
  onEnd?: () => void,
): Promise<void> {
  if (!text.trim()) { onEnd?.(); return Promise.resolve() }

  if (!isSupported()) {
    lastEvent = 'unsupported'
    emitError('SpeechSynthesis not supported in this browser.')
    vlog('speak() aborted — unsupported')
    onEnd?.()
    return Promise.resolve()
  }

  // Defer-until-gesture: if the engine has not been unlocked by a user gesture,
  // do NOT attempt speech (it would fire silently in production and can wedge
  // the engine). Hold the latest request; installSpeechUnlock() flushes it.
  if (!unlocked) {
    pendingSpeak = { text, onStart, onEnd }
    lastEvent = 'deferred'
    vlog('Speech deferred until first user gesture:', text.slice(0, 48))
    return Promise.resolve()
  }

  // Cancel any currently active speech before starting the new utterance.
  stopSpeaking()
  // Defensive: clear any paused/wedged state Chrome may have left behind.
  window.speechSynthesis.resume()

  lastSpokenText = text

  // The voice list may not have populated on the very first call — retry now.
  if (!selectedVoice) refreshVoices()

  return new Promise<void>(resolve => {
    const utterance = new SpeechSynthesisUtterance(text)
    if (selectedVoice) {
      utterance.voice = selectedVoice
      utterance.lang  = selectedVoice.lang
    }
    utterance.rate   = speechRate
    utterance.pitch  = 0.92
    utterance.volume = 0.95

    activeUtterance = utterance
    lastEvent = 'queued'
    vlog(`Speech queued (${text.length} chars) voice=${selectedVoice?.name ?? 'default'}`)

    const done = (isError = false, errorMsg?: string) => {
      clearChromePing()
      if (activeUtterance === utterance) activeUtterance = null
      if (_speaking) emitEnd()
      if (isError && errorMsg) emitError(errorMsg)
      onEnd?.()
      resolve()
    }

    utterance.onstart = () => {
      lastEvent = 'started'
      vlog('Speech started')
      emitStart()
      onStart?.()
    }

    utterance.onend = () => {
      lastEvent = 'ended'
      vlog('Speech ended')
      done()
    }

    utterance.onerror = (e: SpeechSynthesisErrorEvent) => {
      // 'interrupted' and 'canceled' are normal — speech was stopped programmatically
      if (e.error === 'interrupted' || e.error === 'canceled') {
        if (activeUtterance === utterance) activeUtterance = null
        resolve()
        return
      }
      lastEvent = 'error'
      vlog('Speech ERROR:', e.error)
      done(true, `Speech synthesis error: ${e.error}`)
    }

    // Chrome-specific bug: the browser silently pauses speech synthesis when a
    // tab loses focus, or after ~14s of continuous speech. Kicking pause/resume
    // on an interval keeps the audio pipeline alive for the full utterance.
    const isChrome =
      typeof navigator !== 'undefined' &&
      /Chrome/.test(navigator.userAgent) &&
      !/Edg\//.test(navigator.userAgent)

    if (isChrome) {
      chromePingInterval = setInterval(() => {
        if (!window.speechSynthesis.speaking) {
          clearChromePing()
          return
        }
        window.speechSynthesis.pause()
        window.speechSynthesis.resume()
      }, 14_000)
    }

    window.speechSynthesis.speak(utterance)
  })
}

export const startSpeech = speak

/** Re-speak the last narration verbatim ("repeat that"). */
export function repeatLast(onStart?: () => void, onEnd?: () => void): Promise<void> {
  if (!lastSpokenText) { onEnd?.(); return Promise.resolve() }
  return speak(lastSpokenText, onStart, onEnd)
}

// ── Dev helper ────────────────────────────────────────────────────────────────
if (typeof window !== 'undefined') {
  (window as any).__ttsTest = (
    text = 'Transaction Graph Intelligence Engine online. Monitoring financial network for anomalies.',
  ) => {
    unlockSpeech() // allow manual console testing without a page gesture
    return speak(text).catch(console.error)
  }
  ;(window as any).__voiceDiag = () => getDiagnostics()
  vlog('Browser SpeechSynthesis active — test with: window.__ttsTest()  ·  diag: window.__voiceDiag()')
}
