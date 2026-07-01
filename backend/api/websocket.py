"""
WebSocket connection manager — broadcasts real-time graph updates,
fraud alerts, and transaction events to all connected clients.
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Set, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect

from models.transaction import WSMessage
from config import settings


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


class ConnectionManager:
    """Manages active WebSocket connections and provides broadcast primitives."""

    def __init__(self):
        self._active: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()
        self._message_counts: Dict[str, int] = {}
        # Session isolation: each client belongs to a session; broadcasts can be
        # scoped to a single session so two browsers never share a graph.
        self._session_of: Dict[str, str] = {}            # client_id -> session_id
        self._session_clients: Dict[str, Set[str]] = {}  # session_id -> {client_id}
        # Case collaboration rooms: clients viewing the SAME case get its live
        # events + presence. Independent of session/graph isolation above.
        self._case_rooms: Dict[str, Set[str]] = {}       # case_id -> {client_id}
        self._client_cases: Dict[str, Set[str]] = {}     # client_id -> {case_id}
        self._presence: Dict[str, dict] = {}             # client_id -> presence record

    async def connect(self, ws: WebSocket, client_id: str, session_id: str = "default"):
        await ws.accept()
        async with self._lock:
            self._active[client_id] = ws
            self._message_counts[client_id] = 0
            self._session_of[client_id] = session_id
            self._session_clients.setdefault(session_id, set()).add(client_id)

    async def disconnect(self, client_id: str):
        async with self._lock:
            self._active.pop(client_id, None)
            self._message_counts.pop(client_id, None)
            sid = self._session_of.pop(client_id, None)
            if sid is not None:
                clients = self._session_clients.get(sid)
                if clients is not None:
                    clients.discard(client_id)
                    if not clients:
                        self._session_clients.pop(sid, None)
            # leave every case room + drop presence (no leaks on abrupt disconnect)
            for case_id in self._client_cases.pop(client_id, set()):
                room = self._case_rooms.get(case_id)
                if room is not None:
                    room.discard(client_id)
                    if not room:
                        self._case_rooms.pop(case_id, None)
            self._presence.pop(client_id, None)

    async def send_to(self, client_id: str, message: Dict[str, Any]) -> bool:
        ws = self._active.get(client_id)
        if not ws:
            return False
        try:
            await ws.send_text(json.dumps(message, default=_json_default))
            self._message_counts[client_id] = self._message_counts.get(client_id, 0) + 1
            return True
        except Exception:
            await self.disconnect(client_id)
            return False

    async def broadcast(self, message: Dict[str, Any], session_id: Optional[str] = None):
        """Send a message to all clients, or only to one session's clients."""
        if not self._active:
            return
        payload = json.dumps(message, default=_json_default)
        async with self._lock:
            if session_id is None:
                clients = list(self._active.items())
            else:
                ids = self._session_clients.get(session_id, set())
                clients = [(cid, self._active[cid]) for cid in ids if cid in self._active]
        if not clients:
            return

        dead = []
        tasks = []
        for cid, ws in clients:
            tasks.append(self._safe_send(cid, ws, payload, dead))
        await asyncio.gather(*tasks, return_exceptions=True)

        # Cleanup dead connections
        for cid in dead:
            await self.disconnect(cid)

    async def _safe_send(self, cid: str, ws: WebSocket, payload: str, dead: list):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(cid)

    @property
    def connection_count(self) -> int:
        return len(self._active)

    @property
    def client_ids(self) -> Set[str]:
        return set(self._active.keys())

    def session_client_count(self, session_id: str) -> int:
        return len(self._session_clients.get(session_id, ()))

    def active_sessions(self) -> Set[str]:
        return set(self._session_clients.keys())

    # ── case collaboration rooms + presence ───────────────────────────────────
    def client_cases(self, client_id: str) -> Set[str]:
        return set(self._client_cases.get(client_id, set()))

    async def subscribe_case(self, client_id: str, case_id: str,
                             investigator: Optional[dict] = None, activity: str = "viewing"):
        inv = investigator or {}
        async with self._lock:
            self._case_rooms.setdefault(case_id, set()).add(client_id)
            self._client_cases.setdefault(client_id, set()).add(case_id)
            self._presence[client_id] = {
                "investigator_id": inv.get("investigator_id"),
                "name": inv.get("name") or "Investigator",
                "avatar": inv.get("avatar"),
                "case_id": case_id,
                "activity": activity,
                "ts": datetime.utcnow().isoformat(),
            }

    async def unsubscribe_case(self, client_id: str, case_id: str):
        async with self._lock:
            room = self._case_rooms.get(case_id)
            if room is not None:
                room.discard(client_id)
                if not room:
                    self._case_rooms.pop(case_id, None)
            cc = self._client_cases.get(client_id)
            if cc is not None:
                cc.discard(case_id)
                if not cc:
                    self._client_cases.pop(client_id, None)
            pr = self._presence.get(client_id)
            if pr and pr.get("case_id") == case_id:
                self._presence.pop(client_id, None)

    def set_activity(self, client_id: str, case_id: str, activity: str):
        pr = self._presence.get(client_id)
        if pr and pr.get("case_id") == case_id:
            pr["activity"] = activity
            pr["ts"] = datetime.utcnow().isoformat()

    def case_presence(self, case_id: str) -> list:
        """Who is currently in this case's room (deduped per investigator)."""
        out: Dict[str, dict] = {}
        for cid in self._case_rooms.get(case_id, set()):
            pr = self._presence.get(cid)
            if not pr:
                continue
            key = pr.get("investigator_id") or cid
            out[key] = {
                "investigator_id": pr.get("investigator_id"),
                "name": pr.get("name"),
                "avatar": pr.get("avatar"),
                "activity": pr.get("activity"),
            }
        return list(out.values())

    async def broadcast_to_case(self, case_id: str, message: Dict[str, Any]):
        """Send a message to every client currently in this case's room."""
        async with self._lock:
            ids = list(self._case_rooms.get(case_id, set()))
            clients = [(cid, self._active[cid]) for cid in ids if cid in self._active]
        if not clients:
            return
        payload = json.dumps(message, default=_json_default)
        dead: list = []
        await asyncio.gather(*[self._safe_send(cid, ws, payload, dead) for cid, ws in clients],
                             return_exceptions=True)
        for cid in dead:
            await self.disconnect(cid)


# ── Typed broadcast helpers ───────────────────────────────────────────────────

class WSBroadcaster:
    """
    High-level broadcaster — builds typed WSMessage envelopes and
    delegates to ConnectionManager.
    """

    def __init__(self, manager: ConnectionManager):
        self._mgr = manager

    async def broadcast_graph_update(self, graph_state: Dict[str, Any], session: Optional[str] = None):
        await self._mgr.broadcast({
            "type": "graph_update",
            "data": graph_state,
            "timestamp": datetime.utcnow().isoformat(),
        }, session_id=session)

    async def broadcast_transaction(self, txn_dict: Dict[str, Any], session: Optional[str] = None):
        await self._mgr.broadcast({
            "type": "transaction",
            "data": txn_dict,
            "timestamp": datetime.utcnow().isoformat(),
        }, session_id=session)

    async def broadcast_fraud_alert(self, alert_dict: Dict[str, Any], session: Optional[str] = None):
        await self._mgr.broadcast({
            "type": "fraud_alert",
            "data": alert_dict,
            "timestamp": datetime.utcnow().isoformat(),
        }, session_id=session)

    async def broadcast_stats(self, stats: Dict[str, Any], session: Optional[str] = None):
        await self._mgr.broadcast({
            "type": "stats_update",
            "data": stats,
            "timestamp": datetime.utcnow().isoformat(),
        }, session_id=session)

    async def broadcast_simulation_complete(self, data: Dict[str, Any], session: Optional[str] = None):
        await self._mgr.broadcast({
            "type": "simulation_complete",
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }, session_id=session)

    async def broadcast_blue_team_analyzing(self, session: Optional[str] = None):
        """Notify clients that Blue Team is actively analyzing the current graph snapshot."""
        await self._mgr.broadcast({
            "type": "blue_team_analyzing",
            "data": {"status": "analyzing"},
            "timestamp": datetime.utcnow().isoformat(),
        }, session_id=session)

    async def broadcast_blue_team_verdict(self, verdict: Dict[str, Any], session: Optional[str] = None):
        """Broadcast the aggregated Blue Team fraud verdict for the current graph."""
        await self._mgr.broadcast({
            "type": "blue_team_verdict",
            "data": verdict,
            "timestamp": datetime.utcnow().isoformat(),
        }, session_id=session)

    async def broadcast_blue_team_multi_verdict(self, verdicts: list, session: Optional[str] = None):
        """Broadcast independent Blue Team verdicts for each disconnected graph component."""
        await self._mgr.broadcast({
            "type": "blue_team_multi_verdict",
            "data": {"graphs": verdicts},
            "timestamp": datetime.utcnow().isoformat(),
        }, session_id=session)

    async def broadcast_case_registered(self, cases: list, session: Optional[str] = None):
        """Notify clients that the detection just auto-registered investigation case(s)."""
        await self._mgr.broadcast({
            "type": "case_registered",
            "data": {"cases": cases},
            "timestamp": datetime.utcnow().isoformat(),
        }, session_id=session)

    async def broadcast_case_event(self, case_id: str, event: str, payload: Optional[Dict[str, Any]] = None):
        """Real-time collaboration event (comment/task/assignment/…) to a case room.
        Everyone viewing that case refreshes instantly — no page reload."""
        await self._mgr.broadcast_to_case(case_id, {
            "type": "case_event",
            "data": {"case_id": case_id, "event": event, "payload": payload or {}},
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def broadcast_case_presence(self, case_id: str, present: list):
        """Live presence for a case room — who is viewing / editing right now."""
        await self._mgr.broadcast_to_case(case_id, {
            "type": "case_presence",
            "data": {"case_id": case_id, "present": present},
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def ping_all(self):
        await self._mgr.broadcast({
            "type": "ping",
            "data": {"connections": self._mgr.connection_count},
            "timestamp": datetime.utcnow().isoformat(),
        })

    @property
    def connection_count(self) -> int:
        return self._mgr.connection_count
