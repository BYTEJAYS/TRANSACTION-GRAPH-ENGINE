# Gotchas
# Maintained by Claude. Read first when something unexpected happens.
# Add an entry every time a non-obvious problem is found or decision is made.

## 1. FraudGenome field names are NOT what you'd expect

**Wrong**: `genome.lineage`, `genome.parent_id`
**Correct**: `genome.mutation_history`, `genome.parent_genome_id`

**Wrong**: `channels.mix = ["NEFT"]`
**Correct**: `channels.mix = {"NEFT": 1.0}` — it's `Dict[str, float]`

**Wrong**: `FraudGenome(genome_id=..., ...)` as first arg
**Correct**: `FraudGenome(lineage_id="mule_ring", ...)` — lineage_id is first

**Wrong**: `timing.festival_timing = "diwali"` (string)
**Correct**: `timing.festival_timing = {"name": "diwali", "month": 10}` (dict)
Also set `timing.festival_name = "diwali"` (separate field used by fingerprint.py)

## 2. Blue Team cycle gate: checks topology.type field, not graph structure

`cycle_extender` operator uses `topology.type = "chain"` on purpose. If you set it to "cycle", the Blue Team gate fires immediately (returns score 1.0). The 4-hop evasion works because the gate only checks the type string, not the actual graph.

## 3. Bipartite gate: 5-sender threshold is per-collector, not total

The gate fires when `sender_count >= 5 AND density > 0.7`. `sender_count` in mock = `genome.topology.width`. Keep width ≤ 4 OR use merchant flag to suppress. Merchant legitimacy filter suppresses when density < 0.85.

## 4. FAISS returns inner product (cosine for L2-normalized vectors)

`IndexFlatIP.search()` returns similarity (higher = more similar). For cosine similarity, vectors MUST be L2-normalized before adding. `compute_embedding()` in fingerprint.py does this automatically. If you add raw vectors to the index, results will be meaningless.

## 5. Prophecy ledger is in-memory by default

The module-level `ledger = ProphecyLedger()` singleton is in-memory. Data is lost on restart. For production, replace with DB-backed version using SQLAlchemy models in `db/models.py` (ProphecyLedgerRecord table exists).

## 6. MockBlueTeam gate 4 (cash_mule_sink) fires for ANY account ≤ 180 days

Even 179-day-old accounts trigger it. The safe zone is 200+ days. DNA 001/002/003 all use 200+ day accounts. The `age_the_accounts` operator pushes to 200-545 days specifically for this bypass.

## 7. Indian context adjuster: festival check uses avg_amount, not max_amount

The adjuster checks `avg_amount < 5_000`. If one transaction is ₹6K but others average ₹4.5K, the festival reduction still applies. DNA 003 uses amounts ₹4,650-₹4,890 (all safely below ₹5K).

## 8. Operator `festival_timing` sets TimingGene.festival_timing = dict

The operator sets `genome.timing.festival_timing = {"name": "diwali", ...}`. The realism critic checks `bool(genome.timing.festival_timing)` which is truthy for any non-empty dict. The fingerprint uses `genome.timing.festival_name` separately.

## 9. Subagents cannot write files in this project (permission denied)

Background agents with Write/Bash tools fail due to hook restrictions. All file creation must happen in the main conversation. Do not spawn agents for file-writing tasks.

## 10. Migration path is protected by hook

`db/migrations/` path is blocked. Use `db/schema.sql` instead. The init script (`scripts/init_db.py`) references `schema.sql`.

## 11. DEFAULT_OPERATOR_WEIGHTS keyed by function __name__ (string)

When sampling operators in PBT engine, `op.__name__` must match the keys in `DEFAULT_OPERATOR_WEIGHTS`. If you add a new operator without registering it in `ALL_OPERATORS`, it will never be sampled.

## 12. Ghost node injector creates cash_out_method = "atm_withdrawal_redeposit"

This is a new cash_out_method value not in the original `cash_out_disguise` operator's set. MockBlueTeam Gate 4 checks `cash_out_method is None` — having any method set prevents the gate from firing on the simplified check. Good side effect.

## 13. `compute_embedding()` padding uses interaction terms, not zeros

The 256-d embedding pads dimensions 53-255 with `features[i % 53] × features[(i+7) % 53]`. This is intentional — zeros create degenerate FAISS similarity scores where unrelated genomes appear similar because their zero dimensions match.
