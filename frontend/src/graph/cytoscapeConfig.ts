export const RISK_COLORS = {
  safe:     '#4493f8',
  moderate: '#d29922',
  high:     '#e3683e',
  critical: '#f85149',
  mule:     '#a371f7',
}

export const RAIL_COLORS: Record<string, string> = {
  UPI:  '#4493f8',
  IMPS: '#3fb950',
  RTGS: '#d29922',
  NEFT: '#a371f7',
}

export const cytoscapeStylesheet = [
  // ── Base node ─────────────────────────────────────────────────────────
  {
    selector: 'node',
    style: {
      'background-color': '#1c2128',
      'border-color': 'rgba(255,255,255,0.14)',
      'border-width': 1,
      'label': 'data(label)',
      'color': '#484f58',
      'font-size': 7,
      'font-family': 'ui-monospace, SF Mono, Menlo, monospace',
      'text-halign': 'center',
      'text-valign': 'bottom',
      'text-margin-y': 3,
      'width': 20,
      'height': 20,
    },
  },
  // ── Risk levels ────────────────────────────────────────────────────────
  {
    selector: 'node[risk_level = "safe"]',
    style: {
      'border-color': 'rgba(68,147,248,0.40)',
      'background-color': '#111826',
    },
  },
  {
    selector: 'node[risk_level = "moderate"]',
    style: {
      'border-color': 'rgba(210,153,34,0.50)',
      'background-color': '#171208',
      'width': 24,
      'height': 24,
    },
  },
  {
    selector: 'node[risk_level = "high"]',
    style: {
      'border-color': 'rgba(227,104,62,0.60)',
      'background-color': '#1a0e06',
      'width': 28,
      'height': 28,
      'border-width': 1.5,
    },
  },
  {
    selector: 'node[risk_level = "critical"]',
    style: {
      'border-color': 'rgba(248,81,73,0.70)',
      'background-color': '#180806',
      'width': 34,
      'height': 34,
      'border-width': 1.5,
    },
  },
  // ── Account types ──────────────────────────────────────────────────────
  {
    selector: 'node[account_type = "mule"]',
    style: {
      'border-color': 'rgba(163,113,247,0.55)',
      'background-color': '#120d1e',
      'shape': 'diamond',
    },
  },
  {
    selector: 'node[account_type = "high_value"]',
    style: { 'shape': 'hexagon', 'border-width': 1.5 },
  },
  // ── Flagged ────────────────────────────────────────────────────────────
  {
    selector: 'node[?is_flagged]',
    style: { 'border-style': 'dashed', 'border-width': 1.5 },
  },
  // ── Selected ───────────────────────────────────────────────────────────
  {
    selector: 'node:selected',
    style: {
      'border-color': '#e6edf3',
      'border-width': 2,
      'background-color': '#21262d',
    },
  },
  // ── Base edge ──────────────────────────────────────────────────────────
  {
    selector: 'edge',
    style: {
      'line-color': 'rgba(139,148,158,0.18)',
      'target-arrow-color': 'rgba(139,148,158,0.28)',
      'target-arrow-shape': 'triangle',
      'arrow-scale': 0.55,
      'curve-style': 'bezier',
      'width': 0.8,
      'opacity': 0.55,
    },
  },
  // ── Payment rail colors ────────────────────────────────────────────────
  { selector: 'edge[payment_rail = "UPI"]',  style: { 'line-color': 'rgba(68,147,248,0.28)',  'target-arrow-color': 'rgba(68,147,248,0.45)' } },
  { selector: 'edge[payment_rail = "IMPS"]', style: { 'line-color': 'rgba(63,185,80,0.28)',   'target-arrow-color': 'rgba(63,185,80,0.45)' } },
  { selector: 'edge[payment_rail = "RTGS"]', style: { 'line-color': 'rgba(210,153,34,0.28)',  'target-arrow-color': 'rgba(210,153,34,0.45)', 'width': 1.2 } },
  { selector: 'edge[payment_rail = "NEFT"]', style: { 'line-color': 'rgba(163,113,247,0.28)', 'target-arrow-color': 'rgba(163,113,247,0.45)' } },
  // ── Flagged edges ──────────────────────────────────────────────────────
  {
    selector: 'edge[?is_flagged]',
    style: {
      'line-color': 'rgba(248,81,73,0.50)',
      'target-arrow-color': 'rgba(248,81,73,0.65)',
      'width': 1.4,
      'opacity': 0.85,
      'line-style': 'dashed',
      'line-dash-pattern': [4, 3],
    },
  },
  // ── New transaction flash ──────────────────────────────────────────────
  {
    selector: 'edge.new-transaction',
    style: {
      'line-color': '#4493f8',
      'target-arrow-color': '#4493f8',
      'width': 1.8,
      'opacity': 0.9,
    },
  },
  // ── Highlighted path ───────────────────────────────────────────────────
  {
    selector: '.highlighted',
    style: { 'line-color': '#e6edf3', 'target-arrow-color': '#e6edf3', 'width': 2, 'opacity': 0.75, 'z-index': 100 },
  },
  {
    selector: 'node.highlighted',
    style: { 'border-color': '#e6edf3', 'border-width': 2, 'z-index': 100 },
  },
]

export const layoutConfig = {
  name: 'cose',
  animate: true,
  animationDuration: 600,
  randomize: false,
  nodeRepulsion: () => 9000,
  idealEdgeLength: () => 110,
  edgeElasticity: () => 28,
  gravity: 0.55,
  numIter: 1200,
  initialTemp: 280,
  coolingFactor: 0.97,
  minTemp: 1.0,
  fit: true,
  padding: 56,
}
