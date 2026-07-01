import { Component, type ReactNode } from 'react'
import { T } from '../theme'

// Keeps the navbar / shell alive if the Graph Engine (WebGL/three.js) fails to
// initialise — e.g. on a locked-down investigator workstation with no GPU. The
// rest of the platform (search, accounts, profile) stays fully usable.
export class GraphErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      const webgl = /webgl|context/i.test(this.state.error.message)
      return (
        <div style={{
          height: '100%', display: 'grid', placeItems: 'center', background: T.bg, color: T.text2,
          fontFamily: T.font, textAlign: 'center', padding: 32,
        }}>
          <div style={{ maxWidth: 460 }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: T.text, marginBottom: 10 }}>
              Graph Engine unavailable
            </div>
            <p style={{ fontSize: 13, lineHeight: 1.6 }}>
              {webgl
                ? 'This workstation could not initialise hardware-accelerated graphics (WebGL), which the interactive transaction graph requires. Account search, dossiers and investigations remain fully available from the navigation bar above.'
                : 'The graph visualisation failed to load. The rest of the investigation platform remains available.'}
            </p>
            <button onClick={() => this.setState({ error: null })} style={{
              marginTop: 16, padding: '9px 18px', borderRadius: 9, border: `1px solid ${T.goldLine}`,
              background: T.goldDim, color: T.gold, fontSize: 12.5, fontWeight: 600, cursor: 'pointer', fontFamily: T.font,
            }}>Retry</button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
