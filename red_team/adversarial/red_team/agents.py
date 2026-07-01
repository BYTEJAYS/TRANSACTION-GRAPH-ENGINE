"""
Attack agents — each a transform on an AttackGraph that erodes one Blue Team
signal while preserving the laundering objective.

Every agent maps to a specific finding in the white-box report:

    feature_mimicry      → B8 (attacker-controlled node attrs), synthetic fresh-ratio,
                            cashout cash-type, prior-risk inheritance
    amount_dither        → smurfing (identical / near-threshold / round amounts)
    temporal_spread      → velocity / burst / dormancy (absolute-window gates, §8.2)
    cross_component_split → B1 (component isolation) — the dominant evasion
    relay_insertion      → fan_in / fan_out / distribution role (degree gate = 4)
    decoy_edges          → synthetic density+uniformity, global suspiciousness

Agents mutate the AttackGraph in place. They receive an `intensity` ∈ [0,1] that
the evolutionary / RL search tunes. They must never delete a source or sink node,
nor a source-outgoing or sink-incoming edge (those carry the objective).
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from ..common.attack_graph import AttackGraph

# populated by @agent; consumed by base.AGENTS
_REGISTRY: dict[str, callable] = {}

# ── compromised KYC accounts (account-takeover threat model) ──────────────────
# The `account_takeover` agent models an attacker who has seized a small number of
# REAL, KYC-established customer accounts (phished credentials / recruited mules who
# are genuine long-standing customers). It may route laundering value *through* those
# verified identities — the one thing provenance (§14) cannot floor, because the
# accounts truly are established in the bank's records.
#
# This pool is the attacker's finite takeover capacity. It MUST be a subset of the
# same registry the Blue Team's ProvenanceScorer trusts, otherwise the agent would be
# "verifying" accounts the defender has never heard of (which provenance floors to 0).
# A runner wires it via set_compromised_accounts(); left empty, the agent is a no-op,
# so every existing search that never grants a takeover capacity is unaffected.
_COMPROMISED: list[str] = []
# attacker's estimate of each seized account's normal throughput capacity — what it can
# learn from the victim's statements after takeover. Used by `conduit_split` to keep each
# mule's flow within its own envelope (so the behavioural detector, §17, can't flag it).
_COMPROMISED_CAP: dict[str, float] = {}


def set_compromised_accounts(ids, capacities: dict | None = None) -> None:
    """Grant the takeover agents a pool of seized verified account ids, and optionally
    the attacker's per-account capacity estimate (id → typical throughput)."""
    global _COMPROMISED, _COMPROMISED_CAP
    _COMPROMISED = [str(x) for x in (ids or [])]
    _COMPROMISED_CAP = {str(k): float(v) for k, v in (capacities or {}).items()}


def compromised_accounts() -> list[str]:
    return list(_COMPROMISED)


def _estimated_capacity(acct: str, default: float) -> float:
    return _COMPROMISED_CAP.get(acct, default)


def agent(name: str):
    def deco(fn):
        _REGISTRY[name] = fn
        fn.agent_name = name
        return fn
    return deco


def registry() -> dict[str, callable]:
    return dict(_REGISTRY)


# ── helpers ───────────────────────────────────────────────────────────────────
def _iter_edges(ag: AttackGraph):
    for c in ag.components:
        for e in c.get("edges", []):
            yield e


def _protected_edge(ag: AttackGraph, e: dict) -> bool:
    """Edges carrying the objective must survive every transform."""
    s, t = str(e.get("source", "")), str(e.get("target", ""))
    return s in ag.objective.sources or t in ag.objective.sinks


def _parse_ts(raw):
    try:
        return datetime.fromisoformat(str(raw))
    except Exception:
        return None


def _fresh_id(ag: AttackGraph, prefix: str = "rly") -> str:
    existing = ag.all_node_ids()
    i = 1
    while f"{prefix}_{i:05d}" in existing:
        i += 1
    return f"{prefix}_{i:05d}"


# ── agents ────────────────────────────────────────────────────────────────────
@agent("feature_mimicry")
def feature_mimicry(ag: AttackGraph, rng: random.Random, intensity: float) -> None:
    """Make every account look benign and well-aged (B8)."""
    warmth = int(5 + intensity * 95)  # transaction_count to defeat fresh-ratio
    for c in ag.components:
        for n in c.get("nodes", []):
            n["account_type"] = "normal"          # strips cashout cash-type
            n["risk_score"] = 0.0                  # zeros prior_risk / inheritance seed
            n["detected_patterns"] = []
            n["transaction_count"] = max(int(n.get("transaction_count", 0) or 0), warmth)


@agent("amount_dither")
def amount_dither(ag: AttackGraph, rng: random.Random, intensity: float) -> None:
    """Break identical / round / near-threshold amounts that smurfing keys on."""
    jitter = 0.04 + 0.10 * intensity
    for e in _iter_edges(ag):
        amt = float(e.get("amount", 0) or 0)
        if amt <= 0:
            continue
        amt *= (1.0 + rng.uniform(-jitter, jitter))
        # push out of the [46k, 50k) structuring band
        if 46_000 <= amt < 50_000:
            amt = 45_000 * (1.0 - rng.uniform(0.0, 0.05))
        # de-round
        if round(amt) % 1000 == 0:
            amt += rng.uniform(13, 487)
        e["amount"] = round(amt, 2)


@agent("temporal_spread")
def temporal_spread(ag: AttackGraph, rng: random.Random, intensity: float) -> None:
    """
    Re-time transfers so they evade all three temporal gates at once: span ≫600s
    (kills velocity), regular spacing (burst < 0.7), max gap < 6h (no dormancy).
    """
    edges = sorted((e for e in _iter_edges(ag)),
                   key=lambda e: _parse_ts(e.get("timestamp")) or datetime(2026, 1, 1))
    if not edges:
        return
    base = datetime(2026, 5, 30, 9, 0, 0)
    # gap grows with intensity but stays strictly below the 6h dormancy floor
    gap_min = 12 + intensity * (5 * 60 + 30 - 12)   # 12 min … 5h30
    jitter = gap_min * 0.15
    t = 0.0
    for e in edges:
        e["timestamp"] = (base + timedelta(minutes=t)).isoformat()
        t += max(1.0, gap_min + rng.uniform(-jitter, jitter))


def _new_relay_node(ag: AttackGraph, c: dict, rng: random.Random) -> str:
    relay = _fresh_id(ag, "rly")
    c.setdefault("nodes", []).append(
        {"id": relay, "risk_score": 0.0, "account_type": "normal",
         "transaction_count": rng.randint(5, 40), "detected_patterns": []})
    return relay


@agent("relay_insertion")
def relay_insertion(ag: AttackGraph, rng: random.Random, intensity: float) -> None:
    """
    Degree-throttle fan-in / fan-out hubs below the degree gate by building a
    consolidating relay TREE: a hub with d successors is rewritten as
    hub → (≤cap relays) → leaves, so the hub's degree drops to ≤cap while each
    relay carries the summed value of its bucket (value + objective preserved).
    This trades a degree signal for one extra, sub-gate hop.

    cap tightens with intensity: 3 (evades the ≥4 fan gate) → 2 → 1 (also starves
    the cashout/fan-in ≥2 gate, at the cost of a fatter relay the search must then
    throttle again).
    """
    cap = 3 if intensity < 0.6 else 2  # cap=2 beats the ≥4 fan gate with margin

    def _bucket(items: list, k: int) -> list[list]:
        size = max(1, -(-len(items) // k))  # ceil(d/k) → ≤k buckets each ≤size
        return [items[i:i + size] for i in range(0, len(items), size)]

    def _throttle_out(c: dict) -> bool:
        by_src: dict[str, list[dict]] = {}
        for e in c.get("edges", []):
            by_src.setdefault(str(e.get("source", "")), []).append(e)
        changed = False
        keep: list[dict] = []
        for src, es in by_src.items():
            if len(es) <= cap:
                keep.extend(es); continue
            changed = True
            for group in _bucket(es, cap):
                relay = _new_relay_node(ag, c, rng)
                total = sum(float(e.get("amount", 0) or 0) for e in group)
                keep.append({"id": f"txn_r{rng.randint(1, 10**9)}", "source": src,
                             "target": relay, "amount": round(total, 2),
                             "timestamp": group[0].get("timestamp"),
                             "payment_rail": group[0].get("payment_rail", "IMPS")})
                for e in group:
                    e["source"] = relay; keep.append(e)
        c["edges"] = keep
        return changed

    def _throttle_in(c: dict) -> bool:
        by_tgt: dict[str, list[dict]] = {}
        for e in c.get("edges", []):
            by_tgt.setdefault(str(e.get("target", "")), []).append(e)
        changed = False
        keep: list[dict] = []
        for tgt, es in by_tgt.items():
            if len(es) <= cap:
                keep.extend(es); continue
            changed = True
            for group in _bucket(es, cap):
                relay = _new_relay_node(ag, c, rng)
                total = sum(float(e.get("amount", 0) or 0) for e in group)
                for e in group:
                    e["target"] = relay; keep.append(e)
                keep.append({"id": f"txn_r{rng.randint(1, 10**9)}", "source": relay,
                             "target": tgt, "amount": round(total, 2),
                             "timestamp": group[0].get("timestamp"),
                             "payment_rail": group[0].get("payment_rail", "IMPS")})
        c["edges"] = keep
        return changed

    for c in ag.components:
        for _ in range(6):                    # iterate until all degrees ≤ cap
            if not _throttle_out(c):
                break
        for _ in range(6):
            if not _throttle_in(c):
                break


@agent("decoy_edges")
def decoy_edges(ag: AttackGraph, rng: random.Random, intensity: float) -> None:
    """
    Inject benign low-value traffic to break degree uniformity and dilute density
    (synthetic-ring detector) and lower the cluster's overall suspicious texture.
    """
    for c in ag.components:
        ids = sorted({n["id"] for n in c.get("nodes", []) if "id" in n}
                     | {str(e.get("source")) for e in c.get("edges", [])}
                     | {str(e.get("target")) for e in c.get("edges", [])})
        if len(ids) < 2:
            continue
        n_decoy = int(1 + intensity * max(2, len(ids) // 2))
        base = datetime(2026, 5, 30, 9, 0, 0)
        for _ in range(n_decoy):
            s, t = rng.sample(ids, 2)
            c["edges"].append({
                "id": f"txn_d{rng.randint(1, 10**9)}",
                "source": s, "target": t,
                "amount": round(rng.uniform(150, 6_000), 2),
                "timestamp": (base + timedelta(minutes=rng.uniform(0, 60 * 24 * 20))).isoformat(),
                "payment_rail": rng.choice(["UPI", "NEFT"]),
            })


@agent("sink_funnel")
def sink_funnel(ag: AttackGraph, rng: random.Random, intensity: float) -> None:
    """
    Starve the cashout / fan-in gate at the SINK by funnelling all of a sink's
    inflow through a single merge node (sink in-degree → 1, so cashout's fan_in≥2
    test fails). The merge node now looks mule-like — the search must pair this
    with relay_insertion/partition to also suppress that, exposing the Blue Team's
    overlapping-detector depth at consolidation points.
    """
    if intensity < 0.3:
        return
    for c in ag.components:
        present_sinks = {str(e.get("target")) for e in c.get("edges", [])} & ag.objective.sinks
        for s in present_sinks:
            in_edges = [e for e in c.get("edges", []) if str(e.get("target")) == s]
            if len(in_edges) < 2:
                continue
            merge = _new_relay_node(ag, c, rng)
            total = sum(float(e.get("amount", 0) or 0) for e in in_edges)
            ts = in_edges[0].get("timestamp")
            for e in in_edges:
                e["target"] = merge
            c["edges"].append({"id": f"txn_f{rng.randint(1, 10**9)}", "source": merge,
                               "target": s, "amount": round(total, 2), "timestamp": ts,
                               "payment_rail": in_edges[0].get("payment_rail", "IMPS")})


@agent("volume_dilution")
def volume_dilution(ag: AttackGraph, rng: random.Random, intensity: float) -> None:
    """
    Probe the *volume* tell that a margin-based (per-component) detector keys on.

    Laundering must deliver ≈target_value to the sinks, so the sink (and any
    consolidation relay) is an unavoidable high-volume node. But a detector that
    aggregates node signals by a high percentile (p90) can be blinded by *count*:
    pad each component with many low-volume benign nodes so the few high-volume
    nodes fall outside the p90, and keep all added value thin. Objective edges are
    never touched — only benign padding is added — so the laundering goal survives
    while per-component volume concentration is buried. The cost is heavy graph
    distortion, which the search must trade off.
    """
    base_t = datetime(2026, 5, 30, 9, 0, 0)

    def _new_pad() -> str:
        nid = _fresh_id(ag, "pad")
        return nid

    def _add_node(c: dict, nid: str) -> None:
        c.setdefault("nodes", []).append(
            {"id": nid, "risk_score": 0.0, "account_type": "normal",
             "transaction_count": rng.randint(5, 60), "detected_patterns": []})

    def _tiny_edge(c: dict, s: str, t: str) -> None:
        c.setdefault("edges", []).append({
            "id": f"txn_p{rng.randint(1, 10**9)}", "source": s, "target": t,
            "amount": round(rng.uniform(100, 2500), 2),
            "timestamp": (base_t + timedelta(minutes=rng.uniform(0, 60 * 24 * 25))).isoformat(),
            "payment_rail": rng.choice(["UPI", "NEFT"])})

    cap = 3  # added sink fan-in stays under the degree gate
    for c in ag.components:
        scheme_ids = sorted({n["id"] for n in c.get("nodes", []) if "id" in n}
                            | {str(e.get("source")) for e in c.get("edges", [])}
                            | {str(e.get("target")) for e in c.get("edges", [])})
        scheme_ids = [s for s in scheme_ids if s]
        if not scheme_ids:
            continue
        k = int(len(scheme_ids) * (1.0 + 9.0 * intensity)) + 3

        # Root the pad mass at sinks via PROTECTED (target=sink) edges so it
        # survives cross_component_split and actually dilutes the sink's own
        # component. A small cap of collectors keeps the sink's fan-in under the
        # gate; leaves hang off the collectors to add low-volume node count.
        present_sinks = {str(e.get("target")) for e in c.get("edges", [])} & ag.objective.sinks
        collectors: list[str] = []
        for s in present_sinks:
            for _ in range(cap):
                col = _new_pad(); _add_node(c, col)
                _tiny_edge(c, col, s)            # col → sink : protected, survives split
                collectors.append(col)
        roots = collectors or scheme_ids
        for _ in range(k):
            leaf = _new_pad(); _add_node(c, leaf)
            # several edges into the rooted mass so partial edge-cuts don't isolate it
            for _ in range(3):
                _tiny_edge(c, leaf, rng.choice(roots))


@agent("cross_component_split")
def cross_component_split(ag: AttackGraph, rng: random.Random, intensity: float) -> None:
    """
    THE dominant evasion (B1): sever interior connectivity so the single
    laundering component fragments into several disconnected components, none of
    which is a complete scheme. Objective survives because source-out and
    sink-in edges (and thus operation-level delivered value) are untouched —
    only interior links are cut, modelling off-graph completion of the transfer.

    `intensity` = fraction of interior edges to cut. resplit (done by apply_genome)
    realises the fragmentation into real components.
    """
    cut_fraction = 0.4 + 0.6 * intensity
    for c in ag.components:
        edges = c.get("edges", [])
        interior = [e for e in edges if not _protected_edge(ag, e)]
        rng.shuffle(interior)
        k = int(len(interior) * cut_fraction)
        to_cut = set(id(e) for e in interior[:k])
        c["edges"] = [e for e in edges if id(e) not in to_cut]


@agent("profile_mimicry")
def profile_mimicry(ag: AttackGraph, rng: random.Random, intensity: float) -> None:
    """
    Multi-factor benign mimicry — a coordinated macro across every axis a single
    attack controls at once.

    Single-axis evasion fails against a margin detector that reads many factors
    jointly (a laundering cluster betrays itself across velocity, layering,
    proximity, freshness … even after one axis is buried). This agent matches the
    benign profile simultaneously on the axes it can move without breaking the
    objective:
        identity/behaviour → aged 'normal' accounts, zero prior risk/patterns
        temporal           → benign cadence (no velocity/burst/dormancy tell)
        amount texture     → non-objective edges snapped into benign salary/retail
                             bands (objective-carrying edges untouched)
        cover traffic      → benign low-value transfers so the cluster reads like
                             ordinary payroll/retail rather than a tight ring
    Structural axes (degree, volume, fragmentation) are left to relay_insertion /
    volume_dilution / cross_component_split, which this composes with — together
    they form the full multi-factor mimicry the margin hardener is built to resist.
    """
    feature_mimicry(ag, rng, 1.0)
    temporal_spread(ag, rng, 0.5 + 0.5 * intensity)
    bands = [1500, 4999, 9999, 24999, 49999, 99999]
    for e in _iter_edges(ag):
        if _protected_edge(ag, e):
            continue
        e["amount"] = round(rng.choice(bands) * (1.0 + rng.uniform(-0.12, 0.12)), 2)
    base = datetime(2026, 3, 1, 10, 0, 0)
    for c in ag.components:
        ids = sorted({n["id"] for n in c.get("nodes", []) if "id" in n}
                     | {str(e.get("source")) for e in c.get("edges", [])}
                     | {str(e.get("target")) for e in c.get("edges", [])})
        ids = [x for x in ids if x]
        if len(ids) < 2:
            continue
        for _ in range(int(intensity * max(2, len(ids)))):
            s, t = rng.sample(ids, 2)
            c["edges"].append({
                "id": f"txn_c{rng.randint(1, 10**9)}", "source": s, "target": t,
                "amount": round(rng.uniform(300, 9_000), 2),
                "timestamp": (base + timedelta(minutes=rng.uniform(0, 60 * 24 * 30))).isoformat(),
                "payment_rail": rng.choice(["UPI", "NEFT"])})


def _relabel(ag: AttackGraph, mapping: dict[str, str]) -> None:
    """Rename node ids end-to-end: node metadata, every edge endpoint, and the
    objective's source/sink sets — so a relabelled cash-out account is still THE
    sink (the objective tracks the identity swap, it isn't dropped)."""
    if not mapping:
        return
    for c in ag.components:
        for n in c.get("nodes", []):
            if n.get("id") in mapping:
                n["id"] = mapping[n["id"]]
        for e in c.get("edges", []):
            s, t = str(e.get("source", "")), str(e.get("target", ""))
            if s in mapping:
                e["source"] = mapping[s]
            if t in mapping:
                e["target"] = mapping[t]
    ag.objective.sources = {mapping.get(s, s) for s in ag.objective.sources}
    ag.objective.sinks = {mapping.get(s, s) for s in ag.objective.sinks}


@agent("account_takeover")
def account_takeover(ag: AttackGraph, rng: random.Random, intensity: float) -> None:
    """
    Defeat the provenance signal (§14) the one way it admits it can be defeated:
    route the scheme through REAL, KYC-established accounts the attacker has seized.

    Provenance floors the risk of value flowing between fresh / unverified accounts,
    and a rupee only counts as *trusted* when BOTH endpoints of its edge are
    established (``trust = min(est(src), est(tgt))``). Fragmentation, volume- or
    profile-mimicry can't touch that: they edit the submitted graph, not the bank's
    KYC store. The only lever is to make both endpoints genuinely verified — i.e.
    own the accounts.

    Threat model: the attacker controls a finite pool of compromised verified
    accounts (``_COMPROMISED``). ``intensity`` sets how many of them it is willing to
    burn on THIS operation (taking over more accounts costs more and raises exposure).
    It spends that budget greedily on the highest-VALUE edges, relabelling both
    endpoints to seized verified identities, because verifying a big edge buys the
    most reduction in the value-weighted unverified ratio per account spent. Already
    relabelled nodes are reused for free, so consolidation paths (predecessor → sink)
    get fully verified once their shared node is seized.

    Objective-preserving: only identities change, never amounts, edges or topology;
    the objective's source/sink sets are relabelled in lock-step. Cost is paid in
    realism — the search trades takeover budget against the residual unverified tail.
    """
    pool = list(_COMPROMISED)
    if not pool:
        return  # no seized accounts → nothing the attacker can verify; no-op

    present = ag.all_node_ids()
    # don't "seize" an id already in the graph (it would merge two distinct accounts)
    avail = [p for p in pool if p not in present]
    if not avail:
        return
    capacity = max(1, min(len(avail), round(len(avail) * (0.15 + 0.85 * intensity))))

    # highest-value edges first: each verified edge needs BOTH its endpoints seized,
    # so spend the budget where it buys the most trusted value.
    edges = sorted(_iter_edges(ag),
                   key=lambda e: float(e.get("amount", 0) or 0), reverse=True)
    mapping: dict[str, str] = {}
    nxt = 0
    for e in edges:
        if nxt >= capacity:
            break
        for endpoint in (str(e.get("source", "")), str(e.get("target", ""))):
            if not endpoint or endpoint in mapping:
                continue
            if nxt >= capacity:
                break
            mapping[endpoint] = avail[nxt]
            nxt += 1
    _relabel(ag, mapping)


@agent("conduit_split")
def conduit_split(ag: AttackGraph, rng: random.Random, intensity: float) -> None:
    """
    The §17 residual: evade the behavioural-conduit detector with only LOW-baseline
    seized accounts (phished consumers) by splitting the cash-out across many of them.

    account_takeover routes the high-value path through seized verified identities, but
    a terminal still carries the operation's whole value V — fatal against the
    behavioural detector, which flags any verified account moving far beyond its own
    baseline (and against provenance if the terminal is left fresh). The escape models a
    real mule network: spread each source/sink across ENOUGH seized accounts that every
    one stays inside its own envelope. Each mule is verified (beats provenance) AND
    in-profile (beats behavioural); the laundering objective is preserved because the
    objective's source/sink sets are expanded to the full mule fan and still move V.

    The cost is realism and exposure — many seized accounts and many cash-out events —
    and a fat fan-in/out the search must throttle with relay_insertion. The attacker
    sizes the fan from its own capacity estimate of each mule (post-takeover statement
    access); a margin under the detector tolerance keeps each safely in-profile.
    """
    avail = [p for p in _COMPROMISED if p not in ag.all_node_ids()]
    if len(avail) < 4:
        return
    margin = 0.6                      # keep each mule well under the 1.5× tolerance
    per_edge = 9_000.0                # a small, in-profile transfer (below smurf band)
    max_degree = 3                    # stay under the fan gate (≥4)
    cursor = [0]

    V = float(ag.objective.target_value)
    if V <= 0:
        V = ag.objective.value_into_sinks(ag.components)
    if V <= 0:
        return

    def _grab_side() -> list[dict]:
        """Seize accounts until their combined safe capacity covers V."""
        side: list[dict] = []
        total = 0.0
        while cursor[0] < len(avail) and total < V:
            m = avail[cursor[0]]; cursor[0] += 1
            c = _estimated_capacity(m, per_edge / margin) * margin
            side.append({"id": m, "cap": c, "out": 0.0, "deg": 0})
            total += c
        return side, total

    src, src_cap = _grab_side()
    snk, snk_cap = _grab_side()
    # need enough seized in-profile capacity on BOTH sides to actually move V; if the
    # attacker can't, the residual attack is infeasible and the graph is left unchanged.
    if not src or not snk or src_cap < V * 0.85 or snk_cap < V * 0.85:
        return

    # Reconstitute the laundering as a thin mule MESH: many small verified transfers
    # from seized origin-mules to seized cash-out-mules, each within its account's own
    # envelope. Every edge is verified end-to-end (beats provenance) and every account
    # stays in-profile (beats the behavioural detector); the structure looks like
    # ordinary low-value traffic (beats the structural detectors). Cost: a graph with
    # nothing of the original left (max distortion) and a large seized-account count.
    base_t = datetime(2026, 4, 1, 9, 0, 0)
    edges: list[dict] = []
    si = ti = 0
    remaining = V
    guard = 0
    while remaining > 1.0 and guard < 100_000:
        guard += 1
        # advance to a source mule with headroom and degree budget
        while si < len(src) and (src[si]["out"] >= src[si]["cap"] or src[si]["deg"] >= max_degree):
            si += 1
        while ti < len(snk) and (snk[ti]["out"] >= snk[ti]["cap"] or snk[ti]["deg"] >= max_degree):
            ti += 1
        if si >= len(src) or ti >= len(snk):
            break
        s, t = src[si], snk[ti]
        amt = min(per_edge, s["cap"] - s["out"], t["cap"] - t["out"], remaining)
        if amt <= 0:
            si += 1; continue
        edges.append({
            "id": f"txn_m{rng.randint(1, 10**9)}", "source": s["id"], "target": t["id"],
            "amount": round(amt, 2),
            "timestamp": (base_t + timedelta(minutes=rng.uniform(0, 60 * 24 * 30))).isoformat(),
            "payment_rail": rng.choice(["UPI", "IMPS", "NEFT"])})
        s["out"] += amt; t["out"] += amt; s["deg"] += 1; t["deg"] += 1
        remaining -= amt

    used = {e["source"] for e in edges} | {e["target"] for e in edges}
    if not used or remaining > V * 0.15:
        return                        # couldn't place ≥85% of V within profile → abort
    nodes = [{"id": m, "risk_score": 0.0, "account_type": "normal",
              "transaction_count": rng.randint(20, 200), "detected_patterns": []}
             for m in sorted(used)]
    gid = (ag.components[0].get("graph_id", "GRAPH") if ag.components else "GRAPH").split("_p")[0]
    ag.components = [{"graph_id": f"{gid}_mesh", "node_ids": sorted(used),
                      "nodes": nodes, "edges": edges}]
    ag.objective.sources = {e["source"] for e in edges}
    ag.objective.sinks = {e["target"] for e in edges}
