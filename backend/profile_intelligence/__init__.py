"""
Profile Intelligence — makes TGIE understand WHO the customer is, not just what
transaction occurred. The Blue Team evaluates behaviour relative to the customer's
profile and baseline instead of one-size-fits-all thresholds, cutting false positives
for legitimate high-volume customers while keeping fraud explainable.

Public API:
    assess_component(component, explicit_profiles=None) -> dict
    PROFILES / all_profiles() / get_profile(key)
"""
from .engine import AccountFeatures, assess_component, evaluate, extract_features, infer_profile
from .profiles import PROFILES, CustomerProfile, all_profiles, get_profile

__all__ = [
    "assess_component", "extract_features", "infer_profile", "evaluate",
    "AccountFeatures", "PROFILES", "CustomerProfile", "all_profiles", "get_profile",
]
