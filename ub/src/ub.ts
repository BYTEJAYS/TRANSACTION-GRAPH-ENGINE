// ──────────────────────────────────────────────────────────────────────────────
// UB — TGIE intelligence copilot.
// Identity, time-based greeting, and intent dictionary used by the
// wake-word listener to map free-form speech to actionable commands.
// ──────────────────────────────────────────────────────────────────────────────

export const UB = {
  name: 'UB',
  wake: [
    'ub', 'u b', 'u.b.', 'u-b', 'ube', 'ubi', 'oob', 'oobie',
    'you bee', 'you be', 'you b', 'youbee', "you'd be", 'youbie',
    'hugh be', 'hugh bee', 'hub', 'lub',
    'hey ub', 'hey you bee', 'hey you be',
    'okay ub', 'ok ub',
  ],
  voice: { rate: 0.90, pitch: 0.84, volume: 0.95 },
} as const

export function timeOfDayGreeting(date = new Date()): string {
  const h = date.getHours()
  if (h < 5)  return 'Good evening.'
  if (h < 12) return 'Good morning.'
  if (h < 17) return 'Good afternoon.'
  return 'Good evening.'
}

export function buildGreeting(ctx: { hasFraud: boolean; clusters: number }): string {
  const hello  = timeOfDayGreeting()
  const status = ctx.hasFraud
    ? `Fraud monitoring active. ${ctx.clusters} cluster${ctx.clusters !== 1 ? 's' : ''} currently flagged.`
    : 'Transaction systems online. Network analysis ready.'
  return `${hello} This is UB. ${status}`
}

const FRAUD_NARRATIONS: Record<string, string> = {
  fan_out_detected: 'Fan-out fraud detected. Funds are rapidly dispersing across multiple recipient accounts.',
  layering:         'Transaction layering identified. Chain shows deliberate obfuscation behavior.',
  cycling:          'Circular loop detected. Funds cycling through a closed network of connected accounts.',
  smurfing:         'Structuring pattern flagged. Multiple transactions clustered near reporting thresholds.',
  high_velocity:    'Anomalous velocity detected. Transaction frequency exceeds expected behavioral bounds.',
  ML_ensemble:      'Ensemble model consensus: cluster behavior deviates significantly from baseline.',
  cycle_detected:   'Closed transaction cycle identified. Potential circular flow of funds.',
}

export function buildFraudNarration(score: number, reason?: string | null, graphCount = 1): string {
  const template = reason
    ? (FRAUD_NARRATIONS[reason] ?? `${reason.replace(/_/g, ' ')}.`)
    : 'Suspicious transaction pattern identified.'
  return [
    'Alert.',
    template,
    `Confidence score: ${Math.round(score * 100)} percent.`,
    graphCount > 1
      ? `${graphCount} separate clusters have been flagged for review.`
      : 'Initiating deep cluster analysis.',
  ].join(' ')
}

// ── Intent system ─────────────────────────────────────────────────────────────

export type IntentId =
  | 'summarise_fraud'
  | 'fraud_type'
  | 'investigate_graph'
  | 'graph_details'
  | 'explain_node'
  | 'alert_trigger'
  | 'show_path'
  | 'risk_score'
  | 'generate_evidence'
  | 'start_monitoring'
  | 'stop_monitoring'
  | 'sleep'
  | 'greeting'
  | 'thanks'
  | 'cancel'
  | 'entities_count'
  | 'fraud_origin'
  | 'show_suspicious'
  | 'money_flow'
  | 'system_status'
  | 'connected_accounts'
  // ── Deep topology analysis ──
  | 'explain_topology'
  | 'analyze_fanout'
  | 'find_central'
  | 'detect_laundering'
  | 'find_circular'
  | 'find_mules'
  | 'hidden_loops'
  | 'explain_cluster'
  | 'risky_accounts'
  | 'anomaly_scan'
  // ── Camera control ──
  | 'zoom_in'
  | 'zoom_out'
  | 'reset_camera'
  | 'focus_center'
  | 'show_all'
  | 'track_node'
  // ── Voice control ──
  | 'repeat'
  | 'speak_slower'
  | 'speak_faster'
  | 'continue'
  // ── UI control ──
  | 'show_alerts'
  | 'show_intel'
  | 'hide_intel'
  | 'toggle_labels'
  | 'scan_mode'
  // ── Node interaction ──
  | 'open_node'
  // ── Conversation + knowledge ──
  | 'help'
  | 'about'
  | 'define'
  | 'smalltalk'

export interface Intent {
  id:       IntentId
  patterns: string[]
}

export const INTENTS: Intent[] = [
  { id: 'generate_evidence',
    patterns: [
      'give me evidence', 'generate evidence', 'evidence package', 'evidence report',
      'generate report', 'create report', 'build report', 'export report',
      'download report', 'export investigation', 'download summary',
    ],
  },
  { id: 'summarise_fraud',
    patterns: [
      'summarise the fraud', 'summarize the fraud', 'summarise fraud', 'summarize fraud',
      'fraud summary', 'summary of fraud', 'sum up the fraud', 'give me a summary',
      'what is happening', 'what happened', 'brief me',
    ],
  },
  { id: 'fraud_type',
    patterns: [
      'what type of fraud', 'what kind of fraud', 'fraud classification',
      'classify the fraud', 'what is the fraud type', 'what fraud is this',
      'identify the fraud', 'fraud category',
    ],
  },
  { id: 'investigate_graph',
    patterns: [
      'investigate this graph', 'investigate the graph', 'investigate graph', 'investigate this',
      'analyze this graph', 'analyse this graph', 'analyze this', 'analyse this',
      'analyze the graph', 'analyse the graph', 'run a full investigation', 'run investigation',
      'full investigation', 'deep analysis', 'deep dive', 'what is this graph',
      'classify this graph', 'classify the graph', 'what pattern is this', 'what laundering pattern',
    ],
  },
  { id: 'entities_count',
    patterns: [
      'how many entities', 'count suspicious actors', 'how many accounts involved',
      'how many accounts', 'how many nodes', 'count the nodes', 'number of accounts',
      'how many actors', 'entity count',
    ],
  },
  { id: 'fraud_origin',
    patterns: [
      'which account started', 'root source', 'origin account', 'where did the fraud start',
      'where did it start', 'fraud source', 'source account', 'originating account',
      'which account started the fraud', 'where did this begin',
    ],
  },
  { id: 'show_suspicious',
    patterns: [
      'show suspicious nodes', 'highlight suspicious', 'dangerous nodes',
      'show high risk', 'highlight high risk', 'show flagged nodes',
      'show me the suspicious accounts', 'focus on suspicious',
    ],
  },
  { id: 'money_flow',
    patterns: [
      'track money flow', 'follow the money', 'money trail', 'show cash flow',
      'money flow', 'show money trail', 'trace the money', 'track funds',
      'where is the money going', 'follow funds',
    ],
  },
  { id: 'connected_accounts',
    patterns: [
      'show connected accounts', 'related accounts', 'show relationships',
      'connected accounts', 'who is connected', 'linked accounts',
      'show connections', 'account connections',
    ],
  },
  { id: 'graph_details',
    patterns: [
      'show me details of this graph', 'graph details', 'show graph details',
      'details of the graph', 'tell me about this graph', 'graph statistics',
      'graph stats', 'show graph info',
    ],
  },
  { id: 'explain_node',
    patterns: [
      'explain this suspicious node', 'explain this node', 'explain the node',
      'tell me about this node', 'why is this node flagged', 'why is this node suspicious',
      'analyse this node', 'analyze this node', 'node details',
    ],
  },
  { id: 'alert_trigger',
    patterns: [
      'what triggered the alert', 'why was the alert triggered', 'what caused this alert',
      'reason for the alert', 'why did the alert fire', 'what caused the fraud alert',
      'alert reason', 'what caused this',
    ],
  },
  { id: 'show_path',
    patterns: [
      'show transaction path', 'show the path', 'show me the path',
      'highlight the path', 'show fraud path', 'transaction route',
      'show the route', 'transaction chain',
    ],
  },
  { id: 'risk_score',
    patterns: [
      'what is the fraud risk', "what's the fraud risk", 'fraud risk',
      'risk score', 'risk percentage', 'risk level', 'how risky',
      'what is the risk', 'risk assessment', 'danger level',
    ],
  },
  { id: 'system_status',
    patterns: [
      'system status', 'are you online', 'status report', 'how is the system',
      'system check', 'check status', 'engine status', 'status',
    ],
  },
  // ── Deep topology analysis ───────────────────────────────────────────────
  { id: 'explain_topology',
    patterns: [
      'explain graph topology', 'graph topology', 'explain the topology', 'topology',
      'network structure', 'explain the structure', 'analyse topology', 'analyze topology',
      'summarize graph', 'summarise graph', 'summarize the graph', 'summarise the graph',
    ],
  },
  { id: 'analyze_fanout',
    patterns: [
      'analyze fan out', 'analyse fan out', 'analyze fanout', 'analyse fanout',
      'fan out', 'fanout', 'fan-out', 'distribution pattern', 'analyze distribution',
      'show fan out', 'detect fan out',
    ],
  },
  { id: 'find_central',
    patterns: [
      'find central account', 'central account', 'most connected account', 'find the hub',
      'find hub', 'show the hub', 'centrality', 'most central node', 'key account',
      'find the central node',
    ],
  },
  { id: 'detect_laundering',
    patterns: [
      'detect laundering pattern', 'detect laundering', 'laundering pattern', 'money laundering',
      'detect money laundering', 'layering pattern', 'detect layering', 'find layering',
      'explain transaction flow', 'transaction flow', 'multi hop', 'multi-hop',
    ],
  },
  { id: 'find_circular',
    patterns: [
      'find circular movement', 'circular movement', 'circular transaction', 'circular flow',
      'find cycles', 'detect cycle', 'find the cycle', 'find a cycle', 'circular pattern',
      'recycling funds', 'find circular',
    ],
  },
  { id: 'find_mules',
    patterns: [
      'find mule accounts', 'mule accounts', 'find mules', 'show mules', 'detect mules',
      'mule network', 'find the mules', 'relay accounts', 'pass through accounts',
      'passthrough accounts',
    ],
  },
  { id: 'hidden_loops',
    patterns: [
      'show hidden loops', 'hidden loops', 'find hidden loops', 'find loops', 'show loops',
      'detect loops', 'hidden cycles', 'find the loops',
    ],
  },
  { id: 'explain_cluster',
    patterns: [
      'explain this cluster', 'explain the cluster', 'explain cluster', 'analyse this cluster',
      'analyze this cluster', 'tell me about this cluster', 'cluster analysis', 'focus on this cluster',
      'focus on cluster', 'go to cluster',
    ],
  },
  { id: 'risky_accounts',
    patterns: [
      'show risky accounts', 'risky accounts', 'show risk accounts', 'high risk accounts',
      'most risky', 'dangerous accounts', 'show me risky accounts',
    ],
  },
  { id: 'anomaly_scan',
    patterns: [
      'run anomaly detection', 'anomaly detection', 'run the model', 'run model',
      'score the network', 'score network', 'run anomaly scan', 'anomaly scan',
      'run detection', 'run risk model', 'detect anomalies', 'find anomalies',
      'machine learning', 'run ml', 'rank anomalies',
    ],
  },
  // ── Camera control ─────────────────────────────────────────────────────────
  { id: 'zoom_in',  patterns: ['zoom in', 'zoom closer', 'move closer', 'get closer'] },
  { id: 'zoom_out', patterns: ['zoom out', 'zoom back', 'pull back', 'move back'] },
  { id: 'reset_camera', patterns: ['reset camera', 'reset the camera', 'reset view', 'reset the view', 'recenter'] },
  { id: 'focus_center', patterns: ['focus center', 'focus on center', 'focus the center', 'center camera', 'center view'] },
  { id: 'show_all', patterns: ['show entire graph', 'show the entire graph', 'show whole graph', 'show all', 'show everything', 'fit graph', 'frame the graph', 'see the whole graph'] },
  { id: 'track_node', patterns: ['track this node', 'track the node', 'follow this node', 'focus this node', 'focus on this node', 'zoom to node', 'go to this node'] },
  // ── Voice control ──────────────────────────────────────────────────────────
  { id: 'repeat', patterns: ['repeat analysis', 'repeat that', 'repeat', 'say that again', 'say again', 'come again', 'what did you say'] },
  { id: 'speak_slower', patterns: ['speak slower', 'slow down', 'talk slower', 'too fast', 'slower please'] },
  { id: 'speak_faster', patterns: ['speak faster', 'speed up', 'talk faster', 'too slow', 'faster please'] },
  { id: 'continue', patterns: ['continue', 'go on', 'carry on', 'keep going', 'proceed'] },
  // ── UI control ───────────────────────────────────────────────────────────────
  { id: 'show_alerts', patterns: ['show alerts', 'open alerts', 'show the alerts', 'show me alerts', 'open fraud report', 'show fraud report', 'open report', 'show report', 'open evidence panel', 'open the evidence panel', 'show statistics', 'show stats'] },
  { id: 'show_intel', patterns: ['show intel', 'show intel panel', 'show intelligence', 'show graph intelligence', 'open intel', 'open intel panel', 'open intelligence', 'show the intel', 'show intel hud', 'intel panel', 'graph intelligence'] },
  { id: 'hide_intel', patterns: ['hide intel', 'hide intel panel', 'hide intelligence', 'close intel', 'close intel panel', 'close intelligence', 'hide the intel', 'dismiss intel'] },
  { id: 'toggle_labels', patterns: ['hide labels', 'show labels', 'toggle labels', 'turn off labels', 'turn on labels'] },
  { id: 'scan_mode', patterns: ['enable scan mode', 'scan mode', 'enable glow', 'turn on glow', 'enable scanning', 'start scan'] },
  // ── Node interaction ─────────────────────────────────────────────────────────
  { id: 'open_node',
    patterns: [
      'open account', 'open node', 'open the node', 'open the account', 'show account',
      'show node', 'show me account', 'show me node', 'go to account', 'go to node',
      'select node', 'select account', 'pull up account', 'bring up account', 'find account',
      'find node', 'look up account', 'jump to account', 'open up account', 'view account',
      'inspect account', 'inspect node', 'open',
    ],
  },
  // ── Conversation + knowledge ──────────────────────────────────────────────────
  { id: 'help',
    patterns: [
      'what can you do', 'what can i ask', 'what can i say', 'help', 'help me', 'commands',
      'what commands', 'list commands', 'show commands', 'your capabilities', 'capabilities',
      'how do i use this', 'how does this work', 'what should i ask',
    ],
  },
  { id: 'about',
    patterns: [
      'what is tgie', 'what is this', 'what is this project', 'what is this system',
      'tell me about the project', 'explain the project', 'about the project', 'what does this do',
      'who are you', 'what are you', 'your name', "what's your name", 'who made you', 'who built you',
      'introduce yourself', 'tell me about yourself', 'what is your purpose', 'what do you do',
    ],
  },
  { id: 'define',
    patterns: [
      'what is fan out', 'what is fanout', 'what does fan out mean', 'what is fan in',
      'what is layering', 'what does layering mean', 'what is smurfing', 'what is structuring',
      'what is a mule', 'what is a mule account', 'what does mule mean', 'what is a cycle',
      'what is circular flow', 'what is centrality', 'what is a risk score', 'what is isolation forest',
      'explain fan out', 'explain layering', 'explain smurfing', 'explain mule account',
      'what does laundering mean', 'what is money laundering', 'define',
    ],
  },
  { id: 'smalltalk',
    patterns: [
      'how are you', 'how are you doing', 'how is it going', 'hows it going', "how's it going",
      'how do you feel', 'are you okay', 'are you there', 'you there', 'tell me a joke',
      'say something', 'i love you', 'nice to meet you', 'good night', 'whats up', "what's up",
      'what is up', 'are you real', 'are you human', 'are you alive',
    ],
  },
  { id: 'start_monitoring',
    patterns: ['start monitoring', 'resume monitoring', 'begin monitoring', 'enable live alerts', 'enable alerts'],
  },
  { id: 'stop_monitoring',
    patterns: ['stop monitoring', 'pause monitoring', 'halt monitoring', 'mute alerts', 'disable alerts'],
  },
  { id: 'sleep',
    patterns: ['sleep', 'go to sleep', 'sleep mode', 'goodbye', 'bye ub', 'dismiss', 'stand down', 'enter sleep', 'go quiet'],
  },
  { id: 'greeting',
    patterns: ['hello', 'hi there', 'hi ub', 'good morning', 'good afternoon', 'good evening', 'hey', 'wake up', 'ub wake up'],
  },
  { id: 'thanks',
    patterns: ['thank you', 'thanks ub', 'thanks', 'good job', 'well done', 'acknowledged'],
  },
  { id: 'cancel',
    patterns: ['cancel', 'never mind', 'nevermind', 'stop', 'quiet', 'shut up', 'enough'],
  },
]

// ── Fuzzy NLU layer ─────────────────────────────────────────────────────────
// Speech recognition mishears constantly ("summarise" → "summarize the graph"
// might arrive as "somerize graf"). We normalize aggressively, then match in
// two tiers: an exact-substring specificity pass, then a fuzzy token-set pass
// that tolerates typos and dropped/added words via edit distance.

// Common ASR / spelling drift mapped to canonical tokens.
const TOKEN_ALIASES: Record<string, string> = {
  graf: 'graph', graff: 'graph', graphs: 'graph',
  summarise: 'summarize', somerize: 'summarize', summary: 'summarize',
  analyse: 'analyze', analyzes: 'analyze',
  centre: 'center', central: 'central', centrality: 'centrality',
  fanout: 'fan', launder: 'laundering', laundring: 'laundering', lawndering: 'laundering',
  mules: 'mule', muel: 'mule', cycles: 'cycle', loops: 'loop', accounts: 'account',
  nodes: 'node', anomalies: 'anomaly', anomoly: 'anomaly', anomolies: 'anomaly',
  zoomin: 'zoom', suspicous: 'suspicious', suspious: 'suspicious',
}

export function normalize(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9 ]+/g, ' ').replace(/\s+/g, ' ').trim()
}

function canon(token: string): string {
  return TOKEN_ALIASES[token] ?? token
}

// Levenshtein edit distance.
function lev(a: string, b: string): number {
  const m = a.length, n = b.length
  if (m === 0) return n
  if (n === 0) return m
  let prev = Array.from({ length: n + 1 }, (_, i) => i)
  let cur = new Array<number>(n + 1)
  for (let i = 1; i <= m; i++) {
    cur[0] = i
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
    }
    [prev, cur] = [cur, prev]
  }
  return prev[n]
}

// Two tokens count as "the same word" if equal, a shared prefix, or within a
// length-scaled edit distance — so "graf"≈"graph", "somerize"≈"summarize".
function tokenMatch(a: string, b: string): boolean {
  a = canon(a); b = canon(b)
  if (a === b) return true
  const L = Math.max(a.length, b.length)
  if (L >= 5 && (a.startsWith(b) || b.startsWith(a))) return true
  if (L <= 2) return false
  return lev(a, b) <= (L <= 4 ? 1 : 2)
}

export function matchIntent(transcript: string): IntentId | null {
  const t = normalize(transcript)
  if (!t) return null

  // Tier 1 — exact substring, most-specific (longest) pattern wins.
  let bestId: IntentId | null = null
  let bestLen = 0
  for (const intent of INTENTS) {
    for (const p of intent.patterns) {
      const np = normalize(p)
      if (t.includes(np) && np.length > bestLen) { bestLen = np.length; bestId = intent.id }
    }
  }
  if (bestId) return bestId

  // Tier 2 — fuzzy token-set similarity. Score = fraction of a pattern's
  // tokens that fuzzy-match some transcript token, with a small bonus for
  // longer (more specific) patterns to break ties.
  const tTokens = t.split(' ').filter(Boolean)
  let fId: IntentId | null = null
  let fScore = 0
  for (const intent of INTENTS) {
    for (const p of intent.patterns) {
      const pTokens = normalize(p).split(' ').filter(w => w.length > 1)
      if (!pTokens.length) continue
      let matched = 0
      for (const pt of pTokens) if (tTokens.some(tt => tokenMatch(tt, pt))) matched++
      const score = matched / pTokens.length + pTokens.length * 0.001
      if (score > fScore) { fScore = score; fId = intent.id }
    }
  }
  return fScore >= 0.7 ? fId : null
}

// ── Spoken account-reference resolution ─────────────────────────────────────
// "open account 2001", "show me beta", "tell me about A.C.C 1001" → a node id.
const REF_STOP = new Set([
  'open', 'show', 'me', 'the', 'node', 'account', 'about', 'tell', 'this', 'that',
  'explain', 'what', 'is', 'go', 'to', 'select', 'find', 'pull', 'up', 'bring',
  'look', 'view', 'inspect', 'jump', 'a', 'an', 'and', 'of', 'on', 'with', 'please',
  'analyse', 'analyze', 'risk', 'score', 'connected', 'accounts', 'track', 'focus',
])

export function resolveNodeRef(transcript: string, nodeIds: string[]): string | null {
  if (!nodeIds.length) return null
  const t = normalize(transcript)
  const idsLower = nodeIds.map(id => ({ id, low: id.toLowerCase() }))

  // 1) Numeric reference — match a 3–6 digit run against an id suffix/substring.
  const num = t.match(/\b(\d{3,6})\b/)?.[1]
  if (num) {
    const hit = idsLower.find(x => x.low.endsWith(num)) ?? idsLower.find(x => x.low.includes(num))
    if (hit) return hit.id
  }

  // 2) Word reference — a meaningful token contained in an id (e.g. "beta").
  const tokens = t.split(' ').filter(w => w.length >= 3 && !REF_STOP.has(w))
  for (const tok of tokens) {
    const hit = idsLower.find(x => x.low.includes(tok))
    if (hit) return hit.id
  }

  // 3) Fuzzy fallback — closest id-tail token by edit distance.
  let best: string | null = null
  let bestD = 99
  for (const tok of tokens) {
    for (const x of idsLower) {
      const tail = x.low.split(/[_\-]/).pop() ?? x.low
      const d = lev(tok, tail)
      if (d < bestD && d <= 2) { bestD = d; best = x.id }
    }
  }
  return best
}

export function stripWake(transcript: string): string {
  let t = transcript.toLowerCase().trim()
  for (const w of UB.wake) {
    if (t.startsWith(w)) {
      t = t.slice(w.length).trim()
      t = t.replace(/^[,.\s]+(please|can you|could you|would you)?\s*/i, '')
      break
    }
  }
  return t
}

export function containsWake(transcript: string): boolean {
  const t = ' ' + transcript.toLowerCase().replace(/[^\w'.\- ]+/g, ' ') + ' '
  return UB.wake.some(w => t.includes(` ${w.toLowerCase()} `))
}
