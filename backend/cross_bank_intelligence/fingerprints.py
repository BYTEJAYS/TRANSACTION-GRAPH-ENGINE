"""
Fingerprint extraction — per-account identity fingerprints from the read-only
component snapshot + the per-session entity_context. Fraudsters reuse fingerprints
(device / phone / PAN / UPI / email / KYC name / merchant), not account numbers.

Pure reader: takes the component dict TGIE already builds (+ optional entity_context)
and returns a per-account fingerprint map. Never mutates either input.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .schemas import AccountFingerprint, DEFAULT_BANK

# entity_context link relation → fingerprint bucket
_REL_TO_BUCKET = {
    "HAS_DEVICE": "devices",
    "HAS_PHONE": "phones",
    "HAS_PAN": "pans",
    "HAS_EMAIL": "emails",
    "HAS_UPI": "upi_handles",
}


def _add(d: Dict[str, AccountFingerprint], acct: str) -> AccountFingerprint:
    fp = d.get(acct)
    if fp is None:
        fp = {"account": acct, "bank": DEFAULT_BANK, "devices": [], "phones": [],
              "pans": [], "emails": [], "upi_handles": [], "names": [], "merchants": []}
        d[acct] = fp
    return fp


def _push(fp: AccountFingerprint, bucket: str, value: Any) -> None:
    if value is None:
        return
    v = str(value)
    if v and v not in fp[bucket]:
        fp[bucket].append(v)


def build_fingerprints(component: Dict[str, Any],
                       entity_context: Optional[Dict[str, Any]] = None) -> Dict[str, AccountFingerprint]:
    """account_id → AccountFingerprint. Sources, in precedence:
      1. entity_context.banks / .links / .owns  (declared KYC + device intel)
      2. component edges' device_id            (live transaction device)
    """
    out: Dict[str, AccountFingerprint] = {}

    nodes = component.get("nodes") or []
    node_ids = component.get("node_ids") or [n.get("id") for n in nodes if isinstance(n, dict)]
    for nid in node_ids:
        if nid:
            _add(out, str(nid))

    ec = entity_context or {}
    banks = ec.get("banks") or {}
    owns = ec.get("owns") or {}           # account → customer (name)
    links = ec.get("links") or []         # [account, identity, rel]

    # bank assignment (default UNION_BANK)
    for acct, bank in banks.items():
        _add(out, str(acct))["bank"] = str(bank) if bank else DEFAULT_BANK
    # KYC owning customer = a name fingerprint
    for acct, cust in owns.items():
        _push(_add(out, str(acct)), "names", cust)
    # device / phone / pan / email / upi links
    for link in links:
        if not isinstance(link, (list, tuple)) or len(link) < 3:
            continue
        acct, ident, rel = str(link[0]), link[1], str(link[2]).upper()
        bucket = _REL_TO_BUCKET.get(rel)
        if bucket:
            _push(_add(out, acct), bucket, ident)

    # live transaction device_id carried on edges (and any per-edge merchant)
    for e in component.get("edges") or []:
        if not isinstance(e, dict):
            continue
        dev = e.get("device_id")
        if dev and str(dev).upper() not in ("MANUAL", ""):
            for endpoint in (e.get("source"), e.get("target")):
                if endpoint:
                    _push(_add(out, str(endpoint)), "devices", dev)
        merch = e.get("merchant") or e.get("merchant_id")
        if merch and e.get("target"):
            _push(_add(out, str(e["target"])), "merchants", merch)

    # node-level bank/merchant hints if the snapshot carries them (optional)
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id"))
        if not nid or nid not in out:
            continue
        if n.get("bank_id"):
            out[nid]["bank"] = str(n["bank_id"])
        if n.get("account_type") == "merchant":
            _push(out[nid], "merchants", nid)

    return out


def all_fingerprints(fp: AccountFingerprint) -> List[tuple[str, str]]:
    """Flatten one account's fingerprints to (kind, value) pairs for registry lookup."""
    pairs: List[tuple[str, str]] = []
    for kind, bucket in (("device", "devices"), ("phone", "phones"), ("pan", "pans"),
                         ("email", "emails"), ("upi", "upi_handles")):
        for v in fp.get(bucket, []):
            pairs.append((kind, v))
    return pairs
