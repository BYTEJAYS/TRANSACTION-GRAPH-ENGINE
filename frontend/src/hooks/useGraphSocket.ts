import { useEffect, useRef, useState, useCallback } from 'react'
import { generateMockGraph, generateMockTransactions } from '../data/mockGraph'

type MessageHandler = (type: string, data: unknown) => void

interface Options {
  url: string
  onMessage: MessageHandler
  reconnectDelay?: number
  throttleMs?: number
  mockRetryLimit?: number
}

// Cached so we don't regenerate on every mock tick
let _mockGraphCache: ReturnType<typeof generateMockGraph> | null = null
function getMockGraph() {
  if (!_mockGraphCache) _mockGraphCache = generateMockGraph()
  return _mockGraphCache
}

export function useGraphSocket({
  url,
  onMessage,
  reconnectDelay = 2500,
  throttleMs = 0,
  mockRetryLimit = 5,
}: Options) {
  const [connected, setConnected] = useState(false)
  const [isMockMode, setIsMockMode] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mockIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const handlerRef = useRef(onMessage)
  const lastGraphUpdateRef = useRef(0)
  const failCountRef = useRef(0)
  const isMockRef = useRef(false)

  useEffect(() => { handlerRef.current = onMessage }, [onMessage])

  const startMockMode = useCallback(() => {
    if (isMockRef.current) return
    isMockRef.current = true
    setIsMockMode(true)
    setConnected(true)   // demo feed is live — keep UI indicators green

    const graph = getMockGraph()
    const flaggedIds = graph.nodes.filter(n => n.is_flagged).map(n => n.id)

    // Emit full initial graph
    handlerRef.current('graph_update', {
      nodes: graph.nodes,
      edges: graph.links,
      stats: {
        node_count: graph.nodes.length,
        edge_count: graph.links.length,
        flagged_nodes: flaggedIds.length,
        total_volume: graph.links.reduce((s, l) => s + (l.amount ?? 0), 0),
      },
      status: 'normal',
      rules_triggered: [],
      suspicious_nodes: flaggedIds.slice(0, 8),
    })

    // Simulate live transaction ticks every 2.5s
    mockIntervalRef.current = setInterval(() => {
      const txns = generateMockTransactions(1)
      if (txns[0]) {
        handlerRef.current('transaction', txns[0])
      }
    }, 2500)
  }, [])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    if (isMockRef.current) return

    try {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        failCountRef.current = 0
      }

      ws.onmessage = ev => {
        try {
          const msg = JSON.parse(ev.data as string)
          const { type, data } = msg

          if (type === 'graph_update' || type === 'simulation_complete') {
            const now = Date.now()
            if (now - lastGraphUpdateRef.current < throttleMs) return
            lastGraphUpdateRef.current = now
          }

          handlerRef.current(type, data)
        } catch { /* ignore malformed frames */ }
      }

      ws.onclose = () => {
        setConnected(false)
        wsRef.current = null
        failCountRef.current++
        // NOTE: we deliberately NO LONGER auto-inject a mock/demo graph after N
        // failures. The canvas must stay empty until REAL data arrives, so the
        // analyst can never confuse placeholder data for a live investigation.
        // A sample can still be loaded on demand via loadDemo().
        timerRef.current = setTimeout(connect, reconnectDelay)
      }

      ws.onerror = () => ws.close()
    } catch {
      failCountRef.current++
      timerRef.current = setTimeout(connect, reconnectDelay)
    }
  }, [url, reconnectDelay, throttleMs, mockRetryLimit, startMockMode])

  useEffect(() => {
    connect()
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      if (mockIntervalRef.current) clearInterval(mockIntervalRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  // loadDemo is exposed for the empty-state "Generate Sample" offline fallback —
  // it is never called automatically.
  return { connected, isMockMode, loadDemo: startMockMode }
}
