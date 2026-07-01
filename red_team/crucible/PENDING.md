# CRUCIBLE Red Team — Pending Work

## Status: Pre-Integration / Demo-Ready

---

## Completed

- [x] `core/genome.py` — FraudGenome + 6 gene dataclasses + `to_transaction_list()`
- [x] `core/rail_constraints.py` — Hard validation (new rail taxonomy)
- [x] `core/fingerprint.py` — SHA256 fingerprint + 256-d FAISS embedding
- [x] `db/models.py` — SQLAlchemy 2.x, 7 tables
- [x] `db/schema.sql` — PostgreSQL DDL
- [x] `mutation/operators/` — 25 operators (20 standard + 5 advanced)
- [x] `mutation/fitness.py` — Ensemble disagreement × realism × novelty
- [x] `mutation/engine.py` — PBT main loop (500 genomes, 10k gen/night)
- [x] `critics/realism.py` — hard_validate() + soft_score()
- [x] `critics/novelty.py` — Bloom filter + FAISS cosine dedup
- [x] `sandbox/blue_clone.py` — MockBlueTeam + RealBlueTeam
- [x] `prophecy/ledger.py` — Store predictions + nightly matching
- [x] `prophecy/matcher.py` — Cosine ≥ 0.85 matching
- [x] `prophecy/scorer.py` — Hit rate → PBT weights
- [x] `human_gate/queue.py` — Impact-sorted review queue
- [x] `human_gate/router.py` — new_gate | bounded_retrain | human_decision
- [x] `learning/operator_weights.py` — Win-rate tracking
- [x] `learning/seed_enrichment.py` — Missed fraud → HIGH priority seeds
- [x] `learning/lineage_weights.py` — Prophecy + tracker weight blend
- [x] `workers/mutation_worker.py` — Celery nightly mutation (01:00)
- [x] `workers/nightly_worker.py` — Celery beat schedule
- [x] `api/main.py` — FastAPI, 8 endpoints + health
- [x] `test_dna/generator.py` — Genome → transaction JSON
- [x] `test_dna/bypass_verifier.py` — Assert score < 0.5 for all 3 DNAs
- [x] `test_dna/account_fixtures.py` — Account metadata (acc_ + hex format)
- [x] `test_dna/outputs/dna_001_*.json` — Merchant bipartite split
- [x] `test_dna/outputs/dna_002_*.json` — Abandoned node time dilation
- [x] `test_dna/outputs/dna_003_*.json` — Festival fan-out cover
- [x] `demo/seed_data.py` — 50 initial seeds (5 MO types × 10)
- [x] `demo/confirmed_frauds_mock.json` — 20 pre-dated confirmed frauds
- [x] `requirements.txt`, `docker-compose.yml`, `Dockerfile`, `.env.example`
- [x] `README.md` — Full system documentation
- [x] `agent_docs/` — architecture, api, database, gotchas updated
- [x] Transaction format: `acc_` + hex IDs, new payment rail taxonomy

---

## Pending

### High Priority (needed before demo)

- [ ] **5 test files** (`tests/test_operators.py`, `test_rail.py`, `test_fitness.py`, `test_prophecy.py`, `test_api.py`)
  - Wire up pytest for all major paths
  - `test_operators.py`: every operator on valid genome → valid output, no exception
  - `test_rail.py`: violations → correct rejection; valid genomes → pass
  - `test_fitness.py`: zero when mean_score > 0.5; zero when realism < 0.5
  - `test_prophecy.py`: cosine ≥ 0.85 → HIT; hit rate → correct weight tier
  - `test_api.py`: all 8 endpoints return 200; receive_fraud_dna persists to ledger

- [ ] **`scripts/init_db.py`** — Run `schema.sql` against PostgreSQL on first boot

- [ ] **`.claude/CLAUDE.md`** — Project-specific CLAUDE.md with stack, commands, key gotchas

### Medium Priority (needed for integration)

- [ ] **DB-backed Prophecy Ledger** — Replace in-memory `ProphecyLedger` with SQLAlchemy 2.x version using `ProphecyLedgerRecord` + `ConfirmedFraud` + `ProphecyMatch` tables

- [ ] **DB-backed Human Gate Queue** — Replace in-memory `HumanGateQueue` with `HumanGateQueueRecord` table

- [ ] **DB-backed Operator Performance** — Replace in-memory `OperatorPerformanceTracker` with `OperatorPerformance` table

- [ ] **`human_gate/api.py`** — Separate FastAPI router for human gate (currently in `api/main.py`)

- [ ] **Two-investigator confirmation** — Genome approval requires 2 different reviewer_ids

- [ ] **Auth middleware** — JWT/API key for `POST /receive_fraud_dna` and `POST /review/*`

- [ ] **Blue Team client integration** — Verify `POST /receive_fraud_dna` payload matches `red_team_client.py` in Blue Team repo

### Low Priority / Nice-to-Have

- [ ] **`demo/evolution_replay_cache.json`** — Pre-computed 0→50 generation fitness snapshots so demo is instant (no live PBT needed)

- [ ] **More test DNA patterns** — 5 additional DNAs using advanced operators (ghost_node, mule_hub, threshold_fragmenter)

- [ ] **`test_dna/outputs/dna_004_ghost_node_cash_bridge.json`** — Ghost node pattern
- [ ] **`test_dna/outputs/dna_005_mule_hub_nizamabad.json`** — 20-source hub pattern

- [ ] **Grafana dashboard** — Fitness/generation curve, prophecy hit rate over time, operator weight evolution

- [ ] **Add remaining 52-pattern seeds** — 40 of the 52 patterns from fraud taxonomy not yet in seed bank (patterns 8-52 beyond the 5 current MO types)

---

## Known Issues

1. `validate_genome()` in `rail_constraints.py` requires `collector_count >= 1` but `fan_out` topologies have 0 collectors → need to exempt fan_out from that check

2. `blue_clone.py` `_tier2_gates()` Gate 3 (bipartite) has a bug: `density = min(1.0, senders / max(1, senders))` always = 1.0 → always fires when senders ≥ 5. Real bipartite density needs graph-level computation. Current mock is conservative (fires too eagerly).

3. `MockBlueTeam._apply_indian_context()` festival check assumes gifting_history=True when festival operator was applied — this is a simplification. Production would check actual account history.

4. In-memory singletons (`ledger`, `novelty_critic`, `human_gate_queue`) are reset on every API restart. Not a problem for demo, but breaks prophecy continuity in staging.

5. `cycle_extender` sets `topology.type = "chain"` — but this means the counterfactual router can't detect it as a cycle pattern and defaults to `human_decision`. May need a separate flag.

---

## Transaction Format (LOCKED)

All transactions must use this exact format — no deviation:
```json
{
  "from_account": "acc_<10 lowercase hex chars>",
  "to_account": "acc_<10 lowercase hex chars>",
  "amount": <integer>,
  "payment_rail": "<one of: ach_transfer | wire_transfer | p2p_transfer | internal_transfer | crypto_exchange | bill_payment | debit_purchase | atm_withdrawal | pos_transaction>",
  "timestamp": "YYYY-MM-DDTHH:MM:SS"
}
```

---

*Last updated: 2026-05-19*
