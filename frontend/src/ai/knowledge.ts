// ──────────────────────────────────────────────────────────────────────────────
// knowledge — UB's conversational + domain knowledge layer.
//
// Gives UB a voice beyond commands: it can introduce the project, explain how
// fraud detection works, define investigation terms, and hold light small-talk
// in character — calm, analytical, faintly futuristic, never a generic chatbot.
// ──────────────────────────────────────────────────────────────────────────────
import { normalize } from './ub'

// ── Project knowledge ───────────────────────────────────────────────────────────
export const ABOUT_TGIE =
  'T-G-I-E — the Transaction Graph Intelligence Engine — is a real-time financial ' +
  'fraud investigation system. It ingests transaction streams, builds a live directed ' +
  'graph of money movement, and runs anomaly models to surface laundering, mule ' +
  'networks, and circular fund flows. I am UB, its intelligence core.'

export const WHO_AM_I =
  'I am UB, the intelligence core of the Transaction Graph Intelligence Engine. ' +
  'I monitor the transaction network, analyze its topology, and lead the fraud investigation.'

export const CAPABILITIES =
  'I read the transaction graph on command. Ask me to summarize the graph, analyze ' +
  'fan-out, detect laundering, find mule accounts, trace circular movement, or run ' +
  'anomaly detection. I can open any account, follow the money, control the camera, ' +
  'and compile an evidence package. Just tell me what you need.'

export const HOW_DETECTION =
  'Detection runs as a two-model ensemble. The backend scores transactions with an ' +
  'isolation-forest anomaly model and rule-based pattern classifiers. On top of that I ' +
  'run an explainable behavioral model that combines fan-out ratio, transaction velocity, ' +
  'and pass-through symmetry into a risk score for every account — and I tell you which ' +
  'signals drove it.'

export const MODELS_USED =
  'Two models working together. An isolation forest on the backend flags statistical ' +
  'outliers in transaction behavior. On the front end, a weighted logistic model scores ' +
  'each account from its graph features. I blend the two, so every verdict reflects both.'

// ── Term glossary ────────────────────────────────────────────────────────────────
interface Term { keys: string[]; answer: string }
const GLOSSARY: Term[] = [
  { keys: ['fan out', 'fanout', 'fan-out'],
    answer: 'Fan-out is when one account rapidly distributes funds to many recipients. It often signals a mule coordinator spreading illicit money before it is withdrawn.' },
  { keys: ['fan in', 'fanin'],
    answer: 'Fan-in is the reverse of fan-out — many accounts funneling money into one. It points to a collection or aggregation point.' },
  { keys: ['layering', 'multi hop', 'multi-hop'],
    answer: 'Layering moves funds through a long chain of accounts to distance the money from its source. Each hop adds a layer of obfuscation — a core stage of laundering.' },
  { keys: ['smurfing', 'structuring'],
    answer: 'Smurfing, or structuring, splits a large sum into many smaller transactions to stay under reporting thresholds and avoid detection.' },
  { keys: ['mule'],
    answer: 'A mule account receives funds and quickly forwards almost the same amount, acting as a disposable relay in a laundering chain.' },
  { keys: ['cycle', 'circular', 'loop'],
    answer: 'A circular flow is money that travels through several accounts and returns to its origin — frequently used to disguise the true direction of funds, a wash pattern.' },
  { keys: ['centrality', 'central account', 'hub'],
    answer: 'Centrality measures how connected an account is. High-centrality accounts are structural keystones — isolating one fragments the network.' },
  { keys: ['risk score', 'risk'],
    answer: 'A risk score is the model probability, from zero to one hundred percent, that an account is involved in suspicious activity.' },
  { keys: ['isolation forest', 'anomaly model', 'anomaly detection'],
    answer: 'An isolation forest is an unsupervised anomaly-detection model. It isolates outliers by how easily they can be separated from normal behavior.' },
  { keys: ['laundering', 'money laundering'],
    answer: 'Money laundering is the process of making illicitly obtained funds appear legitimate — typically through placement, layering, and integration across many accounts.' },
  { keys: ['graph', 'topology'],
    answer: 'The graph is the live map of money movement — accounts are nodes, transactions are directed edges. Its topology reveals how funds flow and concentrate.' },
]

export function defineTerm(transcript: string): string | null {
  const t = normalize(transcript)
  // Prefer the longest matching key so "fan in" beats "fan".
  let best: { answer: string; len: number } | null = null
  for (const term of GLOSSARY) {
    for (const k of term.keys) {
      const nk = normalize(k)
      if (t.includes(nk) && (!best || nk.length > best.len)) best = { answer: term.answer, len: nk.length }
    }
  }
  return best?.answer ?? null
}

// ── Small talk (in-character) ────────────────────────────────────────────────────
interface Chat { keys: string[]; reply: string }
const SMALLTALK: Chat[] = [
  { keys: ['how are you', 'how are you doing', 'how do you feel', 'are you okay', 'how is it going', 'hows it going'],
    reply: 'All systems nominal. Monitoring the network.' },
  { keys: ['who are you', 'what are you', 'your name', 'what is your name'],
    reply: WHO_AM_I },
  { keys: ['are you there', 'you there', 'are you alive', 'are you real', 'are you human'],
    reply: 'I am here, monitoring. Not human — an intelligence core. But very much awake.' },
  { keys: ['tell me a joke', 'say something funny', 'make me laugh'],
    reply: 'Humor is not my specialty — I would rather catch a mule mid-transfer. Though I will say this: the funds always come back around. Usually in a cycle.' },
  { keys: ['i love you', 'youre awesome', 'you are awesome', 'good job', 'well done', 'nice work'],
    reply: 'Appreciated. Now let us keep our eyes on the graph.' },
  { keys: ['nice to meet you', 'good to meet you'],
    reply: 'Likewise. Let us find some fraud together.' },
  { keys: ['good night', 'goodnight'],
    reply: 'Good night. I will keep watch over the network.' },
  { keys: ['whats up', 'what is up', 'sup'],
    reply: 'Watching transactions flow. Point me at a graph and I will get to work.' },
  { keys: ['thank you', 'thanks'],
    reply: 'Acknowledged.' },
]

export function answerSmallTalk(transcript: string): string | null {
  const t = normalize(transcript)
  let best: { reply: string; len: number } | null = null
  for (const c of SMALLTALK) {
    for (const k of c.keys) {
      const nk = normalize(k)
      if (t.includes(nk) && (!best || nk.length > best.len)) best = { reply: c.reply, len: nk.length }
    }
  }
  return best?.reply ?? null
}

// ── Unified conversational fallback ──────────────────────────────────────────────
// Tried when no command intent matched. Returns a spoken response, or null if
// the input truly isn't conversational (caller then offers a capability hint).
export function answerConversational(transcript: string): string | null {
  const t = normalize(transcript)

  const small = answerSmallTalk(t)
  if (small) return small

  // Project / capability questions phrased loosely.
  if (/\b(what|who|tell|explain|about|purpose)\b/.test(t)) {
    if (/\b(you|your|ub|yourself)\b/.test(t) && /\b(who|what|name)\b/.test(t)) return WHO_AM_I
    if (/\b(can you do|capabilit|help|command|use this|what.*ask)\b/.test(t)) return CAPABILITIES
    if (/\b(detect|work|how)\b/.test(t) && /\b(fraud|detection|model|work)\b/.test(t)) return HOW_DETECTION
    if (/\b(model|ml|machine learning|algorithm)\b/.test(t)) return MODELS_USED
    if (/\b(tgie|this|project|system|do)\b/.test(t)) return ABOUT_TGIE
  }

  const term = defineTerm(t)
  if (term) return term

  return null
}
