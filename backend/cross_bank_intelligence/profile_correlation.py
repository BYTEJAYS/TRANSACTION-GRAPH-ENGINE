"""
Profile correlation — cross-bank identity inconsistencies and shared merchants.

  * same_device_different_names : one device, multiple KYC names → synthetic/mule IDs.
  * same_merchant_across_banks  : one merchant collecting via accounts at many banks.

Pure reader over the fingerprint map; no mutation.
"""
from __future__ import annotations

from typing import Dict, List

from .entity_resolution import shared_fingerprint_index
from .schemas import AccountFingerprint


def same_device_different_names(fingerprints: Dict[str, AccountFingerprint]) -> Dict[str, List[str]]:
    """device fingerprint → distinct KYC names attached to it (only where ≥2 names)."""
    shared = shared_fingerprint_index(fingerprints, "devices")
    out: Dict[str, List[str]] = {}
    for device, accounts in shared.items():
        names: set[str] = set()
        for a in accounts:
            names.update(fingerprints[a].get("names", []))
        if len(names) >= 2:
            out[device] = sorted(names)
    return out


def same_merchant_across_banks(fingerprints: Dict[str, AccountFingerprint]) -> Dict[str, List[str]]:
    """merchant → distinct banks it is seen collecting through (only where ≥2 banks)."""
    merchant_banks: Dict[str, set] = {}
    for fp in fingerprints.values():
        for m in fp.get("merchants", []):
            merchant_banks.setdefault(str(m), set()).add(fp.get("bank"))
    return {m: sorted(b for b in banks if b) for m, banks in merchant_banks.items()
            if len({b for b in banks if b}) >= 2}
