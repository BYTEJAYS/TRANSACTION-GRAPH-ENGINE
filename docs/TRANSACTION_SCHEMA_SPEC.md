# TGIE Transaction Event Schema — Specification

Versioned, backward-compatible ingress contract for `POST /api/transaction/manual`.
Two formats are accepted and auto-detected; both normalize to one internal model.

- **Code:** `backend/models/event_schema.py` (schema) · `backend/models/normalize.py` (detection + conversion)
- **Tests:** `backend/tests/test_event_schema.py`
- Current versions: **`1.0-legacy`** (lightweight list) · **`2.0`** (enterprise envelope/events)

---

## 1. Supported formats

### 1.0 — legacy lightweight (unchanged, still works)
A bare JSON **array** of transactions:
```json
[
  { "from_account": "ACC_1001", "to_account": "ACC_2001", "amount": 500, "payment_rail": "UPI", "timestamp": "2026-05-15T02:30:00" }
]
```
The previously-supported flat enrichment fields (`device_id`, `from_customer`, `to_customer`,
`from_phone`, `to_phone`, `from_pan`, `to_pan`, `from_entity_type`, `to_entity_type`) remain valid.

### 2.0 — enterprise envelope
A JSON **object** wrapping events with optional intelligence blocks:
```json
{
  "schema_version": "2.0",
  "dataset_id": "UB-DEMO-001",
  "investigation_id": "INV-2026-114",
  "source_system": "CBS",
  "ingestion_timestamp": "2026-06-30T08:00:00",
  "transactions": [
    {
      "transaction_id": "TXN-1",
      "from_account": "ACC_1001",
      "to_account": "MERCH_9",
      "amount": 2500000,
      "product": "rtgs",
      "payment":  { "rail": "RTGS", "channel": "internet_banking", "currency": "INR",
                    "direction": "external", "domestic": true, "narration": "vendor payment",
                    "reference_number": "UTR123", "settlement_type": "deferred" },
      "from_party": {
        "customer": { "customer_id": "CUST_1", "profile": "business_owner", "segment": "sme",
                      "kyc_risk": "low", "branch": "Mumbai-Fort", "residency": "resident" },
        "account":  { "account_category": "current", "account_status": "active", "current_balance": 9000000 },
        "device":   { "device_id": "DEV_1", "device_reputation": "good", "proxy_or_vpn": false },
        "geo":      { "city": "Mumbai", "state": "MH", "country": "IN", "impossible_travel": false },
        "network":  { "pan": "PAN_ABC", "mobile_number": "PHONE_99" }
      },
      "to_party":  { "customer": { "profile": "retail_merchant" },
                     "account":  { "account_category": "merchant" } },
      "merchant":  { "merchant_id": "M_9", "mcc": "5732", "risk_rating": "low" },
      "recovery":  { "settlement_status": "pending", "reversible": true, "recovery_priority": "high" },
      "context":   { "scenario_id": "vendor-payment", "synthetic": true }
    }
  ]
}
```
A bare **array of enterprise events** (no envelope) is also accepted.

---

## 2. Fields

### Envelope (all optional except `transactions`)
| Field | Type | Notes |
|---|---|---|
| `schema_version` | string | defaults to `"2.0"` |
| `dataset_id`, `investigation_id`, `source_system` | string | investigation context |
| `ingestion_timestamp` | ISO-8601 | defaults to now |
| `transactions` | **required** array of events | |
| `metadata` | object | free-form |

### Event — money core (**required**)
| Field | Type | Rule |
|---|---|---|
| `from_account`, `to_account` | string | non-empty |
| `amount` | number | **> 0** |

### Event — optional core
`transaction_id` (unique), `timestamp` (ISO-8601), `product`, `payment_rail` (legacy top-level).

### Optional intelligence blocks
| Block | Phase | Key fields |
|---|---|---|
| `payment` | 5 | rail, channel, purpose, settlement_type, currency, fx{base,quote,rate}, reference_number, narration, merchant_category, direction, domestic |
| `from_party` / `to_party` | 2,3,6,7,9,10 | `customer`, `account`, `device`, `geo`, `network`, `behaviour` |
| `from_party.customer` | 2 | customer_id, **profile**, segment, occupation, kyc_risk, branch, onboarding_channel, residency, business_category |
| `from_party.account` | 3 | account_category, current_balance, account_status, opening_date |
| `from_party.device` | 6 | device_id, imei, fingerprint, os, app_version, ip_address, proxy_or_vpn, rooted_or_jailbroken, trusted_device, device_reputation |
| `from_party.geo` | 7 | country, state, city, latitude, longitude, distance_from_previous_km, geo_anomaly, impossible_travel |
| `from_party.network` | 9 | mobile_number, email, pan, masked_aadhaar, gst, business_registration, shared_address, shared_beneficiary, shared_nominee |
| `from_party.behaviour` | 10 | historical_avg/median, typical_daily_volume, typical_txn_count, preferred_rail, preferred_hours, cash_preference, seasonality |
| `merchant` | 8 | merchant_id, mcc, merchant_type, business_category, terminal_id, acquirer, pos_id, risk_rating, known_fraud_merchant |
| `recovery` | 11 | settlement_status, reversible, chargeback_eligible, recovery_priority, recovery_window_hours |
| `context` | 12 | source_dataset, scenario_id, synthetic, simulation_id, training_scenario, demo_scenario, analyst_notes, case_id |

All blocks allow extra keys (`extra="allow"`) — add a field without a schema change.

---

## 3. Enumerated values (known catalogue)
- **Product:** savings, current, upi, credit_card, debit_card, wallet, merchant, atm, pos, qr, internet_banking, mobile_banking, rtgs, neft, imps, swift, forex, loan, trade_finance
- **Account category:** savings, current, loan, credit_card, wallet, merchant, nostro, vostro, escrow, dormant, corporate, joint, overdraft, salary
- **Channel:** branch, atm, pos, qr, internet_banking, mobile_banking, upi_app, call_centre, agent, swift
- **Payment rail:** UPI, IMPS, RTGS, NEFT, CASH, CASH_IN, CASH_OUT, SWIFT
- **Customer profile:** salaried_employee, business_owner, msme, large_corporate, farmer, student, pensioner, freelancer, government_employee, ngo_trust, retail_merchant, ecommerce_seller, hni, cash_intensive_business, exporter_importer

Unknown enum values are **preserved and surfaced as warnings**, never rejected (so demos never break).

---

## 4. Validation rules (Phase 13)
| Rule | Behaviour |
|---|---|
| `amount > 0` | **reject** (400) |
| non-empty `from_account`/`to_account` | **reject** (400) |
| duplicate `transaction_id` | **reject** (400) |
| invalid `timestamp` | warn + treat as now |
| unknown rail / product / profile | warn + keep value |
| missing optional fields | ignored (graceful) |
| non-list / non-envelope payload | **reject** (400) |

The endpoint returns `{ status, count, schema_version, profiles_supplied, warnings }`.

---

## 5. How the data is used (normalization targets)
`normalize_payload()` flattens any format into:
- **`transactions`** → `ManualTransactionInput` (the existing internal model) → the unchanged graph/detection pipeline.
- **`customer_profiles`** `{account: profile}` → fed to **Profile Intelligence** (`risk_engine`) so behaviour is judged relative to the declared customer; inference still runs for accounts without a declared profile.
- **`account_intel`** `{account: {kyc_risk, account_category, products, geo, device, merchant, recovery, …}}` → attached to verdicts as `account_intelligence` and surfaced in the Node Inspector when present.
- **entity context** (customer/device/phone/pan, account_category→entity_type) → the existing cross-product / customer-risk engines via `record_account`.

---

## 6. Migration guide (1.0 → 2.0)
1. **Nothing is forced.** Keep posting the bare array — it stays valid forever.
2. Wrap it in an envelope when you want batch context:
   `{ "schema_version": "2.0", "dataset_id": "...", "transactions": [ …your existing rows… ] }`
3. Enrich incrementally — add a `from_party.customer.profile` here, a `payment.channel` there. Every block is independent and optional.
4. Map legacy flat fields → nested when convenient (both keep working): `from_customer` → `from_party.customer.customer_id`; `device_id` → `from_party.device.device_id`; `from_pan` → `from_party.network.pan`.

---

## 7. Extension strategy
- **New optional field on an existing block:** just send it — blocks are `extra="allow"`; add to the model later for validation/typing.
- **New block (new banking product / intelligence type):** add a model in `event_schema.py`, a field on `TransactionEvent` or `PartyInfo`, and one mapping line in `normalize.py`. No endpoint or downstream change.
- **New schema version:** bump `schema_version`; `normalize_payload` branches on it. Old versions keep working (the detector is shape-based, not version-gated).
- **New enum value:** add to the catalogue; until then it is accepted with a warning.
