"""
Shadow Mode — run the SAME graph through both engines simultaneously and return
both sets of results side-by-side for comparison.

Neither engine is modified. V1 is invoked through its own public adapter exactly
as production does; V2 through its in-process adapter. The output is a single
comparison object that the Graph Validation Panel and the UB AI assistant can
render to compare accuracy, explanations, classifications, confidence, and
pattern detection.
"""
from __future__ import annotations

import asyncio
import logging
import time

log = logging.getLogger(__name__)


async def _run_v1(components, blue_team_url, api_key):
    t0 = time.perf_counter()
    try:
        from blue_team.adapter import analyze_all_components as v1
        results = await v1(components, blue_team_url, api_key)
    except Exception as exc:  # V1 offline must never break shadow comparison
        log.warning("Shadow V1 failed: %s", exc)
        results = [{"graph_id": c.get("graph_id"), "status": "error", "verdict": "UNKNOWN",
                    "risk_score": 0.0, "flagged": False, "flagged_nodes": [],
                    "suspicious_reason": str(exc), "transactions_scored": 0,
                    "nodes": c.get("node_ids", [])} for c in (components or [])]
    return results, (time.perf_counter() - t0) * 1000


async def _run_v2(components):
    t0 = time.perf_counter()
    from blue_team_v2.adapter import analyze_all_components as v2
    results = await v2(components)
    return results, (time.perf_counter() - t0) * 1000


def _index(results: list[dict]) -> dict[str, dict]:
    return {r.get("graph_id", f"G{i}"): r for i, r in enumerate(results or [])}


def _verdict_rank(v: str) -> int:
    return {"CLEAN": 0, "LOGGED": 1, "SUSPICIOUS": 2, "FRAUD": 3, "UNKNOWN": -1}.get(v, 0)


async def run_shadow(components: list[dict], blue_team_url: str = "", api_key: str = "") -> dict:
    """
    Process one graph (its components) through both engines concurrently.

    Returns:
        {
          "v1": {...summary...},
          "v2": {...summary...},
          "comparison": [ per-graph diffs ],
          "agreement": {...},
        }
    """
    (v1_results, v1_ms), (v2_results, v2_ms) = await asyncio.gather(
        _run_v1(components, blue_team_url, api_key),
        _run_v2(components),
    )

    v1_idx, v2_idx = _index(v1_results), _index(v2_results)
    graph_ids = sorted(set(v1_idx) | set(v2_idx))

    comparison: list[dict] = []
    agree = 0
    for gid in graph_ids:
        a = v1_idx.get(gid, {})
        b = v2_idx.get(gid, {})
        v1v = a.get("verdict", "UNKNOWN")
        v2v = b.get("verdict", "UNKNOWN")
        same = v1v == v2v
        agree += int(same)
        b_v2 = b.get("v2", {})
        comparison.append({
            "graph_id": gid,
            "agreement": same,
            "v1": {
                "verdict": v1v,
                "risk_score": a.get("risk_score", 0.0),
                "flagged_nodes": a.get("flagged_nodes", []),
                "reason": a.get("suspicious_reason"),
                "mode": a.get("mode"),
            },
            "v2": {
                "verdict": v2v,
                "risk_score": b.get("risk_score", 0.0),
                "confidence": b_v2.get("confidence"),
                "flagged_nodes": b.get("flagged_nodes", []),
                "primary_classification": b_v2.get("primary_classification"),
                "secondary_classification": b_v2.get("secondary_classification"),
                "patterns": (b_v2.get("cluster_intelligence") or {}).get("patterns_detected", []),
                "narrative": b_v2.get("narrative"),
                "contributors": b_v2.get("contributors", []),
            },
            "delta_risk": round(b.get("risk_score", 0.0) - a.get("risk_score", 0.0), 4),
            "v2_more_severe": _verdict_rank(v2v) > _verdict_rank(v1v),
        })

    return {
        "v1": {"engine": "blue_team_v1", "results": v1_results, "time_ms": round(v1_ms, 2),
               "graphs": len(v1_results or [])},
        "v2": {"engine": "blue_team_v2", "results": v2_results, "time_ms": round(v2_ms, 2),
               "graphs": len(v2_results or [])},
        "comparison": comparison,
        "agreement": {
            "graphs": len(graph_ids),
            "agreed": agree,
            "rate": round(agree / len(graph_ids), 4) if graph_ids else 1.0,
        },
    }
