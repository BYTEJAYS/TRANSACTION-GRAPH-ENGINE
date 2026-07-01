# Blue Team V2 — Migration Strategy

Migration is **evidence-driven** and **manual**. V2 never auto-replaces V1.

## Decision gates

Promote V2 from experiment → default only when all hold on representative data:

1. **Detection** — V2 graph-F1 and node-F1 ≥ V1 across ≥3 seeds.
2. **False positives** — V2 graph FP rate ≤ V1.
3. **Calibration** — V2 fraud/normal risk separation ≥ V1.
4. **Performance** — V2 within the latency budget at production graph sizes.
5. **Explainability** — V2 produces evidence + narrative for every flagged cluster.

Generate the report any time:

```bash
python -m blue_team_v2 benchmark
```

### Current status (synthetic benchmark, 5 seeds)

| Gate | V1 | V2 | Pass |
|---|---|---|---|
| Graph F1 | 0.76 | 0.96 | ✅ |
| Node F1 | 0.83 | 0.96 | ✅ |
| FP (avg/20) | 6.4 | 0.8 | ✅ |
| Risk separation | 0.38 | 0.38 | ✅ |
| Latency (20 comp) | ~170 ms | ~12 ms | ✅ |
| Evidence + narrative | partial | full | ✅ |

> Synthetic data only. Validate on real/labelled production traffic in **shadow
> mode** before promotion.

## Phased rollout

| Phase | Action | Risk |
|---|---|---|
| 0 | Ship V2 dormant (this package) | none |
| 1 | Enable `/api/v2/*` endpoints; run shadow on live graphs | none — V1 still authoritative |
| 2 | Wire router (Level 3, defaults V1); compare in shadow over N days | none until env flips |
| 3 | `ACTIVE_BLUE_TEAM=v2` in staging | isolated |
| 4 | Canary `=v2` for a traffic slice; monitor FP/latency | reversible by env |
| 5 | Promote `=v2` default; keep V1 importable for rollback | reversible |

## Deliverables before promotion

1. **Performance Report** — latency/memory at 1k/10k/50k/100k nodes (`scale`).
2. **Detection Report** — precision/recall/F1, graph + node (`benchmark`).
3. **Benchmark Results** — V1 vs V2 table + winner.
4. **Migration Plan** — this document, with the phase you are in.
5. **Compatibility Assessment** — confirm all consumers read V1 schema unchanged.
6. **Risk Assessment** — rollback = unset env + revert one import. No schema/data change.

## Rollback

```bash
unset ACTIVE_BLUE_TEAM      # or: export ACTIVE_BLUE_TEAM=v1
```
If Level 3 was applied, revert the single import in `api/routes.py`. V1 is never
modified, so it is always immediately available.
