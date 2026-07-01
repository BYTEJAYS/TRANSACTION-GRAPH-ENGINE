# Red Team — Future Roadmap

The current release (`v0.1.0`) establishes the standalone foundation: synthetic
data engine, simulation engine, scenario library, research + evolution engines,
dataset platform, and analytics. The following are candidate directions for
later TGIE versions. **All remain bound by the isolation and ethics controls in
[`ETHICS_AND_SAFETY.md`](ETHICS_AND_SAFETY.md).**

## Near term

- **Richer behavioural modelling** — per-identity temporal patterns (salary
  cycles, festival spikes, dormancy) for more realistic baselines.
- **More topologies** — invoice/trade-based laundering, bust-out fraud,
  card-not-present rings, first-party fraud.
- **Configurable noise profiles** — pluggable benign-activity distributions so
  datasets can mimic different institutions' baselines.
- **Dataset versioning** — content-hashed dataset manifests for reproducible
  research citations.

## Medium term

- **Multi-objective evolution** — Pareto fronts over realism, diversity, and
  scenario novelty instead of a single weighted fitness.
- **Scenario DSL** — a small declarative language for composing scenarios from
  reusable topology primitives.
- **Interactive analytics dashboard** — a read-only web view of the analytics
  JSON (served independently of the Blue Team UI).
- **Benchmark harness** — a standardised, *offline* evaluation protocol so
  researchers can score any detector against the corpus without coupling the
  two systems at runtime.

## Long term (explicitly out of scope today)

- **Optional, governed Red/Blue evaluation** — a future TGIE version *may*
  introduce a carefully governed, offline evaluation bridge. If it ever does, it
  must be: opt-in, audited, batch/offline (no live feedback loop), and incapable
  of training the Red Team to evade a specific deployed detector. Until such a
  design is reviewed and approved, the systems stay fully isolated.

## Non-goals (permanent)

- Real-world fraud facilitation of any kind.
- Detection-evasion tooling targeting a real deployed model.
- Any use of real customer or transaction data.
