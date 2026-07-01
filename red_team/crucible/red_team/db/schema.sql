-- CRUCIBLE Red Team — Database Schema
-- Apply: psql $DATABASE_URL -f red_team/db/schema.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS fraud_genomes (
    genome_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lineage_id      VARCHAR(50) NOT NULL,
    parent_genome_id UUID REFERENCES fraud_genomes(genome_id),
    generation      INTEGER NOT NULL DEFAULT 0,
    topology        JSONB NOT NULL,
    timing          JSONB NOT NULL,
    amounts         JSONB NOT NULL,
    channels        JSONB NOT NULL,
    accounts        JSONB NOT NULL,
    special_nodes   JSONB NOT NULL,
    mutation_history JSONB DEFAULT '[]',
    fitness_score   FLOAT DEFAULT 0.0,
    realism_score   FLOAT DEFAULT 0.0,
    novelty_score   FLOAT DEFAULT 0.0,
    status          VARCHAR(20) DEFAULT 'active',
    flags           JSONB DEFAULT '[]',
    repair_recommendation VARCHAR(20),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_genomes_lineage  ON fraud_genomes(lineage_id);
CREATE INDEX IF NOT EXISTS idx_genomes_status   ON fraud_genomes(status);
CREATE INDEX IF NOT EXISTS idx_genomes_fitness  ON fraud_genomes(fitness_score DESC);

CREATE TABLE IF NOT EXISTS lineage_scores (
    lineage_id          VARCHAR(50) PRIMARY KEY,
    seed_source         VARCHAR(100),
    total_predictions   INTEGER DEFAULT 0,
    confirmed_hits      INTEGER DEFAULT 0,
    status              VARCHAR(20) DEFAULT 'active',
    weight              FLOAT DEFAULT 1.0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_hit_at         TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS prophecy_ledger (
    prediction_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    genome_id           UUID NOT NULL REFERENCES fraud_genomes(genome_id),
    lineage_id          VARCHAR(50) NOT NULL,
    prediction_date     TIMESTAMPTZ NOT NULL,
    match_window_end    TIMESTAMPTZ NOT NULL,
    fingerprint         VARCHAR(64) NOT NULL,
    human_approved      BOOLEAN DEFAULT FALSE,
    repair_recommendation VARCHAR(20),
    matched             BOOLEAN DEFAULT FALSE,
    match_count         INTEGER DEFAULT 0,
    ledger_hash         VARCHAR(64),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_prophecy_lineage     ON prophecy_ledger(lineage_id);
CREATE INDEX IF NOT EXISTS idx_prophecy_fingerprint ON prophecy_ledger(fingerprint);
CREATE INDEX IF NOT EXISTS idx_prophecy_unmatched   ON prophecy_ledger(matched, match_window_end) WHERE matched = FALSE;

CREATE TABLE IF NOT EXISTS confirmed_frauds (
    fraud_id                VARCHAR(100) PRIMARY KEY,
    confirmed_date          TIMESTAMPTZ,
    confirmation_method     VARCHAR(30),
    fraud_type              VARCHAR(50),
    accounts_involved       JSONB,
    amount_total            FLOAT,
    topology                JSONB,
    timing                  JSONB,
    amounts_info            JSONB,
    channels_info           JSONB,
    accounts_info           JSONB,
    fingerprint             VARCHAR(64),
    ingested_into_prophecy  BOOLEAN DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_confirmed_fingerprint ON confirmed_frauds(fingerprint);
CREATE INDEX IF NOT EXISTS idx_confirmed_pending     ON confirmed_frauds(ingested_into_prophecy) WHERE ingested_into_prophecy = FALSE;

CREATE TABLE IF NOT EXISTS prophecy_matches (
    match_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prediction_id       UUID NOT NULL REFERENCES prophecy_ledger(prediction_id),
    fraud_id            VARCHAR(100) NOT NULL REFERENCES confirmed_frauds(fraud_id),
    lineage_id          VARCHAR(50) NOT NULL,
    match_confidence    FLOAT NOT NULL,
    days_ahead          INTEGER NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_matches_lineage ON prophecy_matches(lineage_id);

CREATE TABLE IF NOT EXISTS operator_performance (
    operator_name   VARCHAR(100) PRIMARY KEY,
    total_applied   INTEGER DEFAULT 0,
    hit_contribution INTEGER DEFAULT 0,
    current_weight  FLOAT DEFAULT 1.0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS human_gate_queue (
    queue_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    genome_id               UUID NOT NULL REFERENCES fraud_genomes(genome_id),
    impact_score            FLOAT DEFAULT 0.0,
    novelty_score           FLOAT DEFAULT 0.0,
    realism_score           FLOAT DEFAULT 0.0,
    lineage_trust           FLOAT DEFAULT 0.0,
    autonomy_level          VARCHAR(20) DEFAULT 'new',
    repair_recommendation   VARCHAR(20),
    status                  VARCHAR(20) DEFAULT 'pending',
    review_1_investigator   VARCHAR(50),
    review_1_decision       VARCHAR(20),
    review_1_notes          TEXT,
    review_2_investigator   VARCHAR(50),
    review_2_decision       VARCHAR(20),
    review_2_notes          TEXT,
    final_decision          VARCHAR(20),
    final_at                TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_queue_pending ON human_gate_queue(impact_score DESC) WHERE status = 'pending';
