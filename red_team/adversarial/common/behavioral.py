"""
Behavioural signal on verified accounts — the counter to account-takeover (§16).

Provenance (§14) proves an account is *established*; §16 showed that is not the same
as the account *behaving normally*. An attacker who seizes a real KYC customer and
routes laundering value through it collapses provenance's unverified ratio, because the
identity genuinely is verified. The signal provenance lacks is behavioural: a bank knows
not just *that* an account is established but *how it normally behaves* — its typical
throughput, transaction size and activity. A seized account used as a conduit betrays
itself by operating far outside that envelope: pushing laundering-scale value through an
account whose own history is a ₹20k/month household profile.

This module models that knowledge as a per-account **baseline**, held in the bank's
records and therefore — like establishment — unforgeable by the attacker. The detector
flags a component when a *verified* account is moving value far beyond its own baseline
in a pass-through pattern. It only ever RAISES risk (catches conduits); it never clears,
so it composes after provenance: provenance attenuates trusted clusters, behavioural
re-floors the trusted accounts that are misbehaving.

Two properties keep it from re-introducing false positives:
  * it compares each account to *its own* baseline, so a corporate account moving ₹2M is
    normal (its baseline is corporate-scale) while a household account moving ₹2M is not;
  * it only fires on value a verified account actually carries, so an ordinary customer's
    occasional large-but-in-profile transfer does not trip it.

Documented residual (the next Red probe): an attacker who seizes accounts whose baseline
*does* support the volume — corporate / SME identities — or who splits the flow across
enough seized accounts that each stays within profile, evades this too, at the cost of a
much harder and more expensive set of takeovers.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

# segment → (establishment skew, baseline throughput band, typical txn band)
# throughput = the value an account of this kind moves in an observation window
# comparable to one analysed graph; both bands are what the bank sees historically.
_SEGMENTS: dict[str, dict] = {
    "household":  {"est": (0.45, 0.95), "thru": (5_000, 40_000),     "txn": (500, 8_000)},
    "retail":     {"est": (0.40, 0.90), "thru": (2_000, 25_000),     "txn": (100, 6_000)},
    "salaried":   {"est": (0.55, 0.98), "thru": (40_000, 250_000),   "txn": (25_000, 180_000)},
    "merchant":   {"est": (0.60, 0.99), "thru": (200_000, 3_000_000), "txn": (100, 8_000)},
    "sme":        {"est": (0.60, 0.99), "thru": (300_000, 3_000_000), "txn": (50_000, 500_000)},
    "corporate":  {"est": (0.70, 1.00), "thru": (2_000_000, 30_000_000), "txn": (200_000, 2_000_000)},
}
# population mix of the KYC base (most customers are small)
_MIX = [("household", 0.40), ("retail", 0.28), ("salaried", 0.18),
        ("merchant", 0.07), ("sme", 0.05), ("corporate", 0.02)]


@dataclass
class AccountProfile:
    """What the bank historically knows about one established customer."""
    establishment: float        # KYC standing in [0,1] (same axis provenance uses)
    segment: str
    baseline_throughput: float  # typical value moved per comparable window
    baseline_txn: float         # typical single-transaction size


def build_customer_profiles(n: int = 5000, seed: int = 2024) -> dict[str, AccountProfile]:
    """The bank's KYC + behavioural base: account_id → AccountProfile.

    Establishment is drawn segment-appropriately (bigger customers tend to be more
    established) so this is a drop-in richer replacement for build_customer_universe —
    ``{cid: p.establishment}`` reproduces the same provenance registry shape.
    """
    rng = random.Random(seed)
    profiles: dict[str, AccountProfile] = {}
    for i in range(n):
        r = rng.random()
        acc, seg = 0.0, _MIX[-1][0]
        for name, p in _MIX:
            acc += p
            if r <= acc:
                seg = name
                break
        spec = _SEGMENTS[seg]
        profiles[f"cust_{i:05d}"] = AccountProfile(
            establishment=round(rng.uniform(*spec["est"]), 4),
            segment=seg,
            baseline_throughput=round(rng.uniform(*spec["thru"]), 2),
            baseline_txn=round(rng.uniform(*spec["txn"]), 2),
        )
    return profiles


@dataclass
class BehavioralRegistry:
    """Trusted per-account behavioural baselines. Unknown accounts have none."""
    profiles: dict[str, AccountProfile]

    @property
    def universe(self) -> dict[str, float]:
        """{id: establishment} — feeds a ProvenanceRegistry off the same base."""
        return {cid: p.establishment for cid, p in self.profiles.items()}

    def baseline_throughput(self, account: object) -> float:
        p = self.profiles.get(str(account))
        return p.baseline_throughput if p else 0.0

    def baseline_txn(self, account: object) -> float:
        p = self.profiles.get(str(account))
        return p.baseline_txn if p else 0.0

    def segment_ids(self, *segments: str) -> list[str]:
        s = set(segments)
        return [cid for cid, p in self.profiles.items() if p.segment in s]

    def ids_with_min_baseline(self, min_throughput: float) -> list[str]:
        return [cid for cid, p in self.profiles.items()
                if p.baseline_throughput >= min_throughput]

    def customer_ids(self) -> list[str]:
        return list(self.profiles.keys())


class BehavioralScorer:
    """Re-floors the risk of verified accounts operating outside their own envelope."""

    def __init__(self, registry: BehavioralRegistry,
                 tolerance: float = 1.5, conduit_risk: float = 0.95,
                 min_value_share: float = 0.10) -> None:
        self.reg = registry
        # an account may legitimately spike to `tolerance`× its baseline before it
        # is anomalous (a corporate's bigger month, a household's car purchase).
        self.tolerance = tolerance
        self.conduit_risk = conduit_risk            # risk a clear conduit imposes
        # ignore verified accounts carrying a trivial share of the component's value;
        # a conduit carries the operation's value, an incidental account does not.
        self.min_value_share = min_value_share

    @staticmethod
    def _flows(component: dict) -> tuple[dict[str, float], dict[str, float], float]:
        in_v: dict[str, float] = {}
        out_v: dict[str, float] = {}
        total = 0.0
        for e in component.get("edges", []):
            amt = float(e.get("amount", 0) or 0)
            if amt <= 0:
                continue
            s, t = str(e.get("source", "")), str(e.get("target", ""))
            out_v[s] = out_v.get(s, 0.0) + amt
            in_v[t] = in_v.get(t, 0.0) + amt
            total += amt
        return in_v, out_v, total

    def conduit_anomaly(self, component: dict) -> float:
        """Worst value-significant behavioural anomaly among VERIFIED accounts, in [0,1].

        For each established account carrying a meaningful share of the component's
        value, measure how far its observed throughput exceeds its own baseline. Fresh /
        unverified accounts (no baseline) are left to provenance and skipped here.
        """
        in_v, out_v, total = self._flows(component)
        if total <= 0:
            return 0.0
        worst = 0.0
        for acct in set(in_v) | set(out_v):
            base = self.reg.baseline_throughput(acct)
            if base <= 0:
                continue  # unverified — provenance's job, not this detector's
            observed = max(in_v.get(acct, 0.0), out_v.get(acct, 0.0))
            if observed < self.min_value_share * total:
                continue  # not carrying enough of the operation to be its conduit
            ratio = observed / base
            if ratio <= self.tolerance:
                continue  # operating within its own envelope → normal
            anomaly = 1.0 - self.tolerance / ratio   # → 1 as it blows past baseline
            worst = max(worst, anomaly)
        return max(0.0, min(1.0, worst))

    def adjust(self, component: dict, native_risk: float) -> float:
        """Raise risk to the conduit floor; never lower it (provenance does clearing)."""
        floor = self.conduit_risk * self.conduit_anomaly(component)
        return max(0.0, min(0.999, max(native_risk, floor)))
