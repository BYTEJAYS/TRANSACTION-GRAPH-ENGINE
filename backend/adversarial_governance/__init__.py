"""
Adversarial governance — the human-in-the-loop training-queue + audit layer that
sits BETWEEN the Red Team and the Blue Team's knowledge base.

Nothing the Red Team produces enters the Blue Team's training corpus automatically.
A missed evasion is enqueued for investigator review; only an explicit "learn"
decision adds it to the Blue Knowledge Base, deduped against what's already there,
and every decision is written to an immutable audit trail.
"""
from .store import store, GovernanceStore

__all__ = ["store", "GovernanceStore"]
