"""
TGIE Red Team — Adversarial Fraud Simulation Platform.

A self-contained research environment for generating synthetic fraud
scenarios, producing research datasets, and evolving simulation complexity.

ISOLATION CONTRACT
------------------
This package is intentionally isolated from the Blue Team (fraud detection)
system. It MUST NOT import from, write to, or otherwise communicate with any
Blue Team module. See ``red_team.core.safety`` for the enforced guardrails and
``documentation/ETHICS_AND_SAFETY.md`` for the rationale.

Mission: *Discover weaknesses before criminals do* — using only synthetic,
explainable, reproducible, and auditable simulations.
"""

__version__ = "0.1.0"
__team__ = "red"
__isolation__ = "standalone"  # never couple to blue_team

from red_team.core.safety import assert_isolation

# Fail fast at import time if isolation has been violated.
assert_isolation()
