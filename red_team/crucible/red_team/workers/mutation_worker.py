from __future__ import annotations
"""
Celery worker — nightly mutation run.
Triggered by Celery beat at 01:00 (before prophecy matching at 02:00).
Loads seed bank, builds population, runs PBT for 10k generations,
enqueues top 10 genomes to human gate queue.
"""
import logging

from celery import Celery

app = Celery("red_team", broker="redis://localhost:6379/0")
logger = logging.getLogger(__name__)


@app.task(name="workers.run_nightly_mutation")
def run_nightly_mutation() -> dict:
    from red_team.demo.seed_data import SEED_GENOMES
    from red_team.human_gate.queue import human_gate_queue
    from red_team.learning.seed_enrichment import seed_bank
    from red_team.mutation.engine import MutationEngine, GENERATIONS_PER_NIGHT
    from red_team.prophecy.ledger import ledger
    from red_team.sandbox.blue_clone import get_blue_team

    blue_team = get_blue_team()

    # Build starting population from seed bank (includes missed-fraud HIGH-priority seeds)
    if len(seed_bank) > 0:
        initial_pop = seed_bank.get_initial_population(size=500)
    else:
        initial_pop = list(SEED_GENOMES)

    engine = MutationEngine(
        blue_team=blue_team,
        seed_genomes=initial_pop,
        ledger=ledger,
        generations=GENERATIONS_PER_NIGHT,
    )

    result = engine.run()
    logger.info("Nightly mutation complete", **result)

    # Enqueue top genomes for human review
    top = engine.top_genomes(n=10)
    for genome, fitness in top:
        human_gate_queue.enqueue(genome, fitness)

    return result
