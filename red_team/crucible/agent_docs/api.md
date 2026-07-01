# API Reference
# Generated and maintained by Claude as endpoints are built.

## Base URL
`http://localhost:8001`

## Endpoints

### Health
```
GET /health
→ {"status": "ok", "service": "crucible-red-team"}
```

### Receive Confirmed Fraud (Blue Team → Red Team)
```
POST /api/v1/red_team/receive_fraud_dna

Body:
{
  "fraud_id": "CF_20260401_001",
  "transactions": [
    {"from_account": "ACC_A001", "to_account": "ACC_A100",
     "amount": 18500, "payment_rail": "NEFT", "timestamp": "2026-03-15T10:00:00"}
  ],
  "confirmed_at": "2026-04-01T09:00:00Z",
  "source": "blue_team"
}

→ {"status": "received", "fraud_id": "CF_20260401_001"}
```

### Get Human Gate Queue
```
GET /api/v1/red_team/queue?limit=20

→ {
    "pending": 7,
    "items": [{
      "genome_id": "...",
      "priority_score": 2.34,
      "rupees_at_risk": 48730.0,
      "ease": "moderate",
      "scalability": "medium",
      "requires_senior_review": false,
      "flags": ["complex_chain_low_gain"],
      "summary": { topology_type, depth, fitness, ... }
    }]
  }
```

### Review Genome
```
POST /api/v1/red_team/review/{genome_id}

Body:
{
  "reviewer_id": "investigator_001",
  "decision": "approve",          // "approve" | "discard" | "needs_more_info"
  "notes": "Clear merchant exploitation pattern"
}

→ {
    "genome_id": "...",
    "decision": "approve",
    "repair_recommendation": {
      "recommendation": "new_gate",    // or "bounded_retrain" | "human_decision"
      "gate_name": "bipartite_core_gate",
      "feature_set": [],
      "evidence": {...},
      "confidence": 0.85
    }
  }
```

### Prophecy Stats
```
GET /api/v1/red_team/prophecy/stats

→ {
    "total_predictions": 1247,
    "matched": 89,
    "unmatched": 1158,
    "overall_hit_rate": 0.0714,
    "confirmed_frauds_received": 20,
    "active_lineages": 34,
    "days_ahead_sample": [45, 45, 45, ...]
  }
```

### Lineage Scores
```
GET /api/v1/red_team/lineages

→ {
    "lineage_weights": {"seed_mule_hub_creator": 1.8, ...},
    "operator_boosts": {"ghost_node_injector": 2.0, ...},
    "combined_weights": {"ghost_node_injector": 1.76, ...},
    "operator_stats": [{"operator": "...", "win_rate": 0.12, ...}]
  }
```

### Demo: Run Prophecy Match
```
GET /api/v1/demo/run_prophecy_match

→ {
    "matches": 5,
    "checked": 47,
    "hit_rate": 0.1064,
    "recent_confirmed_count": 20,
    "stats": {...}
  }
```

### Demo: Evolution Replay
```
GET /api/v1/demo/evolution_replay

→ {
    "evolution_replay": [
      {"generation": 10, "top_fitness": 0.012, "population_size": 498},
      {"generation": 20, "top_fitness": 0.034, ...},
      ...
      {"generation": 50, "top_fitness": 0.089, ...}
    ]
  }
```

### Get Test DNA
```
GET /api/v1/test_dna/001   (or 002, 003)

→ {dna_id, name, bypass_gates, transactions, account_fixtures, ...}
```

## Blue Team Integration Endpoint (inbound)
Blue Team's `/app/integrations/red_team_client.py` calls:
```
POST /api/v1/red_team/receive_fraud_dna
Headers: X-API-Key: {BLUE_TEAM_API_KEY}
```
Payload format matches Blue Team's `red_team_client.py` expected structure.
