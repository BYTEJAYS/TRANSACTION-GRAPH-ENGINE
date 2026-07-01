"""
Attack-graph representation, the laundering objective, and a distortion metric.

An *operation* is one laundering scheme. On the wire the Blue Team only ever sees
individual connected components, so an attack may legitimately decompose a single
scheme into several disconnected components (the dominant evasion, B1 in the
white-box report). We therefore model an AttackGraph as a *list of components*
that together realise one objective.

The objective is defined at the OPERATION level (the union of all components):
the scheme must still move ≈ target_value out of the source accounts and into the
sink accounts, anywhere across the operation. This is what makes "minimal
distortion subject to objective preserved" a well-posed optimisation: transforms
that quietly drop the laundering goal are infeasible, not merely low-scoring.
"""
from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass, field, replace
from typing import Any, Iterable

# ── component helpers (a component is the TGiE dict schema) ───────────────────
Component = dict[str, Any]


def _all_edges(components: list[Component]) -> Iterable[dict]:
    for c in components:
        yield from c.get("edges", [])


def _all_node_ids(components: list[Component]) -> set[str]:
    ids: set[str] = set()
    for c in components:
        for n in c.get("nodes", []):
            if "id" in n:
                ids.add(n["id"])
        for e in c.get("edges", []):
            ids.add(str(e.get("source", "")))
            ids.add(str(e.get("target", "")))
    ids.discard("")
    return ids


@dataclass
class AttackObjective:
    """The invariant the laundering scheme must preserve to remain 'the fraud'."""
    sources: set[str]                 # accounts injecting illicit value
    sinks: set[str]                   # accounts where value must arrive (cash-out/terminal)
    target_value: float               # total illicit value to move
    tolerance: float = 0.15           # allowed shortfall fraction

    def value_out_of_sources(self, components: list[Component]) -> float:
        return sum(float(e.get("amount", 0) or 0)
                   for e in _all_edges(components)
                   if str(e.get("source", "")) in self.sources)

    def value_into_sinks(self, components: list[Component]) -> float:
        return sum(float(e.get("amount", 0) or 0)
                   for e in _all_edges(components)
                   if str(e.get("target", "")) in self.sinks)

    def satisfied(self, components: list[Component]) -> bool:
        floor = self.target_value * (1.0 - self.tolerance)
        ids = _all_node_ids(components)
        if not self.sources <= ids or not self.sinks <= ids:
            return False
        return (self.value_out_of_sources(components) >= floor
                and self.value_into_sinks(components) >= floor)

    def shortfall(self, components: list[Component]) -> float:
        """0 = objective fully met; 1 = nothing delivered."""
        if self.target_value <= 0:
            return 0.0
        delivered = min(self.value_out_of_sources(components),
                        self.value_into_sinks(components))
        return max(0.0, min(1.0, 1.0 - delivered / self.target_value))

    # ── strict (on-graph) feasibility ─────────────────────────────────────────
    def value_into_connected_sinks(self, components: list[Component]) -> float:
        """Inflow only to sinks REACHABLE from a source within the same component.

        The permissive ``satisfied`` check credits source-outflow and sink-inflow
        independently, so cross_component_split can sever the middle of a scheme
        into singletons and still "preserve the objective" (modelling off-graph
        completion). This stricter accounting requires an actual directed path
        source→sink on the realized graph, isolating how much of an evasion's
        success depends on that off-graph-completion assumption.
        """
        total = 0.0
        for c in components:
            edges = c.get("edges", [])
            adj: dict[str, set[str]] = {}
            present: set[str] = set()
            for e in edges:
                s, t = str(e.get("source", "")), str(e.get("target", ""))
                adj.setdefault(s, set()).add(t)
                present.add(s); present.add(t)
            comp_sources = self.sources & present
            comp_sinks = self.sinks & present
            if not comp_sources or not comp_sinks:
                continue
            reach: set[str] = set()
            stack = list(comp_sources)
            while stack:
                u = stack.pop()
                for v in adj.get(u, ()):
                    if v not in reach:
                        reach.add(v); stack.append(v)
            connected = comp_sinks & reach
            if connected:
                total += sum(float(e.get("amount", 0) or 0) for e in edges
                             if str(e.get("target", "")) in connected)
        return total

    def on_graph_satisfied(self, components: list[Component]) -> bool:
        """Strict feasibility: value must reach sinks along a connected on-graph
        path from a source (no off-graph-completion credit)."""
        floor = self.target_value * (1.0 - self.tolerance)
        return self.value_into_connected_sinks(components) >= floor


@dataclass
class AttackGraph:
    """A mutable laundering operation: ≥1 components realising one objective."""
    components: list[Component]
    objective: AttackObjective
    # lineage / bookkeeping
    attack_id: str = ""
    parent_ids: list[str] = field(default_factory=list)
    generation: int = 0
    genome_repr: str = ""
    archetype: str = ""

    _ids = itertools.count(1)

    def __post_init__(self) -> None:
        if not self.attack_id:
            self.attack_id = f"atk_{next(self._ids):07d}"

    def clone(self) -> "AttackGraph":
        return AttackGraph(
            components=copy.deepcopy(self.components),
            objective=replace(self.objective,
                              sources=set(self.objective.sources),
                              sinks=set(self.objective.sinks)),
            attack_id="",  # fresh id for the child
            parent_ids=[self.attack_id],
            generation=self.generation + 1,
            archetype=self.archetype,
        )

    # ── convenience ──
    def num_components(self) -> int:
        return len(self.components)

    def num_nodes(self) -> int:
        return len(_all_node_ids(self.components))

    def num_edges(self) -> int:
        return sum(len(c.get("edges", [])) for c in self.components)

    def all_node_ids(self) -> set[str]:
        return _all_node_ids(self.components)

    def objective_satisfied(self) -> bool:
        return self.objective.satisfied(self.components)

    def on_graph_satisfied(self) -> bool:
        """Strict feasibility: an on-graph source→sink path still carries value."""
        return self.objective.on_graph_satisfied(self.components)


# ── distortion metric ─────────────────────────────────────────────────────────
def _edge_key(e: dict) -> tuple[str, str]:
    return (str(e.get("source", "")), str(e.get("target", "")))


def distortion(original: AttackGraph, mutated: AttackGraph) -> float:
    """
    Normalised structural distance in [0,1]: how far the mutated operation has
    drifted from the original fraud graph. Lower = stealthier / more realistic.

    Blends four churn terms: node set, edge set, amount drift on surviving edges,
    and component fragmentation. Component fragmentation is intentionally cheap
    (the partition attack is supposed to be low-distortion) but non-zero.
    """
    o_nodes, m_nodes = original.all_node_ids(), mutated.all_node_ids()
    o_edges = list(_all_edges(original.components))
    m_edges = list(_all_edges(mutated.components))

    n_base = max(1, len(o_nodes))
    e_base = max(1, len(o_edges))

    node_churn = (len(o_nodes - m_nodes) + len(m_nodes - o_nodes)) / n_base

    o_emap: dict[tuple[str, str], float] = {}
    for e in o_edges:
        o_emap[_edge_key(e)] = o_emap.get(_edge_key(e), 0.0) + float(e.get("amount", 0) or 0)
    m_emap: dict[tuple[str, str], float] = {}
    for e in m_edges:
        m_emap[_edge_key(e)] = m_emap.get(_edge_key(e), 0.0) + float(e.get("amount", 0) or 0)

    added = set(m_emap) - set(o_emap)
    removed = set(o_emap) - set(m_emap)
    edge_churn = (len(added) + len(removed)) / e_base

    surviving = set(o_emap) & set(m_emap)
    if surviving:
        drift = sum(abs(m_emap[k] - o_emap[k]) / max(1.0, o_emap[k]) for k in surviving)
        amount_drift = min(1.0, drift / len(surviving))
    else:
        amount_drift = 0.0

    frag = (mutated.num_components() - original.num_components()) / max(1, mutated.num_nodes())
    frag = max(0.0, min(1.0, frag))

    score = 0.40 * node_churn + 0.35 * edge_churn + 0.20 * amount_drift + 0.05 * frag
    return float(max(0.0, min(1.0, score)))
