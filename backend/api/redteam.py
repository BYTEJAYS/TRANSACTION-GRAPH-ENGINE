"""
Red Team panel endpoint (LOCALHOST demo only).

Serves the adversarial Red Team to the TGiE frontend's Red Team panel as a HUMAN-IN-THE-LOOP
review queue: each archetype is evolved into an attack, and the panel shows the actual attack
GRAPH it feeds, the per-generation evolution that produced it, and the deployed-vs-hardened
verdicts. A reviewer then approves (YES) or rejects (NO) each graph, so the Blue Team only ever
trains on real, on-graph evasions — never on garbage (broken-objective or partition-dependent
artifacts the §A audit flagged as "free off-graph credit").

Additive + opt-in: included only when ENABLE_REDTEAM_PANEL is set. blue_team_v2 untouched.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

_REPO_ROOT = Path(__file__).resolve().parents[2]
# The adversarial Red Team package lives at red_team/adversarial/, so red_team/
# must be importable for `import adversarial.*` to resolve.
for _p in (_REPO_ROOT, _REPO_ROOT / "red_team"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

router = APIRouter(prefix="/api/redteam", tags=["redteam"])

# Governance store — the human-in-the-loop Training Queue + audit trail. A Blue
# MISS is auto-enqueued here for review; nothing reaches the Blue Knowledge Base
# without an explicit investigator "learn" decision (deduped + audited).
from adversarial_governance import store as _gov  # noqa: E402

_STATE: dict = {}
_REVIEWS: dict[str, bool] = {}        # candidate id -> approved?  (the human's YES/NO)

_LADDER = [
    ("native V2", "structural snapshot", "partition / fresh-mule laundering"),
    ("provenance", "KYC identity", "account-takeover via verified accounts"),
    ("behavioural", "each account vs its own baseline", "the conduit_split mule mesh"),
    ("coordination", "operation-level linked crowd", "corporate-account seizure"),
    ("relationship", "shared counterparty history", "seasoning fake history"),
    ("maturity", "history depth × age over time", "— priced out: cost ≫ laundered value"),
]
_STRUCTURAL = ("feature_mimicry", "amount_dither", "decoy_edges", "relay_insertion",
               "temporal_spread", "sink_funnel", "cross_component_split")
_ARCHES = ["smurfing", "fan_out", "fan_in", "mule_network",
           "cashout_network", "bridge_network", "hybrid", "large_org"]
_MAX_NODES, _MAX_EDGES = 46, 64


def _state():
    if "htb" not in _STATE:
        from adversarial.integration import HardenedBlueTeam, default_world
        world = default_world()
        _STATE["world"] = world
        _STATE["htb"] = HardenedBlueTeam(world, maturity=True)
    return _STATE


def _native_op(components):
    from blue_team_v2.adapter import analyze_component_sync
    order = {"CLEAN": 0, "LOGGED": 1, "SUSPICIOUS": 2, "FRAUD": 3}
    vs = [analyze_component_sync(c) for c in components]
    worst = max((v["verdict"] for v in vs), key=lambda v: order.get(v, 3), default="CLEAN")
    return worst, round(max((v["risk_score"] for v in vs), default=0.0), 3)


def _which_signal(components, htb):
    prov = max((htb.provenance.unverified_value_ratio(c) for c in components), default=0)
    coord = htb.coordination.operation_risk(components)
    novel = max((htb.relationship.novel_value_ratio(c) for c in components), default=0)
    behav = max((htb.behavioural.conduit_anomaly(c) for c in components), default=0)
    ranked = sorted([("provenance", prov), ("coordination", coord),
                     ("relationship", novel), ("behavioural", behav)], key=lambda x: -x[1])
    return ranked[0][0] if ranked[0][1] > 0 else "native"


def _render_graph(ag):
    """A compact, renderable node-link view of the attack (role-coloured, edge-capped)."""
    srcs, snks = ag.objective.sources, ag.objective.sinks

    def role(n):
        return "source" if n in srcs else "sink" if n in snks else "relay"

    edges = [e for c in ag.components for e in c.get("edges", [])]
    edges.sort(key=lambda e: (0 if (str(e.get("source")) in srcs or str(e.get("target")) in snks) else 1,
                              -float(e.get("amount", 0) or 0)))
    nodes: dict[str, str] = {}
    out: list[dict] = []
    for e in edges:
        s, t = str(e.get("source", "")), str(e.get("target", ""))
        if not s or not t:
            continue
        if len(out) >= _MAX_EDGES:
            break
        if len(nodes) >= _MAX_NODES and s not in nodes and t not in nodes:
            continue
        nodes.setdefault(s, role(s)); nodes.setdefault(t, role(t))
        out.append({"source": s, "target": t, "amount": round(float(e.get("amount", 0) or 0))})
    return {
        "nodes": [{"id": n, "role": r} for n, r in nodes.items()],
        "edges": out,
        "shown_edges": len(out),
    }


# Technique-sets the Red Team has already produced across re-runs, so each re-run is
# pushed toward a NOVEL attack (never repeat the same combination twice).
_SEEN_TECHNIQUES: set = set()


def _escalation(level: int) -> dict:
    """Each re-run (level = seed) makes the Red Team SEARCH harder: a longer genome budget and
    a deeper search (more generations/population) discover attacks that are both more elaborate
    (more chained techniques) AND lower-detection — because the GA only keeps the complexity
    that actually helps it evade (unlike naively bolting on moves, which just adds detectable
    structure). A fitness that rewards evasion more and penalises complexity less each level
    lets it embrace those sophisticated attacks. The budget is CAPPED so a re-run stays
    interactive (an uncapped deeper search hit 45 s; this stays ~10 s worst case).

    Arsenal is the FAST structural set — the graph-exploding agents (volume_dilution,
    profile_mimicry) make an interactive search hang (one timed out); PPO/QD with a surrogate
    world-model is the offline path for those (audit §23)."""
    from adversarial.config import FitnessWeights
    lvl = max(0, int(level))
    return {
        "level": lvl,
        "max_genome_len": min(4 + lvl, 7),
        "max_techniques": min(4 + lvl, 7),
        "generations": min(8 + lvl, 12),
        "population_size": min(18 + 2 * lvl, 26),
        "allowed_agents": _STRUCTURAL,
        "weights": FitnessWeights(
            evasion=min(0.75, 0.55 + 0.04 * lvl),       # reward undetectability more each level
            stealth=0.25,
            distortion=max(0.05, 0.15 - 0.02 * lvl),    # tolerate the distortion complexity needs
            complexity=max(0.0, 0.05 - 0.012 * lvl),    # stop penalising elaborate genomes
        ),
    }


def _evolve_novel(oracle, base, esc: dict, label: str, gseed: int):
    """Evolve an attack; if it repeats a technique-set the Red Team already produced, retry
    once with a different search seed — so every re-run trends toward a genuinely new attack."""
    from adversarial.config import EvolutionConfig
    from adversarial.red_team.evolutionary_engine import EvolutionaryRedTeam
    eng = best = None
    key = (label, frozenset())
    novel = False
    for attempt in range(2):
        cfg = EvolutionConfig(
            population_size=esc["population_size"], generations=esc["generations"],
            eval_samples=1, max_genome_len=esc["max_genome_len"],
            allowed_agents=esc["allowed_agents"], weights=esc["weights"],
            seed=gseed + attempt * 7919)
        eng = EvolutionaryRedTeam(oracle, base, cfg)
        best = eng.evolve()
        key = (label, frozenset(m.agent for m in best.genome))
        novel = key not in _SEEN_TECHNIQUES
        if novel:
            break
    _SEEN_TECHNIQUES.add(key)
    return eng, best, novel


def _build_candidates(seed: int):
    import random
    from adversarial.common.oracle import BlueTeamOracle
    from adversarial.red_team import agents as _agents
    from adversarial.red_team.base import Move, apply_genome
    from adversarial.red_team.evolutionary_engine.engine import stable_seed
    from adversarial.red_team.graph_generator import make_base_attacks

    st = _state(); htb = st["htb"]; world = st["world"]
    _agents.set_compromised_accounts([])
    native_oracle = BlueTeamOracle(target="v2")
    base = {b.archetype: b for b in make_base_attacks(seed=42)}
    esc = _escalation(seed)
    lvl = esc["level"]

    specs = [(a, None, False) for a in _ARCHES]
    # one advanced mesh candidate (seized consumer accounts) for signal variety
    hh = [c for c, p in world.profiles.items()
          if p.segment in ("household", "retail") and p.establishment >= 0.7][:400]
    specs.append(("mesh", hh, True))

    cands = []
    for label, pool, caps in specs:
        if label == "mesh":
            # the mesh gets DEEPER each level: more seized mules + a longer (on-graph)
            # obfuscation chain (relay throttling / time-spreading / decoy edges)
            n_seized = min(120 + lvl * 60, len(hh))
            seized = hh[:n_seized]
            _agents.set_compromised_accounts(seized, {a: world.behav_reg.baseline_throughput(a) for a in seized})
            genome = [Move("conduit_split", 0.9)]
            if lvl >= 1:
                genome.append(Move("relay_insertion", round(min(0.9, 0.6 + 0.06 * lvl), 2)))
            if lvl >= 2:
                genome.append(Move("temporal_spread", 0.7))
            if lvl >= 3:
                genome.append(Move("decoy_edges", 0.6))
            ag = apply_genome(base["layering"], genome, random.Random(stable_seed(f"mesh:{lvl}")))
            arch = "layering (mule mesh)"
            techniques = ["account_takeover"] + [m.agent for m in genome]
            evo = []
            key = ("mesh", frozenset(techniques))
            novel = key not in _SEEN_TECHNIQUES
            _SEEN_TECHNIQUES.add(key)
            _agents.set_compromised_accounts([])
        else:
            arch = label
            eng, best, novel = _evolve_novel(native_oracle, base[label], esc,
                                             label, stable_seed(f"{label}:{lvl}"))
            ag = apply_genome(base[label], best.genome, random.Random(stable_seed(best.repr)))
            techniques = [m.agent for m in best.genome] or ["(identity)"]
            evo = [{"gen": h["generation"], "detection": h["best_detection"], "evaded": h["evaded"]}
                   for h in eng.history]

        nv, nr = _native_op(ag.components)
        op = htb.analyze_operation(ag.components)
        hv = op["operation_verdict"]
        hr = round(max(op["coordination_risk"], max((c["risk_score"] for c in op["components"]), default=0)), 3)
        obj_ok = ag.objective_satisfied()
        on_graph = ag.on_graph_satisfied()
        ne = ag.num_edges()
        if not obj_ok:
            garbage, reason = True, "objective broke — not a real laundering example"
        elif not on_graph:
            garbage, reason = True, "partition-dependent — only 'evades' via off-graph completion (B1 artifact)"
        elif ne < 3:
            garbage, reason = True, "too trivial to learn from"
        else:
            garbage, reason = False, "on-graph & objective intact — a real evasion"

        native_evaded = nv in ("CLEAN", "LOGGED")
        # The deployed Blue Team already recognises this pattern (flagged SUSPICIOUS/FRAUD)
        # → training on it is pointless; instead it means the Red Team must improve its attack.
        blue_catches = not native_evaded
        # Worth feeding the Blue corpus ONLY when Blue couldn't catch it AND it's a real
        # on-graph evasion (not a partition/broken-objective artifact).
        trainable = native_evaded and not garbage

        cand_id = f"{seed}:{label}"
        _STATE.setdefault("components", {})[cand_id] = ag.components   # for /train
        cands.append({
            "id": cand_id,
            "archetype": arch.replace("_", " "),
            "techniques": techniques,
            "graph": _render_graph(ag),
            "nodes_total": ag.num_nodes(),
            "edges_total": ne,
            "components": ag.num_components(),
            "evolution": evo,
            "native": {"verdict": nv, "risk": nr, "evaded": native_evaded},
            "hardened": {"verdict": hv, "risk": hr, "caught": hv in ("SUSPICIOUS", "FRAUD"),
                         "signal": _which_signal(ag.components, htb)},
            "feasibility": {"objective_ok": obj_ok, "on_graph": on_graph},
            "garbage": garbage,
            "reason": reason,
            "blue_catches": blue_catches,
            "trainable": trainable,
            "novel": bool(novel),                 # never produced this technique-set before
            "complexity": len(techniques),        # number of chained attack techniques
        })
    return cands


def _find_candidate(cid: str):
    for cl, _ in _STATE.get("cand_cache", {}).values():
        for c in cl:
            if c["id"] == cid:
                return c
    return None


def _tally():
    approved_ids = [cid for cid, v in _REVIEWS.items() if v]
    rejected = sum(1 for v in _REVIEWS.values() if not v)
    # Blue corpus = approvals that are real evasions Blue COULDN'T catch.
    # Red-must-improve = approvals the deployed Blue already catches (weak attacks).
    corpus = red_must_improve = 0
    for cid in approved_ids:
        c = _find_candidate(cid)
        if c is None:
            corpus += 1
        elif c.get("blue_catches"):
            red_must_improve += 1
        elif c.get("trainable"):
            corpus += 1
    return {"approved": len(approved_ids), "rejected": rejected, "reviewed": len(_REVIEWS),
            "blue_corpus": corpus, "red_must_improve": red_must_improve}


@router.get("/attacks")
def attacks(seed: int = 0):
    cache = _STATE.setdefault("cand_cache", {})
    if seed not in cache:
        t0 = time.time()
        cache[seed] = (_build_candidates(seed), round((time.time() - t0) * 1000))
    cands, took = cache[seed]
    # Blue MISSES → Training Queue (idempotent; deduped on candidate id). Detected
    # attacks are NOT enqueued — those mean the Red Team must evolve a harder variant.
    for c in cands:
        _gov.enqueue(c)
    esc = _escalation(seed)
    evaded = sum(1 for c in cands if c["native"]["evaded"])
    mean_det = round(sum(c["native"]["risk"] for c in cands) / max(1, len(cands)), 3)
    return {
        "ok": True, "seed": seed, "took_ms": took,
        "escalation": {
            "level": esc["level"],
            "max_techniques": esc["max_techniques"],
            "generations": esc["generations"],
            "evaded": evaded, "total": len(cands),
            "mean_detection": mean_det,
            "novel": sum(1 for c in cands if c.get("novel")),
        },
        "ladder": [{"layer": l, "context": c, "probe": p} for l, c, p in _LADDER],
        "candidates": [{**c, "decision": _REVIEWS.get(c["id"])} for c in cands],
        "tally": _tally(),
    }


class Review(BaseModel):
    id: str
    approved: bool


@router.post("/review")
def review(body: Review):
    _REVIEWS[body.id] = body.approved
    c = _find_candidate(body.id)
    outcome, message, blue = "rejected", "", None
    if body.approved and c is not None:
        if c.get("blue_catches"):
            # Blue Team already detects this pattern → don't train on it; Red must improve.
            outcome = "blue_catches"
            blue = {"verdict": c["native"]["verdict"], "risk": c["native"]["risk"],
                    "signal": c["hardened"]["signal"]}
            message = (f"Blue Team already flags this as {c['native']['verdict']} "
                       f"— pointless to train on. Red Team must improve its attack.")
        elif c.get("garbage"):
            outcome = "garbage"
            message = "not a real on-graph evasion — not added to the Blue corpus."
        else:
            outcome = "trained"
            blue = {"verdict": c["native"]["verdict"], "risk": c["native"]["risk"], "signal": None}
            message = "added to the Blue corpus — a real evasion the deployed Blue couldn't catch."
    elif body.approved:
        outcome, message = "trained", "added to the Blue corpus."
    return {"ok": True, "id": body.id, "approved": body.approved,
            "outcome": outcome, "message": message, "blue": blue, "tally": _tally()}


@router.post("/reset")
def reset():
    _REVIEWS.clear()
    _SEEN_TECHNIQUES.clear()          # restart the escalation/novelty memory
    _STATE.pop("last_train", None)
    return {"ok": True, "tally": _tally()}


@router.post("/auto_reject")
def auto_reject(seed: int = 0):
    """Reject every garbage candidate in one click (the obvious bulk action)."""
    cands, _ = _STATE.get("cand_cache", {}).get(seed, ([], 0))
    n = 0
    for c in cands:
        if c["garbage"] and _REVIEWS.get(c["id"]) is not True:
            _REVIEWS[c["id"]] = False
            n += 1
    return {"ok": True, "auto_rejected": n, "tally": _tally()}


def _train_world():
    """Held-out benign (negatives + FP) and real fraud (reflag), with analyses cached."""
    if "train_world" not in _STATE:
        from adversarial.red_team.graph_generator import make_base_attacks, make_benign_corpus
        from adversarial.self_play.detector_hardener import cluster_features
        engine = _state()["htb"].engine
        benign = make_benign_corpus(seed=71, n=60, realistic=True, registry=_state()["world"].behav_reg)
        fraud = [c for ag in make_base_attacks(seed=99) for c in ag.components]
        benign_an = [engine.analyze_component(c) for c in benign]
        _STATE["train_world"] = {
            "fraud_an": [engine.analyze_component(c) for c in fraud],
            "benign_an": benign_an,
            "neg_feats": [cluster_features(a) for a in benign_an[:40]],
            "fp_an": benign_an[40:],
        }
    return _STATE["train_world"]


_THR = 0.62


def _eval_corpus(ids: list[str]):
    """Fit the Blue calibration on the given approved ids and score it. None if too small."""
    from adversarial.self_play.detector_hardener import FactorCalibrationHardener, cluster_features
    engine = _state()["htb"].engine
    comps = _STATE.get("components", {})
    pos = [cluster_features(engine.analyze_component(c))
           for cid in ids for c in comps.get(cid, []) if len(c.get("edges", [])) >= 1]
    if len(pos) < 3:
        return None
    tw = _train_world()
    cal = FactorCalibrationHardener().fit(pos, tw["neg_feats"])
    reflag = sum(1 for a in tw["fraud_an"] if cal.prob(a) >= _THR) / max(1, len(tw["fraud_an"]))
    fp = sum(1 for a in tw["fp_an"] if cal.prob(a) >= _THR) / max(1, len(tw["fp_an"]))
    return {"fragments": len(pos), "reflag": round(reflag, 3),
            "benign_fp": round(fp, 3), "quality": round(reflag - fp, 3)}


@router.post("/train")
def train():
    """Train the Blue calibration ONLY on data the deployed Blue couldn't catch (real,
    on-graph evasions), and contrast it with naively training on everything approved. The
    delta shows why feeding Blue the attacks it already catches is pointless — they add no
    signal and only cost false positives."""
    approved = [cid for cid, ok in _REVIEWS.items() if ok]
    cand_by = {c["id"]: c for (cl, _) in _STATE.get("cand_cache", {}).values() for c in cl}
    trainable = [cid for cid in approved if cand_by.get(cid, {}).get("trainable")]
    n_caught = sum(1 for cid in approved if cand_by.get(cid, {}).get("blue_catches"))
    n_garbage = sum(1 for cid in approved
                    if cand_by.get(cid, {}).get("garbage")
                    and not cand_by.get(cid, {}).get("blue_catches"))
    n_real = len(trainable)

    current = _eval_corpus(approved)         # naive: everything the human approved
    if current is None:
        return {"ok": False, "msg": "approve at least a few graphs (YES) before training Blue."}
    clean = _eval_corpus(trainable)          # curated: only what Blue couldn't catch

    delta = None
    if clean is not None and (n_caught + n_garbage) > 0:
        delta = {"benign_fp": round(clean["benign_fp"] - current["benign_fp"], 3),
                 "quality": round(clean["quality"] - current["quality"], 3)}

    excl = []
    if n_caught:
        excl.append(f"{n_caught} Blue already catches (Red must improve)")
    if n_garbage:
        excl.append(f"{n_garbage} garbage")

    if not excl:
        msg = "corpus is already clean — every approval is a real evasion Blue couldn't catch."
    elif clean is None:
        msg = (f"excluded {', '.join(excl)}; approve a few real evasions Blue couldn't catch "
               f"to train on.")
    else:
        msg = (f"training Blue on {n_real} evasion(s) it couldn't catch — excluded "
               f"{', '.join(excl)}: benign FP {int(current['benign_fp']*100)}% → "
               f"{int(clean['benign_fp']*100)}%, quality {current['quality']:+.2f} → "
               f"{clean['quality']:+.2f}")

    result = {"ok": True, "approved": len(approved), "real": n_real,
              "caught": n_caught, "garbage": n_garbage,
              "current": current, "clean": clean, "delta": delta, "msg": msg}
    _STATE["last_train"] = result
    return result


# ── Training Queue / governance (human-in-the-loop) ─────────────────────────────
# The ONLY path into the Blue Knowledge Base. Blue MISSES are queued by /attacks;
# an investigator reviews each and decides. Detected attacks never appear here.

@router.get("/training/queue")
def training_queue(status: str | None = None):
    """Pending (or filtered) training cases — Blue misses awaiting investigator review."""
    return {"ok": True, "cases": _gov.list(status), "stats": _gov.stats()}


@router.get("/training/audit")
def training_audit(limit: int = 100):
    """Immutable learning audit trail — every enqueue/decision, who and when."""
    return {"ok": True, "audit": _gov.audit(limit), "stats": _gov.stats()}


@router.get("/training/similar")
def training_similar(case_id: str):
    """Existing cases that match (dedup) — same signature or close technique set."""
    return {"ok": True, "case_id": case_id, "similar": _gov.similar(case_id)}


class TrainingDecision(BaseModel):
    case_id: str
    action: str                       # learn | reject | archive | ignore | review
    investigator: str = "investigator"


@router.post("/training/decide")
def training_decide(body: TrainingDecision):
    """Apply an investigator decision. 'learn' is the ONLY action that adds to the
    Blue Knowledge Base (deduped + audited); it also flags the underlying candidate
    approved so the existing /train corpus picks it up. reject/ignore/archive discard."""
    res = _gov.decide(body.case_id, body.action, body.investigator)
    if not res.get("ok"):
        return res
    case = res["case"]
    act = body.action.lower()
    # Keep the legacy approval corpus (_REVIEWS) in lock-step with governance so the
    # real Blue calibration in /train only ever sees investigator-approved evasions.
    cand_id = case.get("candidate_id")
    if cand_id:
        if act in ("learn", "approve"):
            _REVIEWS[cand_id] = True
        elif act in ("reject", "ignore", "archive"):
            _REVIEWS[cand_id] = False
    return {**res, "tally": _tally()}


@router.post("/training/reset")
def training_reset():
    """Clear the training queue, knowledge base, and audit trail (demo reset)."""
    _gov.reset()
    return {"ok": True, "stats": _gov.stats()}
