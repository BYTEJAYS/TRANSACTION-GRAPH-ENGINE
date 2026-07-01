# monitoring/ — Observability (plan)

> **Status: placeholder.** There is no metrics/tracing/alerting stack today — only the
> backend `/health` endpoint (used by the Railway healthcheck) and stdout logs.
> Observability scored **35/100** in `../docs/production_readiness_report.md` and is a
> **critical** pre-production gap.

## What exists

- `GET /health` — liveness for Railway.
- Structured-ish logs to stdout (`LOG_LEVEL` env).
- Frontend dev diagnostics: `window.__voiceDiag()`, `?voicedebug`, `DEBUG_RISK` flag.
- `deployment/infrastructure/` contains Flink + Kafka configs (heavy build only).

## Recommended stack

| Concern | Tool | Signal |
|---|---|---|
| Metrics | Prometheus + Grafana | request latency, WS clients, verdict rate, FP rate, graph size |
| Tracing | OpenTelemetry | ingress → graph build → scoring → broadcast span |
| Alerting | Grafana/Alertmanager | verdict-rate anomaly, FP spike, detector-exception count |
| Audit log | structured JSON sink | every verdict + flagged node (compliance) |
| Frontend RUM | web-vitals | FPS on the 3D canvas, WS reconnects |

## Priority alerts to add first

1. **Detector exceptions** — currently swallowed → silent detection gaps.
2. **Benign FP rate** — given the 56.7% realistic-FP finding, alert on flag rate drift.
3. **WS disconnect / backend down** — the graph silently falls back to mock mode.
