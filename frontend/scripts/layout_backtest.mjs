/**
 * TGIE graph-layout backtest suite.
 *
 * Exercises `computeComponentLayout` (the deterministic motif-aware seed that
 * GraphScene's physics only refines) against the full catalogue of fraud
 * topologies and computes programmatic readability metrics for each:
 *
 *   - node overlap count            (glows must not merge)
 *   - edge length CV                (hub/fan edges should be uniform)
 *   - edge crossing count           (misleading crossings)
 *   - fan angular variance          (fan children evenly distributed)
 *   - ring interior crossings       (no edge cuts a laundering ring)
 *   - cash-out externality          (CASH/EXIT nodes sit outside the cluster)
 *   - determinism                   (identical layout across reruns)
 *
 * Run:  node scripts/layout_backtest.mjs        (from frontend/)
 * Exit code is non-zero if any case FAILS, so it doubles as a CI gate.
 *
 * Self-contained: bundles graphLayout.ts via the local esbuild and imports it.
 */
import { build } from 'esbuild'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { writeFileSync, mkdtempSync } from 'node:fs'
import { pathToFileURL } from 'node:url'

const dir = mkdtempSync(join(tmpdir(), 'tgie-layout-'))
const outfile = join(dir, 'graphLayout.mjs')
await build({
  entryPoints: ['src/components/graphLayout.ts'],
  bundle: true, format: 'esm', platform: 'node', outfile, logLevel: 'error',
})
const { computeComponentLayout } = await import(pathToFileURL(outfile).href)

// ── geometry helpers ──────────────────────────────────────────────────────────
const E = (...pairs) => pairs.map(([source, target]) => ({ source, target }))
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1])
function segCross(p1, p2, p3, p4) {
  const o = (a, b, c) => (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])
  const s = (a, b, c) => { const v = o(a, b, c); return v > 0 ? 1 : v < 0 ? -1 : 0 }
  if ([p3, p4].some(p => p === p1 || p === p2)) return false
  return s(p3, p4, p1) !== s(p3, p4, p2) && s(p1, p2, p3) !== s(p1, p2, p4)
}
function metrics(ids, edges, P) {
  // overlaps (< 30 units apart in XY)
  let overlap = 0
  for (let i = 0; i < ids.length; i++)
    for (let j = i + 1; j < ids.length; j++)
      if (dist(P[ids[i]], P[ids[j]]) < 30) overlap++
  // edge length CV
  const lens = edges.map(e => dist(P[e.source], P[e.target]))
  const mean = lens.reduce((a, b) => a + b, 0) / (lens.length || 1)
  const cv = mean ? Math.sqrt(lens.reduce((a, l) => a + (l - mean) ** 2, 0) / lens.length) / mean : 0
  // crossings (non-adjacent edge pairs)
  let cross = 0
  for (let i = 0; i < edges.length; i++)
    for (let j = i + 1; j < edges.length; j++) {
      const a = P[edges[i].source], b = P[edges[i].target]
      const c = P[edges[j].source], d = P[edges[j].target]
      if ([edges[j].source, edges[j].target].includes(edges[i].source) ||
          [edges[j].source, edges[j].target].includes(edges[i].target)) continue
      if (segCross(a, b, c, d)) cross++
    }
  return { overlap, edgeCV: +cv.toFixed(3), crossings: cross }
}
// fan angular evenness about a hub (0 = perfectly even). Works for BOTH a full-
// circle radial fan and a downstream ARC fan: the single largest gap (the empty
// side an arc fan intentionally leaves open) is excluded before measuring variance,
// so only the spacing BETWEEN adjacent children is judged.
function fanAngleVar(hub, children, P) {
  const angs = children.map(c => Math.atan2(P[c][1] - P[hub][1], P[c][0] - P[hub][0]))
    .sort((a, b) => a - b)
  let gaps = angs.map((a, i) => (i ? a - angs[i - 1] : a - angs[angs.length - 1] + 2 * Math.PI))
  if (gaps.length > 2) gaps = gaps.slice().sort((a, b) => a - b).slice(0, -1)  // drop the wrap/empty gap
  const m = gaps.reduce((a, b) => a + b, 0) / gaps.length
  return +(gaps.reduce((a, g) => a + (g - m) ** 2, 0) / gaps.length).toFixed(4)
}
// does any non-cycle edge pass through the ring interior (< 0.85R of centre)?
function ringInteriorCrossings(ringIds, edges, P) {
  const cx = ringIds.reduce((s, id) => s + P[id][0], 0) / ringIds.length
  const cy = ringIds.reduce((s, id) => s + P[id][1], 0) / ringIds.length
  const R = ringIds.reduce((s, id) => s + dist(P[id], [cx, cy]), 0) / ringIds.length
  const ringSet = new Set(ringIds)
  let bad = 0
  for (const e of edges) {
    if (ringSet.has(e.source) && ringSet.has(e.target)) continue
    const [ax, ay] = P[e.source], [bx, by] = P[e.target]
    const dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy || 1
    const t = Math.max(0, Math.min(1, ((cx - ax) * dx + (cy - ay) * dy) / L2))
    if (Math.hypot(ax + t * dx - cx, ay + t * dy - cy) < 0.85 * R) bad++
  }
  return bad
}

// ── test catalogue (20 topologies) ────────────────────────────────────────────
const fanK = (hub, n, pre = 's') => Array.from({ length: n }, (_, i) => [hub, `${pre}${i}`])
const chain = arr => arr.slice(1).map((x, i) => [arr[i], x])
const ring = arr => arr.map((x, i) => [x, arr[(i + 1) % arr.length]])

const CASES = [
  { name: '1  pure fan-out', ids: ['H', ...Array.from({ length: 6 }, (_, i) => `s${i}`)],
    e: E(...fanK('H', 6)), fan: ['H', ['s0','s1','s2','s3','s4','s5']] },
  { name: '2  fan-out + 1 cash-out', ids: ['H','s0','s1','s2','s3','s4','s5','CASH_OUT'],
    e: E(...fanK('H', 6), ['s2','CASH_OUT']), fan: ['H', ['s0','s1','s2','s3','s4','s5']], cashout: ['CASH_OUT'] },
  { name: '3  fan-out + multi cash-out', ids: ['H','s0','s1','s2','s3','s4','s5','C1','C2','C3'],
    e: E(...fanK('H', 6), ['s1','C1'], ['s3','C2'], ['s5','C3']), fan: ['H', ['s0','s1','s2','s3','s4','s5']], cashout: ['C1','C2','C3'] },
  { name: '4  fan-in', ids: ['s0','s1','s2','s3','s4','SINK'], e: E(['s0','SINK'],['s1','SINK'],['s2','SINK'],['s3','SINK'],['s4','SINK']), flow: ['s0','SINK'] },
  { name: '5  diamond', ids: ['A','B','C','D'], e: E(['A','B'],['A','C'],['B','D'],['C','D']), flow: ['A','D'] },
  { name: '6  double diamond', ids: ['A','B','C','D','E','F','G'], e: E(['A','B'],['A','C'],['B','D'],['C','D'],['D','E'],['D','F'],['E','G'],['F','G']), flow: ['A','G'] },
  { name: '7  pure ring', ids: ['A','B','C','D','E'], e: E(...ring(['A','B','C','D','E'])), ring: ['A','B','C','D','E'] },
  { name: '8  ring + 1 exit', ids: ['A','B','C','D','X','Y','EXIT'], e: E(...ring(['A','B','C','D']), ['C','X'],['X','Y'],['Y','EXIT']), ring: ['A','B','C','D'], cashout: ['EXIT'] },
  { name: '9  ring + multi exit', ids: ['A','B','C','D','X','Y'], e: E(...ring(['A','B','C','D']), ['B','X'],['D','Y']), ring: ['A','B','C','D'] },
  { name: '10 ring + entry', ids: ['SRC','A','B','C','D'], e: E(['SRC','A'], ...ring(['A','B','C','D'])), ring: ['A','B','C','D'] },
  { name: '11 ring + diamond', ids: ['A','B','C','D','P','Q','R','S'], e: E(...ring(['A','B','C','D']), ['C','P'],['P','Q'],['P','R'],['Q','S'],['R','S']), ring: ['A','B','C','D'] },
  { name: '12 chain', ids: ['A','B','C','D'], e: E(...chain(['A','B','C','D'])), flow: ['A','D'] },
  { name: '13 long chain', ids: Array.from({ length: 14 }, (_, i) => `n${i}`), e: E(...chain(Array.from({ length: 14 }, (_, i) => `n${i}`))), flow: ['n0','n13'] },
  { name: '14 two clusters', ids: ['A','B','C','X','Y','Z'], e: E(...chain(['A','B','C']), ...chain(['X','Y','Z'])) },
  { name: '15 dense mesh', ids: ['A','B','C','D','E'], e: E(['A','B'],['A','C'],['B','C'],['B','D'],['C','D'],['C','E'],['D','E'],['A','E']), mesh: true },
  { name: '16 large 100-node fan', ids: ['H', ...Array.from({ length: 99 }, (_, i) => `s${i}`)], e: E(...fanK('H', 99)), fan: ['H', Array.from({ length: 99 }, (_, i) => `s${i}`)] },
  { name: '17 hybrid (fan-out + tails + cash-out)', ids: ['H','a','b','c','d','a1','a2','c1','EXIT'], e: E(...fanK('H', 4, '').map(([h], i) => [h, ['a','b','c','d'][i]]), ['a','a1'],['a1','a2'],['c','c1'],['c1','EXIT']), fan: ['H', ['a','b','c','d']], cashout: ['EXIT'] },
  { name: '18 cash-in → layering → cash-out', ids: ['CASH_IN','L1','L2','L3','CASH_OUT'], e: E(...chain(['CASH_IN','L1','L2','L3','CASH_OUT'])), cashout: ['CASH_OUT'], flow: ['CASH_IN','CASH_OUT'] },
  { name: '19 multi-hub', ids: ['H1','H2','a','b','c','d','e','f'], e: E(['H1','a'],['H1','b'],['H1','c'],['H2','d'],['H2','e'],['H2','f'],['c','d']) },
  { name: '20 bridge network', ids: ['A','B','C','BRIDGE','D','E','F'], e: E(['A','C'],['B','C'],['C','BRIDGE'],['BRIDGE','D'],['D','E'],['D','F']) },
]

// ── run ───────────────────────────────────────────────────────────────────────
let failures = 0
console.log('TGIE LAYOUT BACKTEST — ' + CASES.length + ' topologies\n')
for (const c of CASES) {
  const r1 = computeComponentLayout(c.ids, c.e)
  const r2 = computeComponentLayout(c.ids, c.e)
  const P = Object.fromEntries(c.ids.map(id => [id, r1.positions.get(id)]))
  const m = metrics(c.ids, c.e, P)
  // determinism
  const stable = c.ids.every(id => {
    const a = r1.positions.get(id), b = r2.positions.get(id)
    return a[0] === b[0] && a[1] === b[1] && a[2] === b[2]
  })
  const checks = []
  checks.push(['overlap=0', m.overlap === 0])
  // A mesh is inherently crossing-heavy (no planar embedding); judge it by RATIO.
  checks.push(c.mesh ? ['crossing-ratio<0.4', m.crossings / c.e.length < 0.4] : ['crossings=0', m.crossings === 0])
  checks.push(['stable', stable])
  // Stage/direction: in a hierarchical flow motif the source and the terminal must
  // sit at the two ends of the flow (Y) axis — so an investigator reads "where the
  // money started" and "where it ended" at a glance. (Radial fans/rings centre the
  // hub / form a circle by design, so they declare no `flow`.)
  if (c.flow) {
    const [src, term] = c.flow
    const ys = c.ids.map(id => P[id][1])
    const yMax = Math.max(...ys), yMin = Math.min(...ys), yMid = (yMax + yMin) / 2
    // Terminal sits at a flow extreme; source is on the OPPOSITE side of the midline
    // (a fan-in arcs its sources, so we don't require the source at the exact end).
    const termAtEnd = P[term][1] === yMax || P[term][1] === yMin
    const opposite = Math.sign(P[src][1] - yMid) === -Math.sign(P[term][1] - yMid) && P[src][1] !== yMid
    checks.push(['source upstream / terminal at flow end', termAtEnd && opposite])
  }
  if (c.fan) {
    const [hub, kids] = c.fan
    const av = fanAngleVar(hub, kids, P)
    const dists = kids.map(k => dist(P[k], P[hub]))
    const dcv = (Math.max(...dists) - Math.min(...dists)) / (dists.reduce((a, b) => a + b) / dists.length)
    checks.push(['fan even (angVar<0.05)', av < 0.05])
    checks.push(['fan equal-radius (cv<0.15)', dcv < 0.15])
  }
  if (c.ring) checks.push(['ring interior clean', ringInteriorCrossings(c.ring, c.e, P) === 0])
  if (c.cashout) {
    // cash-out node must be farther from centroid than the mean node
    const cx = c.ids.reduce((s, id) => s + P[id][0], 0) / c.ids.length
    const cy = c.ids.reduce((s, id) => s + P[id][1], 0) / c.ids.length
    const meanR = c.ids.reduce((s, id) => s + dist(P[id], [cx, cy]), 0) / c.ids.length
    checks.push(['cash-out external', c.cashout.every(n => dist(P[n], [cx, cy]) >= meanR)])
  }
  const ok = checks.every(([, v]) => v)
  if (!ok) failures++
  const bad = checks.filter(([, v]) => !v).map(([k]) => k)
  console.log(
    (ok ? '✓' : '✗') + ' ' + c.name.padEnd(38) +
    `type=${(r1.type + (r1.containsFan ? '⊚fan' : r1.containsRing ? '⊚ring' : '')).padEnd(12)} ` +
    `overlap=${m.overlap} cross=${m.crossings} edgeCV=${m.edgeCV}` +
    (bad.length ? `   FAIL: ${bad.join(', ')}` : ''),
  )
}
console.log(`\n${CASES.length - failures}/${CASES.length} passed`)
process.exit(failures ? 1 : 0)
