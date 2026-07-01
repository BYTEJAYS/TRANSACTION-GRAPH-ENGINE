# Architecture
# Generated and maintained by Claude. Never edited manually.
# Updated whenever the system design changes.

## System Overview

CRUCIBLE is a fraud adversarial engine that evolves synthetic fraud patterns using Population-Based Training (PBT) and self-learns over time via a Prophecy Ledger.

## Core Components

### FraudGenome (`core/genome.py`)
Complete representation of a fraud pattern:
- `lineage_id: str` — MO family name (e.g. "mule_ring", "festival_fraud")
- `genome_id: str` — UUID (auto-generated default factory)
- `topology: TopologyGene` — type: fan_in | fan_out | chain | bipartite | layered (NOT "cycle" unless you want the cycle gate to fire)
- `timing: TimingGene` — `festival_timing: Optional[dict]` (not str), `dormancy_periods: List[dict]`
- `channels: ChannelsGene` — `mix: Dict[str, float]` (not list — channel name → weight)
- `mutation_history: List[str]` — operator names applied (**NOT** `lineage`)
- `parent_genome_id: Optional[str]` — (**NOT** `parent_id`)
- `flags: List[str]` — reviewer signals

**CRITICAL FIELD NAMES**: `mutation_history` (not `lineage`), `parent_genome_id` (not `parent_id`), `channels.mix` is `Dict[str, float]` not list.

### PBT Engine (`mutation/engine.py`)
- Population: 500 genomes
- Per generation: evaluate → exploit top 20% → explore 80% → diversity cull
- Every 500 gens: update operator weights from prophecy boosts
- Diversity floor: novelty_score < 0.1 → drop genome
- Operator sampling: weighted random from ALL_OPERATORS (25 total)

### Fitness Function (`mutation/fitness.py`)
```
fitness = ensemble_disagreement × realism × novelty
```
Zero if: Blue Team mean_score > 0.5, realism < 0.5, novelty < 0.1

### Mock Blue Team (`sandbox/blue_clone.py`)
Exact replica of detection pipeline (offline, no DB/Redis/Neo4j):
- Tier 1: velocity spike, night, threshold proximity, new account, amount spike
- Tier 2: 5 gates (cycle, abandoned_sink, bipartite, cash_mule_sink, merchant_terminal)
- Tier 3: XGBoost feature estimate
- Indian context adjuster (festival 0.70×, merchant batch 0.80×)
- Returns [champion, challenger1(0.9×), challenger2(1.1×), challenger3(0.95×)]

### Critics
- `realism.py`: `hard_validate()` → rail_constraints; `soft_score()` → economic rationality
- `novelty.py`: Bloom filter + FAISS 256-d cosine (thresholds: 0.97 = exact, 0.85 = near)

### Prophecy Ledger (`prophecy/ledger.py`)
Nightly at 02:00: match predictions vs confirmed frauds (cosine ≥ 0.85 = HIT)
Hit rate tiers: >20%→2.0×, 10-20%→1.5×, 5-10%→1.0×, <5%→0.3×

### Human Gate (`human_gate/`)
Queue sorted: (₹_at_risk / 100K) × ease_mult × scalability_mult
Router output: new_gate | bounded_retrain | human_decision

## Operator Taxonomy (25 operators)

Standard (20): topology(5), timing(4), amounts(3), channels(2), accounts(3), structural(3)

Advanced (5) — from real Indian fraud intelligence:
- `mule_hub_creator`: 20-46 source hub (Nizamabad ₹152Cr pattern)
- `cycle_extender`: chain topology 4-hop (avoids cycle gate type flag)
- `threshold_fragmenter`: ₹49K chunks below CTR
- `ghost_node_injector`: cash gap (ATM withdrawal + redeposit 200-700km)
- `dormant_activator`: 200+ day aging then burst

## Gate Bypass Reference
| Gate | Threshold | Bypass |
|------|-----------|--------|
| bipartite_core | senders ≥ 5 AND density > 0.7 | ≤4 senders OR merchant flag |
| cash_mule_sink | age ≤ 180d AND inflow ≥ ₹50K | accounts 200+ days old |
| cycle gate | topology.type == "cycle" | use chain/layered type |
| merchant_terminal | terminal_id != None | never set terminal_id |
| Indian adjuster | festival + amount < ₹5K | Diwali + micro-amounts |

## Thread Safety
PBT engine is single-threaded per Celery worker. NoveltyCritic NOT thread-safe.

## Integration
- `BLUE_TEAM_URL` unset → MockBlueTeam (default)
- `BLUE_TEAM_URL` set → RealBlueTeam (POST /api/v1/score, X-Sandbox: true)
