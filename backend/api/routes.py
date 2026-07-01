"""
REST API routes for graph queries, account inspection,
simulation control, and system health.
"""

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel

from models.transaction import (
    ManualTransactionInput,
    PaymentRail,
    SimulationControl,
    Transaction,
)
from graph_engine.graph_manager import TransactionGraphManager
from detection_service import classify_live
# Engine router: Blue Team V2 is the PRODUCTION engine (default). V1 is retired
# and reachable only via an explicit ACTIVE_BLUE_TEAM=v1 rollback. V2's output is
# a superset of V1's schema (every key consumers read, plus an additive `v2`
# block), so this is a behaviour-preserving swap for all existing consumers.
from blue_team_v2.router import route_all_components as analyze_all_components
from config import settings
from evidence import EvidenceGenerator
from evidence.pdf_builder import build_pdf

router = APIRouter()

# Directory where generated evidence files are saved
_EVIDENCE_DIR = os.path.join(os.path.dirname(__file__), "..", "evidence_files")
os.makedirs(_EVIDENCE_DIR, exist_ok=True)

_EVIDENCE_FILENAME_RE = re.compile(
    r"^evidence_GRAPH_\d{3}_\d{4}-\d{2}-\d{2}\.(json|pdf)$"
)


def get_app_state():
    from main import app_state
    return app_state


# ── Per-session graph isolation ────────────────────────────────────────────────
# Each browser (identified by the X-Session-Id header / ?session= WS param) gets
# its OWN graph + simulation state, so two users never share a graph. Clients
# that send no session id fall back to the shared "default" session.
def get_session(state, session_id: str):
    sessions = state.setdefault("sessions", {})
    sess = sessions.get(session_id)
    if sess is None:
        sess = {
            "graph_manager": TransactionGraphManager(),
            "active": False,                     # manual simulation in progress
            "latest_blue_team_verdicts": {},
            "latest_graph_components": {},
            # Cross-product entity context (product types / ownership / shared
            # identities) recorded at ingestion, kept OUT of the rendered money
            # graph and merged in on demand by the knowledge endpoints.
            "entity_context": {"types": {}, "owns": {}, "links": []},
        }
        sessions[session_id] = sess
    return sess


def _session_id(x_session_id: Optional[str]) -> str:
    return x_session_id or "default"


def _session_graph(x_session_id: Optional[str]):
    """Resolve THIS session's live graph manager.

    The analytics GET endpoints previously read a global manager that the
    per-session streaming simulation never writes to — so they 404'd on real
    data. Routing them through the session restores correct results.
    """
    state = get_app_state()
    return get_session(state, _session_id(x_session_id))["graph_manager"]


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health", tags=["System"])
async def health():
    state = get_app_state()
    return {
        "status": "operational",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "graph_engine": "online",
            "anomaly_detector": "online",
            "simulator": "manual-mode",
            "kafka": "active" if state.get("kafka_active") else "fallback-queue",
            "ws_connections": state.get("ws_connections", 0),
        },
    }


# ── Manual Transaction Ingestion ──────────────────────────────────────────────

@router.post("/transaction/manual", tags=["Manual"])
async def submit_manual_transactions(
    background_tasks: BackgroundTasks,
    payload: Any = Body(..., description="Legacy transaction list OR enterprise envelope (schema 2.0)"),
    x_session_id: Optional[str] = Header(None),
):
    """Accept a transaction chain and emit WebSocket graph updates.

    Accepts BOTH the legacy lightweight list and the versioned enterprise envelope
    (schema 2.0) — the payload shape is auto-detected and normalized into one internal
    model (see models/normalize.py). Declared customer/account/product/device/geo
    intelligence is captured per session and fed to the existing engines; omitted
    fields keep the legacy behaviour.
    """
    from models.normalize import normalize_payload
    try:
        batch = normalize_payload(payload)
    except Exception as e:
        raise HTTPException(400, f"Invalid transaction payload: {e}")
    if not batch.transactions:
        raise HTTPException(400, "No transactions provided")
    state = get_app_state()
    session_id = _session_id(x_session_id)
    sess = get_session(state, session_id)
    # Per-session intelligence captured from the enterprise format (empty for legacy).
    sess["account_intel"] = batch.account_intel
    sess["customer_profiles"] = batch.customer_profiles
    sess["batch_meta"] = batch.batch_meta
    background_tasks.add_task(_run_manual_simulation, list(batch.transactions), state, session_id)
    return {"status": "started", "count": len(batch.transactions), "session": session_id,
            "schema_version": batch.batch_meta.get("schema_version"),
            "profiles_supplied": len(batch.customer_profiles),
            "warnings": batch.warnings}


@router.post("/graph/clear", tags=["Graph"])
async def clear_graph(x_session_id: Optional[str] = Header(None)):
    """Reset THIS session's graph to empty and broadcast the cleared state only
    to that session's clients.

    Also flips the session's ``active`` flag to False so any in-flight
    simulation loop aborts on its next iteration — without this, the loop
    would keep adding transactions back into the freshly-cleared graph.
    """
    state = get_app_state()
    session_id = _session_id(x_session_id)
    sess = get_session(state, session_id)
    # Cancel any in-flight manual simulation for this session first.
    sess["active"] = False
    sess["entity_context"] = {"types": {}, "owns": {}, "links": []}
    sess["account_intel"] = {}
    sess["customer_profiles"] = {}
    sess["batch_meta"] = {}
    await sess["graph_manager"].clear()
    broadcaster = state["broadcaster"]
    await broadcaster.broadcast_graph_update({
        "nodes": [],
        "edges": [],
        "stats": {},
        "status": "normal",
        "rules_triggered": [],
        "suspicious_nodes": [],
        "reset": True,
    }, session=session_id)
    return {"status": "cleared", "session": session_id}


async def _run_manual_simulation(
    transactions: List[ManualTransactionInput],
    state: dict,
    session_id: str = "default",
) -> None:
    """Background task: process each transaction with 1.5 s delay, emit WS step
    updates scoped to ONE session so other users' graphs are untouched."""
    sess = get_session(state, session_id)
    graph_mgr = sess["graph_manager"]
    broadcaster = state["broadcaster"]
    sess["active"] = True
    processed: List[dict] = []

    # Each run starts from a CLEAN graph — a new scenario must never accumulate
    # on top of the previous one (which made the old graph "come back"). Reset
    # this session's graph and tell its clients to clear before the build streams.
    await graph_mgr.clear()
    sess["entity_context"] = {"types": {}, "owns": {}, "links": []}  # fresh scenario
    await broadcaster.broadcast_graph_update({
        "nodes": [], "edges": [], "stats": {},
        "status": "normal", "rules_triggered": [], "suspicious_nodes": [],
        "reset": True,
    }, session=session_id)

    try:
        from knowledge import record_account
        ec = sess["entity_context"]
        for i, inp in enumerate(transactions):
            # Honour external cancellation (e.g. /graph/clear sets this flag
            # to False to abort the in-flight simulation cleanly).
            if not sess["active"]:
                return
            # Record optional cross-product context (kept out of the money graph).
            record_account(ec, inp.from_account, entity_type=inp.from_entity_type,
                           customer=inp.from_customer, phone=inp.from_phone,
                           pan=inp.from_pan, device=inp.device_id, bank=inp.from_bank)
            record_account(ec, inp.to_account, entity_type=inp.to_entity_type,
                           customer=inp.to_customer, phone=inp.to_phone, pan=inp.to_pan,
                           bank=inp.to_bank)
            try:
                rail = PaymentRail(inp.payment_rail.upper())
            except ValueError:
                logging.getLogger("tgie.ingest").warning(
                    "Unknown payment_rail %r on %s→%s — defaulting to UPI",
                    inp.payment_rail, inp.from_account, inp.to_account,
                )
                rail = PaymentRail.UPI

            ts = datetime.utcnow()
            if inp.timestamp:
                try:
                    ts = datetime.fromisoformat(inp.timestamp)
                except ValueError:
                    pass

            # ── CASH rail: special off-graph handling ─────────────────────────
            if rail == PaymentRail.CASH:
                from_up = inp.from_account.upper()
                is_deposit = from_up.startswith("CASH")
                parent_account = inp.to_account if is_deposit else inp.from_account
                cash_type = "CASH_IN" if is_deposit else "CASH_OUT"

                await graph_mgr.add_cash_event(
                    parent_id=parent_account,
                    cash_type=cash_type,
                    amount=inp.amount,
                    ts=ts,
                )

                processed.append({
                    "from_account": inp.from_account,
                    "to_account": inp.to_account,
                    "amount": inp.amount,
                })

                graph_state = await graph_mgr.get_graph_state()
                classification = await classify_live(graph_mgr)
                cash_node_id = f"{cash_type}_{parent_account}_{uuid.uuid4().hex[:6].upper()}"

                await broadcaster.broadcast_graph_update({
                    **graph_state,
                    "status": classification["status"],
                    "rules_triggered": classification["rules_triggered"],
                    "suspicious_nodes": classification["suspicious_nodes"],
                    "cash_event": {
                        "id": cash_node_id,
                        "type": cash_type,
                        "parent_account": parent_account,
                        "amount": inp.amount,
                        "timestamp": ts.isoformat(),
                    },
                    "current_transaction": {
                        "from_account": inp.from_account,
                        "to_account": inp.to_account,
                        "amount": inp.amount,
                        "step": i + 1,
                        "total": len(transactions),
                    },
                }, session=session_id)

                if i < len(transactions) - 1:
                    await asyncio.sleep(1.5)
                continue
            # ── End CASH rail ─────────────────────────────────────────────────

            txn = Transaction(
                from_account=inp.from_account,
                to_account=inp.to_account,
                amount=inp.amount,
                payment_rail=rail,
                timestamp=ts,
                device_id=inp.device_id or "MANUAL",
                ip_address="0.0.0.0",
                geo_location="Manual Entry",
            )

            await graph_mgr.add_transaction(txn)

            # ── Diagnostic trace for first-class CASH_IN / CASH_OUT ────────────
            if rail in (PaymentRail.CASH_IN, PaymentRail.CASH_OUT):
                logging.getLogger("tgie.ingest").info(
                    "CASH txn #%d ACCEPTED · %s →(%s)→ %s · ₹%s · node+edge created "
                    "(first-class, connected)",
                    i + 1, inp.from_account, rail.value, inp.to_account, inp.amount,
                )

            processed.append({
                "from_account": inp.from_account,
                "to_account": inp.to_account,
                "amount": inp.amount,
            })

            graph_state = await graph_mgr.get_graph_state()
            classification = await classify_live(graph_mgr)

            await broadcaster.broadcast_graph_update({
                **graph_state,
                "status": classification["status"],
                "rules_triggered": classification["rules_triggered"],
                "suspicious_nodes": classification["suspicious_nodes"],
                "current_transaction": {
                    "from_account": inp.from_account,
                    "to_account": inp.to_account,
                    "amount": inp.amount,
                    "step": i + 1,
                    "total": len(transactions),
                },
            }, session=session_id)

            if i < len(transactions) - 1:
                await asyncio.sleep(1.5)

        # Broadcast completion event
        final_state = await graph_mgr.get_graph_state()
        final_cls = await classify_live(graph_mgr)
        await broadcaster.broadcast_simulation_complete({
            **final_state,
            "status": final_cls["status"],
            "rules_triggered": final_cls["rules_triggered"],
            "suspicious_nodes": final_cls["suspicious_nodes"],
            "total_processed": len(transactions),
        }, session=session_id)

        # ── Blue Team multi-graph analysis ────────────────────────────────────
        # Signal frontend that Blue Team is now receiving and analyzing.
        await broadcaster.broadcast_blue_team_analyzing(session=session_id)

        try:
            components = await graph_mgr.get_connected_components()
            multi_verdicts = await analyze_all_components(
                components,
                blue_team_url=settings.BLUE_TEAM_URL,
                api_key=settings.BLUE_TEAM_API_KEY,
            )
        except Exception as exc:
            multi_verdicts = [{
                "graph_id": "GRAPH_001",
                "status": "offline",
                "verdict": "UNKNOWN",
                "risk_score": None,        # engine offline → no score; UI shows N/A
                "risk_available": False,
                "flagged": False,
                "flagged_nodes": [],
                "suspicious_reason": None,
                "transactions_scored": 0,
                "nodes": [],
                "reason": str(exc),
            }]

        # Store verdicts + component snapshots for evidence generation (per
        # session, plus mirror to app-state for the legacy evidence endpoint).
        verdict_map = {v["graph_id"]: v for v in multi_verdicts}
        comp_map = {c["graph_id"]: c for c in components}
        sess["latest_blue_team_verdicts"] = verdict_map
        sess["latest_graph_components"] = comp_map
        state["latest_blue_team_verdicts"] = verdict_map
        state["latest_graph_components"] = comp_map

        # ── Risk Engine: the decision layer ──────────────────────────────────
        # Score every component with the cumulative multi-factor Risk Engine and
        # attach the explainable result to its verdict BEFORE broadcasting, so the
        # live graph shows the same 0–100 score the case will carry. A case is
        # auto-created ONLY when the score crosses the configured investigation
        # threshold (default 70) — no single amount can trigger an alert.
        assessments: dict = {}
        session_profiles = sess.get("customer_profiles") or {}
        session_account_intel = sess.get("account_intel") or {}
        try:
            from risk_engine import assess as risk_assess
            for v in multi_verdicts:
                comp = comp_map.get(v["graph_id"], {})
                if not comp:
                    # No component snapshot → cannot score honestly. Mark N/A
                    # rather than leaving a misleading model score in place.
                    v["risk_score"] = None
                    v["risk_available"] = False
                    continue
                # Feed declared customer profiles (from the enterprise format) into
                # Profile Intelligence; inference still runs for accounts without one.
                if session_profiles:
                    comp = {**comp, "customer_profiles": session_profiles}
                # Attach the per-session entity_context so Cross-Bank Intelligence can
                # resolve entities by shared device/phone/PAN/bank (metadata only —
                # never enters the money graph). Absent context degrades gracefully.
                _ec = sess.get("entity_context")
                if _ec:
                    comp = {**comp, "entity_context": _ec}
                a = risk_assess(comp)
                # Surface the declared per-account intelligence on the verdict so the
                # Node Inspector can show product / KYC / geo / device when provided.
                comp_accounts = comp.get("node_ids") or [n.get("id") for n in comp.get("nodes", [])]
                v["account_intelligence"] = {
                    str(acc): session_account_intel[str(acc)]
                    for acc in comp_accounts if str(acc) in session_account_intel
                } or None
                assessments[v["graph_id"]] = a
                # WIRE CONTRACT: risk_score is a 0–1 FRACTION (the long-standing
                # frontend contract — every consumer renders it as `* 100`). The
                # Risk Engine's canonical 0–100 integer + full explainability ride
                # alongside as dedicated fields. Sending the 0–100 value here as
                # `risk_score` (the previous behaviour) was the "FRAUD 1000%" bug:
                # the frontend multiplied an already-percentage value by 100.
                v["risk_score"] = round(a["score"] / 100.0, 4)   # 0–1 fraction
                v["risk_available"] = True
                v["risk_points"] = a["score"]                    # canonical 0–100 integer
                v["risk_level"] = a["level"]
                v["risk_confidence"] = a["confidence"]            # 0–100 model certainty (≠ risk)
                v["risk_factors"] = a["top_indicators"]
                v["risk_contributors"] = a["factors"]             # [{label, points, max, detail}]
                v["risk_explanation"] = a["explanation"]          # the "Why?" string
                v["profile_intelligence"] = a.get("profile_intelligence")  # per-account customer profiles
                v["cross_bank"] = a.get("cross_bank")             # cross-bank entity intelligence (metadata)
                v["flagged"] = a["should_create_case"]            # alerting follows the risk score
        except Exception as exc:
            logging.getLogger("tgie.ingest").warning("Risk scoring failed: %s", exc)

        # ── Cross-product correlation (Phase 5) ───────────────────────────────
        # Additively attach the cross-product picture (XP rules, typologies,
        # customer risk, recovery) to each verdict. Defensive: never breaks the
        # live path; consumers that ignore `cross_product` are unaffected.
        try:
            from knowledge.blue_team_xp import correlate
            from knowledge import augment_component
            ec = sess.get("entity_context")
            for v in multi_verdicts:
                comp = comp_map.get(v["graph_id"], {})
                if comp:
                    v["cross_product"] = correlate(augment_component(comp, ec))
        except Exception as exc:
            logging.getLogger("tgie.ingest").warning("Cross-product correlation failed: %s", exc)

        # Broadcast per-graph verdicts (now risk-scored) only to this session.
        await broadcaster.broadcast_blue_team_multi_verdict(multi_verdicts, session=session_id)

        # ── Auto-register investigation cases above the risk threshold ────────
        # One qualifying component → one permanent case (deduped by account set,
        # so the ~1s detection heartbeat never creates duplicates). Best-effort.
        try:
            from case_management.store import store as case_store
            registered = []
            for v in multi_verdicts:
                a = assessments.get(v["graph_id"])
                if not a or not a.get("should_create_case"):
                    continue
                comp = comp_map.get(v["graph_id"], {})
                case = case_store.register_from_detection(verdict=v, component=comp, assessment=a)
                if case:
                    registered.append({
                        "case_id": case["case_id"], "title": case["title"],
                        "priority": case["priority"], "risk_score": case["risk_score"],
                        "risk_level": a["level"], "graph_id": v["graph_id"],
                        "account_count": len(case["accounts"]),
                    })
            if registered:
                await broadcaster.broadcast_case_registered(registered, session=session_id)
                logging.getLogger("tgie.ingest").info(
                    "Auto-registered %d investigation case(s) above risk threshold", len(registered))
        except Exception as exc:
            logging.getLogger("tgie.ingest").warning("Auto case registration failed: %s", exc)
        # ── End Blue Team multi-graph analysis ────────────────────────────────

    finally:
        sess["active"] = False


# ── Graph ─────────────────────────────────────────────────────────────────────

@router.get("/api/graph/state", tags=["Graph"])
async def get_graph_state(x_session_id: Optional[str] = Header(None)):
    state = get_app_state()
    sess = get_session(state, _session_id(x_session_id))
    return await sess["graph_manager"].get_graph_state()


@router.get("/api/graph/node/{account_id}", tags=["Graph"])
async def get_node(account_id: str, x_session_id: Optional[str] = Header(None)):
    detail = await _session_graph(x_session_id).get_account_detail(account_id)
    if not detail:
        raise HTTPException(404, f"Account {account_id} not found in graph")
    return detail


@router.get("/api/graph/node/{account_id}/edges", tags=["Graph"])
async def get_node_edges(
    account_id: str,
    limit: int = Query(20, le=100),
    x_session_id: Optional[str] = Header(None),
):
    edges = await _session_graph(x_session_id).get_recent_edges(account_id, limit)
    return {"account_id": account_id, "edges": edges, "count": len(edges)}


@router.get("/api/graph/node/{account_id}/intelligence", tags=["Graph"])
async def node_intelligence(account_id: str, x_session_id: Optional[str] = Header(None)):
    """
    Full investigation intelligence for a single account, computed on demand.

    Runs the Blue Team V2 engine on the account's connected component and returns
    the rich per-node analysis the Inspector renders: role, explainable risk
    factors ("why"), centralities, detected patterns + evidence, the cluster
    verdict/narrative, and upstream-source / downstream-beneficiary money tracing.

    Session-scoped (reads THIS browser's graph), so it works on live session data
    rather than the empty global manager.
    """
    import networkx as nx

    state = get_app_state()
    sess = get_session(state, _session_id(x_session_id))
    components = await sess["graph_manager"].get_connected_components()
    comp = next((c for c in components if account_id in c.get("node_ids", [])), None)
    if comp is None:
        raise HTTPException(404, f"Account {account_id} not found in the current graph")

    # Heavy-ish; run off the event loop so concurrent requests aren't blocked.
    from blue_team_v2.engine import BlueTeamV2Engine
    analysis = await asyncio.to_thread(BlueTeamV2Engine().analyze_component, comp)

    m = analysis.metrics.get(account_id)
    cluster = analysis.cluster

    # ── money-flow tracing on the component subgraph ──────────────────────────
    G = nx.DiGraph()
    for e in comp.get("edges", []):
        s, t = e.get("source"), e.get("target")
        if not s or not t:
            continue
        amt = float(e.get("amount", 0) or 0)
        if G.has_edge(s, t):
            G[s][t]["amount"] += amt
            G[s][t]["count"] += 1
        else:
            G.add_edge(s, t, amount=amt, count=1)

    def _rank(pairs):  # [(node, amount, count)] desc by amount, top 8
        return [{"account": n, "amount": round(a, 2), "transfers": c}
                for n, a, c in sorted(pairs, key=lambda x: x[1], reverse=True)[:8]]

    direct_in = _rank([(s, d["amount"], d["count"]) for s, _, d in G.in_edges(account_id, data=True)]) if account_id in G else []
    direct_out = _rank([(t, d["amount"], d["count"]) for _, t, d in G.out_edges(account_id, data=True)]) if account_id in G else []
    ancestors = nx.ancestors(G, account_id) if account_id in G else set()
    descendants = nx.descendants(G, account_id) if account_id in G else set()

    origins = set(cluster.origin)
    sinks = set(cluster.cashout) | set(cluster.sinks) | set(cluster.terminals)
    # money origin = fraud origins upstream of this node; destination = cash-outs downstream
    upstream_sources = sorted(ancestors & origins) or sorted(origins)[:5]
    downstream_beneficiaries = sorted(descendants & sinks) or sorted(sinks)[:5]

    flagged_in_cluster = set(BlueTeamV2Engine().flagged_nodes(analysis))
    connected_suspicious = sorted((set(comp.get("node_ids", [])) & flagged_in_cluster) - {account_id})

    if m is None:  # isolated node with no edges in the component
        return {
            "account_id": account_id, "graph_id": comp.get("graph_id"),
            "available": False, "reason": "node has no transactional edges",
        }

    total_in = round(m.incoming_volume, 2)
    total_out = round(m.outgoing_volume, 2)
    return {
        "account_id": account_id,
        "graph_id": comp.get("graph_id"),
        "available": True,
        # ── headline ──
        "role": m.cluster_role.value,
        "node_risk": round(m.risk_score, 4),          # 0..1 independent node score
        "node_risk_pct": round(m.risk_score * 100),    # 0..100 for display
        "confidence": round(m.confidence, 4),
        # ── explainable "why": faithful factor shares ──
        "risk_factors": [{"factor": k, "share": v} for k, v in m.contributions.items()],
        # ── centrality / influence ──
        "centrality": {
            "degree": m.degree_centrality,
            "betweenness": m.betweenness_centrality,
            "closeness": m.closeness_centrality,
            "bridge_importance": m.bridge_importance,
        },
        # ── behavioural metrics ──
        "metrics": {
            "transaction_velocity": m.transaction_velocity,
            "transaction_frequency": m.transaction_frequency,
            "incoming_volume": total_in,
            "outgoing_volume": total_out,
            "total_exposure": round(total_in + total_out, 2),
            "fan_in_count": m.fan_in_count,
            "fan_out_count": m.fan_out_count,
            "pass_through_ratio": m.pass_through_ratio,
            "burst_activity": m.burst_activity,
            "dormancy_reactivation": m.dormancy_reactivation,
            "fraud_distance": m.fraud_distance,
            "layer_distance": m.layer_distance,
            "circular_participation": m.circular_participation,
            "risk_inheritance": m.risk_inheritance,
            "pattern_participation": m.pattern_participation,
        },
        # ── patterns + evidence touching THIS node ──
        "patterns": m.patterns,
        "evidence": [
            {"pattern": e.pattern, "title": e.title, "description": e.description,
             "severity": round(e.severity, 3), "confidence": round(e.confidence, 3)}
            for e in analysis.evidence if account_id in e.nodes
        ],
        # ── cluster context ──
        "cluster": {
            "verdict": analysis.verdict.value,
            "cluster_risk": round(analysis.cluster_risk, 4),
            "primary_classification": analysis.primary_classification,
            "secondary_classification": analysis.secondary_classification,
            "narrative": analysis.narrative,
            "node_count": len(comp.get("node_ids", [])),
        },
        # ── money-flow intelligence ──
        "flow": {
            "direct_inflows": direct_in,
            "direct_outflows": direct_out,
            "upstream_sources": upstream_sources,
            "downstream_beneficiaries": downstream_beneficiaries,
            "upstream_count": len(ancestors),
            "downstream_count": len(descendants),
        },
        "connected_suspicious": connected_suspicious,
    }


@router.get("/api/graph/traverse/bfs/{account_id}", tags=["Graph"])
async def bfs_traverse(
    account_id: str,
    depth: int = Query(3, ge=1, le=6),
    x_session_id: Optional[str] = Header(None),
):
    path = await _session_graph(x_session_id).bfs(account_id, max_depth=depth)
    return {"origin": account_id, "visited": path, "depth": depth, "algorithm": "BFS"}


@router.get("/api/graph/traverse/dfs/{account_id}", tags=["Graph"])
async def dfs_traverse(
    account_id: str,
    depth: int = Query(4, ge=1, le=7),
    x_session_id: Optional[str] = Header(None),
):
    path = await _session_graph(x_session_id).dfs(account_id, max_depth=depth)
    return {"origin": account_id, "visited": path, "depth": depth, "algorithm": "DFS"}


@router.get("/api/graph/path/{source}/{target}", tags=["Graph"])
async def shortest_path(source: str, target: str, x_session_id: Optional[str] = Header(None)):
    path = await _session_graph(x_session_id).shortest_path(source, target)
    if not path:
        raise HTTPException(404, f"No path from {source} to {target}")
    return {"source": source, "target": target, "path": path, "hops": len(path) - 1}


@router.get("/api/graph/cycles", tags=["Graph"])
async def detect_cycles(account_id: Optional[str] = None, x_session_id: Optional[str] = Header(None)):
    cycles = await _session_graph(x_session_id).detect_cycles(account_id)
    return {"cycles": cycles, "count": len(cycles), "account_filter": account_id}


@router.get("/api/graph/communities", tags=["Graph"])
async def get_communities(x_session_id: Optional[str] = Header(None)):
    communities = await _session_graph(x_session_id).detect_communities()
    comm_groups: dict = {}
    for node, cid in communities.items():
        comm_groups.setdefault(str(cid), []).append(node)
    return {
        "community_count": len(comm_groups),
        "communities": comm_groups,
        "node_membership": communities,
    }


@router.get("/api/graph/layout", tags=["Graph"])
async def graph_layout(
    mode: str = Query("auto", description="auto (backend chooses) | force | fund_flow | layered | community | timeline"),
    x_session_id: Optional[str] = Header(None),
):
    """
    Server-computed node coordinates for THIS session's graph.

    Default `mode=auto` lets the BACKEND pick the most investigation-appropriate
    layout from the graph's structure (the investigator never chooses an
    algorithm); the response carries `selection_reason`. An explicit mode is
    still accepted for tooling. Additive — the live WebSocket broadcast is
    unchanged.
    """
    from graph_engine.layout import compute_layout, LAYOUT_MODES

    if mode != "auto" and mode not in LAYOUT_MODES:
        raise HTTPException(400, f"Unknown layout mode '{mode}'. Valid: auto, {', '.join(LAYOUT_MODES)}")

    state = get_app_state()
    sess = get_session(state, _session_id(x_session_id))
    graph_state = await sess["graph_manager"].get_graph_state()
    result = compute_layout(graph_state.get("nodes", []), graph_state.get("edges", []), mode=mode)
    result["available_modes"] = list(LAYOUT_MODES)
    return result


@router.get("/api/rules", tags=["Detection"])
async def rule_catalog():
    """The reusable AML rule catalogue (AML001 …) every detection maps to."""
    from rule_engine import RULES
    return {"rules": [{"rule_id": rid, **meta} for rid, meta in RULES.items()], "count": len(RULES)}


@router.get("/api/graph/motifs", tags=["Detection"])
async def graph_motifs(
    graph_id: Optional[str] = Query(None, description="restrict to one component"),
    x_session_id: Optional[str] = Header(None),
):
    """
    Explicit fraud-motif objects across THIS session's graph. Each motif carries
    its nodes, the sub-graph edges forming it, the AML rule(s) it triggered,
    structured evidence and a plain-language explanation — so every alert is
    traceable to a rule and its supporting evidence.
    """
    from rule_engine import extract_motifs

    sess = get_session(get_app_state(), _session_id(x_session_id))
    components = await sess["graph_manager"].get_connected_components()
    if graph_id:
        components = [c for c in components if c.get("graph_id") == graph_id.upper()]

    def _all():
        out = []
        for c in components:
            out.extend(extract_motifs(c))
        return out

    motifs = await asyncio.to_thread(_all)
    counts: dict = {}
    for m in motifs:
        counts[m["pattern"]] = counts.get(m["pattern"], 0) + 1
    return {"motifs": motifs, "count": len(motifs), "by_pattern": counts}


@router.get("/api/graph/case-summary", tags=["Detection"])
async def graph_case_summary(
    graph_id: Optional[str] = Query(None, description="restrict to one component"),
    x_session_id: Optional[str] = Header(None),
):
    """
    Auto-generated investigation case summary per fraud cluster: exposure,
    suspicious amount, money origin → final beneficiary, layering depth, fraud
    patterns, highest-risk entity, narrative, and prioritised recommended
    actions. Everything an analyst (or evaluator) needs to read a case at a glance.
    """
    from case_intelligence import build_case_summary

    sess = get_session(get_app_state(), _session_id(x_session_id))
    components = await sess["graph_manager"].get_connected_components()
    if graph_id:
        components = [c for c in components if c.get("graph_id") == graph_id.upper()]

    def _all():
        # Only summarise components that actually carry transactions.
        return [build_case_summary(c) for c in components if c.get("edges")]

    summaries = await asyncio.to_thread(_all)
    return {"cases": summaries, "count": len(summaries)}


@router.get("/api/graph/analytics", tags=["Graph"])
async def graph_analytics(
    top: int = Query(10, ge=1, le=50),
    x_session_id: Optional[str] = Header(None),
):
    """
    Full network analytics for THIS session's graph: influence ranking
    (PageRank / HITS / eigenvector / betweenness), density + component structure
    (SCC / WCC / bridges / cut vertices), degree distribution, and fund-flow
    rankings (top sources, beneficiaries, aggregators, distributors).

    Computed off the event loop. Everything is backend-derived — the frontend
    only renders these rankings.
    """
    from graph_engine.analytics import compute_analytics

    sess = get_session(get_app_state(), _session_id(x_session_id))
    gs = await sess["graph_manager"].get_graph_state()
    return await asyncio.to_thread(compute_analytics, gs.get("nodes", []), gs.get("edges", []), top)


@router.get("/api/graph/paths/{source}/{target}", tags=["Graph"])
async def graph_paths(
    source: str,
    target: str,
    cutoff: int = Query(8, ge=1, le=12),
    x_session_id: Optional[str] = Header(None),
):
    """
    Money-path intelligence between two accounts: the shortest, highest-risk,
    largest-value and bottleneck paths — so an investigator can answer "how did
    the money get from A to B, and which route carried the most / the riskiest".
    """
    from graph_engine.analytics import analyze_paths

    sess = get_session(get_app_state(), _session_id(x_session_id))
    gs = await sess["graph_manager"].get_graph_state()
    result = await asyncio.to_thread(
        analyze_paths, gs.get("nodes", []), gs.get("edges", []), source, target, cutoff
    )
    if not result.get("available"):
        raise HTTPException(404, result.get("reason", "path analysis unavailable"))
    return result


@router.get("/api/graph/community-intelligence", tags=["Graph"])
async def graph_community_intelligence(
    top: int = Query(25, ge=1, le=100),
    x_session_id: Optional[str] = Header(None),
):
    """
    Per-community intelligence for THIS session's graph: for each detected
    community its leader (highest internal influence), entry points (funded from
    outside), exit points (paying outside / cashing out), internal vs boundary
    money volume, dominant role, and a 0–1 risk score. Communities are returned
    strongest-risk first. Computed off the event loop; backend-derived only.
    """
    from graph_engine.community_intelligence import analyze_communities

    sess = get_session(get_app_state(), _session_id(x_session_id))
    gs = await sess["graph_manager"].get_graph_state()
    return await asyncio.to_thread(
        analyze_communities, gs.get("nodes", []), gs.get("edges", []), top
    )


@router.get("/api/graph/timeline", tags=["Graph"])
async def graph_timeline(
    bucket_minutes: int = Query(60, ge=1, le=1440),
    x_session_id: Optional[str] = Header(None),
):
    """
    Temporal rollup of THIS session's transactions: activity span, hour-of-day
    and day-of-week distribution, night / weekend concentration, transfer
    velocity (avg + peak), detected bursts, and the AML behaviour rules these
    observations trigger. Backend-derived; the frontend only renders it.
    """
    from graph_engine.timeline import summarize_timeline

    sess = get_session(get_app_state(), _session_id(x_session_id))
    gs = await sess["graph_manager"].get_graph_state()
    return await asyncio.to_thread(summarize_timeline, gs.get("edges", []), bucket_minutes)


@router.get("/api/graph/flow-narrative", tags=["Graph"])
async def graph_flow_narrative(
    max_routes: int = Query(5, ge=1, le=20),
    x_session_id: Optional[str] = Header(None),
):
    """
    Plain-language money-trail narration for THIS session's graph: the most-
    layered route (deepest forwarding chain) and the cash-out routes (highest-
    value paths from an entry source to a terminal / cash-out sink), each with
    hop count, value, triggered AML rules and a narrative an analyst can read.
    """
    from graph_engine.analytics import narrate_flows

    sess = get_session(get_app_state(), _session_id(x_session_id))
    gs = await sess["graph_manager"].get_graph_state()
    return await asyncio.to_thread(
        narrate_flows, gs.get("nodes", []), gs.get("edges", []), max_routes
    )


@router.get("/api/knowledge", tags=["Knowledge"])
async def knowledge_base():
    """
    The Union Bank cross-product knowledge base inventory: products, channels,
    fraud typologies, the XP cross-product rule family and regulatory frameworks.
    Reference data the Blue Team / recovery / rule engines consult.
    """
    from knowledge import KB
    return KB.summary()


@router.get("/api/graph/cross-product", tags=["Graph"])
async def graph_cross_product(
    graph_id: Optional[str] = Query(None, description="restrict to one component"),
    x_session_id: Optional[str] = Header(None),
):
    """
    Cross-product fraud intelligence for THIS session's graph: per component, the
    product categories / channels / identities it spans, the XP rules it trips,
    the named laundering typologies it matches, product-aware recovery actions,
    and regulatory hooks. Detects fraud SPANNING products rather than per-account.
    Computed off the event loop; additive (existing endpoints unchanged).
    """
    from knowledge import cross_product_report, augment_component

    sess = get_session(get_app_state(), _session_id(x_session_id))
    ec = sess.get("entity_context")
    components = await sess["graph_manager"].get_connected_components()
    if graph_id:
        components = [c for c in components if c.get("graph_id") == graph_id.upper()]

    def _all():
        reports = [cross_product_report(augment_component(c, ec)) for c in components if c.get("edges")]
        return [r for r in reports if r["is_cross_product"] or r["xp_signals"]]

    reports = await asyncio.to_thread(_all)
    return {"reports": reports, "count": len(reports)}


@router.get("/api/graph/customer-risk", tags=["Graph"])
async def graph_customer_risk(
    graph_id: Optional[str] = Query(None, description="restrict to one component"),
    x_session_id: Optional[str] = Header(None),
):
    """
    Unified customer risk graph for THIS session's graph: per component, risk for
    customers / products / devices / merchants / identities / channels — each with
    why, evidence, related entities, propagation path, confidence and triggered XP
    rules. Customer risk propagates from owned products and shared identities.
    """
    from knowledge import compute_customer_risk, augment_component

    sess = get_session(get_app_state(), _session_id(x_session_id))
    ec = sess.get("entity_context")
    components = await sess["graph_manager"].get_connected_components()
    if graph_id:
        components = [c for c in components if c.get("graph_id") == graph_id.upper()]

    def _all():
        reports = [compute_customer_risk(augment_component(c, ec)) for c in components if c.get("edges")]
        return [r for r in reports if r["available"]]

    reports = await asyncio.to_thread(_all)
    return {"reports": reports, "count": len(reports)}


@router.get("/api/graph/customer-investigation/{account_id}", tags=["Graph"])
async def graph_customer_investigation(
    account_id: str,
    x_session_id: Optional[str] = Header(None),
):
    """
    Unified single-customer investigation report (Phase 8) for the component
    containing this account/customer: profile, owned + connected products, device
    & identity intelligence, merchant relationships, cross-product flows, money
    trails, fraud motifs, triggered XP rules, timeline, community, recommendations
    and a plain-language narrative. One ecosystem view, not one account.
    """
    from knowledge.investigation import build_customer_investigation
    from knowledge import augment_component

    sess = get_session(get_app_state(), _session_id(x_session_id))
    components = await sess["graph_manager"].get_connected_components()
    comp = next((c for c in components if account_id in c.get("node_ids", [])), None)
    if comp is None:
        raise HTTPException(404, f"Account {account_id} not found in the current graph")
    comp = augment_component(comp, sess.get("entity_context"))
    return await asyncio.to_thread(build_customer_investigation, comp, account_id)


class LearningApply(BaseModel):
    threshold: str
    value: float


@router.get("/api/knowledge/learning", tags=["Knowledge"])
async def learning_status():
    """Current adaptive XP thresholds, defaults, change history, and the Blue
    Team's coverage of the baseline battery + emerging attacks."""
    from knowledge.learning import status
    return await asyncio.to_thread(status)


@router.get("/api/knowledge/learning/propose", tags=["Knowledge"])
async def learning_propose():
    """Run the Red Team→Blue Team learning loop and STAGE threshold proposals that
    close detection gaps on emerging attacks (gated by zero false positives).
    Nothing is applied — proposals await investigator approval."""
    from knowledge.learning import propose_adaptations
    return await asyncio.to_thread(propose_adaptations)


@router.post("/api/knowledge/learning/apply", tags=["Knowledge"])
async def learning_apply(req: LearningApply):
    """Investigator-approved apply of a learning proposal. Re-validates the gate
    (no battery regression, no false positives, above safety floor) before
    committing — an approval can never weaken Blue Team unsafely."""
    from knowledge.learning import apply_proposal
    result = await asyncio.to_thread(apply_proposal, req.threshold, req.value)
    if not result.get("applied"):
        raise HTTPException(409, result.get("reason", "proposal rejected by the learning gate"))
    return result


@router.get("/api/knowledge/red-team-eval", tags=["Knowledge"])
async def red_team_eval():
    """
    Run the Red Team cross-product attack battery against the Blue Team and report
    detection coverage + that legitimate activity yields no false positives.
    """
    from knowledge.red_team import evaluate_blue_team
    return await asyncio.to_thread(evaluate_blue_team)


@router.get("/api/knowledge/scenarios", tags=["Knowledge"])
async def list_scenarios():
    """Names of the synthetic cross-product scenarios available for demo/testing."""
    from knowledge import scenarios
    return {"scenarios": sorted(scenarios.SCENARIOS), "count": len(scenarios.SCENARIOS)}


@router.get("/api/knowledge/scenarios/{name}", tags=["Knowledge"])
async def get_scenario(name: str):
    """
    Generate a synthetic heterogeneous cross-product graph and return it together
    with its cross-product report and unified customer-risk graph — so the
    cross-product intelligence can be exercised without live multi-product data.
    """
    from knowledge import scenarios, cross_product_report, compute_customer_risk

    try:
        component = scenarios.generate(name)
    except KeyError:
        raise HTTPException(404, f"Unknown scenario '{name}'. Valid: {', '.join(sorted(scenarios.SCENARIOS))}")

    def _build():
        return {
            "component": component,
            "cross_product": cross_product_report(component),
            "customer_risk": compute_customer_risk(component),
        }

    return await asyncio.to_thread(_build)


@router.get("/api/graph/trace/{account_id}", tags=["Graph"])
async def multi_hop_trace(
    account_id: str,
    hops: int = Query(4, ge=1, le=6),
    min_risk: float = Query(0.5, ge=0.0, le=1.0),
    x_session_id: Optional[str] = Header(None),
):
    paths = await _session_graph(x_session_id).multi_hop_trace(account_id, hops, min_risk)
    return {"origin": account_id, "paths": paths, "count": len(paths)}


# ── Alerts ────────────────────────────────────────────────────────────────────

@router.get("/api/alerts", tags=["Alerts"])
async def get_alerts(limit: int = Query(50, le=200)):
    state = get_app_state()
    alerts = list(state.get("alert_history", []))
    return {"alerts": alerts[-limit:], "total": len(alerts)}


@router.get("/api/alerts/stats", tags=["Alerts"])
async def alert_stats():
    state = get_app_state()
    alerts = list(state.get("alert_history", []))
    by_type: dict = {}
    by_severity: dict = {}
    for a in alerts:
        t = a.get("alert_type", "unknown")
        s = a.get("severity", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
        by_severity[s] = by_severity.get(s, 0) + 1
    return {"total_alerts": len(alerts), "by_type": by_type, "by_severity": by_severity}


# ── Statistics ────────────────────────────────────────────────────────────────

@router.get("/api/stats", tags=["Stats"])
async def get_stats(x_session_id: Optional[str] = Header(None)):
    state = get_app_state()
    graph_mgr = _session_graph(x_session_id)
    flink = state.get("flink_processor")
    detector = state.get("anomaly_detector")
    gnn = state.get("gnn_manager")
    xgb_clf = state.get("xgboost_classifier")

    graph_stats = {}
    if graph_mgr:
        gs = await graph_mgr.get_graph_state()
        graph_stats = gs.get("stats", {})

    return {
        "graph": graph_stats,
        "streaming": flink.get_global_stats() if flink else {},
        "anomaly_detector": detector.get_status() if detector else {},
        "xgboost_classifier": xgb_clf.get_status() if xgb_clf else {},
        "gnn": gnn.get_status() if gnn else {},
        "simulation": {
            "running": False,
            "mode": "manual",
        },
        "websocket": {"connections": state.get("ws_connections", 0)},
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Simulation Control (legacy) ───────────────────────────────────────────────

@router.post("/api/simulation/control", tags=["Simulation"])
async def control_simulation(cmd: SimulationControl):
    return {"action": cmd.action, "status": "manual-mode — use /transaction/manual"}


# ── Replay ────────────────────────────────────────────────────────────────────

@router.get("/api/replay/recent", tags=["Replay"])
async def get_recent_transactions(limit: int = Query(100, le=500)):
    state = get_app_state()
    history = list(state.get("transaction_history", []))
    sliced = history[-limit:]
    return {"transactions": sliced, "count": len(sliced), "total_stored": len(history)}


# ── Evidence Generation ───────────────────────────────────────────────────────

class EvidenceRequest(BaseModel):
    graph_id: str


@router.post("/api/evidence/generate", tags=["Evidence"])
async def generate_evidence(req: EvidenceRequest):
    """
    Generate a fraud investigation evidence package (JSON + PDF) for the
    requested graph component.  Must be called after Blue Team analysis.
    """
    state = get_app_state()
    graph_id = req.graph_id.upper()

    verdicts   = state.get("latest_blue_team_verdicts", {})
    components = state.get("latest_graph_components", {})

    verdict   = verdicts.get(graph_id)
    component = components.get(graph_id)

    if not verdict:
        raise HTTPException(
            404,
            f"No Blue Team verdict found for {graph_id}. "
            "Run a simulation first.",
        )
    if not component:
        raise HTTPException(
            404,
            f"No graph component snapshot found for {graph_id}.",
        )

    graph_mgr = state.get("graph_manager")
    if not graph_mgr:
        raise HTTPException(503, "Graph engine not initialised")

    node_ids    = component.get("node_ids", [])
    cash_events = await graph_mgr.get_cash_events_for_accounts(node_ids)

    gen      = EvidenceGenerator()
    evidence = gen.generate(
        verdict=verdict,
        nodes=component.get("nodes", []),
        edges=component.get("edges", []),
        cash_events=cash_events,
    )

    date_str      = datetime.utcnow().strftime("%Y-%m-%d")
    json_filename = f"evidence_{graph_id}_{date_str}.json"
    pdf_filename  = f"evidence_{graph_id}_{date_str}.pdf"
    json_path     = os.path.join(_EVIDENCE_DIR, json_filename)
    pdf_path      = os.path.join(_EVIDENCE_DIR, pdf_filename)

    with open(json_path, "w") as fh:
        json.dump(evidence, fh, indent=2, default=str)

    pdf_ok = build_pdf(evidence, pdf_path)

    return {
        "success": True,
        "graph_id": graph_id,
        "json_filename": json_filename,
        "pdf_filename": pdf_filename if pdf_ok else None,
        "json_url": f"/api/evidence/download/{json_filename}",
        "pdf_url": f"/api/evidence/download/{pdf_filename}" if pdf_ok else None,
        "pdf_available": pdf_ok,
        "summary": {
            "case_id": evidence["case_id"],
            "fraud_type": evidence["fraud_metadata"]["fraud_type"],
            "total_amount": evidence["fraud_details"]["amounts"][
                "total_suspicious_amount"
            ],
            "accounts_count": len(
                evidence["fraud_details"]["accounts_involved"]
            ),
        },
    }


@router.get("/api/evidence/download/{filename}", tags=["Evidence"])
async def download_evidence(filename: str):
    """Download a previously generated evidence file (JSON or PDF)."""
    if not _EVIDENCE_FILENAME_RE.match(filename):
        raise HTTPException(400, "Invalid evidence filename")

    filepath = os.path.join(_EVIDENCE_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(404, f"Evidence file not found: {filename}")

    media_type = (
        "application/pdf"
        if filename.endswith(".pdf")
        else "application/json"
    )
    return FileResponse(filepath, filename=filename, media_type=media_type)


@router.get("/api/evidence/list", tags=["Evidence"])
async def list_evidence():
    """List all previously generated evidence files."""
    files = []
    for fname in os.listdir(_EVIDENCE_DIR):
        if _EVIDENCE_FILENAME_RE.match(fname):
            fpath = os.path.join(_EVIDENCE_DIR, fname)
            files.append({
                "filename": fname,
                "url": f"/api/evidence/download/{fname}",
                "size_bytes": os.path.getsize(fpath),
                "created_at": datetime.utcfromtimestamp(
                    os.path.getctime(fpath)
                ).isoformat() + "Z",
            })
    files.sort(key=lambda f: f["created_at"], reverse=True)
    return {"files": files, "count": len(files)}
