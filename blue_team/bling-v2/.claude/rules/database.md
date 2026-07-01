---
paths:
  - "src/models/**"
  - "src/db/**"
  - "models/**"
  - "migrations/**"
  - "alembic/**"
  - "prisma/**"
  - "**/*migration*"
  - "**/*schema*"
  - "**/*model*"
  - "**/*.sql"
---

# Database Rules

## Queries
- Parameterized queries ALWAYS — zero exceptions for user-controlled data
- No string concatenation with user input in SQL
- SELECT only the columns you need — never `SELECT *` in production code
- Add LIMIT to all queries that could return unbounded results
- Use indexes for columns you filter or sort by frequently

## Migrations
- Every migration must have a rollback path
- Never delete a column in the same migration that stops writing to it
  (deprecate → stop writing → later migration to drop)
- Never rename a column directly — add new, copy data, drop old
- Test migrations on a copy of production data before running on prod
- Migration files are sacred — never edit a committed migration, always create a new one

## Schema Design
- Every table has created_at and updated_at timestamps
- Soft deletes: add deleted_at column, filter in queries — don't hard delete user data
- Use UUIDs for public-facing IDs, integer PKs for internal joins
- Foreign keys defined and enforced at the DB level, not just application level
- Nullable columns are explicit — defaults documented

## ORM Usage
- Business logic never goes in model methods — keep models as data containers
- Complex queries in a repository/data access layer — not scattered across the codebase
- Avoid N+1: eager load associations when you know you'll need them
- Never load an entire table into memory — paginate or stream
- Connection pool: configure max_connections appropriate to deployment
  (Postgres default allows 100 total; most apps only need 5–20 per instance)
- Never open a new connection outside a request/job context — connection leak

## Transactions
- Operations that must succeed or fail together use explicit transactions
- Keep transactions short — do not call external services inside a transaction
- On failure: rollback and surface a meaningful error

## Security
- DB connection uses minimum required privileges (read-only user for read-only operations)
- Connection string only in environment variables — never in source code
- Connection pooling configured — never create a new connection per request
