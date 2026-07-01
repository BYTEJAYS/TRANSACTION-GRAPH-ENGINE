import { T } from '../../theme'

// Minimal banking-grade mark: a node-graph hexagon shield in subtle gold.
export function TgieMark({ size = 36 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none" aria-label="TGIE">
      <path d="M24 3 L41 12.5 V35.5 L24 45 L7 35.5 V12.5 Z"
        stroke={T.goldLine} strokeWidth="1.4" fill="rgba(198,162,83,0.06)" />
      {/* graph edges */}
      <g stroke={T.gold} strokeWidth="1.3" opacity="0.85">
        <line x1="24" y1="14" x2="15" y2="24" />
        <line x1="24" y1="14" x2="33" y2="24" />
        <line x1="15" y1="24" x2="24" y2="34" />
        <line x1="33" y1="24" x2="24" y2="34" />
        <line x1="15" y1="24" x2="33" y2="24" />
      </g>
      {/* graph nodes */}
      <g fill={T.goldHi}>
        <circle cx="24" cy="14" r="3" />
        <circle cx="15" cy="24" r="2.6" />
        <circle cx="33" cy="24" r="2.6" />
        <circle cx="24" cy="34" r="3" fill={T.gold} />
      </g>
    </svg>
  )
}
