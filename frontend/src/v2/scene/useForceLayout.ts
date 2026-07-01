import { useEffect, useMemo, useRef } from 'react'
// eslint-disable-next-line import/no-unresolved
import ForceWorker from '../../workers/graphWorld.worker.ts?worker&inline'
import type { GraphNode, GraphLink } from '../../types'

export interface LayoutPositions {
  array: Float32Array | null
  count: number
}

export interface ClusterSector {
  compId: string
  cx: number
  cy: number
  cz: number
}

interface Options {
  nodes: GraphNode[]
  links: GraphLink[]
  nodeGroupIds?: Map<string, string>
}

export interface ForceLayoutResult {
  positions: LayoutPositions
  clusters: ClusterSector[]
}

// Hook owns one worker for the lifetime of the component.
// The worker handles connected-component detection and runs independent
// cluster-aware force simulation. Positions are emitted as a Float32Array
// in the same ordering as the input nodes array.
export function useForceLayout({ nodes, links, nodeGroupIds }: Options): ForceLayoutResult {
  const posRef     = useRef<LayoutPositions>({ array: null, count: 0 })
  const clustersRef = useRef<ClusterSector[]>([])
  const workerRef  = useRef<Worker | null>(null)

  // Stable signature — only re-send when graph topology or group assignments change
  const signature = useMemo(() => {
    const ns = nodes.map(n => n.id).join('|')
    const ls = links.map(l => {
      const s = typeof l.source === 'string' ? l.source : (l.source as any).id
      const t = typeof l.target === 'string' ? l.target : (l.target as any).id
      return `${s}>${t}`
    }).join('|')
    const gs = nodeGroupIds ? [...nodeGroupIds.entries()].map(([k, v]) => `${k}:${v}`).join('|') : ''
    return `${ns}#${ls}#${gs}`
  }, [nodes, links, nodeGroupIds])

  // Create the worker once on mount; terminate on unmount
  useEffect(() => {
    const w = new ForceWorker()
    workerRef.current = w

    w.onmessage = (e: MessageEvent) => {
      const msg = e.data
      if (msg.type === 'tick') {
        posRef.current.array = msg.positions as Float32Array
        posRef.current.count = msg.count as number
      } else if (msg.type === 'clusters') {
        clustersRef.current = msg.sectors as ClusterSector[]
      }
    }

    return () => {
      w.terminate()
      workerRef.current = null
    }
  }, [])

  // Push graph updates to the worker whenever topology changes
  useEffect(() => {
    const w = workerRef.current
    if (!w) return
    const linkMsg = links.map(l => ({
      source: typeof l.source === 'string' ? l.source : (l.source as any).id,
      target: typeof l.target === 'string' ? l.target : (l.target as any).id,
    }))
    const nodeMsg = nodes.map(n => ({ id: n.id }))
    const groupMsg = nodeGroupIds && nodeGroupIds.size > 0
      ? Object.fromEntries(nodeGroupIds)
      : undefined
    w.postMessage({ type: 'update', nodes: nodeMsg, links: linkMsg, nodeGroupIds: groupMsg })
  }, [signature, nodes, links, nodeGroupIds])

  // Return stable object references so callers don't need to memo-guard reads
  return { positions: posRef.current, clusters: clustersRef.current }
}
