# TGiE Adversarial Ecosystem

A coupled **Red Team ⇄ Blue Team** self-play system whose purpose is to make the
TGiE fraud detector progressively more robust by exposing it to sophisticated,
evolving graph attacks. The Red Team is not an enemy — it is an evolutionary
pressure mechanism that continuously discovers the detector's weaknesses and
generates hard examples to harden it.

> Separate from the legacy `red_team/` package, which enforces a hard isolation
> contract (no coupling to the detector). Here coupling is the point.

Design is grounded in a full white-box study of the defender:
**[`reports/BLUE_TEAM_WHITEBOX_REPORT.md`](reports/BLUE_TEAM_WHITEBOX_REPORT.md)**.

---

## Status

| Component | State |
|---|---|
| White-box Blue Team report | ✅ complete |
| Attack representation (objective, distortion) | ✅ |
| Blue Team oracle (operation-level coupling to V2) | ✅ |
| Attack agents (7, each mapped to a finding) | ✅ |
| Evolutionary Red Team (warm-started GA) | ✅ |
| Evaluation metrics (ASR, downgrade, distortion, detector-evasion) | ✅ |
| Attack memory DB + families + genealogy | ✅ |
| Curriculum ladder L1–L10 | ✅ (data + selector) |
| Self-play loop (Red→memory→harden→repeat) | ✅ loop; Blue hardener = proposal-only first strategy |
| RL/PPO Red Team | 🜂 spec + scaffold (MDP fully defined) |
| GraphGAN | 🜂 spec + scaffold (surrogate-distillation formulation chosen) |
| Visualization dashboards | ⬜ pending |
| V1 secondary target | ⬜ pending (D2: V2 primary) |

## Verified result (evolutionary Red Team vs real Blue Team V2)

```
cd backend && ../backend/.venv/bin/python -m adversarial --generations 25 --population 50
# (run from repo root with the backend venv)
```

| metric | value |
|---|---|
| Attack Success Rate (FRAUD→benign, objective intact) | **66.7%** (6/9 archetypes) |
| Mean detection downgrade | 0.56 |
| Mean distortion on success | 0.56 |
| Residual robust gate | **cashout / fan-in consolidation** blocks the other 3 |

**Headline finding:** `cross_component_split` appears in *every* winning attack
family — partitioning a scheme into disconnected components defeats the detector
because V2 analyses each component in isolation (report §B1). Chain schemes
(layering, mule) evade cheaply (distortion ~0.15); hub schemes need heavy
relay/partition (~1.0); cashout-anchored schemes resist (the sink's fan-in≥2 +
₹100k gate is the hardest in the system).

## Layout

```
adversarial/
  reports/            white-box Blue Team report
  common/             attack_graph (objective, distortion), oracle (Blue coupling)
  red_team/
    agents.py         feature_mimicry, amount_dither, temporal_spread,
                      relay_insertion, decoy_edges, sink_funnel, cross_component_split
    base.py           genome (Move list) + apply
    graph_generator.py base fraud graphs + objective derivation + component re-split
    evolutionary_engine/  warm-started GA over genomes
    rl_agent/         PPO spec + scaffold
    graph_gan/        GraphGAN spec + scaffold
  attack_memory/      JSONL store + technique families + genealogy + hard examples
  curriculum/         L1–L10 difficulty ladder
  self_play/          Blue⇄Red hardening loop + hardener strategies
  evaluation/         metrics
  experiments/        reproducible runs
```

## How it works

1. **Start from confirmed fraud.** Base graphs come from the Blue Team's own
   simulator — graphs it flags as FRAUD — so any drop to ≤ LOGGED is a real win.
2. **Objective preservation.** Each scheme has an `AttackObjective` (move ≈X value
   from sources to sinks). Transforms that break it are infeasible, not just
   low-scoring — this makes "minimal distortion subject to objective preserved"
   well-posed.
3. **Operation-level detection.** The oracle runs V2 on every component the attack
   produced (as the deployed system would) and aggregates. An attack succeeds
   only if *no* component is flagged — which is what surfaces the cross-component
   blindness instead of hiding it.
4. **Search.** A warm-started genetic algorithm evolves attack genomes (ordered
   agent+intensity moves); fitness = evasion + stealth − distortion − complexity.
   PPO (sequential) and GraphGAN (generator/discriminator) plug into the same
   oracle + agents.
5. **Self-play.** Successful attacks → attack memory → Blue Team hardening →
   re-measure → climb the curriculum.

## Next steps

- Wire the Blue hardener to a V2 config object and measure **robustness gain**
  (ASR before/after) + false-positive cost on the benign corpus.
- **Fix the eval harness before trusting gains:** strip the Isolation-Forest
  label leak (report §B5) and add an out-of-typology holdout.
- Build the PPO trainer (MDP in `red_team/rl_agent/spec.py`) and the
  surrogate-distillation GraphGAN (`red_team/graph_gan/spec.py`).
- Add a `cashout`-specific consolidation agent to probe the last robust gate.
