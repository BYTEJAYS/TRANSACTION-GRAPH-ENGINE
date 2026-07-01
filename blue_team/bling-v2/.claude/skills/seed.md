# Database Seed / Reset — BLING Blue Team Detection Engine
# Read this file before seeding or resetting the database.

## Seed (Populate With Demo Data)

```bash
# Generate 10K synthetic transactions (270 fraud, 9730 legit)
python scripts/generate_test_data.py

# Load into PostgreSQL + seed Redis velocity counters
python scripts/load_sample_data.py

# Seed Redis feature cache (pre-computed graph features)
python scripts/seed_redis.py
```

## Reset (Wipe and Re-seed From Scratch)

```bash
# Drop and recreate all tables + constraints + indexes
python scripts/init_db.py

# Run migrations to latest schema
alembic upgrade head

# Train initial XGBoost model (required before load_sample_data.py)
python ml/train.py

# Re-seed
python scripts/generate_test_data.py && python scripts/load_sample_data.py && python scripts/seed_redis.py
```

## Required Environment Variables

- `POSTGRES_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis connection string
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` — needed for graph feature seeding

## What Gets Created

**500 accounts** across these profiles:
- Normal retail banking customers (majority)
- Gig workers (high-frequency, same device, daytime)
- Senior citizens (some used in digital arrest scenarios)
- Jan Dhan accounts (low-income, cash-heavy)
- Merchants (round amounts, evening settlements)

**10,000 transactions** split as:
| Category | Count | Description |
|----------|-------|-------------|
| Rapid layering | 50 | 3-6 hops, <60min each |
| Circular round-trips | 40 | 2-5 hops, 2-24hr |
| Fan-out smurfing | 30 | 1 source → 7-12 new accounts |
| Abandoned sink | 25 | Burst received, >80% retained, then silent |
| Cash mule | 20 | Receive→ATM_withdraw→dormant |
| Structuring | 25 | 5+ txns in ₹90K-₹99,999 band |
| Digital arrest | 30 | Senior + new VPA + night + high amount |
| Low-slow mule | 50 | 45-day normal warmup, then spike |
| Normal UPI | 3000 | Merchants, friends, family |
| Salary/payroll | 2000 | Regular, predictable |
| Festival gifts | 1000 | Diwali small amounts, new payees |
| Gig worker receipts | 500 | High frequency, same device, daytime |
| Student remittances | 500 | Education MCC, night, moderate amounts |
| Legit salary cycles | 500 | Cycle fires but legitimacy filter explains |
| Miscellaneous legit | 2230 | |

**Expected metrics after full pipeline run:**
- True Positive Rate: >75%
- False Positive Rate: <20% before Indian context, <5% after
- All 20 cash mule trails reconstructable by fund trail builder

## Warning: Never Run Against Production

`scripts/init_db.py` and `scripts/generate_test_data.py` check that `POSTGRES_URL` does not contain `prod`, `production`, or `bling_prod` before running. They will abort with an error if a production database is detected. Never override this check.
