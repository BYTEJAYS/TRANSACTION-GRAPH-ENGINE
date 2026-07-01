"""
Readiness scorecard (Phase 10) — runs the key gates and prints a MEASURED score,
replacing the stale 55/100 from earlier notes.

    python -m scripts.readiness
"""
from __future__ import annotations

import time
import warnings

warnings.filterwarnings("ignore")


def _check(fn):
    try:
        return fn()
    except Exception as exc:
        return (0.0, f"error: {exc}")


def migration() -> tuple[float, str]:
    from migrations.run import check_roundtrip
    ok = check_roundtrip() == 0
    return (1.0 if ok else 0.0, "cases+users round-trip exact" if ok else "round-trip FAILED")


def detectors() -> tuple[float, str]:
    from blue_team_v2.core.pattern_engine.orchestrator import DETECTORS
    n = len(DETECTORS)
    return (min(1.0, n / 22), f"{n} detectors registered")


def ml() -> tuple[float, str]:
    from ml.platform.features import synthetic_dataset
    from ml.platform.ensemble import RiskEnsemble
    from ml.platform.training import _roc_auc
    import numpy as np
    X, y = synthetic_dataset(n_per_class=800)
    cut = int(len(X) * 0.8)
    ens = RiskEnsemble().fit(X[:cut], y[:cut])
    auc = _roc_auc(y[cut:], ens.predict_proba(X[cut:]))
    return (1.0 if auc >= 0.85 else auc / 0.85, f"ensemble ROC-AUC={auc:.3f} (gate 0.85)")


def evidence() -> tuple[float, str]:
    from case_management.store import store
    from evidence import packager
    cid = store.all()[0]["case_id"]
    p1 = packager.build_package(cid); p2 = packager.build_package(cid)
    ok = p1["integrity"]["sha256"] == p2["integrity"]["sha256"] and len(p1["sections"]) == 15
    return (1.0 if ok else 0.0, "deterministic 15-section package" if ok else "evidence non-deterministic")


def cache_speedup() -> tuple[float, str]:
    from core import cache
    cache.clear_local()

    @cache.cached(ttl=30, key_fn=lambda x: x)
    def slow(x):
        time.sleep(0.03); return x
    t0 = time.perf_counter(); slow(1); cold = time.perf_counter() - t0
    t0 = time.perf_counter(); slow(1); warm = time.perf_counter() - t0
    sp = cold / warm if warm else 999
    return (1.0 if sp >= 10 else sp / 10, f"cache {sp:.0f}x speedup (backend={cache.backend()})")


def api_routes() -> tuple[float, str]:
    import logging; logging.disable(logging.CRITICAL)
    import main
    v1 = len([r for r in main.app.routes if getattr(r, "path", "").startswith("/api/v1")])
    return (min(1.0, v1 / 8), f"{v1} /api/v1 routes mounted")


GATES = [
    ("Migration reversibility", 15, migration),
    ("Detection library", 15, detectors),
    ("ML engine", 15, ml),
    ("Evidence integrity", 15, evidence),
    ("Performance/cache", 10, cache_speedup),
    ("API surface", 10, api_routes),
]
# Live (Docker) dimensions — known pending, scored as partial credit.
LIVE_PENDING = [("Persistence live (Neo4j/PG/Redis)", 10),
                ("Workers + BELS anchoring live", 10)]


def main() -> int:
    print("TGIE — Redesign Readiness Scorecard\n" + "=" * 52)
    total = 0.0
    for name, weight, fn in GATES:
        frac, detail = _check(fn)
        pts = frac * weight
        total += pts
        mark = "✓" if frac >= 0.99 else ("~" if frac > 0 else "✗")
        print(f"  {mark} {name:<34} {pts:4.1f}/{weight:<3}  {detail}")
    for name, weight in LIVE_PENDING:
        print(f"  … {name:<34} {0:4.1f}/{weight:<3}  pending Docker (Wave 2)")
    print("=" * 52)
    print(f"  READINESS (no-Docker build): {total:.0f}/80  "
          f"(+20 reserved for live Docker verification)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
