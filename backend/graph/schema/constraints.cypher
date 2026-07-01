// ════════════════════════════════════════════════════════════════════════════
// TGIE Banking Knowledge Graph — Wave 1 schema DDL (Neo4j 5.x)
// Domains A (Identity) · B (Accounts/Products) · C (Movement) · E (Risk/Investigation)
// All statements are idempotent (IF NOT EXISTS) — safe to re-run by bootstrap.py.
// Generated for Phase 2. Wave 2 (Bank-Org D + Reference/Watchlist F) lives in
// constraints_wave2.cypher (added in Phase 3 / detection enrichment).
// ════════════════════════════════════════════════════════════════════════════

// ── Domain A · Identity & Customer ──────────────────────────────────────────
CREATE CONSTRAINT customer_id   IF NOT EXISTS FOR (n:Customer) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT kyc_id        IF NOT EXISTS FOR (n:KYC)      REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT pan_hash      IF NOT EXISTS FOR (n:PAN)      REQUIRE n.pan_hash IS UNIQUE;
CREATE CONSTRAINT aadhaar_hash  IF NOT EXISTS FOR (n:Aadhaar)  REQUIRE n.aadhaar_hash IS UNIQUE;
CREATE CONSTRAINT phone_e164    IF NOT EXISTS FOR (n:Phone)    REQUIRE n.e164 IS UNIQUE;
CREATE CONSTRAINT email_norm    IF NOT EXISTS FOR (n:Email)    REQUIRE n.address_norm IS UNIQUE;
CREATE CONSTRAINT address_id    IF NOT EXISTS FOR (n:Address)  REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT location_id   IF NOT EXISTS FOR (n:Location) REQUIRE n.id IS UNIQUE;

CREATE INDEX customer_segment   IF NOT EXISTS FOR (n:Customer) ON (n.segment);
CREATE INDEX customer_status    IF NOT EXISTS FOR (n:Customer) ON (n.status);
CREATE INDEX kyc_status         IF NOT EXISTS FOR (n:KYC)      ON (n.status);
CREATE INDEX kyc_expires        IF NOT EXISTS FOR (n:KYC)      ON (n.expires_at);
CREATE INDEX address_geohash    IF NOT EXISTS FOR (n:Address)  ON (n.geohash);
CREATE INDEX address_pincode    IF NOT EXISTS FOR (n:Address)  ON (n.pincode);
CREATE INDEX location_geohash   IF NOT EXISTS FOR (n:Location) ON (n.geohash);
CREATE INDEX location_highrisk  IF NOT EXISTS FOR (n:Location) ON (n.is_high_risk);
CREATE FULLTEXT INDEX customer_name_ft IF NOT EXISTS FOR (n:Customer) ON EACH [n.name];

// ── Domain B · Accounts, Products & Instruments ─────────────────────────────
CREATE CONSTRAINT account_id    IF NOT EXISTS FOR (n:Account)      REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT account_hash  IF NOT EXISTS FOR (n:Account)      REQUIRE n.account_no_hash IS UNIQUE;
CREATE CONSTRAINT card_id       IF NOT EXISTS FOR (n:Card)         REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT wallet_id     IF NOT EXISTS FOR (n:Wallet)       REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT loan_id       IF NOT EXISTS FOR (n:Loan)         REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT fd_id         IF NOT EXISTS FOR (n:FixedDeposit) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT insurance_id  IF NOT EXISTS FOR (n:Insurance)    REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT product_code  IF NOT EXISTS FOR (n:Product)      REQUIRE n.code IS UNIQUE;
CREATE CONSTRAINT beneficiary_id IF NOT EXISTS FOR (n:Beneficiary) REQUIRE n.id IS UNIQUE;

CREATE INDEX account_type       IF NOT EXISTS FOR (n:Account) ON (n.account_type);
CREATE INDEX account_status     IF NOT EXISTS FOR (n:Account) ON (n.status);
CREATE INDEX account_opened     IF NOT EXISTS FOR (n:Account) ON (n.opened_at);
CREATE INDEX account_dormant    IF NOT EXISTS FOR (n:Account) ON (n.dormant_since);
CREATE INDEX card_status        IF NOT EXISTS FOR (n:Card)    ON (n.status);
CREATE INDEX beneficiary_added  IF NOT EXISTS FOR (n:Beneficiary) ON (n.added_at);

// ── Domain C · Movement ─────────────────────────────────────────────────────
CREATE CONSTRAINT transaction_id IF NOT EXISTS FOR (n:Transaction) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT currency_code  IF NOT EXISTS FOR (n:Currency)    REQUIRE n.code IS UNIQUE;

// ts/amount are the hot range indexes for timeline replay + velocity windows
CREATE INDEX txn_ts             IF NOT EXISTS FOR (n:Transaction) ON (n.ts);
CREATE INDEX txn_amount         IF NOT EXISTS FOR (n:Transaction) ON (n.amount);
CREATE INDEX txn_rail           IF NOT EXISTS FOR (n:Transaction) ON (n.rail);
CREATE INDEX txn_flagged        IF NOT EXISTS FOR (n:Transaction) ON (n.is_flagged);
CREATE INDEX txn_risk           IF NOT EXISTS FOR (n:Transaction) ON (n.risk_score);
CREATE INDEX txn_rail_ts        IF NOT EXISTS FOR (n:Transaction) ON (n.rail, n.ts);

// ── Domain E · Risk, Alerts & Investigation ─────────────────────────────────
CREATE CONSTRAINT riskprofile_id IF NOT EXISTS FOR (n:RiskProfile)       REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT pattern_id     IF NOT EXISTS FOR (n:SuspiciousPattern) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT alert_id       IF NOT EXISTS FOR (n:Alert)             REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT case_no        IF NOT EXISTS FOR (n:Case)              REQUIRE n.case_no IS UNIQUE;
CREATE CONSTRAINT investigation_id IF NOT EXISTS FOR (n:Investigation)   REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT evidence_sha   IF NOT EXISTS FOR (n:Evidence)          REQUIRE n.sha256 IS UNIQUE;
CREATE CONSTRAINT regreport_id   IF NOT EXISTS FOR (n:RegulatoryReport)  REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT auditentry_id  IF NOT EXISTS FOR (n:AuditEntry)        REQUIRE n.id IS UNIQUE;

CREATE INDEX riskprofile_band    IF NOT EXISTS FOR (n:RiskProfile)       ON (n.band);
CREATE INDEX riskprofile_when    IF NOT EXISTS FOR (n:RiskProfile)       ON (n.computed_at);
CREATE INDEX pattern_code        IF NOT EXISTS FOR (n:SuspiciousPattern) ON (n.pattern_code);
CREATE INDEX pattern_when        IF NOT EXISTS FOR (n:SuspiciousPattern) ON (n.detected_at);
CREATE INDEX alert_status        IF NOT EXISTS FOR (n:Alert)             ON (n.status);
CREATE INDEX alert_severity      IF NOT EXISTS FOR (n:Alert)             ON (n.severity);
CREATE INDEX alert_created       IF NOT EXISTS FOR (n:Alert)             ON (n.created_at);
CREATE INDEX case_status         IF NOT EXISTS FOR (n:Case)              ON (n.status);
CREATE INDEX case_owner          IF NOT EXISTS FOR (n:Case)              ON (n.owner);
CREATE INDEX case_opened         IF NOT EXISTS FOR (n:Case)              ON (n.opened_at);
CREATE INDEX evidence_created    IF NOT EXISTS FOR (n:Evidence)          ON (n.created_at);
CREATE INDEX regreport_type      IF NOT EXISTS FOR (n:RegulatoryReport)  ON (n.type);
CREATE INDEX auditentry_actor    IF NOT EXISTS FOR (n:AuditEntry)        ON (n.actor);
CREATE INDEX auditentry_ts       IF NOT EXISTS FOR (n:AuditEntry)        ON (n.ts);
