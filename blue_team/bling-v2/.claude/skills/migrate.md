# Migrations — BLING Blue Team Detection Engine
# Read this file before running or rolling back migrations.

## Check Migration Status

```bash
alembic current
# Shows: current revision hash + whether it's the "head"

alembic history
# Shows: full migration history in chronological order
```

## Run Pending Migrations

```bash
# Apply all pending migrations to head
alembic upgrade head

# Apply one migration at a time (safer for large schema changes)
alembic upgrade +1
```

## Rollback Last Migration

```bash
# Roll back one migration
alembic downgrade -1

# Roll back to a specific revision
alembic downgrade <revision_id>
```

## Create a New Migration

```bash
# Auto-detect changes from SQLAlchemy models (app/models/database.py)
alembic revision --autogenerate -m "add_merchant_terminal_velocity_index"

# Always review the generated file before committing
# Location: alembic/versions/<hash>_<description>.py
# Check: upgrade() and downgrade() both look correct
```

## Rules (Always Follow)

- Never edit a migration file after it has been committed and run anywhere (dev, CI, staging, prod)
- Every migration must have a working `downgrade()` function — test it before merging
- Test migrations on a copy of production data before running on prod
- Never drop a column in the same migration that stops writing to it:
  1. Migration A: stop writing to column (application code change)
  2. Wait for full rollout
  3. Migration B: drop the column
- The `model_audit` table has DB-level immutability rules — never try to modify these with a migration
- After creating a migration, run `pytest tests/test_integration/` to catch schema regressions before merging

## Critical Schema Notes

- `transactions` table is append-only. Never create a migration that adds UPDATE or DELETE logic to transactions.
- `model_audit` table has `CREATE RULE` statements that prevent UPDATE/DELETE. These are in migration `001_initial_schema.py`. Do not drop or modify these rules.
- Index on `transactions(account_id, timestamp DESC)` is critical for Tier 1 velocity queries. Never drop it.
