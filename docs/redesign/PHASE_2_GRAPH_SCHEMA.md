# Phase 2 — Banking Knowledge-Graph Schema (DESIGN DOC, for approval)

> Status: **APPROVED & BUILT (Wave 1).** Schema-as-code lives in `backend/graph/schema/` (labels.py, models.py, client.py, constraints.cypher, bootstrap.py); data-layer compose in `deployment/docker-compose.data.yml`. Verified statically (62 DDL stmts parse; 26 node models validate). Live apply blocked on Docker install — see Phase 3 gate.
> Sign-off: reified Transaction node + derived TRANSFERRED_TO ✅ · phased ship A/B/C/E then D/F ✅ · PII hash+mask never-raw ✅
> Persistence decision (locked in Phase 1): **Neo4j = graph source of truth**, Postgres = cases/audit/users, Redis = cache/queue, object store = evidence files. NetworkX remains a *hot cache / live-demo projection* of Neo4j, never the truth.
> Preservation rule: this schema is a **superset** of today's account⇄transaction⇄account model. The current model is the `(:Account)-[:TRANSFERRED_TO]->(:Account)` projection — nothing is removed.

---

## 1. Core modeling decisions (the "why" before the "what")

### 1.1 Transaction is a **reified node**, not an edge
Today a transaction is an edge `Account -> Account`. That cannot connect to the device, IP, channel, merchant, or location used — all of which are central to fraud. Enterprise AML graphs (Quantexa, Neo4j AML reference model) **reify** the transaction:

```
(:Account)-[:SENT]->(:Transaction)-[:RECEIVED_BY]->(:Account)
(:Transaction)-[:VIA_CHANNEL]->(:Channel)
(:Transaction)-[:USED_DEVICE]->(:Device)
(:Transaction)-[:FROM_IP]->(:IPAddress)
(:Transaction)-[:AT_LOCATION]->(:Location)
(:Transaction)-[:TO_MERCHANT]->(:Merchant)
```

To keep the fast graph-viz path (and the NetworkX cache) cheap, we **also** maintain a derived, aggregated edge:

```
(:Account)-[:TRANSFERRED_TO {total_amount, txn_count, first_ts, last_ts, max_amount}]->(:Account)
```

`TRANSFERRED_TO` is *computed* from `SENT/RECEIVED_BY` by a projection job — it is the current model, preserved verbatim, now as a materialized view. Investigators traverse `TRANSFERRED_TO` for speed; evidence drills into `Transaction` nodes for truth.

**Rationale:** decouples "fast topology" from "rich forensic detail". **Risk:** dual-write/projection drift → mitigated by making `TRANSFERRED_TO` strictly derived (rebuilt by job, never hand-edited).

### 1.2 Identity is first-class and shared → this is how rings are found
The single biggest gain over today's model: `Device`, `IPAddress`, `Phone`, `Email`, `PAN`, `Aadhaar`, `Address` are **shared nodes**. Two customers using the same device is an *edge to the same node*, not a string comparison. Every `SHARES_*` relationship in your Part 3 list becomes a **derived edge** computed from shared identity nodes (see §5).

### 1.3 PII handling (PAN / Aadhaar / Phone / Email)
- Aadhaar is **DEMO ONLY** and stored as a salted hash + last-4 in the demo; flagged `synthetic:true`. Never store raw Aadhaar.
- PAN stored masked (`ABCDE****F`) on the node; raw value (demo) only in Postgres PII vault keyed by node id, access-audited.
- These nodes carry a `pii:true` label so RBAC + read-audit can gate them.

### 1.4 Naming conventions
- Node labels: `PascalCase` singular (`:Customer`).
- Relationship types: `UPPER_SNAKE`, verb from subject→object (`:OWNS`, `:USES_DEVICE`).
- Properties: `snake_case`. Every node: `id` (UUID/ULID), `created_at`, `updated_at`, `source_system`.
- IDs are real UUIDs — we **stop inferring type from string prefix** (the `"MUL"/"HVA"` hack in `graph_manager._update_node` is replaced by a real `account_type` property + `RiskProfile`).

---

## 2. Node catalogue

For each: key properties, uniqueness constraint, indexes, typical cardinality vs Account.

### Domain A — Identity & Customer
| Node | Key properties | Constraint | Indexes | Cardinality |
|---|---|---|---|---|
| `Customer` | id, name, dob, customer_since, segment(retail/HNI/business), occupation, declared_income, residency, status, risk_band | UNIQUE id | name(text/fulltext), segment, status | 1 Customer : N Accounts |
| `KYC` | id, level(min/full/video), verified_at, expires_at, status, doc_types[], pep_flag | UNIQUE id | status, expires_at | 1 KYC : 1 Customer (current) + history |
| `PAN` | id, pan_masked, name_on_pan, verified, `pii:true` | UNIQUE pan_hash | pan_hash | shared — N Customers→1 PAN = fraud signal |
| `Aadhaar`* | id, aadhaar_hash, last4, verified, `pii:true synthetic:true` | UNIQUE aadhaar_hash | aadhaar_hash | shared (demo) |
| `Phone` | id, e164, type(mobile/landline), `pii:true` | UNIQUE e164 | e164 | shared |
| `Email` | id, address_norm, domain, `pii:true` | UNIQUE address_norm | domain | shared |
| `Address` | id, line, city, pincode, geohash, country | UNIQUE id | geohash, pincode | shared |
| `Location` | id, name, lat, lon, geohash, country, is_high_risk | UNIQUE id | geohash | shared by txns/devices |

\* Aadhaar = demo only.

### Domain B — Accounts, Products & Instruments
| Node | Key properties | Constraint | Indexes | Cardinality |
|---|---|---|---|---|
| `Account` | id, account_no_masked, account_type(savings/current/mule/merchant/high_value/cash), status(active/dormant/frozen/closed), opened_at, balance_band, currency, dormant_since | UNIQUE id; UNIQUE account_no_hash | account_type, status, opened_at | hub node |
| `Card` | id, card_type(debit/credit), pan_token, network(visa/rupay/mc), issued_at, status | UNIQUE id | status | 1 Account : N Cards |
| `Wallet` | id, provider, kyc_level, balance_band | UNIQUE id | provider | 1 Customer : N Wallets |
| `Loan` | id, type, principal, sanctioned_at, status, dpd | UNIQUE id | status | 1 Customer : N |
| `FixedDeposit` | id, amount, opened_at, maturity, auto_renew | UNIQUE id | maturity | 1 Customer : N |
| `Insurance` | id, type, sum_assured, premium, status | UNIQUE id | status | 1 Customer : N |
| `Product` | id, code, family, risk_weight | UNIQUE code | family | reference |
| `Beneficiary` | id, beneficiary_account_ref, added_at, channel_added | UNIQUE id | added_at | 1 Account : N; explosion = signal |

### Domain C — Movement
| Node | Key properties | Constraint | Indexes | Cardinality |
|---|---|---|---|---|
| `Transaction` | id, amount, currency, rail(UPI/IMPS/RTGS/NEFT/CASH_IN/CASH_OUT), ts, status, direction, narration, risk_score, fraud_pattern, is_flagged | UNIQUE id | **ts (range)**, rail, amount(range), is_flagged, risk_score | high-volume (millions) |
| `Currency` | code, name, is_crypto | UNIQUE code | — | reference |

`Transaction.ts` range index is **the** hot index for timeline replay & velocity windows.

### Domain D — Bank Org & Commerce
| Node | Key properties | Constraint | Indexes | Cardinality |
|---|---|---|---|---|
| `Branch` | id, ifsc, name, city, region | UNIQUE ifsc | city, region | 1 Branch : N Accounts |
| `Channel` | id, type(UPI_app/netbanking/atm/branch/pos/api) | UNIQUE id | type | reference |
| `Employee` | id, emp_code, role, branch_ref, status | UNIQUE emp_code | role | 1 Branch : N |
| `RelationshipManager` | id (Employee subtype), portfolio_size | UNIQUE id | — | 1 RM : N Customers |
| `Organization` | id, name, type, registration_no | UNIQUE registration_no | name(fulltext) | shared employer |
| `Business` | id, name, gstin, incorporation_date, is_shell_suspect | UNIQUE gstin | is_shell_suspect | 1 owner : N |
| `Merchant` | id, mcc, name, category, terminal_id | UNIQUE id | mcc, category | shared |
| `Device` | id, fingerprint, os, model, first_seen, is_emulator | UNIQUE fingerprint | first_seen, is_emulator | shared — key fraud signal |
| `IPAddress` | id, ip, asn, is_vpn, is_tor, country, geohash | UNIQUE ip | asn, is_vpn, country | shared |

### Domain E — Risk, Alerts & Investigation
| Node | Key properties | Constraint | Indexes | Cardinality |
|---|---|---|---|---|
| `RiskProfile` | id, subject_ref, score_0_100, band, factors_json, model_version, computed_at | UNIQUE id | band, computed_at | 1 : 1 with Account/Customer (current) |
| `SuspiciousPattern` | id, pattern_code, family, severity, confidence, detector_version, detected_at | UNIQUE id | pattern_code, detected_at | N per cluster |
| `Alert` | id, type, severity, status(open/triage/escalated/closed/false_pos), score, created_at, assigned_to | UNIQUE id | status, severity, created_at | many |
| `Case` | id, case_no, title, status, priority, opened_at, closed_at, owner, disposition | UNIQUE case_no | status, owner, opened_at | groups alerts |
| `Investigation` | id, case_ref, investigator_ref, started_at, steps_json | UNIQUE id | investigator_ref | 1 Case : N |
| `Evidence` | id, type, sha256, bels_anchor_ref, created_by, created_at, storage_uri | UNIQUE sha256 | created_at | N per Case |
| `RegulatoryReport` | id, type(STR/CTR/FIU), status, period, filed_at, ref_no | UNIQUE id | type, status | per Case |
| `AuditEntry` | id, actor, action, target_ref, ts, ip | UNIQUE id | actor, ts | append-only (also in Postgres) |

### Domain F — Reference & Watchlists
| Node | Key properties | Constraint | Indexes | Cardinality |
|---|---|---|---|---|
| `Watchlist` | id, name, source, type | UNIQUE id | — | reference |
| `SanctionList` | id, name(OFAC/UN/MHA), version | UNIQUE id | — | reference |
| `BlacklistedEntity` | id, name, identifier, reason, listed_at | UNIQUE id | identifier | reference |
| `HighRiskCountry` | code, name, fatf_status | UNIQUE code | fatf_status | reference |

---

## 3. Relationship catalogue (your Part 3 list, fully mapped)

### Structural (asserted at ingest — ground truth)
| Rel | From → To | Properties | Cardinality |
|---|---|---|---|
| `OWNS` | Customer → Account/Card/Wallet/Loan/FD/Insurance | since, ownership_type | 1:N |
| `BELONGS_TO` | Account → Customer; Employee → Branch | role | N:1 |
| `HOLDS_KYC` | Customer → KYC | current:bool | 1:N(history) |
| `HAS_PAN` / `HAS_AADHAAR`* / `HAS_PHONE` / `HAS_EMAIL` | Customer → PAN/Aadhaar/Phone/Email | since, verified | N:1 (shared target) |
| `LOCATED_AT` / `RESIDES_AT` | Account/Customer/Branch → Address/Location | type | N:1 |
| `FROM_BRANCH` / `TO_BRANCH` | Account/Transaction → Branch | — | N:1 |
| `USES_PRODUCT` | Account → Product | opened_at | N:1 |
| `MANAGES` | RelationshipManager → Customer | since | 1:N |
| `EMPLOYED_BY` | Customer → Organization | since, role | N:1 (shared = SAME_EMPLOYER) |
| `CONTROLLED_BY` | Business → Customer | stake_pct | N:1 |
| `SENT` / `RECEIVED_BY` | Account → Transaction → Account | — | 1:N / N:1 |
| `VIA_CHANNEL` / `USED_DEVICE` / `FROM_IP` / `AT_LOCATION` / `TO_MERCHANT` | Transaction → Channel/Device/IP/Location/Merchant | — | N:1 |
| `USED_CHANNEL` | Account → Channel | first_used | N:M |
| `VISITED` | Customer → Branch/Merchant | ts | N:M |
| `ADDED_BENEFICIARY` / `SAME_BENEFICIARY` | Account → Beneficiary | added_at | 1:N |
| `LISTED_ON` | Customer/Account/Business → Watchlist/SanctionList | listed_at, reason | N:M |

### Derived — identity collisions (computed by job, your `SHARES_*` family)
Each is created when ≥2 distinct customers/accounts point to the *same* identity node:
| Rel | Derived from | Meaning |
|---|---|---|
| `SHARES_DEVICE` | common `:Device` | strong ring signal |
| `SHARES_IP` | common `:IPAddress` | medium |
| `SHARES_PHONE` | common `:Phone` | strong |
| `SHARES_EMAIL` | common `:Email` | medium |
| `SHARES_ADDRESS` | common `:Address` | medium |
| `SAME_PAN` | common `:PAN` | very strong (identity theft / synthetic) |
| `SAME_AADHAAR`* | common `:Aadhaar` (demo) | very strong |
| `SAME_EMPLOYER` | common `:Organization` | weak/context |
| `SAME_ORGANIZATION` | common `:Business` ownership | context |
| `RELATED_TO` / `CONNECTED_TO` | aggregate of any shared identity | generic "these entities are linked" edge for the relationship explorer |

Each derived edge carries `{basis, weight, computed_at, shared_node_ids[]}` so the UI can explain *why* two entities are linked.

### Investigation lifecycle (your Part 3 tail)
| Rel | From → To |
|---|---|
| `FLAGGED_BY` | Account/Transaction → SuspiciousPattern / Detector |
| `GENERATED_ALERT` | SuspiciousPattern → Alert |
| `SUPPORTS_PATTERN` | Transaction/Account → SuspiciousPattern |
| `CREATE_CASE` / `PART_OF_CASE` | Alert → Case |
| `INVESTIGATED_IN` | Account/Customer → Investigation |
| `STORE_EVIDENCE` | Case → Evidence |
| `HAS_RISK_PROFILE` | Account/Customer → RiskProfile |
| `REPORTED_IN` | Case → RegulatoryReport |
| `ASSIGNED_TO` | Case/Alert → Employee (investigator) |

---

## 4. Constraints & indexes (Neo4j DDL, summary)

- **Uniqueness constraints** on every `id` and every natural key listed above (also create the backing range index).
- **Range indexes**: `Transaction(ts)`, `Transaction(amount)`, `Alert(created_at)`, `Case(opened_at)`, `RiskProfile(computed_at)`.
- **Lookup indexes**: status/type/band/category fields used in filters (Part 6 graph filters: branch/product/date/amount/risk/channel).
- **Full-text indexes**: `Customer(name)`, `Organization(name)`, `Business(name)`, `Merchant(name)` → powers global search (Part 6).
- **Composite**: `Transaction(rail, ts)` for rail-scoped timeline windows.

## 5. Derivation / projection jobs (Phase 9 scheduling, listed here for completeness)
1. `TRANSFERRED_TO` aggregator — rebuilds the fast topology edge from `SENT/RECEIVED_BY`.
2. `SHARES_*` identity-collision builder — the heart of ring detection.
3. Centrality/community precompute (degree, betweenness, Louvain) → stored as node props (replaces live NetworkX `communities` call that risks blocking the event loop).
4. `RiskProfile` refresh.

## 6. Traversal examples (investigator questions → Cypher)
These prove the schema answers real investigator questions.

**"Show me everyone who shares a device with this customer's accounts":**
```cypher
MATCH (c:Customer {id:$id})-[:OWNS]->(:Account)-[:SENT|RECEIVED_BY]-(t:Transaction)
      -[:USED_DEVICE]->(d:Device)<-[:USED_DEVICE]-(:Transaction)<-[:SENT|RECEIVED_BY]-(a2:Account)<-[:OWNS]-(other:Customer)
WHERE other <> c
RETURN other, d, count(*) AS shared_txns ORDER BY shared_txns DESC
```

**Fund-journey replay (layering chain) from a source account, ≤8 hops, time-ordered:**
```cypher
MATCH p=(src:Account {id:$id})-[:TRANSFERRED_TO*1..8]->(dest:Account)
WHERE all(i IN range(0,length(p)-2) WHERE
      ([rel IN relationships(p)][i]).last_ts <= ([rel IN relationships(p)][i+1]).first_ts)
RETURN p LIMIT 50
```

**Mule fan-in then cash-out (scatter-gather signature):**
```cypher
MATCH (mule:Account)<-[:TRANSFERRED_TO]-(src:Account)
WITH mule, count(DISTINCT src) AS fan_in
WHERE fan_in >= 8
MATCH (mule)-[:SENT]->(co:Transaction {rail:'CASH_OUT'})
RETURN mule, fan_in, sum(co.amount) AS cashed_out ORDER BY cashed_out DESC
```

**Watchlist proximity (within 3 hops of a sanctioned entity):**
```cypher
MATCH (acc:Account {id:$id})-[:RELATED_TO|TRANSFERRED_TO|SHARES_DEVICE*1..3]-(x)-[:LISTED_ON]->(:SanctionList)
RETURN DISTINCT x
```

## 7. Migration strategy (preview of Phase 3, here for traceability)
- `cases.json` (236 KB) → Postgres `cases` table + `Case`/`Alert`/`Evidence` nodes in Neo4j (idempotent loader).
- `investigators.json` → Postgres `users`.
- Existing in-memory graph → seed loader writes `Account` + `SENT/RECEIVED_BY` + projects `TRANSFERRED_TO`; NetworkX then **reads from Neo4j** instead of being authoritative.
- Backfill: detectors/risk/recovery/DNA keep their current input contract by reading the `TRANSFERRED_TO` projection — **zero detector code changes required in Phase 2**.

## 8. Risks
- **Over-modeling**: 40+ labels is a lot. Mitigation — ship Domains A/B/C/E first (the ones detectors need); D/F are reference data that can lag.
- **Projection drift** (`TRANSFERRED_TO` vs `SENT`): mitigated by job-only writes + a consistency check in Phase 10 tests.
- **PII exposure**: gated by `pii:true` label + RBAC + read-audit before Aadhaar/PAN nodes ship.

## 9. Open questions for sign-off
1. Confirm Transaction-as-node (reified) + derived `TRANSFERRED_TO` is acceptable (vs keeping transaction strictly as an edge). **Recommended: yes.**
2. Confirm domain ship order A/B/C/E → D/F, or all at once.
3. Confirm demo Aadhaar/PAN PII handling (hash + mask, never raw) is acceptable for your demo.
