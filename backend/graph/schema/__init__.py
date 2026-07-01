"""TGIE banking knowledge-graph schema (Phase 2).

Single source of truth for graph labels, relationships, typed node models, the
Neo4j client, and the idempotent DDL bootstrap. See docs/redesign/PHASE_2_GRAPH_SCHEMA.md.
"""
from .labels import Label, Rel, PII_LABELS, WAVE1_LABELS, DERIVED_RELS  # noqa: F401
from .client import Neo4jClient, get_client  # noqa: F401
