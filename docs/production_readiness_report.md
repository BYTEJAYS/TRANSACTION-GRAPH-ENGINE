# TGIE Production Readiness Report

> Evaluation of the consolidated TGIE ecosystem against production criteria.
> Scores are 0–100 (weighted composite below). Assessed 2026-06-24 from the
> assembled `TGIE/` workspace and the audits in this folder.

---

## 1. Scorecard

| Dimension | Weight | Score /100 | Notes |
|---|---:|---:|---|
| **Security** | 20% | 55 | Static API key, permissive CORS, no authN on public WS/ingress, attacker-trusted attributes (B8). No secrets manager. |
| **Reliability** | 15% | 65 | Deployed & stable on Railway/Vercel; demo-mode fallback; but single-worker, no retries on WS, swallowed detector exceptions. |
| **Maintainability** | 15% | 55 | 1,287-line GraphScene monolith, duplicated verdict schema, two Blue Team generations, three Python runtimes, dead code. |
| **Scalability** | 15% | 60 | V2 → 100k nodes/22s but detection decays at scale; deploy capped at 150 nodes; BLING horizontally scalable but heavy. |
| **Performance** | 10% | 70 | Good after deploy tuning; per-frame hover loop + particles cost; no DPR clamp. |
| **Observability** | 10% | 35 | Only `/health` + logs. No metrics/tracing/dashboards/alerts. |
| **Testing** | 15% | 50 | 5 pytest suites (backend/blue/red); **no frontend tests**; no unified runner; manual screenshot verification. |
| **Composite** | 100% | **55 / 100** | **Advanced prototype / pre-production.** Strong research core, real deployment, but security/observability/testing gaps block production. |

> **Composite = 0.20·55 + 0.15·65 + 0.15·55 + 0.15·60 + 0.10·70 + 0.10·35 + 0.15·50 ≈ 55.**

---

## 2. Critical Issues (must fix before production)

1. **No authentication/authorization** on the public TGIE WebSocket (`/ws/live`) and
   `POST /transaction/manual`. Anyone can inject transactions and read the stream.
2. **Static shared secret** `BLUE_TEAM_API_KEY=tgie-secret-2025` committed in env docs.
   Rotate, move to a secret manager, scope per-caller.
3. **56.7% benign false-positive rate** on realistic legitimate traffic (V2) — not
   deployable as a fraud blocker until the provenance/context signals are wired into the
   real engine (prototype shows FP → 0%).
4. **B5 label leakage** in V1 (`IsolationForest.score` reads ground-truth) — any reported V1
   accuracy is invalid; strip before trusting metrics.
5. **No observability** — a fraud-detection system in production needs metrics, alerting on
   verdict-rate anomalies, and audit logging. Today there is only `/health`.

## 3. High-Priority Issues

6. **Attacker-controlled attributes (B8)** — derive `risk_score`/`detected_patterns`
   server-side; never trust caller-supplied node attributes.
7. **Untrained GNN (B4)** — remove or actually train; stop emitting random-weight output.
8. **No frontend tests + manual-only verification** — add vitest + a playwright aspect/rotation smoke test (see graph_validation.md).
9. **Graph aspect distortion (rhombus)** — P0 UX bug; fix per `graph_validation.md`.
10. **Swallowed detector exceptions** → silent detection gaps; log and alert.

## 4. Medium-Priority Issues

11. Decompose `GraphScene.tsx`; delete dead JSX and orphaned `RightPanel.tsx`.
12. Extract the duplicated verdict schema into a real `shared/` package.
13. Consolidate the `?v=2` CinematicApp path or retire it.
14. Detection decay at scale (sampled centrality, length-bounded cycles) — document limits and add scale-aware fallbacks.
15. Three Python runtimes — standardize where possible; pin and document clearly.
16. Promote V2 to default once FP is controlled (V2 beats V1 on benchmark).

## 5. Low-Priority Issues

17. Clamp `devicePixelRatio` for crisp Retina rendering.
18. Centralize verdict color/size tokens in the frontend.
19. Populate Red Team genealogy `parent_ids` for lineage analysis.
20. Tiny (7–8px) cluster-label fonts — legibility review.
21. Add CONTRIBUTING/RUNBOOK docs to `docs/` for onboarding.

---

## 6. Go / No-Go Summary

| Use case | Verdict |
|---|---|
| Research / demo / hackathon | ✅ **Go** — impressive, stable, well-documented. |
| Internal analyst tool (trusted network) | ⚠️ **Conditional** — add authN, observability, fix FP. |
| Production fraud blocker (public) | ❌ **No-Go** — critical security, FP, and observability gaps. |

**Path to production:** (1) wire provenance/context signals into the real engine to crush
the 56.7% FP; (2) add authN + secrets management; (3) add observability + alerting;
(4) strip B5, fix B8, address the GNN; (5) frontend tests + the rhombus fix. Estimated this
is a focused multi-week hardening effort on top of a genuinely strong core.
