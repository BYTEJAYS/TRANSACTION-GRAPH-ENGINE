import { useEffect, useRef, useState, useCallback } from 'react'

type AnyHandler = (data: unknown) => void
type HandlerMap = Record<string, AnyHandler>

interface Options {
  url: string
  onMessage: (type: string, data: unknown) => void
  reconnectDelay?: number
}

export function useWebSocket({ url, onMessage, reconnectDelay = 2000 }: Options) {
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onMessageRef = useRef(onMessage)

  useEffect(() => { onMessageRef.current = onMessage }, [onMessage])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    try {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          onMessageRef.current(msg.type, msg.data)
        } catch { /* ignore bad frames */ }
      }

      ws.onclose = () => {
        setConnected(false)
        wsRef.current = null
        timerRef.current = setTimeout(connect, reconnectDelay)
      }

      ws.onerror = () => ws.close()
    } catch {
      timerRef.current = setTimeout(connect, reconnectDelay)
    }
  }, [url, reconnectDelay])

  useEffect(() => {
    connect()
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  return { connected }
}
