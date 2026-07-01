# Blue Team Change Validation Checklist
# READ THIS BEFORE PROPOSING ANY CHANGE TO BLUE TEAM LOGIC
# Source of truth: BLING_BlueTeam_ClaudeCode_Prompt_UPDATED.md (Council of 5 Senior Engineers)

---

## MANDATORY SIGN-OFF
Every change proposal — no exceptions — must end with:
> **"This change will not make our system any dumber and will not cause any risk — no false alarms, no harm to any tier, no real criminal gets away."**

This line is ONLY written when:
- All 5 Part 1 pre-flight questions have written answers
- All 10 NEVER rules below are verified NOT violated
- If ANY doubt remains — do NOT add the line, do NOT propose the change

---

## PART 0 — HARD-SET NEVER RULES
### Absolute prohibitions. No argument overrides these.

**NEVER-1**: Lower `_BIPARTITE_MIN_SENDERS` below 5 without simultaneously adding a per-sender amount floor (≥₹10k per sender) as a compensating control. Reason: family transfers (3 relatives paying for a wedding) would flag.

**NEVER-2**: Remove a threshold ceiling (e.g., `age < 180`) without adding a strictly stronger multi-dimensional compensating requirement in the same code path. Removing one constraint without adding two narrowing constraints is always a net weakening.

**NEVER-3**: Change individual Tier 3 XGBoost feature weights without full model retraining and PR-AUC evaluation on labeled fraud data. The `min(1.0, score)` clamp hides score drift — individual weight bumps break calibration relative to all other 86 features.

**NEVER-4**: Add a new occupation to `_LEGIT_AGGREGATOR_OCCS`, `_LEGIT_SINK_OCCS`, `_LEGIT_CASH_HEAVY_OCCS`, or any other exemption list without documented proof that the occupation cannot be fraudulently claimed. Example: `salary_processor` is whitelisted — a fake salary processor could exploit this. It works because the bipartite gate's structural requirement (≥5 senders + density >0.7) is hard to fake at volume, but the exemption alone is not safe.

**NEVER-5**: Convert a hard gate's output into a score addend (score += x). Gates are categorical vetoes: gate fired = score 1.0, Tier 3 never runs. This is the core architectural principle from Section 3 of the design spec. Violating it makes a confirmed money laundering cycle score 0.40 instead of 1.0 — below every REVIEW threshold.

**NEVER-6**: Add a legitimacy filter that suppresses a gate without it being one of the 5 specifically designed filter types: (1) internal/treasury account, (2) KYC-verified relationship, (3) salary advance return, (4) all-merchant settlement cycle, (5) amount reduction <70%. Any other "explanation" is a criminal cover story.

**NEVER-7**: Change Indian context multipliers without real false positive data from `feedback_log`. Every multiplier has a demographic basis debated by 5 engineers. Do not modify from intuition — obtain investigator-confirmed false positive data first.

**NEVER-8**: Propose a change that addresses only MockBlueTeam (blue_clone.py) without documenting the equivalent real Blue Team change. Real Blue Team uses Cypher (Neo4j), SQL (PostgreSQL), and trained XGBoost. A sandbox fix that doesn't translate to production is security theatre.

**NEVER-9**: Mark a bypass as "fixed" without running bypass verifier (`python -m red_team.test_dna.bypass_verifier`) and confirming the DNA pattern now scores ≥0.62. Proof of fix requires code execution, not reasoning.

**NEVER-10**: Propose a change that causes ANY of the 8 named integration test scenarios to fail, even if it improves detection in another area. Detection is a system — a change that fixes one hole while breaking another test is a net loss.

---

## PART 1 — PRE-CHANGE MANDATORY QUESTIONS
### Answer all 5 in writing before writing a single line of changed code.

**Q1. Which specific detection gap does this fix?**
Name the fraud pattern. State the evidence that it currently bypasses the system (gate condition + why it fails + which DNA / genome / test case demonstrates it). "It seems like it might miss..." is not acceptable — prove it with code or test output.

**Q2. Which legitimate behaviors does this change touch?**
List them by name from Part 2. A change that touches zero legitimate behaviors is safe. A change that touches 3+ legitimate behaviors requires compensating controls for each.

**Q3. Does it change a threshold? If yes: what is the FP rate impact?**
For every threshold changed: show the before/after effect on at least 3 legitimate scenarios from Part 2. If FP rate increases, what compensating condition narrows it back?

**Q4. Does it open any bypass from Part 3 or Part 6?**
Run through every operator in Part 6 that is relevant to the changed gate. For each: does the operator still get caught after the change?

**Q5. Do all 8 named integration test scenarios still pass?**
List expected outcome for each. If any outcome changes, explain why the change is still net-positive.

---

## PART 2 — LEGITIMATE BEHAVIOR CATALOG
### These patterns MUST NOT be flagged. Each entry: behavior | account profile | signal fingerprint | gates touched | why protected.

---

### L-01: NRI Dormant Reactivation
**Behavior**: Account holder lived abroad, account dormant 60-120 days, returns and receives ₹50k-₹3L from 1-2 family members.
**Profile**: account_age=365+, account_type=SAVINGS, kyc_occupation=salaried, avg_amount_30d≈0 (dormant), velocity_ratio≈0
**Signal fingerprint**: old account + dormancy 60-120d + large single inflow + 1-2 senders + no forwarding
**Gates touched**: Gate 2 (abandoned_sink) — dormancy + inflow both fire thresholds
**Why protected**: Single sender. No multi-source fan-in. No forwarding. Retention=100% but dormancy from travel, not fraud. The `age < 180` ceiling in the original abandoned_sink gate protects this because account_age=365 ≥ 180. Any change removing this ceiling MUST add sender_count ≥ 3 requirement before Gate 2 fires.

---

### L-02: Diwali Gift Burst (Legitimate)
**Behavior**: Person sends ₹2k-5k to 5-10 new payees in Oct 1-Nov 15 window.
**Profile**: source account_age=200+, has_festival_gifting_history=True, kyc_occupation=salaried
**Signal fingerprint**: fan-out + festival season + amounts <5k + new payees + payee_vpa_age <30
**Gates touched**: Tier 1 (new_vpa, velocity_spike potentially), Indian context adjuster
**Why protected**: `apply_indian_context` multiplies score by 0.70 IF: is_festival_period + amount <5k + has_festival_gifting_history + payee_vpa_age <30. ALL four must hold. This is a tightly scoped exemption. Do not widen it.

---

### L-03: Jan Dhan Cash-In/Cash-Out
**Behavior**: Jan Dhan account receives cash deposit, withdraws via ATM same week. High ATM ratio.
**Profile**: account_type=JAN_DHAN, kyc_occupation=daily_wage or agricultural_worker, low digital send count
**Signal fingerprint**: high ATM ratio (>80%), inflow + ATM withdrawal, low account age sometimes
**Gates touched**: Gate 4 (cash_mule_sink) — high ATM ratio, inflow >50k sometimes
**Why protected**: `_LEGIT_CASH_HEAVY_TYPES = {"JAN_DHAN"}` and `_LEGIT_CASH_HEAVY_OCCS = {"vegetable_vendor", "daily_wage", "agricultural_worker", "street_vendor"}` are explicit exemptions in Gate 4. Do not remove these. Jan Dhan was designed for cash-in/cash-out by low-income citizens — ATM heavy behavior is the expected pattern, not fraud.

---

### L-04: Gig Worker High Velocity
**Behavior**: Delivery worker/freelancer makes 15-30 UPI transactions per day, same device, 11am-11pm.
**Profile**: kyc_occupation=gig_worker/freelancer/delivery, daily_txn_count>10, channel=UPI, daytime hours
**Signal fingerprint**: velocity_1h >5, UPI, gig occupation, daytime
**Gates touched**: Tier 1 (velocity_spike flag), Indian context adjuster (0.85 multiplier)
**Why protected**: `_HIGH_FREQ_OCCUPATIONS = {"gig_worker", "freelancer", "delivery", "merchant", "retailer"}` exempt from velocity_spike flag in Tier 1. Indian context adjuster applies additional 0.85 multiplier. Do NOT remove gig_worker from this set — their velocity is structural to how they earn.

---

### L-05: Seasonal Merchant Reactivation
**Behavior**: Diwali crackers/sweets seller dormant Jan-Sep, receives payments from 10-30 diverse customers in Oct.
**Profile**: kyc_occupation=merchant or retailer, is_merchant=True, account_age=300+, dormancy=250+ days, diverse buyers
**Signal fingerprint**: dormant old account + multi-source inflow + merchant occupation + Oct timing
**Gates touched**: Gate 2 (abandoned_sink) — dormancy + inflow fire; Gate 3 (bipartite) — many senders fire if >5
**Why protected**: Gate 2: merchant/retailer/shopkeeper in `_LEGIT_SINK_OCCS` — exempted. Gate 3: merchant receiver with diverse customers has density < 0.85 (each customer buys from many merchants) — merchant density exemption. Both protections must remain intact.

---

### L-06: Wedding Gift Aggregation
**Behavior**: Person receives ₹80k-₹3L from 3-5 relatives over 2-4 weeks before wedding.
**Profile**: account_age=300+, source accounts are relatives (old accounts, low velocity), no forwarding
**Signal fingerprint**: 3-5 senders + old account + inflow >50k + dormancy possibly >30d + retention=100%
**Gates touched**: Gate 2 (abandoned_sink) — inflow + dormancy + retention; Gate 3 (bipartite) — 3-5 senders
**Why protected**: Gate 3: 3-5 senders < 5 = bipartite gate never fires. Gate 2: if account_age ≥180, old-account path requires sender_count ≥3 AND dormancy ≥60d AND rapid forward — wedding aggregation has no rapid forward (retention=100%), so retention check fails → gate does not fire. The multi-source + rapid-forward requirement is the critical protection for this scenario.

---

### L-07: Salary Processor Fan-In
**Behavior**: Payroll company receives salary contributions from 50+ employer accounts, distributes to employees.
**Profile**: receiver kyc_occupation=salary_processor or payroll_processor, high sender count, large inflows
**Signal fingerprint**: >5 senders, density close to 1.0, large amounts, legitimate aggregator occupation
**Gates touched**: Gate 3 (bipartite) — fires on sender_count + density, then exemption runs
**Why protected**: `_LEGIT_AGGREGATOR_OCCS = {"salary_processor", "payroll_processor", "insurance_company", "tax_collector", "utility_provider"}` — bipartite gate fires then exemption short-circuits. Do NOT remove any of these occupations. Do NOT add new ones without NEVER-4 proof.

---

### L-08: Legitimate Salary Advance Cycle
**Behavior**: Employer sends advance to employee; employee returns it within 30 days.
**Profile**: origin kyc_occupation=employer/corporate/payroll_processor, cycle closes ≤30d, exit_amount ≤ entry_amount
**Signal fingerprint**: confirmed graph cycle + origin is corporate + duration ≤30d + return ≤ sent
**Gates touched**: Gate 1 (cycle) — fires, then Filter 3 (salary advance) explains it
**Why protected**: Legitimacy Filter 3 in cycle gate: `origin_occ in _PAYROLL_OCCUPATIONS AND duration ≤30d AND exit_amount ≤ entry_amount`. All three must hold. If any is missing (cycle >30 days, origin not employer, amount returned exceeds sent) → fraud. Do not widen these conditions.

---

### L-09: Internal/Treasury Account Cycles
**Behavior**: Branch GL reconciliation, NOSTRO/VOSTRO settlement, treasury operations create fund cycles.
**Profile**: account_type in {INTERNAL, TREASURY, NOSTRO, VOSTRO}
**Signal fingerprint**: confirmed graph cycle + one or both cycle endpoints are internal accounts
**Gates touched**: Gate 1 (cycle) — fires, then Filter 1 (internal account) explains it
**Why protected**: Banks require internal accounts to cycle funds for reconciliation. This is not fraud — it is the banking system's plumbing. Filter 1 must always remain first in the legitimacy filter chain.

---

### L-10: B2B Merchant Settlement Cycle
**Behavior**: Customer pays merchant → merchant pays supplier → supplier returns goods-return credit to customer. All nodes are registered merchants.
**Profile**: All cycle nodes: is_merchant=True, MCC codes present
**Signal fingerprint**: confirmed graph cycle + ALL nodes are merchants
**Gates touched**: Gate 1 (cycle) — fires, then Filter 4 (all-merchant cycle) explains it
**Why protected**: B2B settlement chains create natural cycles. The protection requires ALL nodes to be merchants — one non-merchant node breaks the exemption. This is a tight constraint that cannot be gamed without registering all intermediaries as merchants.

---

### L-11: Fee/Partial Repayment Cycle
**Behavior**: Loan advance sent, partial repayment returned (with fees deducted). Exit amount < 70% of entry.
**Profile**: Any account pair, cycle detected, but return amount <70% of sent
**Signal fingerprint**: confirmed graph cycle + exit_amount / entry_amount < 0.70
**Gates touched**: Gate 1 (cycle) — fires, then Filter 5 (amount reduction) explains it
**Why protected**: Money launderers try to return close to 100% (minimize haircut). Legitimate cycles (fees, taxes, partial repayments) lose >30%. This is why the threshold is 70%, not 50%. Do not raise the threshold — money launderers will calibrate to just below whatever threshold is set.

---

### L-12: Vegetable Vendor / Daily Wage ATM Cash
**Behavior**: Informal economy worker receives daily payments, withdraws cash end of day for daily purchases.
**Profile**: kyc_occupation=vegetable_vendor/daily_wage/agricultural_worker/street_vendor, ATM heavy, sometimes Jan Dhan
**Signal fingerprint**: ATM ratio >80%, inflow from few sources (employer or 1-2 customers), account may be young
**Gates touched**: Gate 4 (cash_mule_sink) — high ATM ratio + inflow
**Why protected**: `_LEGIT_CASH_HEAVY_OCCS` exemption. These occupations are explicitly listed because informal economy cash usage is structurally identical to mule behavior in data — the only differentiator is KYC occupation. Do not remove any of these occupations.

---

### L-13: Corporate Payroll Batch Settlement
**Behavior**: Merchant/retailer does end-of-day batch settlement, round amounts, 6pm-11pm.
**Profile**: kyc_occupation=merchant/retailer/shopkeeper, round amounts (nearest ₹100), hour 18-23
**Signal fingerprint**: round amounts + evening timing + merchant occupation
**Gates touched**: Indian context adjuster (0.80 multiplier for merchant batch)
**Why protected**: Evening batch settlement is how small businesses close their day. Round amounts at evening = batch processing, not structuring. The adjuster requires occupation + round amount + timing — all three together.

---

### L-14: Student Night Education Payment
**Behavior**: Student pays tuition fees at night (after 11pm) — online portals, exam fees, hostel.
**Profile**: kyc_age <25, payee MCC in EDUCATION_MCC_CODES, night hour, moderate amounts
**Signal fingerprint**: night flag + young account + education merchant MCC
**Gates touched**: Tier 1 (night flag), Indian context adjuster (0.80 multiplier)
**Why protected**: Students pay fees at night because they work during the day or portals have less traffic. Night + large amount is suspicious for a senior citizen but normal for a student. The education MCC is the differentiator.

---

### L-15: Senior Citizen Legitimate Evening Transfer
**Behavior**: Elderly person (age 65+) transfers ₹10k-₹50k at 10:30pm to a family member they send to regularly.
**Profile**: kyc_age >60, hour=22, known payee (payee_in_known_contacts=True), moderate amount
**Signal fingerprint**: near-night hour + old account + known payee
**Gates touched**: Tier 1 (night is 23:00-05:00, NOT 22:00), FAST_CLEAN path if payee in contacts
**Why protected**: Night is defined as `hour >= 23 OR hour < 5`. A 10:30pm transfer is NOT night. Senior amplification (1.50x) only applies to actual night hours. An 10:30pm transfer to a known contact by a senior is FAST_CLEAN if amount < avg×2 and velocity <10. This boundary must be maintained precisely.

---

### L-16: Large Family Medical Transfer
**Behavior**: Family member sends ₹1L-₹5L to sibling/parent for medical emergency. Single sender. Old account.
**Profile**: Single sender, receiver account_age=300+, large single transfer, no fan-in, no forwarding
**Signal fingerprint**: single large transfer + old account + no multi-source + no forwarding
**Gates touched**: Gate 2 (abandoned_sink) — inflow >50k + dormancy possibly; Tier 1 (amount_spike if avg_amount_30d is low)
**Why protected**: Gate 2 requires either (old-account path) sender_count ≥3 OR (new-account path) age <180. Single sender to old account fails both paths. Tier 1 amount_spike fires only if amount > avg_30d × 5 — if sender has history of moderate transfers, this may fire but Tier 3 score will be low without graph topology risk.

---

### L-17: Small Business Diverse Customer Base
**Behavior**: Kirana store receives payments from 30+ different customers (each sends only to this one store).
**Profile**: receiver is_merchant=True, MCC code present, sender diversity high (each sender → few merchants)
**Signal fingerprint**: many senders + merchant receiver + low density per sender
**Gates touched**: Gate 3 (bipartite) — many senders fire, but density check differentiates
**Why protected**: Legitimate merchants have diverse customers (each customer buys from MANY merchants → density per merchant is low, ~0.60). Mule networks have dedicated senders (each sender sends to ONLY this one collector → density = 1.0). The density threshold (>0.70) is the critical differentiator. `is_merchant AND density < 0.85 → exempt`. Do not remove merchant density exemption.

---

### L-18: KYC-Verified Relationship Cycle
**Behavior**: Declared joint account holders, spouses, parent-child pairs transfer funds in cycles.
**Profile**: cycle origin and terminus have `kyc_relationships` table entry together
**Signal fingerprint**: confirmed graph cycle + KYC relationship record exists for origin-terminus pair
**Gates touched**: Gate 1 (cycle) — fires, then Filter 2 (known relationship) explains it
**Why protected**: Banks maintain declared relationship tables. If two people declare joint accounts or verified relationship, their fund cycles are by definition not laundering. Filter 2 checks this table — the relationship must be pre-declared in the database, not inferred.

---

### L-19: Festival Merchant Volume Spike (Legitimate 50x)
**Behavior**: Diwali cracker vendor does 50x daily UPI volume on Oct 14-15 (Dhanteras).
**Profile**: kyc_occupation=merchant, terminal_id present, MCC matches festival goods, Oct timing
**Signal fingerprint**: merchant_terminal_velocity 50x+ in 24h
**Gates touched**: Gate 5 (merchant_terminal) — velocity spike pattern fires
**Why protected**: Gate 5 Pattern C (`velocity_ratio > 50`) fires on 50x spike. BUT: Gate 5 requires `terminal_id` in the transaction. FraudGenome has no terminal — so in sandbox, Gate 5 never fires. In production: if a legitimate merchant has a festival spike, the MCC code and registration history are available — the spike alone without amount uniformity (Pattern A) or MCC mismatch (Pattern B) should not trigger REVIEW. The three patterns are independent; festival volume spike alone is insufficient. This is correct by design.

---

### L-20: Ghost Node Legitimate (Same City, Same Person)
**Behavior**: Person withdraws ₹50k from ATM in their home city, deposits ₹49k at a branch in the same city 2 hours later.
**Profile**: same account holder, same city ATM withdrawal + deposit, <2h, single account
**Signal fingerprint**: ATM withdrawal + cash deposit gap + same city
**Gates touched**: Ghost node gate (if implemented) — cash gap signal
**Why protected**: People withdraw and deposit in the same city for many legitimate reasons (rent, personal loans, marketplace transactions). The ghost node gate requires: withdrawal city A → deposit city B (200-700km apart) + shared device near both + 3 common contacts between accounts. Same-city cash recycling without device correlation and city distance fails the ghost node requirements.

---

## PART 3 — FRAUD PATTERN CATALOG
### Every pattern that MUST be caught. Gate that catches it + minimum evidence required.

---

### F-01: Circular Round-Trip Money Laundering
**Pattern**: Funds leave account A, traverse 2-8 intermediaries, return to account A within 7 days.
**Topology**: Any confirmed graph cycle (Neo4j MATCH path A→...→A)
**Gate**: Gate 1 (cycle_gate) → score=1.0
**Minimum evidence**: Graph cycle path detected + none of 5 legitimacy filters explain it
**Thresholds**: 2-8 hops, 7-day window
**Detection path**: Cypher `MATCH path=(start)-[:SENT*2..8]->(start) WHERE all(r... timestamp > 7d ago)`
**Bypass attempts to watch**: `cycle_extender` operator uses topology.type="chain" not "cycle" → Neo4j cycle detection misses it because no actual graph cycle exists. This is a known gap — the gate detects graph cycles, not logical cycles.

---

### F-02: New Mule Abandoned Sink (Classic)
**Pattern**: New account (<180 days) receives burst inflow from multiple sources, retains >80%, goes dormant >30 days.
**Topology**: Fan-in → collector → no forwarding (depth ≤2) or slow forwarding
**Gate**: Gate 2 (abandoned_sink) → score=1.0
**Minimum evidence**: account_age <180 + inflow_30d >50k + retention >80% + dormancy >30d
**Thresholds**: ALL four conditions must hold simultaneously
**Detection path**: Cypher attribute lookup on pre-computed nightly features
**Critical**: This is the original gate design. account_age <180 is intentional. Mule accounts are typically new — criminals recruit new mules, give them SIM cards and pre-opened accounts. Do not remove the age ceiling without NEVER-2 compensation.

---

### F-03: Old Dormant-Reactivated Account (Abandoned Node)
**Pattern**: Long-dormant old account (365+ days, inactive 60+ days) suddenly receives coordinated multi-source inflow and rapidly forwards >90%.
**Topology**: 3+ senders → old dormant account → rapid forward to cash-out within hours
**Gate**: Gate 2 (abandoned_sink extended path) → score=1.0
**Minimum evidence**: account_age ≥180 + sender_count ≥3 + inflow >50k + dormancy ≥60d + rapid forward (depth >2 or retention <40%)
**Thresholds**: OLD path requires ALL: sender_count ≥3, dormancy ≥60d (not 30d), retention threshold relaxed to 0.40 (because rapid forward = low retention)
**Detection path**: Same gate as F-02 but different code path for old accounts
**Critical distinction from L-01 (NRI)**: NRI has single sender + no rapid forward + retention=100%. F-03 has multiple senders + rapid forward. This distinction (sender_count + forwarding behavior) is the ONLY reliable separator.

---

### F-04: Bipartite Mule Network
**Pattern**: 5+ unrelated senders each send to a single collector account, density >0.7 (most senders send exclusively to this collector).
**Topology**: Bipartite core — many senders → few receivers, each sender mostly exclusive to this receiver
**Gate**: Gate 3 (bipartite_core) → score=1.0
**Minimum evidence**: sender_count ≥5 + density >0.70 + NOT in _LEGIT_AGGREGATOR_OCCS + NOT merchant with density <0.85
**Thresholds**: 5 senders and 0.70 density are BOTH required
**Known bypass**: `fan_out_collector` operator splits 1 large fan-in into 3 sub-groups of 2-3 senders each. Each sub-group falls below ≥5 threshold. Currently undetected at gate level — Tier 3 soft score and Tier 1 velocity flags are the backstop.

---

### F-05: Cash Mule Receive-Withdraw-Dormant
**Pattern**: Young account receives large inflow, withdraws ≥80% as ATM cash within 48 hours, then goes digitally silent.
**Topology**: Inflow (digital) → ATM withdrawal burst → digital silence
**Gate**: Gate 4 (cash_mule_sink) → score=1.0
**Minimum evidence**: account_age ≤180 + inflow_7d ≥50k + cash_withdrawn_48h / inflow ≥0.80 + digital_sends_after ≤2
**Thresholds**: ALL four conditions required
**Critical**: Gate 4 ONLY fires when `channel='ATM'` in database. Digital-only rails (UPI/NEFT/RTGS/IMPS) are never caught by Gate 4. This is NOT a bug — digital forwarding is caught by Gate 2 (abandoned_sink). Gate 4 is specifically for the physical cash extraction pattern.

---

### F-06: Fake Merchant Terminal / POS Cash-Out
**Pattern**: Merchant terminal (registered as grocery, restaurant, pharmacy) receives suspicious UPI flows: uniform amounts OR MCC-mismatched high amounts OR 50x velocity spike.
**Topology**: Customers → MerchantTerminal node → IMPS/NEFT cash-out
**Gate**: Gate 5 (merchant_terminal) → score=1.0
**Minimum evidence**: terminal_id present + ONE of: (A) uniformity <5% with ≥5 receipts, OR (B) 3+ oversized amounts >MCC_max×3, OR (C) velocity_ratio >50 vs normal daily
**Critical**: Gate 5 requires `terminal_id` in transaction. FraudGenome has no terminal concept → sandbox Gate 5 always bypassed. In production, all UPI transactions to registered terminals carry terminal_id.

---

### F-07: Nizamabad Hub-and-Spoke (Large Scale Mule Hub)
**Pattern**: 20-46 mule accounts (across 4-14 states) each send ₹10k-28k to a single hub account. Total moved: ₹1Cr+. Per-account amounts carefully kept below individual detection thresholds.
**Topology**: fan_in NOT bipartite — collector is not flagged by Gate 3 because topology.type is fan_in, not bipartite
**Current gate coverage**: NONE at Tier 2. Tier 3 betweenness_centrality + pagerank_fraud_seeded are the primary signals. This is a KNOWN GAP.
**Minimum evidence for Tier 3**: high betweenness_centrality + many distinct counterparties_30d + geographic_spread + sub-threshold amounts + Benford deviation
**Why it escapes Gate 3**: Gate 3 catches bipartite cores. fan_in with 1 collector is not a bipartite graph in the Neo4j sense — it's a star graph. Bipartite means two distinct groups with edges only between groups. Star graphs have sender_count that may reach threshold, but the gate's Cypher query matches the Nizamabad pattern if sender_count ≥5 AND density >0.7. At 46 senders to 1 collector, density = 1.0 → Gate 3 SHOULD catch this. Verify.

---

### F-08: Structuring / Threshold Fragmentation
**Pattern**: Single large amount (₹5L) fragmented into multiple transactions (₹49k × 10) to stay below CTR reporting thresholds. Each transaction individually looks clean.
**Topology**: fan_in (multiple mule accounts) → single collector, all amounts in ₹90k-₹99k or ₹49k-₹50k band
**Gate coverage**: No Tier 2 gate catches this. Tier 3 detects via: benford_first_digit_score, sub_threshold_ratio, split_transaction_score, structuring_90k_99k_count
**Minimum evidence**: 5+ transactions + amounts clustered near threshold bands + Benford deviation + split_transaction_score >0.5
**Threshold bands**: (₹49k-₹50k), (₹99k-₹1L), (₹990k-₹1M) — proximity within 2% of these triggers threshold_proximity in Tier 1

---

### F-09: Low-Slow Mule (Behavioral Baseline Fraud)
**Pattern**: Account behaves normally for 45 days (5 transactions/month, avg ₹3k), then single large transfer (₹1.8L) to new payee at 2am.
**Topology**: Point-to-point transfer — no complex topology
**Gate coverage**: No Tier 2 gate fires (no cycle, no fan-in, no bipartite, no ATM). Tier 3 detects via: dormancy_break, amount_zscore, burst_score, hour_deviation, counterparty_novelty
**Minimum evidence**: amount_zscore >5 + dormancy_break=True + new payee + night hour
**Key insight**: This pattern ONLY reaches Tier 3 if Tier 1 classifies it as SUSPICIOUS (not FAST_CLEAN). The night flag + amount_spike from Tier 1 ensures it reaches Tier 3. If the transfer is at 11am on a weekday in a normal amount — it may reach Tier 3 as UNCERTAIN and score low. This is correct: slow mules are caught by nightly behavioral baseline, not real-time gates.

---

### F-10: Layered Mixing / Trade-Based Money Laundering
**Pattern**: 7+ transaction hops with different "cover stories" (rent, invoice, family gift, loan repayment) at each layer. Each hop looks individually legitimate.
**Topology**: Layered chain, depth 7+, each hop with mimics_legitimate flag set
**Gate coverage**: No single gate catches this. Fund trail reconstruction + SHAP explainer are required. betweenness_centrality of intermediate nodes is high. pagerank_fraud_seeded propagates from confirmed fraud nodes.
**Minimum evidence**: depth >6 + betweenness_centrality outlier + pagerank >0.7 + fund trail reconstruction connects all layers
**Key insight**: The `recognized_pattern_verification` Red Team operator is specifically designed to exploit the legitimacy whitelist. Any change to legitimacy exemptions must be checked against this operator.

---

### F-11: Ghost Node Cash Gap
**Pattern**: Digital funds leave account A, cash withdrawn from ATM in City A (e.g., Mumbai), cash hand-carried 200-700km to City B (e.g., Raipur), deposited at branch, digital funds continue from City B account. Creates a disconnected edge in the graph.
**Topology**: Account A → [ATM withdrawal Mumbai] → [physical cash] → [ATM deposit Raipur] → Account B
**Gate coverage**: Ghost node gate (separate detection) — requires: city distance >200km + same device near both ATMs + 3+ common contacts between A and B + 4hr window
**Why it's the "holy shit" moment**: This pattern is invisible to all other gates because the cash leg has no digital trace. The reconnection is done by matching device fingerprints near both ATMs — data that real banks have but traditional AML systems don't model.

---

### F-12: Digital Arrest Fraud
**Pattern**: Criminal impersonates police/RBI official, convinces elderly victim to transfer ₹5L-₹50L urgently to a new account at 2am.
**Profile**: target kyc_age >60, night hour (23:00-05:00), payee_vpa_age <7 days, high amount
**Gate coverage**: No Tier 2 gate fires. Tier 1 flags: new_vpa + night + amount_spike. Indian context amplifies: 1.50 (senior night) × 1.30 (senior new VPA) = 1.95× amplification. Final score >0.85 → HIGH_RISK.
**Minimum evidence**: kyc_age >60 + hour in [23,0,1,2,3,4] + payee_vpa_age <7 + amount >avg_30d × 5
**Critical**: The senior amplification multipliers (1.50 and 1.30) must NEVER be reduced. These exist specifically because elderly citizens are primary targets of digital arrest scams.

---

### F-13: Festival Season Fraud (Exploiting Context Adjuster)
**Pattern**: Fraudster structures transfers during Diwali season with amounts <₹5k to exploit the 0.70 score multiplier.
**Profile**: Transfers Oct-Nov, amounts carefully kept <₹5k, payee_vpa_age <30 (new VPAs created for the fraud)
**Gate coverage**: Indian context adjuster fires (reduces score by 30%), BUT only if has_festival_gifting_history=True. New accounts with no gifting history do not get the reduction.
**Key differentiator**: `has_festival_gifting_history` flag — legitimate senders have this from prior years. New fraud accounts do not. This is why the flag exists.
**Bypass attempt**: `festival_timing` Red Team operator exploits this — it sets amounts <₹5k and timing to festival months. But the operator cannot set has_festival_gifting_history=True on new accounts. Old accounts with gifting history would get the reduction — but old accounts with gifting history are legitimately lower risk.

---

### F-14: Channel Hopping Evasion
**Pattern**: Fraud chain uses different payment rails at each hop (UPI → IMPS → NEFT → RTGS → crypto), distributing anomaly signal across per-channel behavioral models so no single model flags it.
**Topology**: Chain with channel_sequence varied at each hop
**Gate coverage**: No Tier 2 gate fires (no cycle, no fan-in, no bipartite). Tier 3 channel_entropy feature is LOW (diverse channels = high entropy = lower suspicion, which is backwards — this is a Tier 3 modeling weakness). Fund trail reconstruction connects hops.
**Current gap**: channel_entropy in Tier 3 is currently computed as: single channel = low entropy = suspicious. Multi-channel = high entropy = less suspicious. But for channel HOPPING (deliberate mixing), high entropy should be MORE suspicious. This feature needs a behavioral baseline — channel entropy vs this account's prior channel entropy. Today's Tier 3 score actually REWARDS channel hopping.

---

### F-15: Dormant Activator (Seasoned Mule)
**Pattern**: Mule account transacts ₹500-₹5k/month for 6 months to build legitimate history, then executes ₹10L+ burst with mimics_legitimate="employer_to_employees" cover story.
**Profile**: account_age=210+, 6 months light transactions, then burst with employer cover story
**Gate coverage**: Tier 3: dormancy_reactivation_flag + burst_score + amount_zscore. Tier 1: amount_spike (₹10L vs ₹3k avg = >5× → amount_spike flag). Behavioral baseline is the primary defense.
**Bypass**: The `recognized_pattern_verification` operator mimics a legitimate pattern type — this is flagged as "REQUIRES_SENIOR_REVIEW" in realism.py but still passes validation. Human investigator is the last line of defense here.

---

## PART 4 — GATE-BY-GATE CHANGE RULES
### For each gate: threshold value | design intent | what breaks if changed | scenarios to recheck

---

### Tier 1 — Heuristic Rules

| Threshold | Value | Design Intent | What Breaks If Changed | Recheck |
|-----------|-------|--------------|----------------------|---------|
| `velocity_1h > 5` | 5 tx/hr | Catch rapid-fire fraud bursts | Lower: gig workers flag. Raise: fast structuring escapes | L-04 (gig worker), F-08 (structuring) |
| `amount > avg_30d × 5` | 5× multiplier | Catch sudden amount spikes | Lower: NRI returning (avg≈0 so any amount flags). Raise: large fraud transfers escape | L-01 (NRI), L-16 (medical transfer) |
| `payee_vpa_age < 7` | 7 days | New VPA = unknown payee | Lower: new legitimate VPAs from businesses flagged. Raise: digital arrest gets less signal | L-19 (festival merchant new VPA), F-12 (digital arrest) |
| `payee_account_age < 14` | 14 days | New account = mule account | Lower: new joint accounts flag. Raise: fast mule setup escapes | New account scenarios |
| Night definition | `hour ≥23 OR hour <5` | Fraud clusters in night hours | Widen: senior 10:30pm transfer flags. Narrow: late-night fraud escapes | L-15 (senior evening), F-12 (digital arrest) |
| FAST_CLEAN: `account_age > 365` | 365 days | Old accounts are lower risk | Lower: more accounts reach Tier 2 (compute cost). Raise: some fraud escapes on old account | All old account patterns |
| FAST_CLEAN: `amount < avg_30d × 2` | 2× | Normal amount range | Lower: fewer FAST_CLEAN, more compute. Raise: slow mule spikes escape | F-09 (low-slow mule) |

---

### Gate 2 — Abandoned Sink

| Element | Value | Design Intent | What Breaks If Changed | Recheck |
|---------|-------|--------------|----------------------|---------|
| `account_age < 180` | 180 days | New mule accounts only | REMOVING: NRI + seasonal + wedding scenarios flag. Compensating requirement: sender_count ≥3 AND dormancy ≥60d AND rapid_forward | L-01, L-05, L-06 |
| `inflow > 50k` | ₹50,000 | Meaningful fraud threshold | Raise: small mule accounts escape. Lower to <₹25k: normal family transfers flag | L-16 (medical transfer) |
| `retention > 80%` | 0.80 | Funds kept, not forwarded | Lower: any account holding funds flags. Never lower below 0.70. Old-account path: 0.40 minimum (requires rapid_forward as compensating signal) | L-06 (wedding: no forwarding = retention=1.0 but no multi-source) |
| `dormancy > 30d` | 30 days | Account was inactive | Lower to <14d: anyone on 2-week vacation flags. Raising to 60d is safe. Old-account path must use ≥60d | L-01 (NRI: 60-90d dormancy) |
| Exemptions: merchant/retailer/shopkeeper | occupations | Cash businesses retain legitimately | Removing: seasonal merchants flag at Gate 2 | L-05 (seasonal merchant) |

---

### Gate 3 — Bipartite Core

| Element | Value | Design Intent | What Breaks If Changed | Recheck |
|---------|-------|--------------|----------------------|---------|
| `sender_count ≥ 5` | 5 senders | Mule networks need volume | Lower to 4: family (3 people) triggers. Lower to 3: any group payment flags. NEVER below 5 per NEVER-1 | L-06 (wedding: 3-5 senders), L-07 (payroll) |
| `density > 0.70` | 0.70 | Exclusive sender relationship | Lower: diverse-customer merchants flag. Do not lower below 0.65 | L-17 (kirana store diverse customers) |
| `_LEGIT_AGGREGATOR_OCCS` | 5 occupations | Known legitimate aggregators | Adding carelessly: criminals claim the occupation. Removing: payroll processors flag | L-07 (salary processor), F-04 (fake salary processor) |
| Merchant density exemption: `density < 0.85` | 0.85 | Merchants have diverse customers | Raising: fewer merchants exempt (more FP). Lowering: fake merchants with moderate diversity escape | L-17 (small business) |

---

### Gate 4 — Cash Mule Sink

| Element | Value | Design Intent | What Breaks If Changed | Recheck |
|---------|-------|--------------|----------------------|---------|
| `channel = 'ATM'` only | ATM-only | Physical cash extraction | Adding digital rails: any digital forwarding flags (Gateway 2 handles digital). This is NOT a bug. | L-03 (Jan Dhan), F-05 (cash mule) |
| `account_age ≤ 180` | 180 days | New mule accounts | Same as Gate 2 age ceiling — same reasoning applies | L-01 (NRI old account) |
| `cash_ratio ≥ 0.80` | 80% | High cash extraction | Lowering: vegetable vendors who withdraw 60% for daily needs flag. Never lower below 0.70 without Tier 2 data | L-12 (vegetable vendor), L-03 (Jan Dhan) |
| `digital_sends_after ≤ 2` | 2 sends | Digital silence post-withdrawal | Raising: mules who do 3 test sends escape. Lowering: mules who get a UPI payment after withdrawal escape | F-05 (cash mule) |
| `_LEGIT_CASH_HEAVY_OCCS` | 4 occupations | Informal economy cash users | Removing any: informal workers flag. Adding carelessly: criminals claim occupation | L-12, L-03 |

---

### Gate 5 — Merchant Terminal

| Element | Value | Design Intent | What Breaks If Changed | Recheck |
|---------|-------|--------------|----------------------|---------|
| Pattern A: uniformity <5% | 0.05 | Fake merchant uniform amounts | Raising: some legit corporate batch payments that happen to be uniform flag | L-19 (festival merchant) |
| Pattern B: oversized ≥3 txns | 3 transactions | 3 MCC-mismatched = pattern | Lowering to 1: single unusual transaction flags. Raising: fake merchants with 2 oversized txns escape | MCC mismatch scenarios |
| Pattern C: velocity >50× | 50× normal | Extreme burst = not legit | Lowering: Diwali sale merchants flag. Raising: very high velocity escapes | L-19 (festival merchant 50x) |
| `terminal_id` requirement | mandatory | Terminals exist in production | Removing: FraudGenome (no terminal) would trigger Gate 5 incorrectly in sandbox | Sandbox testing |

---

### Tier 3 — XGBoost Features

| Feature | Weight | Design Intent | What Breaks If Changed | Recheck |
|---------|--------|--------------|----------------------|---------|
| All feature weights | As trained | Calibrated PR-AUC on labeled data | ANY individual weight change without retraining breaks calibration. See NEVER-3 | All 8 integration scenarios |
| Thresholds: PASS/LOG/REVIEW/HIGH_RISK | 0.38/0.62/0.83 | Global action cutoffs | Every 0.01 change shifts thousands of decisions. Calibrate from precision-recall data only | All scenarios |
| Senior amplification: 1.50 (night) | 1.50× | Elderly night fraud protection | Lowering: digital arrest scores drop. Must NEVER be lowered | F-12 (digital arrest) |
| Senior amplification: 1.30 (new VPA) | 1.30× | Elderly new payee risk | Lowering: digital arrest less detectable | F-12 (digital arrest) |
| Festival reduction: 0.70 | 0.70× | Diwali gifting legitimacy | Lowering (more reduction): festival fraud escapes. Raising: legitimate Diwali gifts flag | L-02, F-13 |

---

## PART 5 — ARCHITECTURAL CONSTRAINTS
### Non-negotiable. No change overrides these.

**A-01 HUMAN IN LOOP**: Blue Team detects and escalates. Investigator confirms. No auto-block ever. Changes that route transactions to PASS without human visibility violate the fundamental system design from Section 0 of the build spec.

**A-02 FORENSIC NOT BLOCKING**: System reads settled transactions. Money has moved. Do not add logic that assumes real-time blocking is possible.

**A-03 AUDIT TRAIL FIRST**: `model_audit` INSERT happens BEFORE returning the scoring response. If audit write fails, the whole request fails. This is legally required by RBI PMLA Section 12. Any change that defers or skips audit logging is non-compliant.

**A-04 PII NEVER LOGGED**: Account IDs, names, KYC data are PII. Always pseudonymized in logs via SHA-256 + salt. No change adds raw account_id to any log line.

**A-05 GATES ARE CATEGORICAL VETOES**: Gate fired = score 1.0. Tier 3 does not run. Never convert a gate output into score += penalty. A confirmed money laundering cycle is not "40% suspicious" — it IS money laundering until a legitimacy filter explains it. This principle is from Section 3 of the design spec and is the fundamental architectural insight.

**A-06 LEGITIMACY FILTERS MANDATORY AFTER EVERY GATE**: Every gate must run its legitimacy filters before escalating. A gate that fires without filters = unexplained alerts = investigator loses trust in the system. Every NEW gate proposal must include its own legitimacy filter set.

**A-07 ONLINE LEARNING FEEDBACK LOOP**: Investigator confirmations (POST /feedback) feed the XGBoost online learning. Changes that bypass the feedback endpoint, or that score transactions without saving to `fraud_scores` table, break the learning loop.

**A-08 GATE ORDER IS LOAD-BEARING**: cycle → abandoned_sink → bipartite → cash_mule → merchant_terminal. Gates later in the order never run for transactions caught earlier. Inserting a new gate earlier reduces compute cost but may cause a transaction to be caught by the wrong gate (different evidence package, different STR narrative). Justify gate placement with evidence.

**A-09 INVESTIGATION PACKAGE COMPLETENESS**: Every REVIEW/HIGH_RISK result must produce a complete evidence package: fund trail (10 hops forward + backward), SHAP explanation, STR draft (156 fields). A change that scores HIGH_RISK but cannot produce the evidence package is operationally useless.

**A-10 MOCK ≠ PRODUCTION**: blue_clone.py is a simulation. Every proposed change must document the equivalent change needed in production: which Cypher query changes, which SQL query changes, which XGBoost feature is affected. Changes to blue_clone.py without production documentation are sandbox-only fixes.

---

## PART 6 — RED TEAM BYPASS RESISTANCE CHECK
### For each Red Team operator: what it mutates → which gate currently catches it → does a proposed change affect this?

Run this table for EVERY gate change. Mark each operator: ✅ Still caught | ❌ New bypass created | ⚠️ Changed detection path

| Operator | Mutates | Currently caught by | Notes |
|----------|---------|-------------------|-------|
| add_hop | depth, bridge_nodes | Nothing (chain 4-8 hops not cycle) | Tier 3 depth feature. Betweenness centrality. Changes to cycle gate don't affect this. |
| fan_out_collector | width, collector_count | Gate 3 if width drops to <2 per sub-collector | If bipartite threshold lowered → sub-collectors might flag before split intended |
| insert_abandoned_node | special_nodes.abandoned_nodes, dormancy | Gate 2 (if fixtures show old account, dormancy >60, ≥3 senders, rapid_forward) | The ENTIRE Gate 2 change discussion is about this operator |
| insert_merchant_node | special_nodes.merchant_nodes, MCC codes | Gate 3 merchant density exemption suppresses | Merchant exemption must NOT be removed |
| create_bipartite_split | collector_count, width | Gate 3 — each sub-group <5 senders = escapes | Known gap. Bipartite threshold lowering is the proposed fix, but creates FP |
| time_dilation | spacing_days (×1.5-5×) | Nothing (spacing >30d = dormancy; velocity reads near-zero) | Changes to velocity threshold affect this |
| add_dormancy_period | timing.dormancy_periods | Nothing directly (breaks sequence detection) | Gate 2 dormancy check — if dormancy_days computed from spacing, long spacing bypasses via short dormancy |
| jitter_timing | spacing_days (±15-35%) | Nothing | Tier 1 velocity with jitter may or may not cross threshold |
| festival_timing | festival_timing dict, amounts <5k | Context adjuster (0.70 reduction) | Requires payee_vpa_age <30 AND has_festival_gifting_history. Both must hold. |
| just_under_threshold | amounts.values (8% below threshold) | Tier 1 threshold_proximity (within bands), Tier 3 Benford | Threshold bands are (49k-50k), (99k-100k), (990k-1M). 8% below = 46k — misses the 49k-50k band. |
| amount_noise | amounts.values (±2-8% noise) | Tier 3 amount_series_score, uniformity detection | Breaks amount_uniformity flag in Tier 1 merchant terminal check |
| pyramid_amounts | amounts.values (monotonic series) | Tier 3 amount_acceleration_score | Decreasing amounts mimic purchase series — harder to detect |
| channel_hop | channel_sequence | Nothing — each model sees 1 anomaly | Tier 3 channel_entropy rewards diversity (backwards). Known modeling weakness. |
| upi_app_diversity | channels.upi_apps | Nothing | Breaks device clustering (different app per account) |
| age_the_accounts | source_ages_days (200-545d) | Gate 4 (age >180 = exempted) | Gate 4 age ceiling is the intentional defense against this operator |
| reduce_velocity | velocity_ratio (0.02-0.08) | Tier 1 velocity_spike | If velocity_ratio <0.08, Tier 1 velocity flag doesn't fire. Accounts look dormant. |
| geographic_spread | geographic_spread (4-5 cities) | Nothing directly | Breaks PIN code clustering. Tier 3 location_entropy_30d affected |
| recognized_pattern_verification | mimics_legitimate flag | Nothing — whitelist exploits | HIGHEST RISK OPERATOR. Flags REQUIRES_SENIOR_REVIEW in realism.py. Human is last defense. |
| cash_out_disguise | cash_out_method, cash_out_delay | Gate 4 (delay >48h bypasses cash window) | Cash out delay >48h breaks Gate 4's 48h window requirement |
| layered_mixing | topology.layers, depth 7+, cover stories | Fund trail reconstruction + SHAP | Gate not applicable — Tier 3 only. betweenness_centrality of intermediate nodes |
| mule_hub_creator | fan_in, width 20-46, geographic_spread | Gate 3 if sender_count ≥5 AND density >0.7 | At 46 senders to 1 collector: density=1.0, sender_count=46 → Gate 3 SHOULD fire. Verify. |
| cycle_extender | topology.type="chain" not "cycle" | Nothing — cycle gate checks type field | Known gap. Graph cycle detection misses logical cycles in chain topology. |
| threshold_fragmenter | amounts (₹49k chunks), fan_in width | Tier 3 Benford + sub_threshold_ratio | No Tier 2 gate. Requires graph correlation across accounts (not single-account analysis). |
| ghost_node_injector | ATM withdrawal + redeposit, geo pair | Ghost node gate (if implemented) | Gate requires device correlation near both ATMs. Bank has this data. |
| dormant_activator | long light history, then burst, mimics employer | Tier 3 burst_score + amount_zscore | recognized_pattern_verification also applied — human review required |

---

## PART 7 — TESTING REQUIREMENTS BEFORE ANY CHANGE SHIPS
### Run before AND after. All must pass. No exceptions.

### 7.1 — 8 Named Fraud Scenarios (ALL must score ≥ 0.62, action = REVIEW or HIGH_RISK)

| Test | Pattern | Expected Gate/Mechanism | Expected Score |
|------|---------|------------------------|----------------|
| test_rapid_layering | 4 hops in 18 minutes, amounts declining 5% per hop | cycle gate | >0.85 |
| test_low_slow_mule | 45d normal → ₹1.8L spike to new payee at 2am | Tier 3 behavioral (amount_zscore + burst_score + hour_deviation) | >0.62 |
| test_festival_gifting_false_positive | Diwali, 12 × ₹2k to new accounts | Indian context adjuster (0.70) | <0.50 — this is a FALSE POSITIVE TEST, must NOT alert |
| test_digital_arrest | Senior age 68, 2am, ₹5L to VPA created 2 days ago | Tier 1 new_vpa + night + amount_spike → Tier 3 → amplified by 1.50 × 1.30 | >0.85 |
| test_ghost_node_cash_trail | ₹1.26L ATM Mumbai → ₹1.24L deposit Raipur 18h later | Ghost node gate | >0.85, trail reconstructed across gap |
| test_structuring_below_threshold | 5 txns ₹93k-97k in 7 days | Tier 3 Benford + sub_threshold_ratio + structuring_90k_99k | >0.62 |
| test_bipartite_mule_network | 7 senders → 1 collector age 14d density 0.85 | Gate 3 bipartite_core | score=1.0 |
| test_legitimate_salary_cycle | Employer advance → employee returns 25 days later | Gate 1 cycle fires → Filter 3 de-escalates | Action = LOG, NOT REVIEW |

### 7.2 — 5 Legitimacy Filter Tests (cycle fires but correctly explained → LOG not REVIEW)

| Filter | Test Case | Expected Result |
|--------|-----------|-----------------|
| Filter 1: Internal account | Cycle with INTERNAL account_type at origin | LOG("internal_transfer") |
| Filter 2: KYC relationship | Cycle between accounts in kyc_relationships table | LOG("known_relationship") |
| Filter 3: Salary advance | Corporate origin → employee return ≤30d ≤ sent amount | LOG("salary_advance_return") |
| Filter 4: All-merchant cycle | All cycle nodes is_merchant=True | LOG("merchant_settlement_cycle") |
| Filter 5: Amount reduction | exit_amount / entry_amount = 0.55 (<0.70) | LOG("fee_or_partial_repayment") |

### 7.3 — 6 Indian Context Adjustment Tests

| Adjustment | Test Case | Expected Score Change |
|------------|-----------|----------------------|
| Festival legit | Diwali, amount ₹3k, payee_vpa_age=15d, has_festival_gifting=True | score × 0.70 |
| Festival fraud block | Diwali, amount ₹3k, payee_vpa_age=45d (≥30) | NO reduction — payee too old |
| Gig worker velocity | 18 UPI transactions today, gig_worker occupation, 2pm | score × 0.85 |
| Senior night | kyc_age=72, hour=2am | score × 1.50 |
| Senior new VPA | kyc_age=72, payee_vpa_age=4d | score × 1.30 |
| Jan Dhan cash | account_type=JAN_DHAN | score × 0.75 |

### 7.4 — Legitimate Scenario False Positive Tests (ALL must score < 0.40 = PASS)

| Scenario | Test Parameters | Maximum Acceptable Score |
|----------|----------------|--------------------------|
| NRI returning after 90d | account_age=365, 1 sender, inflow=₹2L, no forwarding | 0.40 (PASS) |
| Seasonal merchant Oct reactivation | account_age=400, merchant occupation, 15 diverse buyers, Oct | 0.62 (LOG max) |
| Wedding gift aggregation | account_age=350, 4 family senders, ₹80k total, no forwarding | 0.40 (PASS) |
| Salary processor fan-in | 10 senders → payroll_processor account | 0.40 (PASS — bipartite exempt) |
| B2B merchant settlement cycle | All-merchant cycle, exit/entry=0.60 | LOG("merchant_settlement_cycle") |
| Gig worker velocity | 20 UPI/day, gig_worker, daytime | 0.40 (PASS) |
| Senior 10:30pm known contact | kyc_age=70, hour=22, known payee, ₹15k | 0.40 (PASS — not night, known payee) |

### 7.5 — Red Team Bypass Verifier (Existing bypasses must remain as-is)
```bash
python -m red_team.test_dna.bypass_verifier
# DNA 001 (merchant bipartite split): must score < 0.35
# DNA 002 (abandoned node time dilation): must score < 0.30
# DNA 003 (festival fanout): must score < 0.25
# NOTE: These are KNOWN bypasses scheduled for separate fixes.
# A proposed change must not accidentally "fix" them in a way that also
# breaks any legitimate scenario from Section 7.4.
# If a change makes a DNA score ≥ 0.62: verify it doesn't also
# flag any legitimate scenario before claiming it as a fix.
```

---

## QUICK REFERENCE: THRESHOLD CONSTANTS IN blue_clone.py

```python
# Gate thresholds — exact values from Blue Team source
_BIPARTITE_MIN_SENDERS      = 5       # Gate 3 — NEVER lower below 5 (NEVER-1)
_BIPARTITE_DENSITY_THRESHOLD = 0.70   # Gate 3 — do not lower below 0.65
_BIPARTITE_MERCHANT_DENSITY  = 0.85   # Gate 3 merchant exemption

_SINK_MIN_INFLOW             = 50_000  # Gate 2 — do not raise (misses small mules)
_SINK_MIN_RETENTION          = 0.80   # Gate 2 — do not lower below 0.70
_SINK_MIN_DORMANCY_DAYS      = 30     # Gate 2 — can raise to 60 safely
_SINK_MAX_AGE_DAYS           = 180    # Gate 2 — removal requires NEVER-2 compensation

_CASH_MULE_MIN_INFLOW        = 50_000  # Gate 4
_CASH_MULE_CASH_RATIO        = 0.80   # Gate 4 — do not lower below 0.70
_CASH_MULE_MAX_AGE           = 180    # Gate 4 — same ceiling as Gate 2

_VELOCITY_1H_MAX             = 5      # Tier 1
_NEW_VPA_DAYS                = 7      # Tier 1 — do not lower
_NEW_PAYEE_ACCOUNT_DAYS      = 14     # Tier 1
_AMOUNT_SPIKE_MULTIPLIER     = 5.0   # Tier 1

# Score action thresholds
_THRESHOLD_LOG               = 0.40   # Below = PASS
_THRESHOLD_REVIEW            = 0.62   # Below LOG = LOG
_THRESHOLD_HIGH_RISK         = 0.80   # Above = HIGH_RISK

# Indian context multipliers — NEVER-7 applies
FESTIVAL_REDUCTION           = 0.70   # × score during Diwali
GIG_WORKER_REDUCTION         = 0.85
JAN_DHAN_REDUCTION           = 0.75
MERCHANT_BATCH_REDUCTION     = 0.80
SENIOR_NIGHT_AMPLIFICATION   = 1.50   # NEVER reduce — digital arrest protection
SENIOR_NEW_VPA_AMPLIFICATION = 1.30   # NEVER reduce
```

---

## PART 8 — PRODUCTION EQUIVALENTS FOR SANDBOX CHANGES
### NEVER-8 compliance. Every blue_clone.py change requires this section filled before it ships.

Sandbox changes that lack a production equivalent are security theatre — the real Blue Team still has the gap.

---

### P8-A: Gate 2 — Abandoned Sink (Two-Path Restructure)
**Sandbox change**: `_simulate_sink_data()` restructured into two code paths to extend detection from new mule accounts (age < 180d) to old dormant-reactivated accounts (age ≥ 180d).

**Status**: ✅ Sandbox fix complete | ⚠️ Production Cypher NOT yet updated

**Production file**: `sink_queries.py` → `check_abandoned_sink()` Cypher

**Current production Cypher (exact — contains the gap)**:
```cypher
MATCH (sink:Account)
WHERE sink.account_age_days < 180
  AND sink.inflow_last_30d > 50000
  AND sink.retention_ratio > 0.80
  AND sink.days_since_last_send > 30
  AND NOT sink.kyc_occupation IN ['merchant', 'retailer', 'shopkeeper']
RETURN sink
```

**Required production Cypher change (NEVER-2 compliant — three compensating conditions)**:
```cypher
// PATH A: NEW MULE ACCOUNTS (age < 180d) — unchanged, exactly as production today
MATCH (sink:Account)
WHERE sink.account_age_days < 180
  AND sink.inflow_last_30d > 50000
  AND sink.retention_ratio > 0.80
  AND sink.days_since_last_send > 30
  AND NOT sink.kyc_occupation IN ['merchant', 'retailer', 'shopkeeper']
RETURN sink, 'new_mule' AS detection_path

UNION

// PATH B: OLD DORMANT-REACTIVATED ACCOUNTS (age >= 180d) — NEW PATH
// Three compensating conditions required by NEVER-2 (removing the age<180 ceiling
// requires ≥2 narrowing conditions; we add 3 for safety margin):
//   1. Multi-source: sender_count >= 3  (NRI/vacation: 1-2 senders only)
//   2. Extended dormancy: days_since_last_send >= 60  (vacation = 30-45d, not 60+)
//   3. Rapid forwarding: account sent funds within 7d of receiving burst
MATCH (sink:Account)
WHERE sink.account_age_days >= 180
  AND sink.inflow_last_30d > 50000
  AND sink.days_since_last_send >= 60
  AND NOT sink.kyc_occupation IN ['merchant', 'retailer', 'shopkeeper']
// Condition 1: multi-source — count distinct senders in last 30d
MATCH (source:Account)-[t:TRANSACTION]->(sink)
WHERE t.timestamp > datetime() - duration('P30D')
WITH sink, count(DISTINCT source) AS sender_count
WHERE sender_count >= 3
// Condition 3: rapid forwarding — sent within 7d of receiving burst
MATCH (sink)-[fwd:TRANSACTION]->(forward:Account)
WHERE fwd.timestamp > datetime() - duration('P7D')
RETURN sink, 'old_dormant_reactivated' AS detection_path
```

**FP risk after change** (verified against legitimate catalog):
| Scenario | Before | After | Protected by |
|----------|--------|-------|-------------|
| L-01 NRI returning (1 sender) | PASS (age≥180 blocked Gate 2) | PASS | sender_count ≥3 fails — 1 sender only |
| L-05 Seasonal merchant | PASS (merchant occupation exempt) | PASS | occupation exemption applies both paths |
| L-06 Wedding (4 senders, no forward) | PASS (age≥180 blocked) | PASS | no forwarding within 7d — condition 3 fails |
| L-08 Salary advance cycle | PASS (cycle legit filter catches) | PASS | Gate 2 fires first, cycle gate exemption not needed |

**Who must approve**: Blue Team lead engineer + Neo4j DBA (Cypher requires testing on production graph schema). PR must include query plan `EXPLAIN` output — `days_since_last_send` must be indexed.

---

### P8-B: Gate 0 — Rapid Relay (NEW GATE — no production equivalent yet)
**Sandbox change**: New backstop gate `_simulate_rapid_relay()` added. Catches the abandoned node pattern when account fixture data is unavailable (genome-level signals only).

**Status**: ✅ Sandbox implementation complete | ❌ No production equivalent exists

**Two bugs fixed in sandbox implementation**:
- **Conservation calc bug**: For fan_in/bipartite genomes, `amounts[-1]` is the last SOURCE payment, not the forwarded outflow. Fixed to use `total_inflow × 0.97` for fan_in/bipartite.
- **Timing proxy bug**: `spacing_days` measures gap between source transactions, not the relay window. An attacker spaces sources 1d apart (normal-looking) while relaying instantly. Fixed to use `dormancy_days ≥ 60` as the reactivation signal.

**Required production implementation**:
The real Blue Team does not have this gate. This must be proposed as a new gate (Gate 0, runs before all existing gates) in the real Blue Team build.

**Production Cypher equivalent**:
```cypher
// Gate 0: Rapid Relay — multi-source coordinated inflow with near-full conservation
// Catches: ≥4 sources → dormant account (≥60d) → near-immediate forwarding (≥95% conservation)
// Does NOT catch: NRI (1-2 senders), weddings (no forwarding), seasonal merchants (occupation exempt)
MATCH (collector:Account)
WHERE collector.days_since_last_send >= 60
  AND collector.inflow_last_30d >= 100000
  AND NOT collector.kyc_occupation IN ['merchant', 'retailer', 'shopkeeper',
                                        'salary_processor', 'payroll_processor',
                                        'insurance_company', 'tax_collector',
                                        'utility_provider']
// Count distinct sources in last 14d
MATCH (source:Account)-[t_in:TRANSACTION]->(collector)
WHERE t_in.timestamp > datetime() - duration('P14D')
WITH collector, count(DISTINCT source) AS source_count,
     sum(t_in.amount) AS total_inflow
WHERE source_count >= 4
// Measure conservation: outflow vs inflow within 7d of receiving burst
MATCH (collector)-[t_out:TRANSACTION]->(forward:Account)
WHERE t_out.timestamp > datetime() - duration('P7D')
WITH collector, source_count, total_inflow, sum(t_out.amount) AS total_outflow
WHERE total_outflow / total_inflow >= 0.95
RETURN collector, source_count, total_inflow, total_outflow,
       total_outflow / total_inflow AS conservation_ratio
```

**SQL equivalent (PostgreSQL — for transaction-level evidence package)**:
```sql
-- Conservation calculation — replaces amounts[-1] for fan_in topologies
SELECT
    collector_account_id,
    COUNT(DISTINCT sender_account_id)          AS source_count,
    SUM(amount) FILTER (WHERE direction='in')  AS total_inflow,
    SUM(amount) FILTER (WHERE direction='out'
                        AND txn_date >= burst_start)
                                               AS total_outflow,
    ROUND(
      SUM(amount) FILTER (WHERE direction='out' AND txn_date >= burst_start)
      / NULLIF(SUM(amount) FILTER (WHERE direction='in'), 0),
    3)                                         AS conservation_ratio
FROM account_transaction_summary
WHERE collector_dormancy_days >= 60
GROUP BY collector_account_id, burst_start
HAVING COUNT(DISTINCT sender_account_id) >= 4
   AND SUM(amount) FILTER (WHERE direction='in') >= 100000
   AND ROUND(
      SUM(amount) FILTER (WHERE direction='out' AND txn_date >= burst_start)
      / NULLIF(SUM(amount) FILTER (WHERE direction='in'), 0), 3) >= 0.95;
```

**Gating criteria before this gate can go to production**:
1. Cypher query tested on historical Neo4j graph — FP rate must be < 5% on confirmed-legit transactions
2. SQL query `EXPLAIN ANALYZE` run — `collector_dormancy_days` index required
3. Gate 0 must produce complete evidence package (fund trail + STR draft fields) before it can fire REVIEW — not just a score
4. Human investigator pilot: run gate in LOG-only mode for 2 weeks, review every triggered case, tune `source_count ≥ 4` and `conservation ≥ 0.95` thresholds from actual data
5. `model_audit` INSERT must fire before Gate 0 returns (A-03 architectural constraint)

**Risk if shipped without pilot**: Conservation ratio ≥ 0.95 is a strict threshold. Real mule operations vary — some extract 5-10% fees, dropping conservation to 0.90-0.95. Consider tuning to 0.90 after pilot data confirms FP rate.

---

*Generated from: BLING_BlueTeam_ClaudeCode_Prompt_UPDATED.md + blue_clone.py source analysis + Red Team operator catalog*
*Purpose: Pre-flight checklist for ALL Blue Team logic changes*
*Update this document whenever: a new fraud pattern is discovered, a new operator is added to Red Team, a new legitimate banking behavior is identified, or a threshold is changed with evidence*
