"""
Entity resolution — link accounts that share a fingerprint into a single
real-world entity, even across banks and account numbers. Union-Find over the
shared (device / phone / pan / email / upi) fingerprints.

Pure: operates on the fingerprint map; returns cluster membership. No mutation.
"""
from __future__ import annotations

from typing import Dict, List

from .fingerprints import all_fingerprints
from .schemas import AccountFingerprint


class _UnionFind:
    def __init__(self):
        self.parent: Dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # deterministic: lexicographically smaller root wins
            lo, hi = (ra, rb) if ra < rb else (rb, ra)
            self.parent[hi] = lo


def resolve_entities(fingerprints: Dict[str, AccountFingerprint]) -> Dict[str, List[str]]:
    """account_id → sorted list of accounts in its resolved entity (incl. itself).
    Accounts are linked when they share ANY device/phone/pan/email/upi fingerprint."""
    uf = _UnionFind()
    for acct in fingerprints:
        uf.find(acct)

    # map each fingerprint value → the accounts that carry it, then union them
    fp_to_accounts: Dict[str, List[str]] = {}
    for acct, fp in fingerprints.items():
        for kind, value in all_fingerprints(fp):
            key = f"{kind}:{value}".upper()
            fp_to_accounts.setdefault(key, []).append(acct)
    for accounts in fp_to_accounts.values():
        for other in accounts[1:]:
            uf.union(accounts[0], other)

    clusters: Dict[str, List[str]] = {}
    for acct in fingerprints:
        root = uf.find(acct)
        clusters.setdefault(root, []).append(acct)

    return {acct: sorted(clusters[uf.find(acct)]) for acct in fingerprints}


def shared_fingerprint_index(fingerprints: Dict[str, AccountFingerprint],
                             bucket: str) -> Dict[str, List[str]]:
    """fingerprint value (in `bucket`, e.g. 'devices') → accounts carrying it,
    restricted to values shared by ≥2 accounts. Used to surface shared devices/phones."""
    idx: Dict[str, List[str]] = {}
    for acct, fp in fingerprints.items():
        for v in fp.get(bucket, []):
            idx.setdefault(str(v), []).append(acct)
    return {v: sorted(set(accts)) for v, accts in idx.items() if len(set(accts)) >= 2}
