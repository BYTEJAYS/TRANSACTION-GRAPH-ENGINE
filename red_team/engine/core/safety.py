"""
Safety and ethical guardrails for the Red Team platform.

Two responsibilities:

1. **Isolation enforcement** — programmatically guarantee the Red Team never
   couples to the Blue Team. ``assert_isolation()`` runs at package import and
   raises if the contract is violated.

2. **Synthetic provenance** — helpers that stamp and verify the
   ``SYNTHETIC_WATERMARK`` on every artefact, so generated data can always be
   distinguished from real-world data in an audit.

This module deliberately contains no offensive capability. It does not, and
must not, produce real-world-actionable instructions. Everything the platform
emits is structured synthetic data for controlled research.
"""

from __future__ import annotations

import sys
from typing import Any, Iterable

# Modules the Red Team is forbidden from importing. Coupling to any of these
# would break the isolation contract described in the package docstring.
FORBIDDEN_IMPORT_PREFIXES = (
    "blue_team",
    "backend.blue_team",
    "anomaly_detection",
    "graph_engine",
)


class IsolationViolation(RuntimeError):
    """Raised when the Red Team has coupled to a forbidden subsystem."""


class SafetyViolation(RuntimeError):
    """Raised when a synthetic-provenance invariant is broken."""


def assert_isolation() -> None:
    """
    Verify that no forbidden Blue Team / detection module has been imported
    into the running process *by the Red Team*. This is a defence-in-depth
    check; the primary guarantee is that Red Team code simply never references
    those modules.
    """
    # We only care about modules imported *under* the red_team namespace having
    # pulled in a forbidden dependency. We approximate this by checking that no
    # red_team module's globals reference a forbidden module object.
    for mod_name, module in list(sys.modules.items()):
        if not mod_name.startswith("red_team"):
            continue
        for prefix in FORBIDDEN_IMPORT_PREFIXES:
            referenced = getattr(module, prefix.split(".")[-1], None)
            if referenced is not None and getattr(referenced, "__name__", "").startswith(prefix):
                raise IsolationViolation(
                    f"Red Team module '{mod_name}' references forbidden subsystem "
                    f"'{prefix}'. Red Team must remain fully isolated from Blue Team."
                )


def stamp(obj: Any) -> Any:
    """
    Ensure an artefact carries the synthetic watermark. Accepts any object that
    exposes a ``provenance`` attribute (all Red Team models do).
    """
    prov = getattr(obj, "provenance", None)
    if prov is None:
        raise SafetyViolation(f"{type(obj).__name__} has no provenance stamp.")
    if not getattr(prov, "is_synthetic", False):
        raise SafetyViolation(f"{type(obj).__name__} is not marked synthetic.")
    return obj


def verify_all_synthetic(artefacts: Iterable[Any]) -> bool:
    """Audit helper: assert every artefact in a batch is watermarked synthetic."""
    for a in artefacts:
        stamp(a)
    return True
