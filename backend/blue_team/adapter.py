"""
Blue Team adapter — translates the Graph Engine's graph snapshot into
individual Blue Team /api/v1/score calls and aggregates per-transaction
results into a single graph-level fraud verdict.

Never modifies Blue Team source code.  All Blue Team communication happens
via its public HTTP API using the x-api-key authentication it already requires.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone

import httpx

log = logging.getLogger(__name__)

# Action severity ranking for aggregation
_ACTION_RANK: dict[str, int] = {"PASS": 0, "LOG": 1, "REVIEW": 2, "HIGH_RISK": 3}

# Concurrency guard — prevents flooding Blue Team with a huge graph
_SEMAPHORE = asyncio.Semaphore(6)

_TXN_ID_RE = re.compile(r"[^a-zA-Z0-9_\-]")


def _sanitize_txn_id(raw: str) -> str:
    """Strip chars not allowed by Blue Team's transaction_id pattern."""
    clean = _TXN_ID_RE.sub("", raw)[:36]
    return clean or "TXN-GRAPH"


def _edge_to_request(edge: dict) -> dict | None:
    """Convert a graph snapshot edge to a Blue Team TransactionScoreRequest dict."""
    try:
        amount = float(edge.get("amount", 0))
        if amount <= 0 or amount >= 100_000_000:
            return None

        channel = str(edge.get("payment_rail", "UPI")).upper()
        if channel not in ("UPI", "IMPS", "RTGS", "NEFT"):
            channel = "UPI"

        ts_raw = edge.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_raw) if ts_raw else datetime.now(timezone.utc)
        except ValueError:
            ts = datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if ts > now:
            ts = now

        txn_id = _sanitize_txn_id(str(edge.get("id", f"{edge.get('source')}-{edge.get('target')}")))
        account_id = str(edge.get("source", "UNKNOWN"))[:20]
        payee_id = str(edge.get("target", "UNKNOWN"))[:20]

        return {
            "transaction_id": txn_id,
            "account_id": account_id,
            "payee_account_id": payee_id,
            "amount": str(round(amount, 2)),
            "channel": channel,
            "timestamp": ts.isoformat(),
        }
    except Exception as exc:
        log.debug("Edge-to-request mapping failed: %s", exc)
        return None


async def _score_one(client: httpx.AsyncClient, body: dict, blue_team_url: str, api_key: str) -> dict | None:
    """POST one transaction to Blue Team. Returns result dict or None on failure."""
    async with _SEMAPHORE:
        try:
            resp = await client.post(
                f"{blue_team_url}/api/v1/score",
                json=body,
                headers={"x-api-key": api_key},
                timeout=8.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "transaction_id": data.get("transaction_id"),
                    "score": float(data.get("score", 0.0)),
                    "action": data.get("action", "PASS"),
                    "gate_fired": data.get("gate_fired"),
                    "source": body.get("account_id"),
                    "target": body.get("payee_account_id"),
                }
            log.warning("Blue Team HTTP %s for txn %s", resp.status_code, body.get("transaction_id"))
        except httpx.TimeoutException:
            log.warning("Blue Team timeout for txn %s", body.get("transaction_id"))
        except Exception as exc:
            log.debug("Blue Team call error: %s", exc)
    return None


def _aggregate(scored: list[dict]) -> dict:
    """Fold per-transaction results into one graph-level verdict."""
    if not scored:
        return {
            "status": "analyzed",
            "verdict": "CLEAN",
            "score": 0.0,
            "action": "PASS",
            "confidence": 0,
            "flagged_nodes": [],
            "suspicious_reason": None,
            "transactions_scored": 0,
        }

    worst = max(scored, key=lambda r: _ACTION_RANK.get(r.get("action", "PASS"), 0))
    max_score = max(r.get("score", 0.0) for r in scored)

    flagged_nodes: set[str] = set()
    reasons: list[str] = []
    for r in scored:
        if r.get("action") in ("REVIEW", "HIGH_RISK"):
            for acct in (r.get("source"), r.get("target")):
                if acct:
                    flagged_nodes.add(acct)
            if r.get("gate_fired"):
                reasons.append(r["gate_fired"])

    action = worst.get("action", "PASS")
    verdict = (
        "FRAUD" if action == "HIGH_RISK"
        else "SUSPICIOUS" if action == "REVIEW"
        else "LOGGED" if action == "LOG"
        else "CLEAN"
    )

    return {
        "status": "analyzed",
        "verdict": verdict,
        "score": round(max_score, 4),
        "action": action,
        "confidence": int(max_score * 100),
        "flagged_nodes": list(flagged_nodes),
        "suspicious_reason": (
            reasons[0] if reasons
            else "ML ensemble" if max_score > 0.38
            else None
        ),
        "transactions_scored": len(scored),
    }


async def analyze_component(
    component: dict,
    blue_team_url: str,
    api_key: str,
) -> dict:
    """
    Analyze one disconnected graph component independently through Blue Team.

    Accepts a component dict from TransactionGraphManager.get_connected_components():
      { graph_id, node_ids, nodes, edges }

    Returns a per-graph verdict dict:
      { graph_id, status, verdict, risk_score, flagged, flagged_nodes,
        suspicious_reason, transactions_scored, nodes }
    """
    from blue_team.standalone import analyze_standalone_component

    graph_id: str = component.get("graph_id", "GRAPH_001")
    edges: list[dict] = component.get("edges", [])
    node_ids: list[str] = component.get("node_ids", [])

    if not edges:
        return {
            "graph_id": graph_id,
            "status": "no_data",
            "verdict": "CLEAN",
            "risk_score": 0.0,
            "flagged": False,
            "flagged_nodes": [],
            "suspicious_reason": None,
            "transactions_scored": 0,
            "nodes": node_ids,
        }

    # Probe Blue Team HTTP
    blue_team_available = False
    try:
        async with httpx.AsyncClient() as probe:
            health = await probe.get(f"{blue_team_url}/health", timeout=2.0)
            blue_team_available = health.status_code in (200, 204)
    except Exception:
        pass

    if blue_team_available:
        async with httpx.AsyncClient() as client:
            async with _SEMAPHORE:
                try:
                    payload = {
                        "graph_id": graph_id,
                        "nodes": component.get("nodes", []),
                        "edges": edges,
                    }
                    resp = await client.post(
                        f"{blue_team_url}/api/v1/analyze-graph",
                        json=payload,
                        headers={"x-api-key": api_key},
                        timeout=12.0,
                    )
                    if resp.status_code == 200:
                        result = resp.json()
                        verdict = result.get("verdict", "CLEAN")
                        return {
                            "graph_id": graph_id,
                            "status": "analyzed",
                            "verdict": verdict,
                            "risk_score": result.get("fraud_score", 0.0),
                            "flagged": result.get("flagged", False),
                            "flagged_nodes": result.get("flagged_nodes", []),
                            "suspicious_reason": result.get("fraud_type") if verdict != "CLEAN" else None,
                            "transactions_scored": result.get("transactions_scored", 0),
                            "nodes": node_ids,
                            "mode": "blue_team_api",
                        }
                    log.warning("Blue Team /analyze-graph HTTP %s", resp.status_code)
                except httpx.TimeoutException:
                    log.warning("Blue Team /analyze-graph timeout for %s", graph_id)
                except Exception as exc:
                    log.debug("Blue Team /analyze-graph error: %s", exc)

    # Fallback: standalone graph analyzer
    log.info("Blue Team HTTP offline for %s — running standalone analyzer", graph_id)
    sa = analyze_standalone_component(component)
    return {
        "graph_id": graph_id,
        "status": "analyzed",
        "verdict": sa["verdict"],
        "risk_score": sa["score"],
        "flagged": sa["verdict"] in ("FRAUD", "SUSPICIOUS"),
        "flagged_nodes": sa["flagged_nodes"],
        "suspicious_reason": sa["suspicious_reason"],
        "transactions_scored": sa["transactions_scored"],
        "nodes": node_ids,
        "mode": "standalone",
    }


async def analyze_all_components(
    components: list[dict],
    blue_team_url: str,
    api_key: str,
) -> list[dict]:
    """
    Analyze every disconnected graph component independently.

    Each component is scored through Blue Team in parallel (within the
    existing semaphore limits). Returns a list of per-graph verdict dicts
    in the same order as the input components.
    """
    if not components:
        return []
    tasks = [analyze_component(c, blue_team_url, api_key) for c in components]
    return list(await asyncio.gather(*tasks))


async def analyze_graph(graph_snapshot: dict, blue_team_url: str, api_key: str) -> dict:
    """
    Entry point called by the Graph Engine after each manual simulation completes.

    Primary path: calls Blue Team's /api/v1/score HTTP API for each graph edge.
    Fallback path: runs the built-in standalone analyzer when Blue Team is offline.
    Both paths return the same verdict schema.
    """
    from blue_team.standalone import analyze_standalone

    edges: list[dict] = graph_snapshot.get("edges", [])
    if not edges:
        return {
            "status": "no_data",
            "verdict": "CLEAN",
            "score": 0.0,
            "action": "PASS",
            "confidence": 0,
            "flagged_nodes": [],
            "suspicious_reason": None,
            "transactions_scored": 0,
        }

    requests = [r for e in edges if (r := _edge_to_request(e)) is not None]

    # ── Try Blue Team HTTP service first ─────────────────────────────────────
    blue_team_available = False
    try:
        async with httpx.AsyncClient() as probe:
            health = await probe.get(f"{blue_team_url}/health", timeout=2.0)
            blue_team_available = health.status_code in (200, 204)
    except Exception:
        blue_team_available = False

    if blue_team_available and requests:
        log.info("Blue Team HTTP: scoring %d transactions (sequential)", len(requests))
        # Sequential scoring ensures each transaction is committed to the Blue Team DB
        # before the next leg is scored — required for PG-based cycle/bipartite detection.
        async with httpx.AsyncClient() as client:
            scored = []
            for req in requests:
                result = await _score_one(client, req, blue_team_url, api_key)
                if result:
                    scored.append(result)
        if scored:
            result = _aggregate(scored)
            log.info("Blue Team HTTP verdict=%s score=%.3f", result["verdict"], result["score"])
            return result

    # ── Fallback: standalone graph analyzer (no external dependencies) ────────
    log.info("Blue Team HTTP offline — running standalone graph analyzer")
    return analyze_standalone(graph_snapshot)
