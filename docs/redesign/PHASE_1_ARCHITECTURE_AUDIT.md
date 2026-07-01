# Phase 1 — Architecture Audit & Locked Decisions

Authoritative tree: **`~/Desktop/TGIE`** (the live workspace serving the :3000 dev server).
Top-level `~/bling-blue-team`, `~/blue team v2 `, `~/red team union bank`, `~/transaction-graph-intelligence` are demoted to **read-only archives** (mined for the bling Neo4j/evidence-packager code).

## Central finding
**The wrong Blue Team is wired into the running app.** The live `backend/` engine is 100% in-memory (`graph_engine/graph_manager.py` = a NetworkX `DiGraph`) with **flat-JSON persistence** (`case_management/_data/cases.json`, `auth/_data/investigators.json`). A far more enterprise-shaped engine — `blue_team/bling/` — already has a real **Neo4j client**, Alembic migrations, SQLAlchemy, Celery, `evidence_packager`, custody `trail_builder`, and a `nightly_batch` precompute, but is **not mounted**. The platform regressed from a production design into a demo build. Phase 2/3 re-converge on the persistent core *without removing* the rich work built on the in-memory engine.

## Preserve (do not remove)
`blue_team_v2/` (11 modular detectors + `PatternEngine` hybrid-network meta-detector), `risk_engine/` (cumulative explainable 0–100, no single-factor trip — already Actimize-grade philosophy), `fraud_dna/`, `recovery/`, `case_management/`, `evidence/`, BELS (:8200), UB (:8001), `adversarial_governance` (learning gate), Red Team evolution, the frontend pages.

## 19-dimension audit
See conversation/transcript for the full table. Highest-leverage weaknesses, in order:
1. **No database** (in-RAM + JSON) → blocks scale, concurrency, audit integrity, horizontal replicas.
2. **Single node type** (account string; type inferred from `"MUL"/"HVA"` prefix) → identity/ring fraud structurally inexpressible.
3. **State in one process `app_state`** → cannot scale horizontally (replicas would diverge).
4. **Three graph renderers** in frontend (Cytoscape + react-force-graph-3d + raw R3F/postprocessing) → redundant, fights the "no neon, enterprise" UI bar.
5. **GNN is a stub** (`main.py` logs "rule-based fallback"); models rebuilt every boot, no registry/feature-store/drift.
6. **API**: one 20-route file + 6 bolted-on routers, no versioning, inconsistent prefixes, no pagination, graph/evidence routes unauthenticated.
7. **Evidence** = client-side jsPDF screenshots (not regulator-grade); bling's server packager unused.

## LOCKED DECISIONS
- **Persistence**: Neo4j (graph truth) + Postgres (cases/audit/users) + Redis (cache/queue) + object store (evidence, BELS-anchored). **NetworkX demoted to hot cache / live-demo projection of Neo4j.**
- **Cadence**: design doc per phase → user approval → build → verify → gate. No phase starts before the prior is finalized.

## 10-phase roadmap
1 Audit ✅ · 2 Graph schema (design doc written) · 3 Backend redesign (persistence/API/security/event store) · 4 Detection library (~60 patterns on new graph) · 5 ML engine (feature store/registry/real GNN/drift/SHAP-LIME) · 6 Frontend consolidation · 7 Investigation workstation · 8 Evidence + FIU/STR + BELS · 9 Performance (cache/workers/lazy graph/pagination) · 10 Testing.
