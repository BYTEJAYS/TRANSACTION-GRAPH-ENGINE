# shared/ — Cross-cutting Contracts (proposed)

This directory is a **placeholder for the shared library that does not yet exist** as a
formal package. Today the ecosystem's cross-cutting contract is **duplicated** rather than
shared.

## The de-facto contract: the verdict schema

Every Blue Team implementation emits the same shape:

```jsonc
{
  "graph_id": "GRAPH_001",
  "status": "ok",
  "verdict": "FRAUD | SUSPICIOUS | CLEAN | LOGGED",
  "risk_score": 0.0,            // 0..1
  "flagged": true,
  "flagged_nodes": ["acc_123"],
  "suspicious_reason": "…",
  "nodes": [ /* per-node intel */ ],
  "mode": "v1 | v2"
}
```

This is currently re-declared in:
- `backend/blue_team/adapter.py` (V1)
- `backend/blue_team_v2/adapter.py` (V2) — plus an additive `v2` block
- `red_team/adversarial/integration` (HardenedBlueTeam) — plus an additive `hardening` block

## Recommended extraction (technical debt, see repository_analysis.md §7)

Create a real shared package here holding:
1. The verdict schema (pydantic model) imported by all engines.
2. Risk thresholds (V2: `LOG 0.38 / REVIEW 0.62 / HIGH_RISK 0.83`).
3. The transaction ingress model (`ManualTransactionInput`).
4. Common graph types (node/edge/component).

Until then, treat this README as the contract reference.
