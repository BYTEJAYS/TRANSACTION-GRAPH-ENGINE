"""
Detector contract + small shared helpers.

Every detector is a module exposing:

    NAME: str
    def detect(tg, metrics, meta) -> list[Evidence]

It receives the built TransactionGraph, the per-node NodeMetrics map, and the
`meta` dict from the risk engine (origins, chain, cycle_nodes, traits).  It must
return *evidence*, not just a score — each Evidence carries the implicated
nodes, a severity, a confidence, and structured supporting data.
"""
from __future__ import annotations

from typing import Callable, Protocol

from ..core.graph_engine.builder import TransactionGraph
from ..types import Evidence, NodeMetrics


class Detector(Protocol):
    NAME: str

    def detect(
        self,
        tg: TransactionGraph,
        metrics: dict[str, NodeMetrics],
        meta: dict,
    ) -> list[Evidence]: ...


DetectFn = Callable[[TransactionGraph, dict, dict], list[Evidence]]
