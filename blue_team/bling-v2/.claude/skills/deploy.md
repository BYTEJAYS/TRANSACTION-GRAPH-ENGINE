# Deploy — BLING Blue Team Detection Engine
# Read this file before deploying. Follow every step in order.

## Pre-deploy Checklist

```bash
# 1. All tests pass
pytest tests/ -v
# Must see: 8 fraud scenarios PASSED, no failures

# 2. Build succeeds
docker-compose build

# 3. .env has all required vars (compare with .env.example)
diff <(grep -v '^#' .env.example | grep '=' | cut -d= -f1 | sort) \
     <(grep -v '^#' .env | grep '=' | cut -d= -f1 | sort)
# No missing vars

# 4. Model file exists
ls ml/models/xgboost_v1.json
# If missing: python ml/train.py first

# 5. No hardcoded secrets in source
grep -r "password\|secret\|api_key" app/ --include="*.py" | grep -v "os.environ\|settings\." | grep -v "test\|mock"
```

## Deploy Command

```bash
# Start all services (PostgreSQL + Redis + API + Celery worker)
docker-compose up -d

# Wait for services to be healthy
docker-compose ps
# All containers should show "healthy" or "running"

# Initialize DB (first deploy only)
docker-compose exec blue-team-api python scripts/init_db.py

# Run migrations (every deploy)
docker-compose exec blue-team-api alembic upgrade head
```

## Environment Variables Required in Production

See `.env.example` for full list. Critical vars:
- `POSTGRES_URL` — PostgreSQL connection string
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` — teammate's Neo4j instance
- `REDIS_URL` — Redis connection string
- `GRAPH_ENGINE_API_KEY` — key for Graph Engine teammate to call /score
- `INVESTIGATOR_API_KEY` — key for Dashboard teammate to call /alerts + /feedback
- `BLOCKCHAIN_SERVICE_URL` — teammate's blockchain API endpoint
- `RED_TEAM_SERVICE_URL` — teammate's Red Team API endpoint
- `SALT` — PII pseudonymization salt (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)
- `MODEL_VERSION` — e.g. `v1.0`

**INTERNAL_API_KEY must NOT be set in production.**

## Post-deploy Verification

```bash
# 1. Health check
curl http://localhost:8000/health
# Expected: {"status": "ok", "version": "1.0"}

# 2. Readiness (confirms DB + Redis connected)
curl http://localhost:8000/ready
# Expected: {"status": "ready"}

# 3. Score a test transaction
curl -X POST http://localhost:8000/api/v1/score \
  -H "X-API-Key: $GRAPH_ENGINE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"transaction_id":"deploy_test_001","account_id":"TEST","payee_account_id":"TEST2","amount":1000,"channel":"UPI","timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}'
# Expected: 200 with score, action, processing_ms

# 4. Check Celery worker is running
docker-compose logs celery-worker | tail -20
# Expected: "celery@... ready." with no error lines

# 5. Check APScheduler registered nightly batch
docker-compose logs blue-team-api | grep "nightly_batch"
# Expected: "Scheduled nightly_graph_batch job"
```

## Rollback Procedure

```bash
# 1. Stop current deployment
docker-compose down

# 2. Rollback DB migration if schema changed
alembic downgrade -1

# 3. Rebuild with previous image (or restore from backup)
git checkout <previous-sha>
docker-compose build
docker-compose up -d
```
