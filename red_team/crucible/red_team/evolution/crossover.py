from __future__ import annotations
"""
Crossover — breed two fraud genomes into a hybrid that combines fraud families.

Genome genes are independent dataclasses (topology / timing / amounts / channels
/ accounts / special_nodes), so crossover is gene-level recombination: the child
inherits each gene from one parent (uniform crossover), with the structural genes
kept coherent and special-node capabilities UNIONed so hybrids genuinely layer
techniques (e.g. smurfing topology + dormant timing + crypto exit).

The child records both parents in `mutation_history` so lineage/evolution history
stays intact. Amounts are kept integer (locked transaction format); to_transaction_list
tolerates length mismatch via modulo, so genes mix freely.
"""
import copy
import random
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from red_team.core.genome import FraudGenome


def _merge_special_nodes(a, b, dominant):
    """Union the special-node capabilities so the hybrid layers both parents' tricks."""
    sn = copy.deepcopy(dominant.special_nodes)
    for parent in (a.special_nodes, b.special_nodes):
        for attr in ("merchant_nodes", "abandoned_nodes", "bridge_nodes", "exchange_nodes"):
            cur = getattr(sn, attr)
            other = getattr(parent, attr)
            if other.get("count", 0) > cur.get("count", 0):
                setattr(sn, attr, copy.deepcopy(other))
    # Prefer any explicit cash-out exit from either parent.
    sn.cash_out_method = a.special_nodes.cash_out_method or b.special_nodes.cash_out_method
    sn.cash_out_delay_days = max(a.special_nodes.cash_out_delay_days,
                                 b.special_nodes.cash_out_delay_days)
    return sn


def crossover(a: "FraudGenome", b: "FraudGenome",
              rng: random.Random | None = None) -> "FraudGenome":
    """Return a hybrid child of genomes ``a`` and ``b``."""
    rng = rng or random.Random()
    # Structural backbone comes from one parent (keeps topology coherent).
    dominant, recessive = (a, b) if rng.random() < 0.5 else (b, a)
    child = copy.deepcopy(dominant)

    # Uniform crossover on the behavioural genes.
    if rng.random() < 0.5:
        child.timing = copy.deepcopy(recessive.timing)
    if rng.random() < 0.5:
        child.amounts = copy.deepcopy(recessive.amounts)
    if rng.random() < 0.5:
        # Merge channel mixes (renormalised) so the hybrid spans both rails.
        merged: dict[str, float] = {}
        for mix in (a.channels.mix, b.channels.mix):
            for k, v in mix.items():
                merged[k] = merged.get(k, 0.0) + float(v)
        total = sum(merged.values()) or 1.0
        child.channels = copy.deepcopy(dominant.channels)
        child.channels.mix = {k: round(v / total, 4) for k, v in merged.items()}
    if rng.random() < 0.5:
        child.accounts = copy.deepcopy(recessive.accounts)

    child.special_nodes = _merge_special_nodes(a, b, dominant)

    # Lineage / bookkeeping.
    child.genome_id = str(uuid.uuid4())
    child.lineage_id = f"{a.lineage_id}+{b.lineage_id}"
    child.parent_genome_id = dominant.genome_id
    child.generation = max(a.generation, b.generation) + 1
    child.mutation_history = list(dict.fromkeys(
        list(a.mutation_history) + list(b.mutation_history) + ["crossover"]
    ))
    child.fitness_score = 0.0
    child.flags = []
    child.status = "active"
    return child
