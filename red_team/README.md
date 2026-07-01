# Red Team

Offensive / adversarial systems that harden the Blue Team by finding evasions.

| Subfolder | What | Status |
|---|---|---|
| `adversarial/` | Red⇄Blue self-play research program — GA, MAP-Elites, PPO, GraphGAN, 11 attack agents, 6 context-signal counters | Primary; full §16–§23 engagement done |
| `engine/` | In-repo isolated red team with curated scenario datasets (A01–A03 laundering/mule/hybrid, B01–B02) | Isolated (no blue_team coupling) |
| `crucible/` | CRUCIBLE evolutionary fraud-genome engine + human gate + prophecy/learning | Standalone (Union Bank) |

## adversarial/ — the research engine

Attacks the **real V2 engine** via `BlueTeamOracle`. Closed loops:
- `python -m adversarial --generations N --population N` — GA campaign
- `python -m adversarial.qd --evaluations N` — MAP-Elites quality-diversity
- `python -m adversarial.rl` — PPO RL agent
- `python -m adversarial.self_play.final_stack` — capstone: full Blue stack vs full adversary

Reports live in `adversarial/reports/`:
- `BLUE_TEAM_WHITEBOX_REPORT.md` — the white-box analysis underpinning `../docs/blue_team_audit.md`
- `RED_TEAM_AUDIT.md` — the SOTA-gap audit underpinning `../docs/red_team_audit.md`

## Key findings (see `../docs/red_team_audit.md`)

- Permissive ASR ~0.56–0.67; **strict (on-graph) ASR = 0.0** — every win is partition-dependent (B1).
- The arms race terminates in **economics** — relationship-maturity prices the attacker out.
- 6 composed context signals drive a full adversary to **0.00 ASR @ 0% FP** on honest corpora.

## crucible/ — Union Bank analogue

Nightly genome evolution → human review gate → prophecy/learning when predicted patterns
appear in real fraud. Subsystems: `core, mutation, critics, learning, prophecy, human_gate,
workers, db, api, sandbox`.

## Safety

- `engine/` enforces an import-time isolation contract (`assert_isolation()`).
- The frontend red-team panel (`../backend/api/redteam.py`) is **localhost-gated** — never
  exposed on a public deploy.
