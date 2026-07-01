"""
Cross-Bank Intelligence Engine — the orchestrator.

`analyze_component(component, entity_context)` reads a READ-ONLY component snapshot
(the exact dict TGIE already produces) plus the per-session entity_context and
returns a CrossBankReport of intelligence ONLY. It NEVER mutates the component,
creates nodes/edges, or touches layout — the graph engine does not know it exists.

Pipeline: fingerprints → entity resolution → external (registry) signals →
velocity/profile correlation → money-flow bank patterns → per-account mule scoring →
component aggregate. Defensive: any failure degrades to an empty (available=False)
report so the Blue Team path can never break.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .entity_resolution import resolve_entities, shared_fingerprint_index
from .external_signals import external_signals
from .fingerprints import build_fingerprints
from .mule_scoring import component_risk, score_account
from .profile_correlation import same_device_different_names, same_merchant_across_banks
from .risk_registry import CrossBankRiskRegistry, get_registry
from .schemas import CrossBankReport, band_for, empty_report
from .velocity_engine import detect_velocity_signals


def _bank_of(fingerprints) -> Dict[str, str]:
    return {a: fp.get("bank") for a, fp in fingerprints.items()}


def _chains(edges: List[dict]) -> List[List[str]]:
    """Longest forwarding chains (bounded DFS) for multi-bank-layering detection."""
    succ: Dict[str, List[str]] = {}
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s is not None and t is not None and s != t:
            succ.setdefault(str(s), []).append(str(t))
    paths: List[List[str]] = []

    def dfs(node: str, path: List[str], seen: set, depth: int):
        if depth > 8:
            paths.append(path[:]); return
        nxt = [c for c in succ.get(node, []) if c not in seen]
        if not nxt:
            paths.append(path[:]); return
        for c in nxt:
            dfs(c, path + [c], seen | {c}, depth + 1)

    sources = [n for n in succ] or []
    for s in sorted(set(sources)):
        dfs(s, [s], {s}, 0)
    return paths


def _detect_flow_patterns(component: Dict[str, Any], fingerprints) -> tuple[List[str], int]:
    """Money-flow patterns that span MULTIPLE banks. Returns (patterns, boost)."""
    edges = [e for e in (component.get("edges") or []) if isinstance(e, dict)]
    bank_of = _bank_of(fingerprints)
    patterns: set[str] = set()
    boost = 0

    out_targets: Dict[str, List[str]] = {}
    in_sources: Dict[str, List[str]] = {}
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s is None or t is None:
            continue
        out_targets.setdefault(str(s), []).append(str(t))
        in_sources.setdefault(str(t), []).append(str(s))

    # multi-bank fan-out / fan-in (banks of the recipients / senders)
    for src, tgts in out_targets.items():
        banks = {bank_of.get(t) for t in tgts if bank_of.get(t)}
        if len(tgts) >= 4 and len(banks) >= 3:
            patterns.add("multi_bank_fanout"); boost = max(boost, 10)
    for sink, srcs in in_sources.items():
        banks = {bank_of.get(s) for s in srcs if bank_of.get(s)}
        if len(srcs) >= 4 and len(banks) >= 3:
            patterns.add("multi_bank_fanin"); boost = max(boost, 10)

    # multi-bank layering: a forwarding chain whose accounts span ≥3 distinct banks
    for path in _chains(edges):
        banks = [bank_of.get(n) for n in path if bank_of.get(n)]
        if len(path) >= 3 and len(set(banks)) >= 3:
            patterns.add("multi_bank_layering"); boost = max(boost, 12)
            break

    # cross-bank circular routing: a cycle whose accounts span ≥3 banks
    try:
        import networkx as nx
        G = nx.DiGraph()
        for e in edges:
            if e.get("source") is not None and e.get("target") is not None:
                G.add_edge(str(e["source"]), str(e["target"]))
        for cyc in nx.simple_cycles(G):
            if len(cyc) >= 3 and len({bank_of.get(n) for n in cyc if bank_of.get(n)}) >= 3:
                patterns.add("cross_bank_circular"); boost = max(boost, 14)
                break
    except Exception:
        pass

    return sorted(patterns), boost


def analyze_component(component: Optional[Dict[str, Any]],
                      entity_context: Optional[Dict[str, Any]] = None,
                      registry: Optional[CrossBankRiskRegistry] = None) -> CrossBankReport:
    try:
        if not component:
            return empty_report()
        reg = registry or get_registry()
        fingerprints = build_fingerprints(component, entity_context)
        if not fingerprints:
            return empty_report()

        clusters = resolve_entities(fingerprints)
        ext = external_signals(fingerprints, reg)
        velocity = detect_velocity_signals(component, fingerprints)
        shared_dev = shared_fingerprint_index(fingerprints, "devices")
        shared_phone = shared_fingerprint_index(fingerprints, "phones")
        dev_names = same_device_different_names(fingerprints)
        merch_banks = same_merchant_across_banks(fingerprints)
        bank_of = _bank_of(fingerprints)

        # how many shared devices/phones each account participates in
        def _shared_count(acct: str, idx: Dict[str, List[str]]) -> int:
            return sum(1 for accts in idx.values() if acct in accts)

        accounts = {}
        for acct, fp in fingerprints.items():
            cluster = clusters.get(acct, [acct])
            linked_banks = len({bank_of.get(a) for a in cluster if bank_of.get(a)}
                               | set(ext[acct].get("banks_seen", [])))
            accounts[acct] = score_account(
                account=acct,
                linked_accounts=cluster,
                linked_banks=linked_banks,
                shared_devices=_shared_count(acct, shared_dev),
                shared_phones=_shared_count(acct, shared_phone),
                external=ext[acct],
                velocity_reasons=velocity.get(acct, []),
            )

        # component-level patterns
        patterns, boost = _detect_flow_patterns(component, fingerprints)
        if shared_dev and any(len({bank_of.get(a) for a in accts if bank_of.get(a)}) >= 2
                              for accts in shared_dev.values()):
            patterns.append("same_device_multi_bank"); boost = max(boost, 10)
        if any(len(accts) >= 3 for accts in shared_phone.values()):
            patterns.append("same_phone_multiple_accounts"); boost = max(boost, 8)
        if dev_names:
            patterns.append("same_device_different_names"); boost = max(boost, 10)
        if merch_banks:
            patterns.append("same_merchant_across_banks"); boost = max(boost, 8)
        if any("dormant_activation" in v for v in velocity.values()):
            patterns.append("dormant_activation"); boost = max(boost, 10)
        if any(a["known_suspicious"] for a in accounts.values()):
            patterns.append("known_suspicious_entity")
        patterns = sorted(set(patterns))

        banks_involved = sorted({b for b in bank_of.values() if b}
                                | {b for s in ext.values() for b in s.get("banks_seen", [])})
        risk = component_risk(accounts, boost)
        known_count = sum(1 for a in accounts.values() if a["known_suspicious"])
        top = max(accounts.values(), key=lambda a: a["cross_bank_risk"], default=None)

        explanation = None
        if risk >= 45 and top:
            bits = []
            if len(banks_involved) >= 2:
                bits.append(f"activity spans {len(banks_involved)} banks")
            if known_count:
                bits.append(f"{known_count} fingerprint(s) known to other banks")
            if patterns:
                bits.append("patterns: " + ", ".join(patterns[:3]))
            explanation = ("Cross-bank intelligence: " + "; ".join(bits) + ".") if bits else None

        available = risk > 0 or len(banks_involved) > 1 or bool(patterns)
        return {
            "available": available,
            "cross_bank_risk": risk,
            "band": band_for(risk),
            "linked_banks": len(banks_involved),
            "linked_accounts": max((a["linked_accounts"] for a in accounts.values()), default=0),
            "shared_devices": len(shared_dev),
            "shared_phone_numbers": len(shared_phone),
            "known_suspicious_entities": known_count,
            "banks_involved": banks_involved,
            "cross_bank_patterns": patterns,
            "accounts": accounts,
            "explanation": explanation,
        }
    except Exception:
        return empty_report()
