# Blue Team V2 — TGIE Integration Guide

V2 is built as a **drop-in alternative intelligence engine**. Every integration
step below is optional and additive. None of them is applied automatically, and
**no existing TGIE file is modified by this package** — production stays on V1
until you choose otherwise.

> The current Blue Team (`backend/blue_team/`), `api/routes.py`, the graph
> manager, database structures, dashboards, and AI assistant are untouched.

---

## Level 0 — nothing wired (default)

Importing `blue_team_v2` changes no behaviour. V1 runs exactly as before.

## Level 1 — programmatic / shadow only

Use V2 from scripts, notebooks, or the benchmark without touching the API:

```python
from blue_team_v2.shadow import run_shadow
comparison = await run_shadow(components)   # both engines, side by side
```

## Level 2 — additive API endpoints (recommended first step)

Adds `/api/v2/*` **without** overriding any existing route. One line in `main.py`:

```python
from blue_team_v2.api import router as blue_team_v2_router
app.include_router(blue_team_v2_router)
```

New endpoints: `GET /api/v2/health`, `GET /api/v2/engine`,
`POST /api/v2/analyze`, `POST /api/v2/shadow`, `POST /api/v2/validation-panel`.
The existing `/api/*` surface is unchanged.

## Level 3 — route production analysis through the router (opt-in)

The router defaults to V1, so this is safe to wire and leaves behaviour
identical until `ACTIVE_BLUE_TEAM=v2` is set. In `api/routes.py`, the single
import the manual-simulation path uses can be swapped:

```python
# before
from blue_team.adapter import analyze_all_components

# after — identical signature, selects engine via ACTIVE_BLUE_TEAM (default v1)
from blue_team_v2.router import route_all_components as analyze_all_components
```

Then flip engines per environment, with **zero** code change:

```bash
export ACTIVE_BLUE_TEAM=v1   # production-safe default
export ACTIVE_BLUE_TEAM=v2   # experiment
```

> This is the only change that touches an existing file. It is intentionally a
> one-line, behaviour-preserving swap, and it is left for you to apply after
> reviewing the benchmark — this package never edits `routes.py` itself.

---

## Output compatibility

Every consumer reads the same keys it always has:

```json
{ "graph_id", "status", "verdict", "risk_score", "flagged",
  "flagged_nodes", "suspicious_reason", "transactions_scored", "nodes", "mode" }
```

V2 adds an `mode: "blue_team_v2"` value and an additive `v2` block. Existing
consumers read by known key and ignore `v2`, so graph rendering, risk badges,
fraud labels, hover panels, the analytics dashboard, and the cluster view all
keep working unchanged.

## AI assistant — engine awareness

Each verdict carries `mode` (`blue_team_v2` / `standalone` / `blue_team_api`) and,
for V2, `v2.narrative` + `v2.primary_classification`. The UB assistant can quote
which engine produced a result and compare them, e.g.:

> "Blue Team V2 detected a layering network involving 3 bridge accounts and 2
> mule chains (risk 94%, confidence 93%), whereas V1 classified the same graph
> as suspicious on fan-out activity alone."

## Frontend — Graph Validation Panel

`POST /api/v2/shadow` returns a `validation_panel` with both engines'
Active Engine · Nodes Processed · Clusters Found · Fraud Nodes ·
Patterns Detected · Risk/Confidence Distribution · Execution Time ·
Memory · Fraud Classifications — everything the developer comparison panel needs.

## Rollback

Unset `ACTIVE_BLUE_TEAM` (or set `=v1`) and, if you applied Level 3, revert the
one-line import. No data migration, no schema change.
