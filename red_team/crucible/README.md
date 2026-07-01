# CRUCIBLE — Red Team Fraud Engine
### BLING Blue Team | Union Bank of India Hackathon 2026

```
  ██████╗██████╗ ██╗   ██╗ ██████╗██╗██████╗ ██╗     ███████╗
 ██╔════╝██╔══██╗██║   ██║██╔════╝██║██╔══██╗██║     ██╔════╝
 ██║     ██████╔╝██║   ██║██║     ██║██████╔╝██║     █████╗
 ██║     ██╔══██╗██║   ██║██║     ██║██╔══██╗██║     ██╔══╝
 ╚██████╗██║  ██║╚██████╔╝╚██████╗██║██████╔╝███████╗███████╗
  ╚═════╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝╚═╝╚═════╝ ╚══════╝╚══════╝
```

---

## What Is This?

CRUCIBLE is the **adversarial half** of the BLING fraud detection system.

Its job: **find fraud patterns that Blue Team can't detect — before real criminals do.**

It works by continuously evolving synthetic fraud "genomes" using an AI evolution engine. Every night it generates thousands of variations, keeps the ones that slip through detection, and sends them to human reviewers. When a predicted pattern later appears in real fraud data, the system learns and gets smarter.

> Think of it as: *a red team that never sleeps, never gets bored, and learns from every real fraud case.*

---

## The Closed Loop — In Plain English

```
                          ┌─────────────────────────────┐
  50 Seed Fraud Patterns  │   PBT Evolution Engine      │
  (5 real fraud types) ──►│   500 genomes × 10,000      │
                          │   mutations every night      │
                          └──────────────┬──────────────┘
                                         │  Top survivors
                          ┌──────────────▼──────────────┐
                          │   Human Review Queue        │
                          │   Sorted by: money at risk  │
                          │   × ease of execution       │
                          └──────────────┬──────────────┘
                                         │  Approved
                          ┌──────────────▼──────────────┐
                          │  Blue Team Hardening        │
                          │  new_gate | retrain | alert │
                          └─────────────────────────────┘

  Real Fraud ──► Prophecy Ledger ──► Match (≥ 85% similar) ──► Smarter evolution
```

**Step-by-step:**
1. Start with 50 known fraud patterns as seeds
2. Mutate them 10,000 ways every night using 25 mutation operators
3. Score each mutation: is it realistic? novel? does it evade detection?
4. Keep the top survivors, discard the rest
5. Send top bypasses to a human investigator queue
6. When real fraud matches a past prediction → that mutation style gets promoted

---

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env with your PostgreSQL and Redis connection strings

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Start backing services
docker-compose up postgres redis -d

# 4. Start the API server
uvicorn red_team.api.main:app --host 0.0.0.0 --port 8001 --reload

# 5. Confirm the 3 bypass DNAs evade detection
python -m red_team.test_dna.bypass_verifier
```

### Run the Demo

```bash
# Trigger prophecy matching (matches predictions against known frauds)
curl http://localhost:8001/api/v1/demo/run_prophecy_match

# Watch fitness improve across 50 generations of evolution
curl http://localhost:8001/api/v1/demo/evolution_replay

# View the human review queue
curl http://localhost:8001/api/v1/red_team/queue

# System health
curl http://localhost:8001/health
```

### Run Nightly Workers (background evolution)

```bash
celery -A red_team.workers.mutation_worker worker &
celery -A red_team.workers.nightly_worker beat &
```

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Language | Python 3.11 | Rich ML/data ecosystem |
| API | FastAPI + Uvicorn | Async, fast, automatic OpenAPI docs |
| Evolution engine | Custom PBT | Population-Based Training for genome evolution |
| Vector search | FAISS-cpu (256-d) | Fast cosine similarity for novelty detection |
| Deduplication | Bloom filter + FAISS | Two-layer: fast reject → precise distance |
| Task queue | Celery 5 + Redis 7 | Scheduled nightly workers |
| Database | PostgreSQL 15 + SQLAlchemy 2 | Genome persistence, prophecy ledger |
| Containerization | Docker + docker-compose | One-command service startup |

---

## Project Structure

```
red_team/
│
├── core/                    ← The genome data model
│   ├── genome.py            #  FraudGenome + 6 gene dataclasses
│   ├── rail_constraints.py  #  Hard rules: UPI limits, NEFT blackout, KYC tiers
│   └── fingerprint.py       #  SHA256 fingerprint + 256-d FAISS embedding
│
├── mutation/                ← The evolution engine
│   ├── engine.py            #  PBT loop: 500 genomes, 10,000 gen/night
│   ├── fitness.py           #  Score = disagreement × realism × novelty
│   └── operators/           #  25 mutation operators (see table below)
│       ├── topology.py      #    Graph shape mutations
│       ├── timing.py        #    Timing and dormancy mutations
│       ├── amounts.py       #    Amount-level evasions
│       ├── channels.py      #    Payment rail hopping
│       ├── accounts.py      #    Account age and velocity
│       ├── structural.py    #    Structural camouflage
│       └── advanced.py      #    5 advanced Indian fraud patterns
│
├── critics/                 ← Quality filters on evolved genomes
│   ├── realism.py           #  Is this economically plausible? (hard + soft check)
│   └── novelty.py           #  Is this actually new? (Bloom filter + FAISS)
│
├── prophecy/                ← Prediction and self-learning
│   ├── ledger.py            #  Store predictions; receive real fraud reports
│   ├── matcher.py           #  Cosine ≥ 0.85 → PROPHECY HIT
│   └── scorer.py            #  Hit rate → PBT weight multiplier
│
├── sandbox/
│   └── blue_clone.py        #  MockBlueTeam: 5 gates + Tier 3 + Indian adjuster
│
├── human_gate/              ← Investigator review workflow
│   ├── queue.py             #  Impact-sorted queue
│   ├── router.py            #  new_gate | bounded_retrain | human_decision
│   └── api.py               #  FastAPI endpoints
│
├── learning/                ← Feedback loop into evolution
│   ├── operator_weights.py  #  Which operators produce real hits?
│   ├── seed_enrichment.py   #  Real missed fraud → HIGH priority seed (5×)
│   └── lineage_weights.py   #  Blend prophecy + hit tracker weights
│
├── workers/
│   ├── mutation_worker.py   #  Celery: 10,000 generations at 01:00
│   └── nightly_worker.py    #  Celery beat: prophecy match at 02:00
│
├── api/main.py              ← 9 REST endpoints + CORS + health
│
├── test_dna/                ← 3 verified bypass transaction chains
│   ├── generator.py         #  Genome → transaction JSON
│   ├── bypass_verifier.py   #  Assert all 3 DNAs score < 0.5
│   ├── account_fixtures.py  #  Standardised account metadata
│   └── outputs/             #  Pre-generated JSON chains (dna_001, 002, 003)
│
├── demo/
│   ├── seed_data.py              #  50 initial seeds (5 fraud types × 10)
│   └── confirmed_frauds_mock.json  #  20 pre-dated frauds for prophecy demo
│
└── db/
    ├── models.py            #  SQLAlchemy 2: 7 tables
    └── schema.sql           #  Raw DDL
```

---

## How Evolution Works

### The Fitness Function

Every evolved genome is scored on three axes:

```
fitness = ensemble_disagreement × realism_score × novelty_score

  ensemble_disagreement  how much Blue Team models disagree → higher = harder to detect
  realism_score          economic rationality: mule profit/risk, timing, geography
  novelty_score          distance from all known genomes (FAISS cosine)

Genome is killed (fitness = 0) if:
  - Blue Team detects it on average (mean_score > 0.5)
  - realism_score < 0.5  (physically impossible transaction)
  - novelty_score < 0.1  (near-duplicate of existing genome)
```

### The 25 Mutation Operators

| # | Operator | Category | Weight | What it does |
|---|----------|----------|--------|-------------|
| 1 | `add_hop` | Topology | 1.2 | Insert intermediate account hop |
| 2 | `fan_out_collector` | Topology | 1.0 | Split flow to multiple collectors |
| 3 | `insert_abandoned_node` | Topology | 1.3 | Add dormant relay account |
| 4 | `insert_merchant_node` | Topology | 1.0 | Add MCC-coded merchant cover |
| 5 | `create_bipartite_split` | Topology | 1.0 | Fan-in → fan-out split |
| 6 | `time_dilation` | Timing | 1.0 | Stretch spacing 1.5–5× |
| 7 | `add_dormancy_period` | Timing | 1.0 | Insert 30–90 day gap |
| 8 | `jitter_timing` | Timing | 1.0 | ±15–35% organic noise |
| 9 | `festival_timing` | Timing | 1.3 | Diwali / Eid / Holi cover |
| 10 | `just_under_threshold` | Amounts | 1.0 | 8% below reporting thresholds |
| 11 | `amount_noise` | Amounts | 1.0 | 2–8% organic variation |
| 12 | `pyramid_amounts` | Amounts | 1.0 | Decreasing/increasing pattern |
| 13 | `channel_hop` | Channels | 1.0 | Mix UPI / NEFT / IMPS |
| 14 | `upi_app_diversity` | Channels | 1.0 | Rotate BHIM / GPay / PhonePe |
| 15 | `age_the_accounts` | Accounts | 1.4 | Push ages to 200–545 days |
| 16 | `reduce_velocity` | Accounts | 1.0 | Velocity ratio 0.02–0.08 |
| 17 | `geographic_spread` | Accounts | 1.0 | 4–5 cities |
| 18 | `recognized_pattern_verification` | Structural | 0.3 | Mimic salary / B2B |
| 19 | `cash_out_disguise` | Structural | 0.7 | Delayed / POS / wallet / gold |
| 20 | `layered_mixing` | Structural | 0.6 | 3–6 layer obfuscation |
| 21 | `mule_hub_creator` | **Advanced** | **1.8** | 20–46 source hub (Nizamabad pattern) |
| 22 | `cycle_extender` | **Advanced** | **1.4** | 2-hop → 4-hop chain |
| 23 | `threshold_fragmenter` | **Advanced** | **1.5** | ₹49K × N mule splitting |
| 24 | `ghost_node_injector` | **Advanced** | **2.0** | ATM cash gap (breaks traceability) |
| 25 | `dormant_activator` | **Advanced** | **1.6** | 180+ day dormancy then burst |

Higher weight = selected more often during PBT sampling.

---

## The Prophecy Ledger — Self-Learning Loop

```
Day  0:  Red Team evolves genome G, stores its 256-d embedding
Day 30:  Blue Team sends confirmed real-world fraud F
Day 31:  Nightly job → cosine(G_embedding, F_embedding)
         ≥ 0.85 → PROPHECY HIT — Red Team predicted this 30 days early

Hit rate → PBT weight multiplier:
  > 20%  →  2.0×  (double sampling probability)
  10-20% →  1.5×
   5-10% →  1.0×  (no change)
   < 5%  →  0.3×  (deprioritised)

Day 32:  PBT uses updated weights → more mutations like G generated
```

This loop is why CRUCIBLE gets better over time without manual tuning.

---

## 3 Verified Blue Team Bypasses (Test DNAs)

Each DNA is a hand-crafted transaction chain that scores **< 0.5** on MockBlueTeam.

### DNA 001 — Merchant Bipartite Split
**Target: < 0.35** | 9 transactions

```
ACC_4001 → ACC_MERCH_01   ₹8,347   NEFT   2026-05-15 10:03
ACC_4002 → ACC_MERCH_01   ₹7,891   NEFT   2026-05-16 11:22
ACC_4003 → ACC_MERCH_02   ₹9,214   NEFT   2026-05-15 14:15
ACC_4004 → ACC_MERCH_02   ₹8,603   NEFT   2026-05-17 10:45
ACC_4005 → ACC_MERCH_03   ₹8,021   NEFT   2026-05-16 09:30
ACC_4006 → ACC_MERCH_03   ₹7,654   NEFT   2026-05-18 13:55
ACC_MERCH_01 → ACC_SINK_01  ₹15,938  IMPS  2026-06-02 11:00  [18-day gap]
ACC_MERCH_02 → ACC_SINK_01  ₹17,517  IMPS  2026-06-03 14:30
ACC_MERCH_03 → ACC_SINK_01  ₹15,275  IMPS  2026-06-04 10:15
```

**Why it bypasses:** Only 2 senders per merchant (threshold is ≥ 5). Merchant flag suppresses bipartite gate. All accounts 200+ days old.

---

### DNA 002 — Abandoned Node Time Dilation
**Target: < 0.30** | 4 transactions

```
ACC_4007 → ACC_COLLECT_01  ₹13,450  NEFT  2026-05-01 09:15
ACC_4008 → ACC_COLLECT_01  ₹11,870  NEFT  2026-06-05 10:30  [35-day gap]
ACC_4009 → ACC_COLLECT_01  ₹14,230  NEFT  2026-07-10 11:00  [35-day gap]
ACC_4010 → ACC_COLLECT_01  ₹12,615  NEFT  2026-08-14 09:45  [35-day gap]
```

**Why it bypasses:** Only 4 senders (threshold is ≥ 5). 35-day spacing falls outside all rolling monitoring windows. All accounts 300+ days old.

---

### DNA 003 — Festival Fan-Out Cover
**Target: < 0.25** | 5 transactions

```
ACC_4011 → ACC_RCP_01  ₹4,800  UPI  2026-10-15 14:03  [Diwali]
ACC_4011 → ACC_RCP_02  ₹4,650  UPI  2026-10-15 16:22
ACC_4011 → ACC_RCP_03  ₹4,750  UPI  2026-10-16 13:15
ACC_4011 → ACC_RCP_04  ₹4,890  UPI  2026-10-16 15:45
ACC_4011 → ACC_RCP_05  ₹4,720  UPI  2026-10-17 12:30
```

**Why it bypasses:** Diwali timing (Oct 15–17) triggers Indian context adjuster → 30% score reduction. All amounts < ₹5K look like festival gifts.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/health` | Liveness probe |
| `POST` | `/api/v1/red_team/receive_fraud_dna` | Blue Team sends confirmed fraud here |
| `GET`  | `/api/v1/red_team/queue` | Human review queue, sorted by impact |
| `POST` | `/api/v1/red_team/review/{genome_id}` | Investigator approves or discards |
| `GET`  | `/api/v1/red_team/prophecy/stats` | Prediction hit rates and accuracy |
| `GET`  | `/api/v1/red_team/lineages` | Operator weights and lineage scores |
| `GET`  | `/api/v1/demo/run_prophecy_match` | Manually trigger prophecy matching |
| `GET`  | `/api/v1/demo/evolution_replay` | Fitness trajectory across gen 0→50 |
| `GET`  | `/api/v1/test_dna/{dna_id}` | Fetch a test DNA transaction chain |

Interactive docs available at `http://localhost:8001/docs` when the server is running.

---

## Blue Team Gate Bypass Reference

| Gate | Fires When | Bypass Used |
|------|-----------|-------------|
| Cycle gate | `topology.type == "cycle"` | Use `chain` type — no cycle flag set |
| Bipartite gate | ≥ 5 senders AND density > 0.7 | Use ≤ 4 senders OR set merchant flag |
| Cash mule sink | Account age ≤ 180d AND inflow ≥ ₹50K | All accounts 200+ days old |
| Abandoned sink | Young accounts + burst + no delay | Continuous forwarding, no dormancy |
| Merchant terminal | `terminal_id != None` | Never set terminal_id |
| Indian adjuster | Festival + amount < ₹5K → 0.70× | Diwali timing + micro-amounts |

---

## Fraud Pattern Intelligence (Seed Data)

CRUCIBLE seeds with **52 real-world fraud patterns** from 5 categories:

**Mule Networks** — Nizamabad ₹152Cr hub-and-spoke, sleeping mule rings (4,200 accounts), cross-state routing (UP→Bihar→GJ→TG), MuleHunter.ai evasion clusters

**Cycle & Layering** — 4-hop cycles, temporal graph smearing (30-day windows), ghost node cash bridges, amount fragmentation (₹49K × 20 mules)

**Velocity & Threshold** — ₹99,800 × 50 mules (just under ₹1L UPI limit), time-shifted NEFT/IMPS (11:58 PM / 12:02 AM), gradual amount spikes, normal business-hour operation to invert night-flag signals

**Synthetic Identities** — 18-month seasoned synthetics, Frankenstein IDs (PAN Delhi / Mobile Bangalore / Txn Mumbai), full synthetic mule rings

---

## Verification Checklist

```bash
# Unit tests
pytest tests/ -v

# All 3 bypass DNAs must score < 0.5
python -m red_team.test_dna.bypass_verifier
#   DNA 001: < 0.35
#   DNA 002: < 0.30
#   DNA 003: < 0.25

# API health
curl http://localhost:8001/health

# Human gate queue (expect ≥ 3 items)
curl http://localhost:8001/api/v1/red_team/queue

# Evolution replay (fitness must increase gen 0 → 50)
curl http://localhost:8001/api/v1/demo/evolution_replay

# Prophecy match (expect ≥ 5 hits from confirmed_frauds_mock.json)
curl http://localhost:8001/api/v1/demo/run_prophecy_match
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Purpose | Example |
|----------|---------|---------|
| `DATABASE_URL` | PostgreSQL connection | `postgresql://red_team:password@localhost:5432/red_team` |
| `REDIS_URL` | Celery broker | `redis://localhost:6379/0` |
| `BLUE_TEAM_URL` | Real Blue Team API (blank = sandbox) | *(leave blank for demo)* |
| `BLUE_TEAM_API_KEY` | Blue Team auth | *(leave blank for demo)* |
| `API_HOST` | Bind address | `0.0.0.0` |
| `API_PORT` | Port | `8001` |
| `LOG_LEVEL` | Verbosity | `INFO` |
| `SECRET_KEY` | App secret (auth pending) | *(any random string)* |

**Never commit `.env` — it is gitignored.**

---

## Current Status (Pre-Integration / Demo-Ready)

| Feature | Status |
|---------|--------|
| PBT evolution engine (500 genomes, 25 operators) | ✅ Complete |
| MockBlueTeam (5 gates + Indian adjuster) | ✅ Complete |
| 3 verified bypass DNAs | ✅ Complete |
| Prophecy Ledger + matching | ✅ Complete |
| Human Gate review queue | ✅ Complete |
| Fitness function (3-factor) | ✅ Complete |
| Nightly Celery workers | ✅ Complete |
| FastAPI (9 endpoints) | ✅ Complete |
| Real Blue Team integration | 🔲 Post-hackathon |
| DB-backed singletons (ledger persistence) | 🔲 Pending |
| Auth / JWT | 🔲 Out of MVP scope |
| Grafana dashboards | 🔲 Out of MVP scope |

---

*Built for BLING Blue Team — Union Bank of India Hackathon 2026*
*Pre-integration mode: all evolution runs against MockBlueTeam (offline sandbox)*
