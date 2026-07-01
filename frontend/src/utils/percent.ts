/**
 * percent.ts — the SINGLE source of percentage formatting for the whole UI.
 *
 * WHY THIS EXISTS
 * ---------------
 * Union Bank investigators prioritise cases by these numbers, so a fabricated or
 * out-of-range percentage destroys trust. This module enforces three rules that
 * the rest of the app must never bypass:
 *
 *   1. The frontend NEVER computes a risk/confidence/recovery percentage. It only
 *      formats a value the backend already computed. (If you find yourself doing
 *      arithmetic to derive a risk %, it belongs in the backend.)
 *   2. A missing / non-finite / out-of-contract value renders as "N/A" — never a
 *      guessed 0% and never a clamped 100%. We surface the absence honestly
 *      instead of inventing a number.
 *   3. A valid value is shown exactly as the backend computed it (rounded for
 *      display only). We do NOT clamp a real in-range value.
 *
 * Two input contracts exist in the backend, so there are two formatters:
 *   - fraction  ∈ [0,1]   → use pctFraction()   (e.g. risk_score, confidence 0–1)
 *   - points    ∈ [0,100] → use pctValue()      (e.g. risk_confidence, risk_points)
 */

export const NA = 'N/A'

/** True only for a real, finite number we can display. */
function finite(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

/**
 * Format a backend 0–1 FRACTION as a percentage string.
 * Returns "N/A" for null/undefined/NaN, or for any value outside the [0,1]
 * contract (an out-of-range value is a backend bug, not something we mask with a
 * clamp — we refuse to display a fabricated number).
 */
export function pctFraction(v: number | null | undefined, digits = 0): string {
  if (!finite(v)) return NA
  if (v < -1e-9 || v > 1 + 1e-9) return NA   // out of contract → honest N/A, never >100%
  return `${(v * 100).toFixed(digits)}%`
}

/**
 * Format a backend 0–100 POINTS value as a percentage string.
 * Same N/A discipline; rejects values outside [0,100].
 */
export function pctValue(v: number | null | undefined, digits = 0): string {
  if (!finite(v)) return NA
  if (v < -1e-9 || v > 100 + 1e-9) return NA
  return `${v.toFixed(digits)}%`
}

/**
 * Risk percentage for a backend graph-component verdict. Honours the explicit
 * `risk_available` flag: when the Risk Engine could not score the component the
 * investigator sees "N/A", not a misleading 0%.
 */
export function riskPct(
  g: { risk_score?: number | null; risk_available?: boolean } | null | undefined,
  digits = 0,
): string {
  if (!g) return NA
  if (g.risk_available === false) return NA
  return pctFraction(g.risk_score, digits)
}

/** Numeric risk fraction for arithmetic (sorting/colour), missing → 0 (never shown). */
export function riskValue(
  g: { risk_score?: number | null; risk_available?: boolean } | null | undefined,
): number {
  if (!g || g.risk_available === false || !finite(g.risk_score)) return 0
  return g.risk_score as number
}
