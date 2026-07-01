import { motion, HTMLMotionProps } from 'framer-motion'
import { ReactNode, CSSProperties } from 'react'

interface Props extends Omit<HTMLMotionProps<'div'>, 'children'> {
  children: ReactNode
  glowColor?: string
  borderColor?: string
  intense?: boolean
  style?: CSSProperties
}

// Floating holographic glass panel — used as the chrome for every HUD module.
// Variables (glowColor, borderColor, intense) let each panel express state
// (alarm pulse for fraud feed, calm cyan for stats, etc.).
export function HoloPanel({
  children,
  glowColor   = 'rgba(0,245,255,0.18)',
  borderColor = 'rgba(0,245,255,0.22)',
  intense     = false,
  style,
  ...rest
}: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12, filter: 'blur(8px)' }}
      animate={{ opacity: 1, y: 0,  filter: 'blur(0px)' }}
      transition={{ duration: 0.55, ease: [0.22, 0.61, 0.36, 1] }}
      style={{
        position: 'relative',
        background:
          'linear-gradient(180deg, rgba(6,10,22,0.78) 0%, rgba(2,4,10,0.86) 100%)',
        backdropFilter: 'blur(14px) saturate(1.4)',
        WebkitBackdropFilter: 'blur(14px) saturate(1.4)',
        border: `1px solid ${borderColor}`,
        borderRadius: 12,
        boxShadow: `
          0 0 32px ${glowColor},
          inset 0 0 24px rgba(0,245,255,0.04),
          inset 0 1px 0 rgba(255,255,255,0.05)
        `,
        color: '#bef0ff',
        fontFamily: '"JetBrains Mono", monospace',
        ...style,
      }}
      {...rest}
    >
      {/* Corner ticks — gives the panel an instrument feel */}
      <CornerTick pos="tl" color={borderColor} />
      <CornerTick pos="tr" color={borderColor} />
      <CornerTick pos="bl" color={borderColor} />
      <CornerTick pos="br" color={borderColor} />

      {/* Subtle scanline overlay */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none', borderRadius: 12,
        background: 'repeating-linear-gradient(0deg, rgba(255,255,255,0.012) 0px, rgba(255,255,255,0.012) 1px, transparent 1px, transparent 3px)',
        opacity: intense ? 0.9 : 0.6,
      }} />

      <div style={{ position: 'relative', zIndex: 1 }}>{children}</div>
    </motion.div>
  )
}

function CornerTick({ pos, color }: { pos: 'tl' | 'tr' | 'bl' | 'br'; color: string }) {
  const size = 10
  const off  = -1
  const style: CSSProperties = {
    position: 'absolute',
    width: size, height: size,
    borderColor: color,
    borderStyle: 'solid',
    borderWidth: 0,
  }
  if (pos === 'tl') { style.top = off; style.left  = off; style.borderTopWidth = 2; style.borderLeftWidth  = 2 }
  if (pos === 'tr') { style.top = off; style.right = off; style.borderTopWidth = 2; style.borderRightWidth = 2 }
  if (pos === 'bl') { style.bottom = off; style.left  = off; style.borderBottomWidth = 2; style.borderLeftWidth  = 2 }
  if (pos === 'br') { style.bottom = off; style.right = off; style.borderBottomWidth = 2; style.borderRightWidth = 2 }
  return <div style={style} />
}
