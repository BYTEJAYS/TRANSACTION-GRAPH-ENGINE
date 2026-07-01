# Red Team — Ethics & Safety Controls

The Red Team exists to **strengthen** financial fraud defences by studying how
fraud *looks*, in a controlled environment, using only synthetic data. It is a
research instrument, not an attack tool.

## Non-negotiable invariants

The Red Team **must never**:

- enable, instruct, or facilitate real-world fraud;
- generate actionable attack procedures, credentials, or document-forgery steps;
- interact with any real financial system or payment network;
- use, ingest, or derive from any real customer information;
- access external banking infrastructure.

Everything it emits is **synthetic, explainable, measurable, reproducible, and
auditable**.

## Enforced controls

| Control | Where | What it does |
|---------|-------|--------------|
| Isolation assertion | `core/safety.assert_isolation()` | Runs at package import and at CLI start; raises `IsolationViolation` if a forbidden Blue Team / detection module has been coupled in. |
| Forbidden-import list | `core/safety.FORBIDDEN_IMPORT_PREFIXES` | `blue_team`, `backend.blue_team`, `anomaly_detection`, `graph_engine`. |
| Synthetic watermark | `core/models.Provenance` (`TGIE-RED-TEAM-SYNTHETIC`) | Stamped on every identity, account, transaction, and dataset; written into every exported file. |
| Provenance audit | `core/safety.verify_all_synthetic()` | The simulator verifies every produced artefact is watermarked before returning. |
| Config isolation | `core/config.RedTeamConfig` | Reads only `REDTEAM_*` env vars; `allow_blue_team_integration` is hard-defaulted `False`. |

## Isolation from the Blue Team

At this stage of TGIE, Red Team and Blue Team are **completely separate
systems**. There is intentionally:

- no integration, no automated feedback loop, no retraining pipeline;
- no shared model training, databases, or cross-system APIs;
- no exchange of datasets, model weights, or intelligence;
- no adversarial self-learning loop involving the Blue Team.

The realism/diversity fitness used by the research and evolution engines is
computed **only** from the synthetic data itself — never from a detector's
response. The objective is dataset richness, **not** detector evasion.

## Why this is safe

The platform's output is the same *class* of artefact a bank's own data-science
team already generates for model training: labelled synthetic transaction
graphs. It contains no real identities and no operational tradecraft. Modelling
the *shape* of fraud (graph topology, timing, amount dispersion) is what enables
defenders to evaluate detection coverage — which is the entire purpose.

## Reporting concerns

If any future change appears to weaken these controls — for example, an import
of a Blue Team module, removal of the watermark, or a fitness function that
queries a detector — treat it as a defect and revert it. The isolation assertion
is designed to fail loudly rather than silently degrade.
