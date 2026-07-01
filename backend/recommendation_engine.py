"""
Investigation recommendation engine.

Turns a Blue Team V2 cluster analysis (roles, verdict, detected motifs) into
concrete, self-explaining next actions for an investigator — freeze, escalate
SAR, KYC review, velocity hold, etc. Every recommendation states WHY it fired,
WHICH accounts it targets, and which AML rule(s) support it.

Purely derived from the existing analysis — no new detection.
"""
from __future__ import annotations

from typing import Any

from blue_team_v2.types import Verdict
from rule_engine import rules_for

# action → default priority (higher = more urgent)
_PRIORITY = {
    "FREEZE_ACCOUNT": 5,
    "ESCALATE_SAR": 5,
    "VELOCITY_HOLD": 4,
    "REVIEW_BENEFICIARY": 4,
    "INVESTIGATE_SOURCE": 4,
    "VERIFY_KYC": 3,
    "REVIEW_COMMUNITY": 3,
    "MANUAL_REVIEW": 2,
    "MONITOR": 1,
}


def _rec(action: str, targets: list[str], reason: str, rule_ids: list[str] | None = None) -> dict[str, Any]:
    return {
        "action": action,
        "priority": _PRIORITY.get(action, 2),
        "targets": sorted(set(targets))[:12],
        "reason": reason,
        "supporting_rules": rule_ids or [],
    }


def recommend(analysis: Any, motifs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Build prioritised, self-explaining recommendations for one cluster."""
    motifs = motifs or []
    ci = analysis.cluster
    patterns = {m["pattern"] for m in motifs}
    recs: list[dict[str, Any]] = []

    # CLEAN and LOGGED both sit below the review threshold → monitoring only;
    # investigative actions are reserved for SUSPICIOUS / FRAUD clusters.
    if analysis.verdict in (Verdict.CLEAN, Verdict.LOGGED):
        return [_rec("MONITOR", [], "Below the review threshold — routine periodic monitoring only.")]

    # Cash-out exits are the most urgent: money is leaving the banking network.
    if ci.cashout:
        recs.append(_rec("FREEZE_ACCOUNT", ci.cashout,
                         "Cash-out accounts are moving funds out of the banking network — freeze to halt loss.",
                         rules_for("cashout") and ["AML011"]))
    # Origins: where illicit funds enter — investigate source + KYC.
    if ci.origin:
        recs.append(_rec("INVESTIGATE_SOURCE", ci.origin,
                         "Origin accounts inject funds into the network — trace and verify the funding source."))
        recs.append(_rec("VERIFY_KYC", ci.origin,
                         "Confirm KYC / beneficial ownership on the funding accounts."))
    # Mules: receive-and-forward relays.
    if ci.mules:
        recs.append(_rec("REVIEW_BENEFICIARY", ci.mules,
                         "Mule / pass-through accounts rapidly forward received value — review their beneficiaries.",
                         ["AML008"]))
    # Bridges link sub-networks → community review.
    if ci.bridges:
        recs.append(_rec("REVIEW_COMMUNITY", ci.bridges,
                         "Bridge accounts connect otherwise separate sub-networks — review the wider community."))
    # Behaviour-driven holds.
    if patterns & {"velocity", "temporal_spike"}:
        fast = sorted(nid for nid, m in analysis.metrics.items() if m.transaction_velocity > 0.6)
        recs.append(_rec("VELOCITY_HOLD", fast or analysis.node_ids[:5],
                         "Abnormal transaction velocity / burst detected — apply a temporary velocity hold.",
                         ["AML010", "AML018"]))
    if "dormant_accounts" in patterns:
        recs.append(_rec("VERIFY_KYC", [],
                         "Dormant accounts reactivated at volume — re-verify identity before further activity.",
                         ["AML012"]))
    # Composite / critical → regulatory escalation.
    if analysis.verdict == Verdict.FRAUD or "hybrid_network" in patterns:
        recs.append(_rec("ESCALATE_SAR", analysis.node_ids,
                         "Cluster meets the fraud threshold with multiple corroborating techniques — file an STR/SAR with the FIU.",
                         ["AML019"]))
    # Highest-betweenness controller → manual review.
    if analysis.metrics:
        controller = max(analysis.metrics.values(), key=lambda m: m.betweenness_centrality)
        if controller.betweenness_centrality > 0.15:
            recs.append(_rec("MANUAL_REVIEW", [controller.node_id],
                             "Highest path-centrality account controls flow through the network — prioritise for manual review."))

    # Dedup by (action) keeping the most-targeted, sort by priority desc.
    merged: dict[str, dict] = {}
    for r in recs:
        cur = merged.get(r["action"])
        if cur is None or len(r["targets"]) > len(cur["targets"]):
            merged[r["action"]] = r
    return sorted(merged.values(), key=lambda r: r["priority"], reverse=True)
