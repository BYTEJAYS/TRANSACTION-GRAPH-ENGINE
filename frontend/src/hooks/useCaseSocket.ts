import { useEffect, useRef, useState, useCallback } from 'react'
import { WS_URL } from '../config'
import type { PresentUser } from '../cases/api'

interface MiniInvestigator { investigator_id: string; name: string; avatar?: string }

/**
 * Subscribes to a case's collaboration room over the live WebSocket:
 *  • receives `case_event` (comment/task/assignment/…) → fires onEvent so the
 *    page can refetch and everyone sees changes WITHOUT a reload.
 *  • receives `case_presence` → who is viewing / editing right now.
 *  • setActivity() announces what this investigator is doing ("editing notes").
 * Reconnects on drop and unsubscribes cleanly on unmount. Independent of the
 * graph-page socket, so it works on the case page on its own.
 */
export function useCaseSocket(
  caseId: string | undefined,
  investigator: MiniInvestigator | null,
  onEvent: (event: string, payload: Record<string, unknown>) => void,
) {
  const [present, setPresent] = useState<PresentUser[]>([])
  const [connected, setConnected] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const onEventRef = useRef(onEvent)
  const invRef = useRef(investigator)
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const closedRef = useRef(false)

  useEffect(() => { onEventRef.current = onEvent }, [onEvent])
  useEffect(() => { invRef.current = investigator }, [investigator])

  const connect = useCallback(() => {
    if (!caseId) return
    const want = caseId.toUpperCase()
    closedRef.current = false
    let ws: WebSocket
    try { ws = new WebSocket(WS_URL) } catch { return }
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      const inv = invRef.current
      try {
        ws.send(JSON.stringify({
          type: 'case:subscribe', case_id: want,
          investigator: inv ? { investigator_id: inv.investigator_id, name: inv.name, avatar: inv.avatar } : undefined,
          activity: 'viewing',
        }))
      } catch { /* ignore */ }
    }

    ws.onmessage = ev => {
      try {
        const msg = JSON.parse(ev.data as string)
        const cid = (msg.data?.case_id as string | undefined)?.toUpperCase()
        if (cid !== want) return
        if (msg.type === 'case_event') onEventRef.current(msg.data.event, msg.data.payload ?? {})
        else if (msg.type === 'case_presence') setPresent(msg.data.present ?? [])
      } catch { /* ignore malformed frames */ }
    }

    ws.onclose = () => {
      setConnected(false)
      wsRef.current = null
      if (!closedRef.current) retryRef.current = setTimeout(connect, 2500)
    }
    ws.onerror = () => ws.close()
  }, [caseId])

  useEffect(() => {
    connect()
    return () => {
      closedRef.current = true
      if (retryRef.current) clearTimeout(retryRef.current)
      const ws = wsRef.current
      if (ws && ws.readyState === WebSocket.OPEN && caseId) {
        try { ws.send(JSON.stringify({ type: 'case:unsubscribe', case_id: caseId.toUpperCase() })) } catch { /* ignore */ }
      }
      ws?.close()
    }
  }, [connect, caseId])

  const setActivity = useCallback((activity: string) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN && caseId) {
      try { ws.send(JSON.stringify({ type: 'case:presence', case_id: caseId.toUpperCase(), activity })) } catch { /* ignore */ }
    }
  }, [caseId])

  return { present, connected, setActivity }
}
