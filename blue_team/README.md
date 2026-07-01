# Blue Team

Defensive fraud-detection engines. **Five implementations** exist across the ecosystem;
two live inside the TGIE core backend, two are the standalone Union Bank BLING service, and
one is the research-hardened wrapper.

| Implementation | Location | Type | Status |
|---|---|---|---|
| **V1** | `../backend/blue_team/` | ML/statistical (IsolationForest + XGBoost + rules) | Production default (`ACTIVE_BLUE_TEAM=v1`) |
| **V2** | `../backend/blue_team_v2/` | Deterministic graph engine, 11 detectors | Opt-in; faster + more accurate (graph-F1 0.96 vs 0.76) |
| **BLING** | `bling/` | FastAPI + Postgres + Neo4j + Celery forensic service (:8001) | Standalone (Union Bank) |
| **BLING v2** | `bling-v2/` | Newer BLING iteration | Standalone |
| **Hardened** | `../red_team/adversarial/integration/` | V2 wrapped + 6 context signals | Research → prod path |

## Engine selection (TGIE core)

`ACTIVE_BLUE_TEAM` env var selects V1/V2; **shadow mode** runs both on the same graph.
Both emit the identical verdict schema (see `../shared/README.md`).

## The 11 V2 detectors

`layering · smurfing · mule_accounts · fan_in · fan_out · velocity · cashout ·
circular_flow · bridge_accounts · dormant_accounts · synthetic_networks`

## Key findings

See **`../docs/blue_team_audit.md`** for the full subsystem scorecard. Headlines:
- **B1 (dominant):** component isolation — no cross-component/temporal correlation.
- **56.7% benign FP** on realistic legit traffic — the most important gap; fixed to ~0% by
  the provenance/context signals in the hardened stack.
- GNN ships untrained (random weights); V1 has label leakage (B5).

## Run

- V2 CLI: `python -m blue_team_v2 {demo,benchmark,shadow,scale}` (from `backend/`).
- BLING: `docker-compose up` in `bling/` (needs Postgres + Neo4j + Redis).
