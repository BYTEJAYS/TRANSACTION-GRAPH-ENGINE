// ── Recovery redesign · shared primitives ────────────────────────────────────
// Quiet, enterprise building blocks on an 8px spacing grid. Deliberately calm:
// no glow, no gradient fills, no animated backgrounds, no glassmorphism. Colour
// is reserved for meaning (recovery band · status · money), never decoration.
import { motion } from 'framer-motion'
import type { CSSProperties, ReactNode } from 'react'
import { T, cream } from '../../theme'

// One soft, restrained elevation — a hint of depth, never a halo.
export const SOFT_SHADOW = '0 1px 2px rgba(0,0,0,0.40), 0 16px 40px -28px rgba(0,0,0,0.85)'

// ── Cream accent ──────────────────────────────────────────────────────────────
// The recovery surfaces use a soft cream/ivory as their brand + primary-action
// accent instead of gold. Derived from the app's existing cream palette (the
// auth panels) so it stays consistent: warm, understated, premium on matte black.
export const A = {
  base: cream.panel,                // #d9d3c2  soft ivory — brand / primary accent
  hi:   cream.input,                // #e7e2d3  brighter ivory — hover
  dim:  'rgba(217,211,194,0.12)',   // flat tint background
  line: 'rgba(217,211,194,0.30)',   // tint border
  on:   T.textOn,                   // near-black text on a cream button
} as const

const EASE: [number, number, number, number] = [0.16, 1, 0.3, 1]

// A single calm surface. The page uses very few of these on purpose — most
// content sits directly on the canvas, separated by whitespace, not boxes.
export function Card({ children, style, pad = 24 }: { children: ReactNode; style?: CSSProperties; pad?: number }) {
  return (
    <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 16, padding: pad, boxShadow: SOFT_SHADOW, ...style }}>
      {children}
    </div>
  )
}

// Tiny uppercase label that introduces a value or a region.
export function Eyebrow({ children, color = T.text3, style }: { children: ReactNode; color?: string; style?: CSSProperties }) {
  return <div style={{ fontSize: 10.5, letterSpacing: '0.14em', textTransform: 'uppercase', fontWeight: 600, color, ...style }}>{children}</div>
}

// A page section: heading + optional one-line hint + optional right-aligned
// control. Generous top margin sets the vertical rhythm; one subtle fade on view.
export function Section({ title, hint, action, children, first }: {
  title: string; hint?: string; action?: ReactNode; children: ReactNode; first?: boolean
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-80px' }} transition={{ duration: 0.5, ease: EASE }}
      style={{ marginTop: first ? 0 : 56 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 16, marginBottom: 22 }}>
        <div style={{ minWidth: 0 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600, color: T.text, margin: 0, letterSpacing: '-0.01em' }}>{title}</h2>
          {hint && <p style={{ fontSize: 12.5, color: T.text2, margin: '6px 0 0', maxWidth: 600, lineHeight: 1.55 }}>{hint}</p>}
        </div>
        {action && <div style={{ flexShrink: 0 }}>{action}</div>}
      </div>
      {children}
    </motion.section>
  )
}

// Status / band chip. Always pairs a colour with a text label so status is never
// communicated by colour alone (accessibility).
export function StatusPill({ label, color, strong }: { label: string; color: string; strong?: boolean }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 7, padding: '4px 11px 4px 9px', borderRadius: 8,
      background: strong ? hexA(color, 0.12) : T.raised, border: `1px solid ${strong ? hexA(color, 0.4) : T.border}`,
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: color }} />
      <span style={{ fontSize: 11.5, fontWeight: 600, color: strong ? color : T.text2 }}>{label}</span>
    </span>
  )
}

// A single key figure — quiet uppercase label over a tabular value.
export function Metric({ label, value, sub, color = T.text }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: 10.5, letterSpacing: '0.08em', textTransform: 'uppercase', color: T.text3, marginBottom: 11 }}>{label}</div>
      <div style={{ fontSize: 21, fontWeight: 600, color, fontFamily: T.mono, fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: T.text3, marginTop: 7 }}>{sub}</div>}
    </div>
  )
}

// Thin progress / share bar. `value` is 0..100.
export function Bar({ value, color, height = 8, track = T.raised, delay = 0 }: {
  value: number; color: string; height?: number; track?: string; delay?: number
}) {
  return (
    <div style={{ height, background: track, borderRadius: height / 2, overflow: 'hidden' }}>
      <motion.div
        initial={{ width: 0 }} whileInView={{ width: `${Math.max(0, Math.min(100, value))}%` }}
        viewport={{ once: true }} transition={{ duration: 0.8, delay, ease: EASE }}
        style={{ height: '100%', background: color, borderRadius: height / 2 }} />
    </div>
  )
}

// Quiet empty-state line for sections with no data — keeps the engine honest
// (it never invents figures) without leaving a blank hole.
export function Empty({ children }: { children: ReactNode }) {
  return <div style={{ fontSize: 12.5, color: T.text3, padding: '8px 0', lineHeight: 1.6 }}>{children}</div>
}

// hex + alpha → rgba tint. Keeps every tint flat and consistent (no gradients).
// Falls back to the input for rgba()/named colours.
export function hexA(hex: string, a: number): string {
  if (!hex.startsWith('#') || hex.length !== 7) return hex
  const r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${a})`
}
