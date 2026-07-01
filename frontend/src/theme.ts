// ── TGIE banking-grade design tokens ─────────────────────────────────────────
// Deep matte black, subtle gold accent, dark grey, white typography.
// Deliberately NOT cyberpunk/neon — this is the shell that wraps the platform
// (login, navbar, dashboard, search, account view, profile).
export const T = {
  // surfaces
  bg:       '#0a0b0d',   // deep matte black canvas
  bg2:      '#101216',   // app background behind panels
  panel:    '#14161b',   // card / panel
  raised:   '#1a1d23',   // raised element (inputs, hover)
  raisedHi: '#22262e',   // active / selected
  border:   'rgba(255,255,255,0.08)',
  borderHi: 'rgba(255,255,255,0.16)',

  // typography
  text:     '#f3f5f8',
  text2:    '#9aa3af',
  text3:    '#5b6470',
  textOn:   '#0a0b0d',   // text on gold

  // accent — restrained gold
  gold:     '#c6a253',
  goldHi:   '#dcbd6e',
  goldDim:  'rgba(198,162,83,0.14)',
  goldLine: 'rgba(198,162,83,0.35)',

  // status (muted, enterprise — not neon)
  danger:   '#e5484d',
  dangerDim:'rgba(229,72,77,0.14)',
  warn:     '#d9a23a',
  warnDim:  'rgba(217,162,58,0.14)',
  success:  '#46a758',
  successDim:'rgba(70,167,88,0.14)',
  info:     '#5b8def',
  infoDim:  'rgba(91,141,239,0.14)',

  // misc
  shadow:   '0 8px 40px rgba(0,0,0,0.55)',
  radius:   10,
  font:     "'Inter','Segoe UI',system-ui,-apple-system,sans-serif",
  mono:     "'JetBrains Mono','SF Mono',ui-monospace,monospace",
} as const

// Dull cream-white palette for the auth panels (login + registration):
// dark text on a light card, with a green primary action.
export const cream = {
  panel:   '#d9d3c2',
  input:   '#e7e2d3',
  border:  'rgba(58,50,30,0.22)',
  text:    '#2a2620',
  text2:   '#574f3d',
  text3:   '#7a7360',
  green:   '#2f9e44',
  greenHi: '#3fb24f',
  greenDim:'#246b31',
} as const

// Risk band → colour
export function riskColor(band: string): string {
  switch (band) {
    case 'Critical': return T.danger
    case 'High':     return '#f0883e'
    case 'Medium':   return T.warn
    default:         return T.success
  }
}

export function riskColorFromScore(score: number): string {
  if (score >= 80) return T.danger
  if (score >= 60) return '#f0883e'
  if (score >= 35) return T.warn
  return T.success
}

// status pill colour
export function statusColor(status: string): string {
  const s = status.toLowerCase()
  if (s.includes('frozen') || s.includes('escalat')) return T.danger
  if (s.includes('investigat') || s.includes('watch') || s.includes('open')) return T.warn
  if (s.includes('clear')) return T.success
  if (s.includes('dormant')) return T.text3
  return T.info
}

export function fmtINR(v: number): string {
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(1)} K`
  return `₹${v}`
}
