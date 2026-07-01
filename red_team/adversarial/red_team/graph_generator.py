"""
Graph generator — the source of base fraud graphs and component realisation.

We start from the Blue Team's OWN simulator archetypes (the graphs it is built to
catch and does catch as FRAUD), derive each one's laundering objective, and wrap
it as an AttackGraph the Red Team can transform. Starting from confirmed-FRAUD
graphs makes evasion success unambiguous: any drop to ≤ LOGGED is a real win.
"""
from __future__ import annotations

import random

from ..common.attack_graph import AttackGraph, AttackObjective, Component
from .. import config

# Archetypes with a well-defined source→sink money objective.
_ARCHETYPES = [
    "layering", "smurfing", "fan_out", "fan_in", "mule_network",
    "cashout_network", "bridge_network", "hybrid", "large_org",
]

_DEFAULT_NODE = {"risk_score": 0.0, "account_type": "normal",
                 "transaction_count": 2, "detected_patterns": []}


# ── objective derivation ──────────────────────────────────────────────────────
def _volumes(component: Component) -> tuple[dict[str, float], dict[str, float]]:
    in_v: dict[str, float] = {}
    out_v: dict[str, float] = {}
    for e in component.get("edges", []):
        s, t = str(e.get("source", "")), str(e.get("target", ""))
        a = float(e.get("amount", 0) or 0)
        out_v[s] = out_v.get(s, 0.0) + a
        in_v[t] = in_v.get(t, 0.0) + a
    return in_v, out_v


def build_objective(component: Component, tolerance: float | None = None) -> AttackObjective:
    in_v, out_v = _volumes(component)
    nodes = set(in_v) | set(out_v)
    sources = {n for n in nodes if out_v.get(n, 0) > 0 and in_v.get(n, 0) == 0}
    sinks = {n for n in nodes if in_v.get(n, 0) > 0 and out_v.get(n, 0) == 0}
    # fallbacks for cyclic / fully-internal schemes
    if not sources and out_v:
        sources = {max(out_v, key=out_v.get)}
    if not sinks and in_v:
        sinks = {max(in_v, key=in_v.get)}
    # Calibrate the target to what the BASE graph actually delivers. Laundering
    # chains dissipate value (each hop ×0.9–0.96, fan-outs split), so the value
    # arriving at sinks is far below the value leaving sources. Using the min of
    # the two baseline volumes makes the untouched fraud graph feasible and
    # defines preservation as "still launder ≈ as much as the original did".
    src_out = sum(out_v.get(s, 0.0) for s in sources)
    snk_in = sum(in_v.get(t, 0.0) for t in sinks)
    target = min(src_out, snk_in) if (src_out > 0 and snk_in > 0) else max(src_out, snk_in)
    target = target or sum(out_v.values())
    return AttackObjective(
        sources=sources, sinks=sinks, target_value=float(target),
        tolerance=config.OBJECTIVE_TOLERANCE if tolerance is None else tolerance,
    )


def make_base_attacks(seed: int = 42, archetypes: list[str] | None = None) -> list[AttackGraph]:
    """One confirmed-FRAUD AttackGraph per archetype, each with its objective."""
    from blue_team_v2.simulation.generators import Simulator
    sim = Simulator(seed=seed)
    names = archetypes or _ARCHETYPES
    out: list[AttackGraph] = []
    for name in names:
        component, gt = getattr(sim, name)()
        obj = build_objective(component)
        out.append(AttackGraph(components=[component], objective=obj, archetype=gt.archetype))
    return out


def _size_to_baseline(edges: list[dict], registry, rng: random.Random,
                      frac: tuple[float, float] = (0.15, 0.5)) -> None:
    """Resize each edge so NO verified account moves more than ~half its own baseline
    throughput in the component — i.e. legitimate accounts always operate within their
    historical envelope. This makes the behavioural-conduit FP test (§17) sound by
    construction: any account seen above its baseline is then genuinely anomalous, not
    an artefact of arbitrary benign amounts. (Caveat carried in the report: in
    production the baseline is an estimated high-percentile of real history, so this
    0%-by-construction FP must be re-measured on real data — the §13 realism discipline.)
    """
    from collections import Counter
    outdeg, indeg = Counter(), Counter()
    for e in edges:
        outdeg[str(e.get("source", ""))] += 1
        indeg[str(e.get("target", ""))] += 1
    for e in edges:
        s, t = str(e.get("source", "")), str(e.get("target", ""))
        bs, bt = registry.baseline_throughput(s), registry.baseline_throughput(t)
        cap_s = bs / max(1, outdeg[s]) if bs > 0 else float("inf")
        cap_t = bt / max(1, indeg[t]) if bt > 0 else float("inf")
        cap = min(cap_s, cap_t)
        if cap == float("inf"):
            continue  # both ends unknown → leave the original amount
        e["amount"] = round(max(50.0, cap * rng.uniform(*frac)), 2)


def _benign_component(gid: str, edges: list[dict], rng: random.Random,
                      registry=None) -> Component:
    if registry is not None:
        _size_to_baseline(edges, registry, rng)
    ids = sorted({str(e["source"]) for e in edges} | {str(e["target"]) for e in edges})
    nodes = [{"id": n, "account_type": "normal", "risk_score": 0.0,
              "transaction_count": rng.randint(40, 400), "detected_patterns": []}
             for n in ids]
    return {"graph_id": gid, "node_ids": ids, "nodes": nodes, "edges": edges}


def _ts(rng: random.Random, span_days: float) -> str:
    from datetime import datetime, timedelta
    base = datetime(2026, 3, 1, 10, 0, 0)
    return (base + timedelta(minutes=rng.uniform(0, span_days * 24 * 60))).isoformat()


def _accts(rng: random.Random, pool: list[str] | None, k: int, prefix: str,
           registry=None, segments: tuple[str, ...] | None = None) -> list[str]:
    """k distinct accounts. When a behavioural `registry` and `segments` are given,
    draw SEGMENT-APPROPRIATE verified identities (a corporate graph from corporate
    accounts, a household graph from household accounts) so each participant's
    activity is consistent with its own baseline — otherwise the behavioural detector
    would flag legitimate traffic. Falls back to the flat KYC pool, then fresh names."""
    if registry is not None and segments is not None:
        seg_ids = registry.segment_ids(*segments)
        if len(seg_ids) >= k:
            return rng.sample(seg_ids, k)
    if pool and len(pool) >= k:
        return rng.sample(pool, k)
    return [f"{prefix}_{rng.randint(0, 10**9)}" for _ in range(k)]


def _hub_and_leaves(rng, pool, registry, hub_segs, leaf_segs, k, prefix):
    """One hub + k distinct leaves. With a registry the hub is drawn from `hub_segs`
    and leaves from `leaf_segs`; without one this preserves the original single
    (k+1)-draw so the flat-pool corpus is byte-identical to before segmentation."""
    if registry is None:
        accts = _accts(rng, pool, k + 1, prefix)
        return accts[0], accts[1:]
    hub = _accts(rng, pool, 1, prefix, registry, hub_segs)[0]
    leaves = [x for x in _accts(rng, pool, k + 1, prefix, registry, leaf_segs)
              if x != hub][:k]
    return hub, leaves


def _payroll(gid, rng, pool=None, registry=None):
    """One employer paying many employees — a legitimate high-fan-out, high-volume
    cluster that structurally resembles a distribution/smurfing scheme."""
    k = rng.randint(8, 25)
    emp, employees = _hub_and_leaves(rng, pool, registry,
                                     ("corporate", "sme"), ("salaried",), k, "emp")
    edges = [{"id": f"e{i}", "source": emp, "target": e,
              "amount": round(rng.uniform(25_000, 180_000), 2),
              "timestamp": _ts(rng, 3), "payment_rail": "NEFT"}
             for i, e in enumerate(employees)]
    return _benign_component(gid, edges, rng, registry)


def _merchant(gid, rng, pool=None, registry=None):
    """Many customers paying one merchant — a legitimate high-fan-in cluster that
    structurally resembles a collection/cash-out scheme."""
    k = rng.randint(10, 40)
    m, custs = _hub_and_leaves(rng, pool, registry,
                               ("merchant",), ("retail", "household"), k, "cust")
    edges = [{"id": f"e{i}", "source": cu, "target": m,
              "amount": round(rng.uniform(100, 8_000), 2),
              "timestamp": _ts(rng, 14), "payment_rail": "UPI"}
             for i, cu in enumerate(custs)]
    return _benign_component(gid, edges, rng, registry)


def _corporate(gid, rng, pool=None, registry=None):
    """A business making a few VERY large supplier payments — legitimate, low-fan,
    high-volume. The hardest false-positive test for any volume-based signal."""
    k = rng.randint(3, 6)
    accts = _accts(rng, pool, k + 1, "corp", registry, ("corporate", "sme"))
    p, suppliers = accts[0], accts[1:]
    edges = [{"id": f"e{i}", "source": p, "target": s,
              "amount": round(rng.uniform(200_000, 2_000_000), 2),
              "timestamp": _ts(rng, 21), "payment_rail": "RTGS"}
             for i, s in enumerate(suppliers)]
    return _benign_component(gid, edges, rng, registry)


def _household(gid, rng, pool=None, registry=None):
    """A few accounts with small recurring transfers — ordinary retail activity."""
    accts = _accts(rng, pool, rng.randint(3, 6), "usr", registry, ("household", "retail"))
    edges = []
    for k in range(rng.randint(4, 12)):
        s, t = rng.sample(accts, 2)
        edges.append({"id": f"e{k}", "source": s, "target": t,
                      "amount": round(rng.uniform(500, 15_000), 2),
                      "timestamp": _ts(rng, 30), "payment_rail": rng.choice(["UPI", "IMPS"])})
    return _benign_component(gid, edges, rng, registry)


def _random_legit(gid, rng, pool=None, registry=None):
    """Small random transfers among ordinary (verified) customers."""
    accts = _accts(rng, pool, rng.randint(6, 16), "usr", registry, ("household", "retail"))
    edges = []
    for i in range(rng.randint(3, len(accts))):
        s, t = rng.sample(accts, 2)
        edges.append({"id": f"e{i}", "source": s, "target": t,
                      "amount": round(rng.uniform(200, 15_000), 2),
                      "timestamp": _ts(rng, 30), "payment_rail": rng.choice(["UPI", "NEFT"])})
    if not edges:
        edges.append({"id": "e0", "source": accts[0], "target": accts[1], "amount": 2500.0,
                      "timestamp": _ts(rng, 30), "payment_rail": "UPI"})
    return _benign_component(gid, edges, rng, registry)


def make_benign_corpus(seed: int = 7, n: int = 80, realistic: bool = True,
                       pool: list[str] | None = None, registry=None) -> list[Component]:
    """Legitimate (CLEAN) components for false-positive measurement.

    The realistic corpus deliberately includes legitimate traffic that *structurally
    resembles* fraud — high-fan payroll/merchant clusters and high-VALUE corporate
    payments — so the fraud–benign margin is tested honestly. A volume-based detector
    that only ever saw tiny random transfers would look robust for the wrong reason;
    here it must separate laundering from legitimate big money and hub accounts.

    When a behavioural `registry` is supplied, participants are drawn SEGMENT-
    APPROPRIATELY (so a corporate payment is between corporate-baseline accounts) — the
    honest FP test for the behavioural detector (§17). Without it, behaviour is
    unchanged from the flat-`pool` path used by the existing arms race.
    """
    rng = random.Random(seed)
    if not realistic:
        from blue_team_v2.simulation.generators import Simulator
        sim = Simulator(seed=seed)
        return [sim.normal(gid=f"GRAPH_BENIGN_{i:04d}", n_accounts=6 + (i % 9))[0]
                for i in range(n)]

    builders = [
        (0.34, _random_legit),
        (0.20, _payroll),
        (0.20, _merchant),
        (0.14, _corporate),
        (0.12, _household),
    ]
    corpus: list[Component] = []
    for i in range(n):
        r = rng.random()
        acc = 0.0
        chosen = builders[0][1]
        for prob, fn in builders:
            acc += prob
            if r <= acc:
                chosen = fn
                break
        corpus.append(chosen(f"GRAPH_BENIGN_{i:04d}", rng, pool, registry))
    return corpus


# ── component realisation ─────────────────────────────────────────────────────
class _UF:
    def __init__(self) -> None:
        self.p: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def resplit_components(ag: AttackGraph) -> AttackGraph:
    """
    Recompute true connected components over the current edge set. Edges severed
    by an agent become real graph fragmentation here. Node metadata is preserved;
    isolated objective nodes survive as singleton components so the objective's
    node-presence check still holds.
    """
    node_meta: dict[str, dict] = {}
    for c in ag.components:
        for n in c.get("nodes", []):
            if "id" in n:
                node_meta[n["id"]] = dict(n)

    edges: list[dict] = []
    for c in ag.components:
        edges.extend(c.get("edges", []))

    uf = _UF()
    all_nodes: set[str] = set(node_meta)
    for e in edges:
        s, t = str(e.get("source", "")), str(e.get("target", ""))
        if not s or not t:
            continue
        all_nodes.add(s); all_nodes.add(t)
        uf.union(s, t)
    # keep objective nodes present even if isolated
    for n in ag.objective.sources | ag.objective.sinks:
        all_nodes.add(n)
        uf.find(n)

    groups_edges: dict[str, list[dict]] = {}
    for e in edges:
        s = str(e.get("source", ""))
        groups_edges.setdefault(uf.find(s), []).append(e)
    groups_nodes: dict[str, set[str]] = {}
    for n in all_nodes:
        groups_nodes.setdefault(uf.find(n), set()).add(n)

    base_gid = (ag.components[0].get("graph_id", "GRAPH") if ag.components else "GRAPH")
    base_gid = base_gid.split("_p")[0]

    new_components: list[Component] = []
    for i, (root, nids) in enumerate(sorted(groups_nodes.items())):
        ids = sorted(nids)
        nodes = []
        for nid in ids:
            meta = node_meta.get(nid)
            if meta is None:
                meta = {"id": nid, **_DEFAULT_NODE}
            else:
                meta.setdefault("id", nid)
            nodes.append(meta)
        new_components.append({
            "graph_id": f"{base_gid}_p{i}",
            "node_ids": ids,
            "nodes": nodes,
            "edges": groups_edges.get(root, []),
        })

    ag.components = new_components
    return ag
