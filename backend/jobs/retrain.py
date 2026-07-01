"""ML retraining job — wraps the Phase 5 training pipeline so drift can trigger a
retrain via the task abstraction (inline now, Celery in prod)."""
from __future__ import annotations

from core.tasks import task


@task("retrain_models")
def retrain_models(version: str = "v_auto") -> dict:
    from ml.platform.training import train_and_register
    return train_and_register(version=version)
