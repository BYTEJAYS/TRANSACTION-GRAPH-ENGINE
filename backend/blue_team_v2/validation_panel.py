"""
Graph Validation Panel — developer-facing comparison metrics for a run.

Builds the data the comparison panel displays:
  Active Engine · Nodes Processed · Clusters Found · Fraud Nodes ·
  Patterns Detected · Risk Distribution · Confidence Distribution ·
  Execution Time · Memory Usage · Fraud Classifications

Works for a single engine's output, or for a shadow run (both engines).
"""
from __future__ import annotations

from collections import Counter

try:
    import resource

    def _peak_memory_mb() -> float:
        kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # ru_maxrss is bytes on macOS, kilobytes on Linux
        import sys
        return round(kb / (1024 * 1024 if sys.platform == "darwin" else 1024), 2)
except Exception:  # pragma: no cover
    def _peak_memory_mb() -> float:
        return 0.0


_RISK_BANDS = [("clean", 0.0, 0.38), ("logged", 0.38, 0.62),
               ("suspicious", 0.62, 0.83), ("fraud", 0.83, 1.01)]


def _distribution(values: list[float]) -> dict[str, int]:
    dist = {name: 0 for name, _, _ in _RISK_BANDS}
    for v in values:
        for name, lo, hi in _RISK_BANDS:
            if lo <= v < hi:
                dist[name] += 1
                break
    return dist


def panel_for_results(engine: str, results: list[dict], time_ms: float = 0.0) -> dict:
    """Build a validation-panel dict from one engine's per-component results."""
    results = results or []
    clusters = len(results)
    node_risks: list[float] = []
    confidences: list[float] = []
    fraud_nodes = 0
    patterns: Counter = Counter()
    classifications: Counter = Counter()
    nodes_processed = 0

    for r in results:
        nodes_processed += len(r.get("nodes", []))
        fraud_nodes += len(r.get("flagged_nodes", []))
        v2 = r.get("v2", {})
        if v2:
            confidences.append(float(v2.get("confidence", 0.0)))
            for nid, score in (v2.get("node_risk_scores") or {}).items():
                node_risks.append(float(score))
            ci = v2.get("cluster_intelligence", {})
            for p in ci.get("patterns_detected", []):
                patterns[p] += 1
            pc = v2.get("primary_classification")
            if pc and r.get("verdict") != "CLEAN":
                classifications[pc] += 1
        else:
            node_risks.append(float(r.get("risk_score", 0.0)))
            if r.get("suspicious_reason"):
                patterns[r["suspicious_reason"]] += 1
            if r.get("verdict") and r["verdict"] != "CLEAN":
                classifications[r["verdict"]] += 1

    return {
        "active_engine": engine,
        "nodes_processed": nodes_processed,
        "clusters_found": clusters,
        "fraud_nodes": fraud_nodes,
        "patterns_detected": dict(patterns),
        "risk_distribution": _distribution(node_risks),
        "confidence_distribution": _distribution(confidences) if confidences else {},
        "execution_time_ms": round(time_ms, 2),
        "memory_peak_mb": _peak_memory_mb(),
        "fraud_classifications": dict(classifications),
        "verdict_breakdown": dict(Counter(r.get("verdict", "UNKNOWN") for r in results)),
    }


def panel_for_shadow(shadow_result: dict) -> dict:
    """Build side-by-side panels from a shadow.run_shadow() result."""
    v1 = shadow_result.get("v1", {})
    v2 = shadow_result.get("v2", {})
    return {
        "mode": "shadow",
        "v1": panel_for_results("blue_team_v1", v1.get("results", []), v1.get("time_ms", 0.0)),
        "v2": panel_for_results("blue_team_v2", v2.get("results", []), v2.get("time_ms", 0.0)),
        "agreement": shadow_result.get("agreement", {}),
    }
