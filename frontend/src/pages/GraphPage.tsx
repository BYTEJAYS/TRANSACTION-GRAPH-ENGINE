import { lazy, Suspense } from 'react'
import { GraphErrorBoundary } from '../components/GraphErrorBoundary'

// Lazy-loaded so the heavy three.js / R3F / postprocessing bundle is code-split
// out of the default workstation path and only fetched when the cinematic / 3D
// graph is actually opened.
const App = lazy(() => import('../App'))
const CinematicApp = lazy(() => import('../v2/CinematicApp'))

// The Graph Engine — the existing full investigation canvas, rendered inside the
// authenticated shell (navbar + global search stay accessible above it).
// Preserves the legacy ?v=2 / ?cinematic escape hatch. Wrapped in an error
// boundary so a WebGL failure can't take down the rest of the platform.
export default function GraphPage() {
  const params = new URLSearchParams(window.location.search)
  const isV2 = params.get('v') === '2' || params.has('cinematic')
  return (
    <div style={{
      position: 'relative', width: '100%', height: '100%', overflow: 'hidden',
      // `transform` makes this a containing block for the App's position:fixed
      // overlays (NodeInspector, status pills, Red Team button), so they anchor
      // below the navbar instead of escaping over it.
      transform: 'translateZ(0)',
    }}>
      <GraphErrorBoundary>
        <Suspense fallback={<div style={{ padding: 24, color: '#9aa3af', fontFamily: 'system-ui' }}>Loading graph engine…</div>}>
          {isV2 ? <CinematicApp /> : <App />}
        </Suspense>
      </GraphErrorBoundary>
    </div>
  )
}
