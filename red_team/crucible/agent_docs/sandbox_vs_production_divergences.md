# Sandbox vs Production — Divergence Log
# Every place blue_clone.py differs from the real Blue Team.
# This is the production migration to-do list.
#
# MANDATORY: Update this file EVERY TIME blue_clone.py is changed.
# No sandbox change is complete until this file is updated.
# Steps: (1) add/update D-XX entry, (2) update Changelog table, (3) update Priority table.
# Rule source: .claude/CLAUDE.md Rule #12

---

## How to use this document

1. When you are satisfied with a sandbox change → pick the entry from this log
2. Follow the "Production change required" instructions
3. Run the gating criteria listed for that entry
4. Once production is updated → mark entry SHIPPED and add the deploy date

**Direction key**:
- `SANDBOX AHEAD` — sandbox has detection that production lacks (production is blind to this pattern)
- `PRODUCTION AHEAD` — production has logic that sandbox approximates incorrectly (sandbox gives wrong signal)
- `BOTH WRONG` — neither is correct; fix must go to both

---

## DIVERGENCE-01: Gate 2 — Abandoned Sink (Two-Path Restructure)
**Direction**: SANDBOX AHEAD  
**Status**: ⚠️ Sandbox fixed | ❌ Production still has the gap  
**Risk if not fixed**: Old dormant-reactivated accounts (age ≥ 180d, 3+ sources, rapid forward) bypass Gate 2 permanently

### What production has today (the gap)
```cypher
-- sink_queries.py → check_abandoned_sink()
MATCH (sink:Account)
WHERE sink.account_age_days < 180          -- ← HARD CEILING: old accounts completely exempt
  AND sink.inflow_last_30d > 50000
  AND sink.retention_ratio > 0.80
  AND sink.days_since_last_send > 30
  AND NOT sink.kyc_occupation IN ['merchant', 'retailer', 'shopkeeper']
RETURN sink
```

### What sandbox has (two-path structure)
```python
# blue_clone.py → _simulate_sink_data()
# PATH A (age < 180): identical to production Cypher above — UNCHANGED
# PATH B (age >= 180): NEW — requires 3 compensating conditions (NEVER-2 compliant):
#   1. sender_count >= 3   (NRI = 1-2 senders; they are safe)
#   2. dormancy >= 60d     (vacation = 30-45d; 60d+ = reactivated mule)
#   3. has_forwarding=True (wedding/savings = hold, not forward; they are safe)
```

### Production Cypher required (NEVER-2 compliant)
```cypher
-- PATH A: New mule accounts — UNCHANGED from production
MATCH (sink:Account)
WHERE sink.account_age_days < 180
  AND sink.inflow_last_30d > 50000
  AND sink.retention_ratio > 0.80
  AND sink.days_since_last_send > 30
  AND NOT sink.kyc_occupation IN ['merchant', 'retailer', 'shopkeeper']
RETURN sink, 'new_mule' AS detection_path

UNION

-- PATH B: Old dormant-reactivated accounts — NEW ADDITION
MATCH (sink:Account)
WHERE sink.account_age_days >= 180
  AND sink.inflow_last_30d > 50000
  AND sink.days_since_last_send >= 60
  AND NOT sink.kyc_occupation IN ['merchant', 'retailer', 'shopkeeper']
-- Condition 1: multi-source
MATCH (source:Account)-[t:TRANSACTION]->(sink)
WHERE t.timestamp > datetime() - duration('P30D')
WITH sink, count(DISTINCT source) AS sender_count
WHERE sender_count >= 3
-- Condition 3: rapid forwarding within 7d of burst
MATCH (sink)-[fwd:TRANSACTION]->(forward:Account)
WHERE fwd.timestamp > datetime() - duration('P7D')
RETURN sink, 'old_dormant_reactivated' AS detection_path
```

### Gating criteria before production deploy
- [ ] `EXPLAIN` the Cypher — `days_since_last_send` and `account_age_days` must be indexed in Neo4j
- [ ] Run on 30-day historical graph — FP rate < 5% on confirmed-legit transactions
- [ ] Verify 4 protection scenarios pass (see validation checklist Part 8-A FP risk table)
- [ ] DBA reviews the UNION query plan — two separate MATCH patterns must not cause a full graph scan
- [ ] PR approved by Blue Team lead engineer
- [ ] `model_audit` INSERT must fire for both detection paths (A-03 constraint)

### Sandbox test results (4 scenarios verified)
| Scenario | Score | Action | Gate |
|----------|-------|--------|------|
| Fraud: 4 sources, age=365, dormancy=90d, depth=3 | 1.0 | HIGH_RISK | abandoned_sink |
| NRI: 1 sender, age=365, no forward | 0.25 | PASS | — |
| Wedding: 4 senders, age=350, no forward | 0.21 | PASS | — |
| Seasonal merchant: 8 senders, merchant, age=400 | 0.26 | PASS | — |

---

## DIVERGENCE-02: Gate 0 — Rapid Relay (NEW GATE, SANDBOX ONLY)
**Direction**: SANDBOX AHEAD  
**Status**: ⚠️ Sandbox built and tested | ❌ Does not exist in production  
**Risk if not built in production**: Multi-source abandoned node pattern (≥4 sources, near-full conservation, long dormancy) bypasses real Blue Team entirely when account fixtures aren't available for Gate 2

### What sandbox has
```python
# blue_clone.py → _simulate_rapid_relay()
# Backstop gate — fires when:
#   - sources >= 4
#   - total_inflow >= ₹1L
#   - dormancy_days >= 60
#   - conservation >= 95%   (fan_in: uses total_inflow × 0.97, not amounts[-1])
#   - collector NOT in legit aggregator occupations
```

### Two bugs fixed in sandbox (relevant to production build)
1. **Conservation calculation**: For fan_in/bipartite topologies, `amounts[-1]` is the last SOURCE payment, not the forwarded outflow. Must use `total_inflow × 0.97` (UPI/NEFT fee) or compute actual forwarded sum from transaction graph.
2. **Timing proxy**: `spacing_days` measures gap between source transactions (attacker can space these normally). The reactivation signal is `dormancy_days ≥ 60` — account was asleep before the burst, not transaction-to-transaction spacing.

### Production Cypher required
```cypher
-- Gate 0: Rapid Relay (run BEFORE all existing Tier 2 gates)
MATCH (collector:Account)
WHERE collector.days_since_last_send >= 60
  AND collector.inflow_last_30d >= 100000
  AND NOT collector.kyc_occupation IN [
      'merchant', 'retailer', 'shopkeeper',
      'salary_processor', 'payroll_processor',
      'insurance_company', 'tax_collector', 'utility_provider'
  ]
-- Count distinct sources in last 14 days
MATCH (source:Account)-[t_in:TRANSACTION]->(collector)
WHERE t_in.timestamp > datetime() - duration('P14D')
WITH collector, count(DISTINCT source) AS source_count, sum(t_in.amount) AS total_inflow
WHERE source_count >= 4
-- Measure conservation: what fraction left within 7d of burst
MATCH (collector)-[t_out:TRANSACTION]->(forward:Account)
WHERE t_out.timestamp > datetime() - duration('P7D')
WITH collector, source_count, total_inflow, sum(t_out.amount) AS total_outflow
WHERE total_outflow / total_inflow >= 0.95
RETURN collector, source_count, total_inflow, total_outflow,
       round(total_outflow / total_inflow, 3) AS conservation_ratio
```

### Production SQL (PostgreSQL — evidence package)
```sql
-- Conservation ratio for fan_in/bipartite — do NOT use last transaction amount
SELECT
    collector_account_id,
    COUNT(DISTINCT sender_account_id)                                 AS source_count,
    SUM(amount) FILTER (WHERE direction = 'in')                       AS total_inflow,
    SUM(amount) FILTER (WHERE direction = 'out'
                        AND txn_date >= burst_start_date)             AS total_outflow,
    ROUND(
        SUM(amount) FILTER (WHERE direction = 'out' AND txn_date >= burst_start_date)
        / NULLIF(SUM(amount) FILTER (WHERE direction = 'in'), 0),
    3)                                                                AS conservation_ratio
FROM account_transaction_summary
WHERE collector_dormancy_days >= 60
GROUP BY collector_account_id, burst_start_date
HAVING COUNT(DISTINCT sender_account_id) >= 4
   AND SUM(amount) FILTER (WHERE direction = 'in') >= 100000
   AND ROUND(
       SUM(amount) FILTER (WHERE direction = 'out' AND txn_date >= burst_start_date)
       / NULLIF(SUM(amount) FILTER (WHERE direction = 'in'), 0), 3) >= 0.95;
```

### Gating criteria before production deploy
- [ ] Run in LOG-ONLY mode for 2 weeks — do NOT escalate to REVIEW yet
- [ ] Review every triggered case manually — tune `source_count ≥ 4` and `conservation ≥ 0.95` from pilot data
- [ ] FP rate must be < 3% on confirmed-legit transactions before switching to REVIEW
- [ ] `model_audit` INSERT wired before gate returns
- [ ] Evidence package (fund trail + STR draft) built for this gate — required before REVIEW escalation (A-09 constraint)
- [ ] Gate inserted at position 0 — before all existing Tier 2 gates (A-08 constraint: justify placement)
- [ ] Conservation threshold: consider loosening from 0.95 → 0.90 after pilot if real mule operations show fees of 5-10%

### NOTE: This gate is NOT ready for immediate production ship
Gate 0 was built to close a sandbox testing gap (genome-level signals without account fixtures). The real Blue Team has account fixtures (DB records). Run the 2-week pilot first, verify with investigators, then ship.

---

## DIVERGENCE-03: Bipartite Density — Sandbox Uses Hardcoded Approximation
**Direction**: PRODUCTION AHEAD (production is more accurate)  
**Status**: ⚠️ Sandbox uses approximation | ✅ Production uses real graph density  
**Risk**: Sandbox may over-detect or under-detect compared to production; bypass scores are not exactly calibrated

### What production has
Real Blue Team computes actual graph density from Neo4j:
```cypher
-- bipartite_queries.py (inferred from design spec)
-- density = count(edges) / (sender_count × receiver_count)
-- For mule fan-in: all senders go to 1 collector → density ≈ 1.0
-- For merchant bipartite: customers spread across merchants → density ≈ 0.40-0.65
```

### What sandbox has
```python
# blue_clone.py → _simulate_bipartite_data()
# Hardcoded approximation — no actual edge counting:
density = 0.60 if is_merchant else 1.0
```

### Impact on sandbox reliability
- Non-merchant collectors always get density=1.0 → always fire Gate 3 if sender_count ≥ 5
- Merchant collectors always get density=0.60 → always exempt from Gate 3
- Real scenario where this diverges: a non-merchant account with 5 senders but moderate diversity (density ≈ 0.65-0.75 in Neo4j) — sandbox says 1.0 (fire), production says 0.65 (borderline or exempt)
- Bypass DNA scores from sandbox may be slightly more conservative than production reality

### Production change required
None — production is already correct. This divergence only affects sandbox bypass calibration accuracy.

### Recommended sandbox fix (low priority)
Add a `density_override` field to account fixtures. If not provided, use current approximation. Allows test scenarios to specify exact density for calibration testing.

---

## DIVERGENCE-04: Indian Context — Festival Gifting History Default
**Direction**: BOTH WRONG (different wrong assumptions)  
**Status**: ⚠️ Known Issue #3 from CLAUDE.md | Documented, not yet fixed  
**Risk**: Sandbox may suppress festival fraud score differently than production

### What production has
Real Blue Team reads `has_festival_gifting_history` from account DB. If account record has it True → legitimate Diwali sender. If False → no reduction.

### What sandbox does
```python
# blue_clone.py → _apply_context()
# Reads from source account fixture:
has_festival_gifting = src_data.get("has_festival_gifting_history", False)
# Default=False is correct. But when festival_timing operator is applied to a genome,
# the Red Team does NOT set has_festival_gifting_history=True in fixtures.
# So festival fraud genomes get has_festival_gifting=False → context adjuster
# does NOT apply the 0.70 reduction → score stays high → correctly detected.
# This is accidentally correct behavior for current test DNAs.
```

### Why this matters
DNA 003 (festival fan-out) correctly scores < 0.25 BECAUSE payee_vpa_age is 200+ days (old VPA). The `has_festival_gifting_history=False` default is not the primary protection — the `payee_vpa_age < 30` gate is. If someone builds a DNA with payee_vpa_age < 30 AND manually sets `has_festival_gifting_history=True` in fixtures, the sandbox context adjuster fires a 0.70 reduction — same as production would.

### Production change required
None. Monitor if bypass DNAs start setting `has_festival_gifting_history=True` explicitly in fixtures — that's when this divergence becomes exploitable.

---

## DIVERGENCE-05: Bipartite Density Bug (Legacy — Possibly Fixed)
**Direction**: SANDBOX WRONG (if bug exists)  
**Status**: ⚠️ CLAUDE.md lists as Known Issue #2, but current code shows different formula  
**Risk**: If the formula `density = min(1.0, senders / max(1, senders))` exists anywhere, it always evaluates to 1.0

### CLAUDE.md Known Issue #2 (original)
> `_tier2_gates()` bipartite density bug: `density = min(1.0, senders / max(1, senders))` always = 1.0

### Current code (may already be fixed)
```python
# blue_clone.py → _simulate_bipartite_data()
density = 0.60 if is_merchant else 1.0  # hardcoded approximation, not the broken formula
```

### Verified 2026-05-20
```bash
grep -n "senders / max" "red_team/sandbox/blue_clone.py"
# No output — formula does not exist in current code.
# Known Issue #2 is RESOLVED. blue_clone.py now uses hardcoded density approximation (D-03).
# CLAUDE.md Known Issue #2 should be removed.
```

---

## DIVERGENCE-06: V2 Target Wiring — `get_blue_team()` engine selection
**Direction**: BOTH WRONG (different blind spots — they are different engines)
**Status**: ✅ Sandbox wired | n/a production (this is an attack-target switch, not a gate)
**Risk if not understood**: bypass DNAs verified against MockBlueTeam do NOT imply a
bypass of the real V2 engine, and vice-versa. Always state which target a result used.

### What changed in blue_clone.py
`get_blue_team()` gained a third branch. Resolution order is now:

1. `CRUCIBLE_BLUE_TEAM=v2` (aliases `blue_team_v2`, `real_v2`) → **`V2BlueTeam`**
   (`sandbox/v2_target.py`) — the **real TGIE Blue Team V2 engine**, reached through
   its stable `blue_team_v2.red_team_interface.RedTeamTarget`. Coupling is one-way
   (Red imports Blue; Blue never imports Red).
2. `BLUE_TEAM_URL` set → legacy HTTP `RealBlueTeam` (union-bank API). Unchanged.
3. default → frozen sandbox `MockBlueTeam`. Unchanged — bypass DNAs/tests still
   score against the clone, so existing verification is untouched.

The `MockBlueTeam` scoring logic was **not** modified; only the factory selector.

### How V2 differs from the MockBlueTeam clone (the actual divergence)
| Aspect | MockBlueTeam (sandbox clone) | V2BlueTeam (real engine) |
|--------|------------------------------|--------------------------|
| Source | Frozen clone of OLD union-bank BT (5 gates + Tier-3 + Indian adjuster) | Live `blue_team_v2` engine TGIE deploys |
| Input | `genome.to_transaction_list()` **+ account_fixtures** (KYC age, occupation, VPA age, festival history) | `genome.to_transaction_list()` **only** — structure + amounts |
| Account context | Drives festival adjuster, JAN_DHAN, gig-velocity, payee-VPA bypasses | **Ignored** — fixtures accepted for parity but unused |
| Implication | Context-dependent bypass DNAs (esp. DNA-003 festival) are tuned to the clone | Those KYC/context bypasses have **no effect**; V2 must be evaded on graph structure |

### Production change required
None — V2 *is* the production engine. The migration work this unlocks is the
inverse of the rest of this log: instead of porting sandbox detections into the old
BT, re-run the evolution loop with `CRUCIBLE_BLUE_TEAM=v2` to discover bypasses
against the engine that actually ships, then triage those into V2 hardening.

### Gating criteria
```bash
# default path unchanged (clone)
python -c "from red_team.sandbox.blue_clone import get_blue_team; print(type(get_blue_team()).__name__)"   # MockBlueTeam
# v2 path active
CRUCIBLE_BLUE_TEAM=v2 python -c "from red_team.sandbox.blue_clone import get_blue_team; print(type(get_blue_team()).__name__)"  # V2BlueTeam
pytest red_team/tests/test_v2_target.py -q   # 6 passed (or skipped if backend absent)
```

---

## Quick Reference — Production Migration Priority

| # | Divergence | Direction | Production Risk | Effort | Priority |
|---|------------|-----------|-----------------|--------|----------|
| D-01 | Gate 2 two-path abandoned sink | SANDBOX AHEAD | HIGH — old mule accounts bypass Gate 2 | Medium (Cypher UNION + index) | **P1** |
| D-02 | Gate 0 rapid relay (new gate) | SANDBOX AHEAD | MEDIUM — backstop only; Gate 2 covers most cases with fixtures | High (new gate + pilot) | **P2** |
| D-03 | Bipartite density approximation | PRODUCTION AHEAD | LOW — affects calibration only, not detection | Low (add density_override to fixtures) | P3 |
| D-04 | Festival gifting history default | BOTH WRONG | LOW — accidentally correct for current DNAs | None now | P4 |
| D-05 | Legacy density bug (possibly fixed) | SANDBOX WRONG | NONE if already fixed | Verify + CLAUDE.md update | P3 |
| D-06 | V2 target wiring (`get_blue_team` selector) | BOTH WRONG | INFO — different engine, different blind spots; V2 ignores KYC fixtures | Low (done; opt-in via `CRUCIBLE_BLUE_TEAM=v2`) | P2 |

---

## Changelog

| Date | Divergence | Change | Author |
|------|------------|--------|--------|
| 2026-05-20 | D-01 | Sandbox Gate 2 restructured to two-path; production Cypher documented | Claude |
| 2026-05-20 | D-02 | Sandbox Gate 0 built (conservation + timing bugs fixed); production Cypher documented | Claude |
| 2026-05-20 | D-03 | Documented density approximation divergence (no code change) | Claude |
| 2026-05-20 | D-04 | Documented festival gifting history divergence (no code change) | Claude |
| 2026-05-20 | D-05 | Verified legacy density bug RESOLVED — formula not present in current code | Claude |
| 2026-06-28 | D-06 | Wired `get_blue_team()` to real Blue Team V2 via `sandbox/v2_target.py` (opt-in `CRUCIBLE_BLUE_TEAM=v2`); default sandbox path unchanged; 6 tests added | Claude |

---

*Update this file every time blue_clone.py diverges from production.*
*One entry per divergence. Mark SHIPPED once production is updated with deploy date.*
