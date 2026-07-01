"""
Counterparty-relationship signal — the counter to corporate-account seizure (§20).

§17-C / §19-C left one residual standing: an attacker who seizes a high-baseline CORPORATE
account routes the laundering through it and through other seized corporate accounts. That
beats every signal built so far — provenance (the accounts are KYC-verified), behavioural
(a corporate baseline absorbs the volume) and coordination (there is a real high-baseline
hub, and the flow need not fragment). All of those ask *about the accounts*. The signal they
miss asks *about the relationship between them*.

A bank does not only know who its customers are and how they behave; it knows **who they
normally transact with**. A real business pays its own registered suppliers and employees —
a stable counterparty circle built over years. A seized business account betrays itself the
moment it starts moving money to verified accounts it has **no history with**: the laundering
ring is a set of compromised identities with no genuine commercial relationship to each other.

This module models that as relationship *circles* — a customer's established counterparty set,
held in the bank's records and unforgeable by the attacker (it can route a payment, but it
cannot retro-fit years of shared history). `RelationshipScorer` flags value moving between two
VERIFIED accounts that are not in each other's circle (novel high-value counterparties),
leaving unverified value to provenance and within-circle value alone.

Honest residual (the next probe): an attacker patient enough to first build genuine history
between the accounts it controls — seasoning mule relationships with months of small legit-
looking traffic before the laundering run — erodes this signal, at a large time cost. And, as
with every layer, counterparty novelty has real false positives in production (legitimate
first-time business payments are common); here benign operations are circle-coherent by
construction, so that FP must be re-measured on real history (the §13 discipline).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field


# a relationship circle is a business ecosystem: a corporate anchor, SME suppliers, a
# merchant, its salaried employees, and household/retail customers — the accounts that
# genuinely transact with each other. Sized so the benign generators can draw a whole
# operation (a full payroll, a full merchant collection) WITHIN one circle, so every legit
# counterparty pair is an established relationship.
_CIRCLE_RECIPE = [("corporate", 2), ("sme", 6), ("merchant", 2),
                  ("salaried", 26), ("household", 45), ("retail", 30)]


def build_relationship_circles(profiles, seed: int = 31) -> dict[str, int]:
    """Partition the KYC base into business-ecosystem circles. Returns account → circle id.

    Only COMPLETE circles (every segment quota met) are formed; leftover accounts have no
    established relationships (circle -1) — related to no one, exactly like a freshly seized
    identity.
    """
    rng = random.Random(seed)
    by_seg: dict[str, list[str]] = {}
    for cid, p in profiles.items():
        by_seg.setdefault(p.segment, []).append(cid)
    for seg in by_seg:
        rng.shuffle(by_seg[seg])

    cursors = {seg: 0 for seg in by_seg}
    circle_of: dict[str, int] = {}
    circle = 0
    while True:
        # only form a circle if every segment still has its full quota remaining
        if any(cursors[seg] + k > len(by_seg.get(seg, [])) for seg, k in _CIRCLE_RECIPE):
            break
        for seg, k in _CIRCLE_RECIPE:
            take = by_seg[seg][cursors[seg]:cursors[seg] + k]
            cursors[seg] += k
            for m in take:
                circle_of[m] = circle
        circle += 1
    return circle_of


@dataclass
class LearnedRelationship:
    """A relationship the bank inferred from OBSERVED traffic — not a god-given circle but
    history it accumulated. This is what a seasoning attacker can manufacture (and what a
    maturity-weighted detector discounts when it is recent / shallow / low-value)."""
    count: int            # how many prior transactions the bank has seen on this pair
    total_value: float    # cumulative value of that history
    age_days: float       # how long ago the relationship first appeared (older = more genuine)

    def matured_capacity(self) -> float:
        """How much value this relationship can legitimately vouch for. A relationship that has
        only ever carried ₹5k over two weeks cannot make a ₹5L transfer look established."""
        age_f = min(1.0, self.age_days / 365.0)
        depth_f = min(1.0, self.count / 10.0)
        return self.total_value * age_f * depth_f


@dataclass
class RelationshipRegistry:
    """The bank's record of who normally transacts with whom: established circles (deep, aged,
    genuine) plus relationships LEARNED from observed traffic (which seasoning can inject)."""
    circle_of: dict[str, int]
    profiles: dict = field(default_factory=dict)   # for verified() lookups
    learned: dict = field(default_factory=dict)    # frozenset({a,b}) -> LearnedRelationship

    def verified(self, account: object) -> bool:
        return str(account) in self.profiles

    def _circle_related(self, a: str, b: str) -> bool:
        ca = self.circle_of.get(a, -1)
        cb = self.circle_of.get(b, -1)
        return ca != -1 and ca == cb

    def related(self, a: object, b: object) -> bool:
        """Binary relationship (the §20 view): an established circle OR any learned history."""
        a, b = str(a), str(b)
        return self._circle_related(a, b) or frozenset((a, b)) in self.learned

    def relationship_capacity(self, a: object, b: object) -> float:
        """How much value the relationship can vouch for (the §21 maturity view). Genuine circle
        relationships are aged and deep → effectively unlimited; learned ones are bounded by the
        history actually observed, so cheap seasoning vouches for almost nothing."""
        a, b = str(a), str(b)
        if self._circle_related(a, b):
            return float("inf")
        lr = self.learned.get(frozenset((a, b)))
        return lr.matured_capacity() if lr else 0.0

    def members(self, circle: int) -> list[str]:
        return [a for a, c in self.circle_of.items() if c == circle]

    def num_circles(self) -> int:
        return (max(self.circle_of.values()) + 1) if self.circle_of else 0


def season(registry: RelationshipRegistry, cohort: list[str], count: int,
           value_per_pair: float, age_days: float, seed: int = 0) -> int:
    """Model an attacker SEASONING its mule cohort: register learned relationships between the
    accounts it controls, as if it had run prior (small, legit-looking) traffic among them. Seasons
    the complete graph on the cohort so whatever pairs the laundering later uses are already
    'related'. Returns the number of relationships injected (the attacker's seasoning footprint)."""
    n = 0
    for i in range(len(cohort)):
        for j in range(i + 1, len(cohort)):
            registry.learned[frozenset((cohort[i], cohort[j]))] = LearnedRelationship(
                count=count, total_value=value_per_pair, age_days=age_days)
            n += 1
    return n


class RelationshipScorer:
    """Floors the risk of value moving between verified accounts with no shared history."""

    def __init__(self, registry: RelationshipRegistry,
                 novel_risk: float = 0.9, min_value_share: float = 0.10,
                 maturity: bool = False) -> None:
        self.reg = registry
        self.novel_risk = novel_risk
        self.min_value_share = min_value_share
        # maturity=False → §20 binary view (any shared history counts, so seasoning defeats it).
        # maturity=True  → §21 view: a relationship only vouches for value up to the history it
        # actually has, so cheap/recent seasoning cannot cover a large laundering flow.
        self.maturity = maturity

    def novel_value_ratio(self, component: dict) -> float:
        """Value-weighted fraction of VERIFIED↔VERIFIED flow not backed by a real relationship.

        Unverified value is provenance's job and is excluded here. In binary mode any related
        pair is trusted; in maturity mode flow is trusted only up to each relationship's
        matured capacity, and the EXCESS counts as novel.
        """
        if not self.maturity:
            total_verified = 0.0
            novel = 0.0
            for e in component.get("edges", []):
                amt = float(e.get("amount", 0) or 0)
                if amt <= 0:
                    continue
                s, t = e.get("source"), e.get("target")
                if not (self.reg.verified(s) and self.reg.verified(t)):
                    continue
                total_verified += amt
                if not self.reg.related(s, t):
                    novel += amt
            return (novel / total_verified) if total_verified > 0 else 0.0

        # maturity mode: aggregate verified flow per counterparty pair, then charge each pair
        # against the value its history can vouch for.
        flows: dict[frozenset, float] = {}
        total_verified = 0.0
        for e in component.get("edges", []):
            amt = float(e.get("amount", 0) or 0)
            if amt <= 0:
                continue
            s, t = str(e.get("source")), str(e.get("target"))
            if not (self.reg.verified(s) and self.reg.verified(t)) or s == t:
                continue
            total_verified += amt
            pair = frozenset((s, t))
            flows[pair] = flows.get(pair, 0.0) + amt
        novel = 0.0
        for pair, flow in flows.items():
            a, b = tuple(pair)
            novel += max(0.0, flow - self.reg.relationship_capacity(a, b))
        return (novel / total_verified) if total_verified > 0 else 0.0

    def adjust(self, component: dict, native_risk: float) -> float:
        """Raise risk on novel verified-counterparty value; never lower it."""
        ratio = self.novel_value_ratio(component)
        if ratio < self.min_value_share:
            return native_risk
        return max(0.0, min(0.999, max(native_risk, self.novel_risk * ratio)))


class CircleView:
    """A BehavioralRegistry view restricted to one circle's members, so the existing benign
    generators draw a circle-coherent (all-related) operation without modification."""

    def __init__(self, base_registry, members: list[str]) -> None:
        self.base = base_registry
        self.members = set(members)

    def segment_ids(self, *segments: str) -> list[str]:
        return [m for m in self.base.segment_ids(*segments) if m in self.members]

    def baseline_throughput(self, account: object) -> float:
        return self.base.baseline_throughput(account)


def make_circle_benign_corpus(behav_reg, rel_reg: RelationshipRegistry,
                              n: int = 80, seed: int = 23) -> list[dict]:
    """Legitimate operations whose participants all come from ONE relationship circle, so every
    counterparty pair is an established relationship (novel-value ratio 0 by construction)."""
    from ..red_team.graph_generator import _payroll, _corporate, _merchant, _household, _random_legit
    rng = random.Random(seed)
    circles = [c for c in range(rel_reg.num_circles()) if rel_reg.members(c)]
    builders = [_random_legit, _payroll, _merchant, _corporate, _household]
    corpus: list[dict] = []
    for i in range(n):
        circle = rng.choice(circles)
        view = CircleView(behav_reg, rel_reg.members(circle))
        builder = builders[i % len(builders)]
        corpus.append(builder(f"GRAPH_BENIGN_{i:04d}", rng, None, view))
    return corpus
