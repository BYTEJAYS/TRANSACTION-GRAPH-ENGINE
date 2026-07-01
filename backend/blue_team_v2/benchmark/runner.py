"""
Benchmarking System — automated V1-vs-V2 comparison against labelled data.

Generates a labelled dataset with the Simulator, runs BOTH engines over the
identical components, and computes:

  graph-level:  detection accuracy, false positives, false negatives
  node-level:   precision, recall, F1  (flagged_nodes vs ground-truth fraud_nodes)
  pattern:      pattern-detection accuracy (V2)
  performance:  processing speed, peak memory
  calibration:  mean risk on fraud vs normal (separation)

Produces a structured report dict; `format_report()` renders it as text.
"""
from __future__ import annotations

import asyncio
import time

from ..simulation.generators import GroundTruth, Simulator
from ..validation_panel import _peak_memory_mb

# verdict → "is this flagged as fraud/suspicious?"
_FLAGGED_VERDICTS = {"FRAUD", "SUSPICIOUS"}


def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


async def _run_engine(engine: str, components: list[dict]) -> tuple[list[dict], float]:
    t0 = time.perf_counter()
    if engine == "v2":
        from ..adapter import analyze_all_components as run
        results = await run(components)
    else:
        # V1 via its own adapter — falls back to its standalone analyzer when the
        # Blue Team HTTP service is offline (the realistic local comparison).
        from blue_team.adapter import analyze_all_components as run
        results = await run(components, blue_team_url="http://localhost:8001", api_key="x")
    return results, (time.perf_counter() - t0) * 1000


def _score_engine(results: list[dict], truths: dict[str, GroundTruth]) -> dict:
    g_tp = g_fp = g_fn = g_tn = 0
    n_tp = n_fp = n_fn = 0
    pattern_hits = pattern_total = 0
    fraud_risk: list[float] = []
    normal_risk: list[float] = []

    by_id = {r.get("graph_id"): r for r in results}
    for gid, gt in truths.items():
        r = by_id.get(gid, {})
        verdict = r.get("verdict", "CLEAN")
        flagged = verdict in _FLAGGED_VERDICTS
        is_fraud = gt.expected_verdict in _FLAGGED_VERDICTS

        # graph-level confusion
        if is_fraud and flagged:       g_tp += 1
        elif is_fraud and not flagged: g_fn += 1
        elif not is_fraud and flagged: g_fp += 1
        else:                          g_tn += 1

        # risk calibration
        (fraud_risk if is_fraud else normal_risk).append(float(r.get("risk_score", 0.0)))

        # node-level confusion
        flagged_nodes = set(r.get("flagged_nodes", []))
        truth_nodes = gt.fraud_nodes
        all_nodes = set(r.get("nodes", [])) or truth_nodes
        for node in all_nodes:
            in_truth = node in truth_nodes
            in_flag = node in flagged_nodes
            if in_truth and in_flag:       n_tp += 1
            elif in_truth and not in_flag: n_fn += 1
            elif not in_truth and in_flag: n_fp += 1

        # pattern detection (V2 only)
        v2 = r.get("v2")
        if v2 and gt.expected_patterns:
            detected = set((v2.get("cluster_intelligence") or {}).get("patterns_detected", []))
            for p in gt.expected_patterns:
                pattern_total += 1
                if p in detected:
                    pattern_hits += 1

    total = max(1, g_tp + g_fp + g_fn + g_tn)
    return {
        "graph_level": {
            **_prf(g_tp, g_fp, g_fn),
            "accuracy": round((g_tp + g_tn) / total, 4),
            "true_positives": g_tp, "false_positives": g_fp,
            "false_negatives": g_fn, "true_negatives": g_tn,
        },
        "node_level": _prf(n_tp, n_fp, n_fn),
        "pattern_detection_accuracy": round(pattern_hits / pattern_total, 4) if pattern_total else None,
        "risk_calibration": {
            "mean_risk_fraud": round(sum(fraud_risk) / len(fraud_risk), 4) if fraud_risk else 0.0,
            "mean_risk_normal": round(sum(normal_risk) / len(normal_risk), 4) if normal_risk else 0.0,
            "separation": round((sum(fraud_risk) / len(fraud_risk) if fraud_risk else 0) -
                                (sum(normal_risk) / len(normal_risk) if normal_risk else 0), 4),
        },
    }


async def run_benchmark(n_fraud: int = 10, n_normal: int = 10, seed: int = 42) -> dict:
    sim = Simulator(seed=seed)
    dataset = sim.mixed_dataset(n_fraud=n_fraud, n_normal=n_normal)
    components = [c for c, _ in dataset]
    truths = {c["graph_id"]: gt for c, gt in dataset}

    mem_before = _peak_memory_mb()
    (v1_results, v1_ms), (v2_results, v2_ms) = await asyncio.gather(
        _run_engine("v1", components),
        _run_engine("v2", components),
    )
    mem_after = _peak_memory_mb()

    v1_metrics = _score_engine(v1_results, truths)
    v2_metrics = _score_engine(v2_results, truths)

    return {
        "dataset": {"fraud_clusters": n_fraud, "normal_clusters": n_normal,
                    "total_components": len(components),
                    "total_nodes": sum(len(c["node_ids"]) for c in components)},
        "v1": {"metrics": v1_metrics, "time_ms": round(v1_ms, 2),
               "throughput_comp_per_s": round(len(components) / (v1_ms / 1000), 1) if v1_ms else 0},
        "v2": {"metrics": v2_metrics, "time_ms": round(v2_ms, 2),
               "throughput_comp_per_s": round(len(components) / (v2_ms / 1000), 1) if v2_ms else 0},
        "memory_peak_mb": max(mem_before, mem_after),
        "winner": _pick_winner(v1_metrics, v2_metrics),
    }


def _pick_winner(v1: dict, v2: dict) -> dict:
    v1f, v2f = v1["graph_level"]["f1"], v2["graph_level"]["f1"]
    v1n, v2n = v1["node_level"]["f1"], v2["node_level"]["f1"]
    v2_better = (v2f + v2n) > (v1f + v1n)
    return {
        "graph_f1": {"v1": v1f, "v2": v2f},
        "node_f1": {"v1": v1n, "v2": v2n},
        "verdict": "v2" if v2_better else "v1",
    }


def format_report(report: dict) -> str:
    d = report["dataset"]
    lines = [
        "═" * 64,
        "  BLUE TEAM  V1  vs  V2   —   BENCHMARK REPORT",
        "═" * 64,
        f"Dataset: {d['total_components']} components, {d['total_nodes']} nodes "
        f"({d['fraud_clusters']} fraud / {d['normal_clusters']} normal)",
        "",
        f"{'Metric':<34}{'V1':>14}{'V2':>14}",
        "-" * 64,
    ]

    def row(label, a, b, pct=False):
        fa = f"{a*100:.1f}%" if pct and a is not None else ("—" if a is None else f"{a}")
        fb = f"{b*100:.1f}%" if pct and b is not None else ("—" if b is None else f"{b}")
        lines.append(f"{label:<34}{fa:>14}{fb:>14}")

    v1, v2 = report["v1"]["metrics"], report["v2"]["metrics"]
    row("Graph Detection Accuracy", v1["graph_level"]["accuracy"], v2["graph_level"]["accuracy"], True)
    row("Graph Precision", v1["graph_level"]["precision"], v2["graph_level"]["precision"], True)
    row("Graph Recall", v1["graph_level"]["recall"], v2["graph_level"]["recall"], True)
    row("Graph F1", v1["graph_level"]["f1"], v2["graph_level"]["f1"], True)
    row("False Positives (graphs)", v1["graph_level"]["false_positives"], v2["graph_level"]["false_positives"])
    row("False Negatives (graphs)", v1["graph_level"]["false_negatives"], v2["graph_level"]["false_negatives"])
    lines.append("-" * 64)
    row("Node Precision", v1["node_level"]["precision"], v2["node_level"]["precision"], True)
    row("Node Recall", v1["node_level"]["recall"], v2["node_level"]["recall"], True)
    row("Node F1", v1["node_level"]["f1"], v2["node_level"]["f1"], True)
    row("Pattern Detection Acc.", v1["pattern_detection_accuracy"], v2["pattern_detection_accuracy"], True)
    lines.append("-" * 64)
    row("Mean Risk · Fraud", v1["risk_calibration"]["mean_risk_fraud"], v2["risk_calibration"]["mean_risk_fraud"], True)
    row("Mean Risk · Normal", v1["risk_calibration"]["mean_risk_normal"], v2["risk_calibration"]["mean_risk_normal"], True)
    row("Risk Separation", v1["risk_calibration"]["separation"], v2["risk_calibration"]["separation"], True)
    lines.append("-" * 64)
    row("Processing Time (ms)", report["v1"]["time_ms"], report["v2"]["time_ms"])
    lines.append("=" * 64)
    lines.append(f"  WINNER (combined F1): {report['winner']['verdict'].upper()}")
    lines.append("=" * 64)
    return "\n".join(lines)
