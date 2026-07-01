"""
Cross-component coordination signal — the counter to the conduit_split mule mesh (§19).

§18 showed the mule mesh defeats the entire PER-COMPONENT defense stack: it fragments one
laundering ring into many small hub-less consumer components, each of which — in isolation —
is a handful of verified accounts moving in-profile money, indistinguishable from benign.
Provenance, the behavioural detector and V2 itself all judge one component at a time, so none
can see that fifty such components are a single coordinated network. That blindness is B1,
the very first finding of the white-box report.

This detector is the missing capability: it scores an OPERATION — the set of components a
cross-session linkage (shared device / funding source / timing burst) has tied together —
rather than a component. Across that linked set the mesh has a signature no legitimate
operation has:

  * no HUB — a legitimate fan-in/fan-out (payroll, merchant, supplier run) is anchored by a
    high-baseline business account; the mesh is deliberately hub-less (degree ≤3, all
    consumer accounts) so its illicit value never concentrates anywhere visible;
  * many CONSUMER identities — dozens of distinct low-baseline verified accounts carrying
    value, which only happens when an attacker has seized a crowd of them;
  * FRAGMENTED — the same illicit flow is split across many disconnected components.

A legitimate operation is none of these at once: it is one component, or it has a hub, or it
involves only a few accounts. The mesh is all three. The detector flags an operation that is
hub-less AND consumer-heavy AND fragmented, and raises its risk toward a conduit floor.

Honest framing (the whole point of the §19 round): this signal is only available to a Blue
Team that can LINK the components into an operation. The deployed V2 cannot — it is
per-component by construction — so this detector quantifies exactly what the B1 blind spot
costs and what closing it requires: cross-session correlation, not another per-account score.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CoordinationScorer:
    registry: object                      # BehavioralRegistry (per-account baselines)
    hub_baseline: float = 300_000.0       # an account this established can anchor a legit fan
    min_consumer_accounts: int = 15       # distinct seized consumer identities to call it a crowd
    min_fragments: int = 4                # how split the flow must be
    conduit_risk: float = 0.9

    def _flow_accounts(self, component: dict) -> set[str]:
        ids: set[str] = set()
        for e in component.get("edges", []):
            if float(e.get("amount", 0) or 0) > 0:
                ids.add(str(e.get("source", "")))
                ids.add(str(e.get("target", "")))
        ids.discard("")
        return ids

    def operation_risk(self, components: list[dict]) -> float:
        """Coordination risk in [0,1] over a LINKED set of components."""
        fragments = [c for c in components if self._flow_accounts(c)]
        if len(fragments) < self.min_fragments:
            return 0.0                          # not fragmented → provenance/behavioural suffice

        consumers: set[str] = set()
        for c in fragments:
            for acct in self._flow_accounts(c):
                base = self.registry.baseline_throughput(acct)
                if base <= 0:
                    continue                    # unverified → provenance's job
                if base >= self.hub_baseline:
                    return 0.0                  # a high-baseline hub anchors it → legitimate fan
                consumers.add(acct)             # verified consumer-grade identity carrying value

        if len(consumers) < self.min_consumer_accounts:
            return 0.0                          # too few identities to be a seized crowd

        # hub-less, consumer-heavy, fragmented → coordinated mule network. Scale the risk by
        # how far past the crowd threshold it is (more seized identities = more certain).
        over = len(consumers) / self.min_consumer_accounts
        return max(0.0, min(1.0, self.conduit_risk * min(1.0, 0.5 + 0.5 * over)))
