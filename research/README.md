# research/

Pointers to the research-grade artifacts in the ecosystem. The work itself lives with the
code it analyses (kept there so it stays runnable and version-coupled).

| Artifact | Location | What |
|---|---|---|
| Blue Team white-box report | `../red_team/adversarial/reports/BLUE_TEAM_WHITEBOX_REPORT.md` | Code-grounded analysis of V2's detectors, gates, blind spots |
| Red Team audit | `../red_team/adversarial/reports/RED_TEAM_AUDIT.md` | SOTA-gap audit of the adversarial engine |
| Adversarial engagement (§16–§23) | `../red_team/adversarial/` | Full closed Red⇄Blue arc: provenance → behavioural → coordination → relationship → maturity |
| Distilled audits | `../docs/blue_team_audit.md`, `../docs/red_team_audit.md` | Scorecards derived from the above |

## Research narrative (one paragraph)

The engagement began by naming V2's component-isolation weakness (B1) and ended proving it
adversarially: every attack found the defender's next missing **context** capability, every
counter supplied it, and the arms race terminated not in a perfect detector but in
**economics** (relationship-maturity makes laundering self-defeating). The transferable
result: a context-free, component-isolated snapshot detector is evadable on every axis;
each axis is closed by injecting **memory/context** (identity, behaviour, linkage,
relationship, temporal depth).

## Open research threads

- Black-box / transfer evaluation (white-box only today).
- V1 as a first-class target (V2-only today).
- True attack genealogy / lineage (`parent_ids` unpopulated).
- World-model-scaled QD so heavy agents don't time out.
- Recalibration of every 0% FP claim on real account-history data.
