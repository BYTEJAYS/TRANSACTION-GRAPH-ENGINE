# datasets/

Sample and scenario data for the TGIE ecosystem.

| Item | Location | Purpose |
|---|---|---|
| `sample_transactions.json` | here | Canonical sample feed (mirrors the frontend unified sim) |
| Red Team scenarios | `../red_team/engine/datasets/` | Curated fraud archetypes (see below) |
| Adversarial corpora | `../red_team/adversarial/_data/` (gitignored, regenerable) | Attack memory / benign corpora |
| BLING training data | `../blue_team/bling/ml/` | IsolationForest training + BAF/Kaggle augmentation bridges |

## Red Team scenario archetypes (`red_team/engine/datasets/`)

- `A01-multi-stage-laundering`
- `A02-mule-network` (+ `-evo` evolved variant)
- `A03-hybrid-operation`
- `B01-single-suspicious-transfer`
- `B02-account-takeover-burst`
- plus `analytics.json` / `ANALYTICS.md`

These are the labelled graphs the Blue Team is evaluated against and the Red Team evolves from.

> **Note:** the unified live feed is generated, not stored — see
> `frontend/src/data/sampleDataset.ts` and the backend `simulator/`.
