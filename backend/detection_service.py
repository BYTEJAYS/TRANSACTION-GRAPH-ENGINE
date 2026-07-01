"""
Unified live-detection service.

The streaming simulation used to label each step with a 4-rule hard-coded
classifier (`fraud_classifier.ManualFraudClassifier`), while the authoritative
verdict came from the Blue Team V2 engine only at the END of the run. The two
disagreed — the graph could flash "fraud" mid-stream on a benign chain, or look
clean while V2 later flagged it. That split-brain is what this module removes.

`classify_live` derives the live `{status, rules_triggered, suspicious_nodes}`
from the SAME V2 engine that produces the final verdict, so the live picture and
the final verdict are always consistent and the detection is fully algorithmic
(no hard-coded thresholds).
"""
from __future__ import annotations

import asyncio
from typing import Any

_NORMAL = {"status": "normal", "rules_triggered": [], "suspicious_nodes": []}


async def classify_live(graph_manager) -> dict[str, Any]:
    """
    Run the production V2 engine over the graph's current connected components
    and project the result onto the live classification schema the frontend
    already consumes.

    status            : "fraud" if any component is SUSPICIOUS/FRAUD, else "normal"
    rules_triggered   : the distinct detected pattern names driving the flags
    suspicious_nodes   : every node V2 flags across all components
    """
    components = await graph_manager.get_connected_components()
    if not components:
        return dict(_NORMAL)

    # V2 is synchronous and CPU-bound — keep it off the event loop.
    from blue_team_v2.adapter import analyze_all_components_sync
    verdicts = await asyncio.to_thread(analyze_all_components_sync, components)

    suspicious: set[str] = set()
    rules: set[str] = set()
    is_fraud = False
    for v in verdicts:
        if v.get("flagged") or v.get("verdict") in ("FRAUD", "SUSPICIOUS"):
            is_fraud = True
            suspicious.update(v.get("flagged_nodes") or [])
            reason = v.get("suspicious_reason")
            if reason:
                rules.add(reason)

    return {
        "status": "fraud" if is_fraud else "normal",
        "rules_triggered": sorted(rules),
        "suspicious_nodes": sorted(suspicious),
    }
