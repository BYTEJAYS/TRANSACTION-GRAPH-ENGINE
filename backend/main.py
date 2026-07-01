"""
Transaction Graph Intelligence Engine — FastAPI entry point.

Production build: Kafka, GNN, and live retraining are removed.
Flink stream processor runs in-process (pure Python).
"""

import asyncio
import json
import logging
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s: %(message)s")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from models.transaction import FraudAlert
from streaming.flink_processor import FlinkStreamProcessor
from graph_engine.graph_manager import TransactionGraphManager
from anomaly_detection.isolation_forest_detector import IsolationForestDetector
from anomaly_detection.shap_explainer import SHAPExplainer
from ml.xgboost_classifier import XGBoostFraudClassifier
from api.routes import router
from api.websocket import ConnectionManager, WSBroadcaster


app_state: Dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    flink = FlinkStreamProcessor()
    graph_mgr = TransactionGraphManager()
    detector = IsolationForestDetector()
    shap_exp = SHAPExplainer(detector)
    xgb_classifier = XGBoostFraudClassifier()
    ws_manager = ConnectionManager()
    broadcaster = WSBroadcaster(ws_manager)

    alert_history: deque = deque(maxlen=500)
    txn_history: deque = deque(maxlen=2000)
    explanations: Dict[str, dict] = {}

    app_state.update({
        "flink_processor": flink,
        "graph_manager": graph_mgr,   # default/legacy manager (debug GET endpoints)
        "sessions": {},               # session_id -> per-browser graph + state
        "anomaly_detector": detector,
        "shap_explainer": shap_exp,
        "xgboost_classifier": xgb_classifier,
        "ws_manager": ws_manager,
        "broadcaster": broadcaster,
        "alert_history": alert_history,
        "transaction_history": txn_history,
        "explanations": explanations,
        "simulation_running": False,
        "manual_simulation_active": False,
        "kafka_active": False,
        "ws_connections": 0,
        "gnn_status": "rule-based fallback",
    })

    async def on_flink_alert(alert: FraudAlert):
        d = alert.model_dump(mode="json")
        alert_history.append(d)
        await broadcaster.broadcast_fraud_alert(d)

    flink.on_alert(on_flink_alert)

    tasks = [
        asyncio.create_task(
            _housekeeping_loop(ws_manager, app_state),
            name="housekeeping",
        ),
        asyncio.create_task(_ping_loop(broadcaster), name="ping"),
    ]

    yield

    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def _housekeeping_loop(ws_manager, state: Dict[str, Any]):
    """Connection-count heartbeat + prune abandoned sessions.

    We never re-broadcast a persisted graph (a fresh visitor must open to an
    EMPTY canvas). This loop just refreshes the connection count and frees the
    per-session graph of any session whose clients have all disconnected and
    which has no simulation in flight — keeping memory bounded as visitors come
    and go.
    """
    try:
        while True:
            await asyncio.sleep(settings.WS_BROADCAST_INTERVAL)
            state["ws_connections"] = ws_manager.connection_count
            sessions = state.get("sessions", {})
            for sid in list(sessions.keys()):
                if sid == "default":
                    continue
                if ws_manager.session_client_count(sid) == 0 and not sessions[sid].get("active"):
                    sessions.pop(sid, None)
    except asyncio.CancelledError:
        pass


async def _ping_loop(broadcaster: WSBroadcaster):
    try:
        while True:
            await asyncio.sleep(30)
            if broadcaster.connection_count > 0:
                await broadcaster.ping_all()
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Transaction Graph Intelligence Engine",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# ── /api/v1 (Phase 3 redesign) ────────────────────────────────────────────────
# Versioned, auth-gated, paginated API mounted ALONGSIDE the legacy routes above
# (legacy stays live until the frontend cuts over in Phase 6). Repository layer
# behind it honours TGIE_PERSIST=json|db, so this is a no-op for current data
# until the Neo4j/Postgres/Redis stack is brought up. Fails safe.
try:
    from api.v1 import mount as mount_v1
    mount_v1(app)
    logging.getLogger(__name__).info("API v1 mounted at /api/v1/* (persist mode: %s)",
                                      __import__("core.settings", fromlist=["data_settings"]).data_settings.persist)
except Exception as _e:  # pragma: no cover
    logging.getLogger(__name__).warning(f"API v1 not loaded: {_e}")

# ── Investigator authentication + account intelligence ────────────────────────
# Self-contained (stdlib-only) auth layer: JWT login, RBAC, account search and
# investigator profile. Mounted under /api/auth, /api/accounts, /api/investigator
# so it rides the existing /api proxy. Fails safe if the module can't import.
try:
    from auth import auth_router
    app.include_router(auth_router)
    logging.getLogger(__name__).info("Investigator auth mounted at /api/auth/*")
except Exception as _e:  # pragma: no cover
    logging.getLogger(__name__).warning(f"Auth module not loaded: {_e}")

# ── Case Management System ────────────────────────────────────────────────────
# Investigation case lifecycle (create → investigate → evidence → resolve) under
# /api/cases. This is the CRITICAL read path for the Investigations module: the
# Blue-Team auto-registration hook writes cases through case_management.store, and
# the frontend reads them back through THIS router. A failure here leaves the
# Investigations panel EMPTY even though cases are on disk, so — unlike the truly
# optional layers below — we log it LOUDLY (ERROR + traceback), never silently.
try:
    from case_management import cases_router
    app.include_router(cases_router)
    _case_routes = [r for r in app.routes if getattr(r, "path", "").startswith("/api/cases")]
    logging.getLogger(__name__).info(
        "Case Management mounted at /api/cases/* (%d routes) — Investigations API live",
        len(_case_routes),
    )
except Exception as _e:  # pragma: no cover
    logging.getLogger(__name__).error(
        "CRITICAL: Case Management FAILED to mount — the Investigations module will "
        "be EMPTY (every /api/cases request returns 404). Blue-Team auto-registered "
        "cases are still written to disk but cannot be read back by the frontend. "
        "Cause: %s", _e, exc_info=True,
    )

# ── Risk Scoring & Threshold Engine ───────────────────────────────────────────
# Cumulative, explainable multi-factor Risk Score (0–100) + admin-tunable
# thresholds under /api/risk. The decision layer for auto case creation. Fails safe.
try:
    from risk_engine import risk_router
    app.include_router(risk_router)
    logging.getLogger(__name__).info("Risk Scoring Engine mounted at /api/risk/*")
except Exception as _e:  # pragma: no cover
    logging.getLogger(__name__).warning(f"Risk Scoring Engine not loaded: {_e}")

# ── Fraud DNA Engine ──────────────────────────────────────────────────────────
# Behavioural fingerprinting (8 genes) + similarity / comparison / trends under
# /api/dna. Generates DNA for all existing cases at startup. Fails safe.
try:
    from fraud_dna import dna_router
    app.include_router(dna_router)
    logging.getLogger(__name__).info("Fraud DNA Engine mounted at /api/dna/*")
except Exception as _e:  # pragma: no cover
    logging.getLogger(__name__).warning(f"Fraud DNA Engine not loaded: {_e}")

# ── Recovery Probability Engine ───────────────────────────────────────────────
# Post-detection fund-recovery intelligence (10 factors → recovery probability,
# funnel, ranked actions, decay timeline, simulation) under /api/recovery. Reads
# live case + Fraud DNA data. Fails safe.
try:
    from recovery import recovery_router
    app.include_router(recovery_router)
    logging.getLogger(__name__).info("Recovery Probability Engine mounted at /api/recovery/*")
except Exception as _e:  # pragma: no cover
    logging.getLogger(__name__).warning(f"Recovery Probability Engine not loaded: {_e}")

# ── Red Team demo panel (LOCALHOST only, opt-in) ──────────────────────────────
# Additive: exposes /api/redteam/* for the local frontend's Red Team panel. Gated on
# ENABLE_REDTEAM_PANEL so the deployed/GitHub build never includes it. Never touches the
# fraud pipeline or blue_team_v2.
import os as _os
if _os.getenv("ENABLE_REDTEAM_PANEL", "").strip().lower() in ("1", "true", "yes"):
    try:
        from api.redteam import router as redteam_router
        app.include_router(redteam_router)
        logging.getLogger(__name__).info("Red Team demo panel enabled at /api/redteam/run")
    except Exception as _e:  # pragma: no cover - demo only
        logging.getLogger(__name__).warning(f"Red Team panel not loaded: {_e}")

# ── UB (Universal Brain) cognitive layer ──────────────────────────────────────
# By default UB runs as its OWN independently-controlled service (TGIE/control →
# port 8001), so the backend does NOT embed it. Set TGIE_MOUNT_UB=1 to also mount
# /ub/* on this backend (combined single-process mode). Fails safe either way.
if _os.getenv("TGIE_MOUNT_UB", "").strip().lower() in ("1", "true", "yes"):
    try:
        from ub_service import ub_router
        app.include_router(ub_router)
        logging.getLogger(__name__).info("UB (Universal Brain) mounted at /ub/* (TGIE_MOUNT_UB=1)")
    except Exception as _e:  # pragma: no cover - optional layer
        logging.getLogger(__name__).warning(f"UB service not loaded: {_e}")
else:
    logging.getLogger(__name__).info("UB runs as a standalone service (:8001); backend /ub mount disabled.")


async def _ws_handler(ws: WebSocket):
    ws_manager: ConnectionManager = app_state["ws_manager"]
    client_id = str(uuid.uuid4())
    # Per-browser session isolation: the frontend passes ?session=<id>. Clients
    # with the same id share a graph; different ids are fully independent.
    session_id = ws.query_params.get("session") or "default"

    await ws_manager.connect(ws, client_id, session_id)
    app_state["ws_connections"] = ws_manager.connection_count

    # Deliberately do NOT send a snapshot of the persisted graph on connect.
    # Every newly-opened page starts with an EMPTY canvas; the graph is only
    # streamed live while a simulation is actively running (each step
    # broadcasts the full current graph, so a mid-build client still catches up
    # within one step). This prevents a fresh visitor from inheriting whatever
    # graph a previous session left behind.

    broadcaster: WSBroadcaster = app_state["broadcaster"]

    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                mtype = msg.get("type")
                if mtype == "ping":
                    await ws_manager.send_to(client_id, {"type": "pong", "data": {}})
                elif mtype == "case:subscribe":
                    # Join a case room → receive its live collaboration events + presence.
                    case_id = (msg.get("case_id") or "").upper()
                    if case_id:
                        await ws_manager.subscribe_case(
                            client_id, case_id,
                            investigator=msg.get("investigator"),
                            activity=msg.get("activity") or "viewing",
                        )
                        await broadcaster.broadcast_case_presence(case_id, ws_manager.case_presence(case_id))
                elif mtype == "case:unsubscribe":
                    case_id = (msg.get("case_id") or "").upper()
                    if case_id:
                        await ws_manager.unsubscribe_case(client_id, case_id)
                        await broadcaster.broadcast_case_presence(case_id, ws_manager.case_presence(case_id))
                elif mtype == "case:presence":
                    # Update what this investigator is doing ("editing notes", …).
                    case_id = (msg.get("case_id") or "").upper()
                    if case_id:
                        ws_manager.set_activity(client_id, case_id, msg.get("activity") or "viewing")
                        await broadcaster.broadcast_case_presence(case_id, ws_manager.case_presence(case_id))
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        # snapshot the rooms BEFORE cleanup so we can refresh their presence after
        cases = ws_manager.client_cases(client_id)
        await ws_manager.disconnect(client_id)
        for cid in cases:
            try:
                await broadcaster.broadcast_case_presence(cid, ws_manager.case_presence(cid))
            except Exception:
                pass
        app_state["ws_connections"] = ws_manager.connection_count


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await _ws_handler(ws)


@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    await _ws_handler(ws)
