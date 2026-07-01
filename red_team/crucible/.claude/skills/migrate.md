# Migrations — [Project Name]
# Claude fills this during /new-project based on the chosen ORM and DB.
# Read this file before running or rolling back migrations.

## Check Migration Status
[Claude fills this — e.g., `alembic current` or `npx prisma migrate status` or `python manage.py showmigrations`]

## Run Pending Migrations
[Claude fills this — e.g., `alembic upgrade head` or `npx prisma migrate deploy` or `python manage.py migrate`]

## Rollback Last Migration
[Claude fills this — e.g., `alembic downgrade -1` or the equivalent for this stack]

## Create a New Migration
[Claude fills this — e.g., `alembic revision --autogenerate -m "description"` or `npx prisma migrate dev --name description`]

## Rules (Always Follow)
- Never edit a migration file after it has been committed and run anywhere
- Every migration must have a rollback path — verify before committing
- Test on a copy of production data before running on prod
- Never drop a column in the same migration that stops writing to it
  (deprecate first → stop writing → later migration to drop)
