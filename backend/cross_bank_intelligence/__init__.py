"""
Cross-Bank Intelligence — a PLUG-IN enrichment layer for TGIE.

Answers "has this entity behaved suspiciously ELSEWHERE?" by resolving accounts to
real-world entities via shared fingerprints (device / phone / PAN / UPI / KYC name /
merchant) and correlating against a cross-bank risk registry (Kafka-fed in
production, seeded in the demo).

CONTRACT — this module is metadata-only:
  * It reads a read-only component snapshot + the per-session entity_context.
  * It returns a CrossBankReport (intelligence signals) and per-account metadata.
  * It NEVER mutates the graph, creates/removes nodes or edges, changes positions,
    layout, colours or physics. The graph engine does not know it exists.

Integration:
  * risk_engine.assess() consults it as ONE capped factor (`cross_bank`, weight 10) —
    it contributes to the Blue Team score but can never dominate it.
  * api/routes.py attaches the report to each verdict as `v["cross_bank"]`.
  * Designed for async/Celery offload (see analyze_component_async) so it NEVER
    blocks graph rendering.
"""
from .intelligence_engine import analyze_component
from .risk_registry import CrossBankRiskRegistry, get_registry
from .schemas import KNOWN_BANKS, CROSS_BANK_PATTERNS, CrossBankReport, empty_report

__all__ = [
    "analyze_component", "analyze_component_async",
    "CrossBankRiskRegistry", "get_registry",
    "KNOWN_BANKS", "CROSS_BANK_PATTERNS", "CrossBankReport", "empty_report",
]


def analyze_component_async(component, entity_context=None, on_done=None):
    """Celery/threadpool seam: cross-bank scoring can be expensive at scale, so it is
    designed to run OFF the graph-render path. Today it runs inline (cheap: O(nodes));
    swap the body for `tasks.enqueue(...)` to offload without changing callers. The
    graph renders immediately regardless — this only enriches the verdict afterward."""
    report = analyze_component(component, entity_context)
    if on_done:
        on_done(report)
    return report
