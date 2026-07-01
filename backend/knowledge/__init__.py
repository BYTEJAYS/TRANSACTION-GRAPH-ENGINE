"""
Union Bank cross-product knowledge layer.

A reusable banking-intelligence package (products, channels, fraud typologies,
recovery playbooks, regulatory mapping, entity taxonomy and the XP cross-product
rule family) that the Blue Team, rule/recommendation/recovery engines, case
intelligence and narratives reference instead of re-encoding the same facts.
Additive and backward-compatible — importing it changes nothing until a caller
chooses to consult it.
"""
from .entities import (
    EntityType,
    RelationshipType,
    ProductCategory,
    classify_entity,
    classify_node,
    classify_edge,
    involved_categories,
)
from .xp_rules import XP_RULES, detect_xp_signals
from .knowledge_base import KB, KnowledgeBase, cross_product_report
from .hetero import HeteroGraph, is_transaction_edge
from .customer_risk import compute_customer_risk
from .ingest import augment_component, record_account, empty_context
from . import scenarios

__all__ = [
    "EntityType", "RelationshipType", "ProductCategory",
    "classify_entity", "classify_node", "classify_edge", "involved_categories",
    "XP_RULES", "detect_xp_signals",
    "KB", "KnowledgeBase", "cross_product_report",
    "HeteroGraph", "is_transaction_edge",
    "compute_customer_risk", "scenarios",
    "augment_component", "record_account", "empty_context",
]
