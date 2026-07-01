// ── PERSISTENT GRAPH LAYOUT CACHE ─────────────────────────────────────────────
// The settled 3D coordinate of every node, keyed by durable node id, held OUTSIDE
// the React tree so it survives:
//   • route navigation   (GraphScene unmounts → its refs die, this does not)
//   • tab switches        (same component instance or a remount — cache persists)
//   • a full page reload  (mirrored to localStorage)
//
// WHY THIS EXISTS
// GraphScene's convergence-freeze pins each node (fx/fy/fz) once the force sim
// settles, but it recorded those pins ONLY in a component-local `useRef`
// (frozenPosRef). Navigating away unmounted GraphScene and destroyed that ref, so
// on return the simulation re-solved from scratch into a DIFFERENT equilibrium —
// clusters split, rings became stretched polygons, nodes drifted. This module is
// the durable home for the settled layout: freezeLayout() writes here, and
// GraphScene rehydrates frozenPosRef from here on mount, so a stabilized layout is
// reproduced EXACTLY (nodes re-emitted pinned) instead of recomputed.
//
// INVALIDATION (the only times a layout is allowed to change):
//   • graph reset / clear                 → clear() (store: mergeGraphUpdate reset, clearGraph)
//   • explicit "Recalculate Layout" / mode change → clear() (GraphScene thaw path)
//   • new nodes                           → seed + settle, then added here on next freeze
// Navigation is NOT in that list — hence it can never alter positions.

export type Vec3 = [number, number, number]

const LS_KEY = 'tgie:graph:layout:v1'

// In-memory singleton — the fast path (navigation / tab switch never touch disk).
let mem = new Map<string, Vec3>()
let hydratedFromDisk = false

function hasLS(): boolean {
  try {
    return typeof window !== 'undefined' && !!window.localStorage
  } catch {
    return false
  }
}

// Load the persisted layout (localStorage → memory) exactly once per page load,
// then always serve from memory.
function ensureHydrated(): void {
  if (hydratedFromDisk) return
  hydratedFromDisk = true
  if (!hasLS()) return
  try {
    const raw = window.localStorage.getItem(LS_KEY)
    if (!raw) return
    const arr = JSON.parse(raw) as Array<[string, number, number, number]>
    if (Array.isArray(arr)) {
      for (const [id, x, y, z] of arr) {
        if (typeof id === 'string' && Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z)) {
          mem.set(id, [x, y, z])
        }
      }
    }
  } catch {
    /* corrupt entry — ignore, start clean */
  }
}

function persistToDisk(): void {
  if (!hasLS()) return
  try {
    // Round to 2dp: enough precision to reproduce the layout, ~40% smaller payload.
    const arr: Array<[string, number, number, number]> = []
    for (const [id, [x, y, z]] of mem) {
      arr.push([id, Math.round(x * 100) / 100, Math.round(y * 100) / 100, Math.round(z * 100) / 100])
    }
    window.localStorage.setItem(LS_KEY, JSON.stringify(arr))
  } catch {
    /* quota / private mode — the in-memory cache still fixes navigation */
  }
}

export const layoutCache = {
  /** Fresh copy of every persisted node position — used to rehydrate frozenPosRef on mount. */
  load(): Map<string, Vec3> {
    ensureHydrated()
    return new Map(mem)
  },

  /** True if a stabilized layout is on hand (any node persisted). */
  has(): boolean {
    ensureHydrated()
    return mem.size > 0
  },

  /**
   * Replace the persisted layout with the given settled positions and write
   * through to disk. Called once per freeze (settle), never per tick — cheap.
   */
  saveAll(positions: Map<string, Vec3>): void {
    ensureHydrated()
    mem = new Map(positions)
    persistToDisk()
  },

  /** Drop the entire persisted layout (memory + disk). Called on reset/clear/recalc. */
  clear(): void {
    hydratedFromDisk = true // nothing left to hydrate
    mem = new Map()
    if (!hasLS()) return
    try {
      window.localStorage.removeItem(LS_KEY)
    } catch {
      /* ignore */
    }
  },
}
