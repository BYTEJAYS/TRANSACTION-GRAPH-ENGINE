"""
BELS anchoring + custody for evidence packages (Phase 8).

Reuses case_management/bels_client (which already degrades gracefully — returns
None when BELS :8200 is unreachable). The package's canonical SHA-256 is what gets
anchored, so verification is a pure re-hash + chain check.
"""
from __future__ import annotations

from typing import Any


def anchor_package(package: dict) -> dict:
    """Anchor the package hash in BELS. Mutates+returns package['integrity']['anchor'].
    Never raises — marks 'unanchored' if BELS is down (re-anchor later)."""
    sha = package["integrity"]["sha256"]
    case_id = package["case_id"]
    result: dict[str, Any]
    try:
        from case_management import bels_client
        if not bels_client.healthy():
            result = {"status": "unanchored", "reason": "BELS unreachable (:8200 down)"}
        else:
            rec = bels_client.register(
                file_hash=sha, case_id=case_id,
                filename=f"{package['package_id']}.json", evidence_type="report",
            )
            result = ({"status": "anchored", "evidence_id": rec.get("evidence_id"),
                       "anchor_tx_id": rec.get("anchor_tx_id"),
                       "block_index": rec.get("block_index"),
                       "block_hash": rec.get("block_hash")}
                      if rec else {"status": "unanchored", "reason": "register returned no record"})
    except Exception as exc:  # never break package generation on anchoring
        result = {"status": "unanchored", "reason": f"anchor error: {exc}"}
    package["integrity"]["anchor"] = result
    return result


def verify_package(package: dict) -> dict:
    """Re-hash the core and verify against BELS. Returns a tamper-check result."""
    from .packager import canonical_hash
    recomputed = canonical_hash({"case_id": package["case_id"], "sections": package["sections"]})
    stored = package["integrity"]["sha256"]
    local_ok = recomputed == stored
    out: dict[str, Any] = {"local_match": local_ok, "recomputed_sha256": recomputed,
                           "stored_sha256": stored}
    anchor = package["integrity"].get("anchor", {})
    if anchor.get("status") == "anchored" and anchor.get("evidence_id"):
        try:
            from case_management import bels_client
            v = bels_client.verify_hash(anchor["evidence_id"], recomputed)
            out["bels"] = v or {"status": "unavailable"}
        except Exception as exc:
            out["bels"] = {"status": "error", "detail": str(exc)}
    else:
        out["bels"] = {"status": "unanchored"}

    if not local_ok:
        out["verdict"] = "TAMPERED"
    elif out["bels"].get("outcome") == "VERIFIED":
        out["verdict"] = "VERIFIED"          # local hash matches AND anchored on-chain
    else:
        out["verdict"] = "VERIFIED_LOCAL"    # hash matches; not (re)confirmed on-chain
    return out
