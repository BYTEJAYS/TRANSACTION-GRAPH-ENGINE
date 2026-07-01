# backups/

Snapshot location for any destructive operation. **Policy: never delete or overwrite
without backing up here first.**

## Assembly note (2026-06-24)

This `TGIE/` workspace was built by **clean, additive copies** from four source
repositories. **No destructive cleanup was performed during assembly**, so no backups were
required:

- The four source repos (`~/transaction-graph-intelligence`, `~/bling-blue-team`,
  `~/blue team v2`, `~/red team union bank`) are themselves the authoritative backup —
  they were not modified or deleted.
- Duplicate/dead-code **candidates** (e.g. orphaned `RightPanel.tsx`, dead header JSX,
  duplicated verdict schema, the untrained GNN) are **documented, not removed** — see
  `../docs/production_readiness_report.md` and `../docs/repository_analysis.md` §7.

## If you run cleanup later

```bash
# snapshot before any destructive edit
tar czf backups/pre-cleanup-$(date +%Y%m%d-%H%M%S).tar.gz <target-path>
```
Then proceed. Keep at least the most recent two snapshots.
