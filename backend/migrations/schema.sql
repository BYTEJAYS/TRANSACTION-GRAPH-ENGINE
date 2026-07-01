-- TGIE Postgres schema (Phase 3). System-of-record for workflow + audit + events.
-- Idempotent (IF NOT EXISTS). Applied by migrations/run.py before data loaders.

CREATE TABLE IF NOT EXISTS users (
    investigator_id TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    employee_id     TEXT UNIQUE NOT NULL,
    department      TEXT,
    role            TEXT NOT NULL,
    branch          TEXT,
    email           TEXT UNIQUE,
    password_hash   TEXT NOT NULL,          -- PBKDF2, migrated verbatim (never re-hashed)
    created_at      TIMESTAMPTZ DEFAULT now(),
    extra           JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS cases (
    case_id          TEXT PRIMARY KEY,
    title            TEXT,
    category         TEXT,
    status           TEXT,
    priority         TEXT,
    risk_score       DOUBLE PRECISION,
    fraud_confidence DOUBLE PRECISION,
    assigned_to      TEXT,
    department       TEXT,
    created_at       TIMESTAMPTZ,
    updated_at       TIMESTAMPTZ,
    due_date         TIMESTAMPTZ,
    primary_account  TEXT,
    source           TEXT,
    payload          JSONB NOT NULL          -- full enrich.py output, verbatim
);
CREATE INDEX IF NOT EXISTS cases_status_idx   ON cases (status);
CREATE INDEX IF NOT EXISTS cases_assigned_idx ON cases (assigned_to);
CREATE INDEX IF NOT EXISTS cases_opened_idx   ON cases (created_at);
CREATE INDEX IF NOT EXISTS cases_payload_gin  ON cases USING gin (payload);

-- Append-only transaction event log → powers timeline replay / reprocessing.
CREATE TABLE IF NOT EXISTS txn_events (
    seq        BIGSERIAL PRIMARY KEY,
    event_id   TEXT UNIQUE NOT NULL,
    ts         TIMESTAMPTZ NOT NULL,
    ingest_ts  TIMESTAMPTZ DEFAULT now(),
    payload    JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS txn_events_ts_idx ON txn_events (ts);

-- Read/write audit trail ("who viewed/changed what").
CREATE TABLE IF NOT EXISTS audit_entries (
    id          TEXT PRIMARY KEY,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    target_ref  TEXT,
    ip          TEXT,
    pii         BOOLEAN DEFAULT FALSE,
    ts          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_actor_idx ON audit_entries (actor);
CREATE INDEX IF NOT EXISTS audit_ts_idx    ON audit_entries (ts);

-- PII vault — raw demo PAN/Aadhaar (if ever needed), access-gated. Graph holds only hash+mask.
CREATE TABLE IF NOT EXISTS pii_vault (
    node_id    TEXT PRIMARY KEY,
    kind       TEXT NOT NULL,               -- pan | aadhaar
    raw_value  TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
