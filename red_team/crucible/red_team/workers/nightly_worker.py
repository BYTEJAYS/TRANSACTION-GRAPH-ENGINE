from __future__ import annotations
"""
Celery beat schedule — nightly jobs.

01:00 → run_nightly_mutation    (10k PBT generations, enqueue top 10)
02:00 → run_prophecy_matching   (match predictions vs confirmed frauds)
03:00 → apply_operator_decay    (decay old win counts, update weights)
"""
from celery import Celery
from celery.schedules import crontab
import logging

app = Celery("red_team", broker="redis://localhost:6379/0")
logger = logging.getLogger(__name__)


app.conf.beat_schedule = {
    "nightly-mutation": {
        "task": "workers.run_nightly_mutation",
        "schedule": crontab(hour=1, minute=0),
    },
    "prophecy-matching": {
        "task": "workers.run_prophecy_matching",
        "schedule": crontab(hour=2, minute=0),
    },
    "operator-decay": {
        "task": "workers.apply_operator_decay",
        "schedule": crontab(hour=3, minute=0),
    },
}


@app.task(name="workers.run_prophecy_matching")
def run_prophecy_matching() -> dict:
    from red_team.prophecy.ledger import ledger
    result = ledger.nightly_matching_job()
    logger.info("Prophecy matching complete", **result)
    return result


@app.task(name="workers.apply_operator_decay")
def apply_operator_decay() -> None:
    from red_team.learning.operator_weights import operator_tracker
    operator_tracker.apply_decay()
    logger.info("Operator decay applied")
