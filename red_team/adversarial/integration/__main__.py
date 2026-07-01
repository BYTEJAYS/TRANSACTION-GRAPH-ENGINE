"""
Local end-to-end demo: the hardened Blue Team, connected to the REAL blue_team_v2 engine.

Generates real laundering operations with the Red arsenal and real benign traffic, then runs BOTH
the deployed blue_team_v2 verdict and the context-hardened verdict on each — side by side — so you
can see, locally, exactly what the §16–§21 signals add to the shipped engine.

Run:  cd <repo> && backend/.venv/bin/python -m adversarial.integration
"""
from __future__ import annotations

import random

from .hardened_blue_team import HardenedBlueTeam, default_world
from ..red_team import agents as _agents
from ..red_team.base import Move, apply_genome
from ..red_team.evolutionary_engine.engine import stable_seed
from ..red_team.graph_generator import make_base_attacks


def _native_op(components):
    from blue_team_v2.adapter import analyze_component_sync
    order = {"CLEAN": 0, "LOGGED": 1, "SUSPICIOUS": 2, "FRAUD": 3}
    vs = [analyze_component_sync(c) for c in components]
    worst = max((v["verdict"] for v in vs), key=lambda v: order.get(v, 3), default="CLEAN")
    return worst, max((v["risk_score"] for v in vs), default=0.0)


def _row(name, lv, lr, rv, rr, note, good_when_clean=False):
    raised = rv in ("FRAUD", "SUSPICIOUS")
    mark = ("✓ cleared" if not raised else "✗ flagged") if good_when_clean \
        else ("🚨 CAUGHT" if raised else "· missed")
    print(f"  {name:<32} {lv:<10} {lr:>4.2f}   →   {rv:<10} {rr:>4.2f}   {mark}   {note}")


def main():
    world = default_world()
    htb = HardenedBlueTeam(world, maturity=True)
    breg = world.behav_reg
    base = {b.archetype: b for b in make_base_attacks(seed=42)}

    print(f"\n{'='*100}")
    print(" HARDENED BLUE TEAM — connected to the real blue_team_v2 engine, run locally")
    print(f" world: {len(world.profiles)} KYC customers · {max(world.circles.values())+1} relationship circles")
    print(f"{'='*100}")

    # ════ 1. DEPLOYED ENGINE vs HARDENED — sensitivity AND specificity ════
    print(f"\n  [1] DEPLOYED blue_team_v2   →   HARDENED        (same engine, same V1 schema)\n")

    # (a) the conduit_split mule mesh — native MISSES it, coordination catches it
    hh = [c for c, p in world.profiles.items()
          if p.segment in ("household", "retail") and p.establishment >= 0.7][:400]
    _agents.set_compromised_accounts(hh, {a: breg.baseline_throughput(a) for a in hh})
    mesh = apply_genome(base["layering"], [Move("conduit_split", 0.9)], random.Random(stable_seed("mesh")))
    nv, nr = _native_op(mesh.components)
    op = htb.analyze_operation(mesh.components)
    print("   laundering the deployed engine misses:")
    _row("conduit_split mule mesh", nv, nr, op["operation_verdict"], op["coordination_risk"],
         "← coordination: hub-less linked crowd")

    # (b) legitimate traffic native OVER-flags — hardening clears it (the provenance FP-fix)
    from ..common.relationships import make_circle_benign_corpus
    benign = make_circle_benign_corpus(breg, world.rel_reg, n=6, seed=23)
    labels = ["payroll run", "merchant collection", "corporate supplier run",
              "household transfers", "retail mix", "legit fan-out"]
    print("\n   legitimate traffic the deployed engine over-flags (hardening must clear):")
    from blue_team_v2.adapter import analyze_component_sync
    for lab, comp in zip(labels, benign):
        nv = analyze_component_sync(comp)
        hv = htb.analyze_component(comp)
        _row(lab, nv["verdict"], nv["risk_score"], hv["verdict"], hv["risk_score"],
             "", good_when_clean=True)

    # ════ 2. THE §17-C RESIDUAL — provenance opens it, relationship closes it ════
    print(f"\n  [2] THE CORPORATE-SEIZURE RESIDUAL     FP-fixed stack (prov+behav)  →  + relationship\n")
    corp = breg.segment_ids("corporate", "sme")[:120]
    _agents.set_compromised_accounts(corp)
    ato = apply_genome(base["cashout_network"],
                       [Move("account_takeover", 0.9), Move("cross_component_split", 0.9)],
                       random.Random(stable_seed("corp")))
    comp = max(ato.components, key=lambda c: len(c.get("edges", [])))
    hv = htb.analyze_component(comp)
    h = hv["hardening"]
    print("   account-takeover routed through SEIZED VERIFIED CORPORATE accounts:")
    _row("corporate account-takeover", h["pre_relationship_verdict"], h["pre_relationship_risk"],
         hv["verdict"], h["hardened_risk"], "← relationship: pays verified strangers")
    print(f"\n   why: native blue_team_v2 = {h['native_verdict']} ({h['native_risk']:.2f}) — flags it structurally,")
    print(f"        but provenance correctly CLEARS verified accounts (unverified_ratio {h['provenance_unverified_ratio']:.2f})")
    print(f"        and the corporate baseline absorbs the volume (conduit_anomaly {h['behavioural_conduit_anomaly']:.2f}),")
    print(f"        so the FP-fixed stack drops to {h['pre_relationship_verdict']} ({h['pre_relationship_risk']:.2f}) — the §17-C hole.")
    print(f"        relationship sees verified STRANGERS (novel_ratio {h['relationship_novel_ratio']:.2f}) → back to {hv['verdict']}.")

    print(f"\n{'-'*100}")
    print(" Same engine, same V1 verdict schema — graph rendering / risk badges / API unchanged. The")
    print(" hardened path is MORE sensitive (catches the mesh native misses) AND more specific (clears")
    print(" legit traffic native over-flags), and closes the residual it opens. blue_team_v2 is untouched;")
    print(" the hardening WRAPS it — `HardenedBlueTeam(world).analyze_component(...)` is the drop-in.\n")


if __name__ == "__main__":
    main()
