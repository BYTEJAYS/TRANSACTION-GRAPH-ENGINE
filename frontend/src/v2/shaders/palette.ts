// Cinematic palette — shared across shaders + UI.
// Keep hex values in sync with mockGraph.ts nodeColorFromRisk() so v1 and v2
// stay visually consistent on risk thresholds.

export const PALETTE = {
  bgDeep:        '#02040a',
  bgGraphite:    '#070a14',
  gridCyan:      '#0a3a5a',
  safe:          '#00f5ff', // cyan — risk < 0.45
  moderate:      '#f59e0b', // amber — 0.45–0.65
  high:          '#a855f7', // violet — 0.65–0.85
  critical:      '#ff3366', // crimson — >0.85 or flagged
  hologramEdge:  '#00f5ff',
  fraudEdge:     '#ff3366',
  cashIn:        '#ff8c00',
  cashOut:       '#818cf8',
  holoText:      '#bef0ff',
} as const

// rgb 0..1 helpers for shaders
export const rgb = (hex: string): [number, number, number] => {
  const h = hex.replace('#', '')
  const n = parseInt(h, 16)
  return [((n >> 16) & 0xff) / 255, ((n >> 8) & 0xff) / 255, (n & 0xff) / 255]
}

export function riskColor(score: number, flagged: boolean): string {
  if (flagged || score > 0.85) return PALETTE.critical
  if (score > 0.65)            return PALETTE.high
  if (score > 0.45)            return PALETTE.moderate
  return PALETTE.safe
}

export function riskRgb(score: number, flagged: boolean): [number, number, number] {
  return rgb(riskColor(score, flagged))
}
