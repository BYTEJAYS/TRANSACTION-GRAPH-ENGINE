# tests/ — Test Index

There is **no unified test runner** yet. Tests live per-component. This index maps them.

| Suite | Location | Runner | Coverage |
|---|---|---|---|
| Blue Team V2 | `../backend/blue_team_v2/tests/` | `pytest blue_team_v2/tests -q` (21 tests) | detectors, scoring, adapter, shadow |
| BLING Blue Team | `../blue_team/bling/tests/` | `pytest` | detection, evidence, graph, API |
| BLING v2 | `../blue_team/bling-v2/tests/` | `pytest` | — |
| CRUCIBLE Red Team | `../red_team/crucible/red_team/tests/` | `pytest` | mutation, critics, human gate |
| Adversarial | smoke runs via `python -m adversarial …` | manual | GA/QD/PPO reproducibility |
| **Frontend** | — | **none** | ⚠️ missing — verified manually via puppeteer screenshots |

## Recommended additions (see `../docs/production_readiness_report.md`)

1. **Frontend vitest** unit tests for `frontend/src/ai/riskPropagation.ts` (the risk-intel core).
2. **Playwright smoke test** asserting `canvas.width/canvas.height ≈ clientWidth/clientHeight`
   after a simulated viewport rotation — directly guards the rhombus regression
   (`../docs/graph_validation.md`).
3. A top-level `pytest` config that discovers all backend suites in one run.
4. Strip the V1 label leak (B5) from any eval harness before trusting accuracy numbers.

## Proposed unified runner

```bash
# from TGIE/
( cd backend && pytest blue_team_v2/tests -q )
( cd blue_team/bling && pytest -q )
( cd red_team/crucible && pytest red_team/tests -q )
( cd frontend && npm test )   # once frontend tests exist
```
