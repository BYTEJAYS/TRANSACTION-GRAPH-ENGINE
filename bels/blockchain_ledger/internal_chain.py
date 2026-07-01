"""
InternalChainProvider — a real, self-contained, tamper-evident blockchain.

Properties it genuinely provides (the four proofs BELS must demonstrate):
  • Proof of existence  — each anchor lands in a timestamped, hash-sealed block.
  • Proof of integrity   — blocks are hash-linked (prev_hash) with a Merkle root over
                           their transactions; altering any record breaks every later
                           block hash, which `verify_integrity()` detects.
  • Traceability         — every evidence_id maps to an ordered list of on-chain txs.
  • Independent verify   — anyone with the ledger file can recompute the hashes.

It uses a lightweight proof-of-work (configurable leading-zero difficulty) so blocks
are "mined", mirroring how a public chain seals state, while needing no network or gas.
Persistence is an append-only JSONL file (one sealed block per line).
"""
from __future__ import annotations

import json
import threading
import uuid
from typing import Any, Dict, List, Optional

from .. import config
from ..security import sha256_hex, sha256_of_obj, utc_now_iso
from .provider import BlockchainProvider, OnChainRecord, TxReceipt


def _merkle_root(tx_hashes: List[str]) -> str:
    """Standard binary Merkle root; duplicates the last node on odd levels."""
    if not tx_hashes:
        return sha256_hex(b"")
    level = list(tx_hashes)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [sha256_hex((level[i] + level[i + 1]).encode()) for i in range(0, len(level), 2)]
    return level[0]


class InternalChainProvider(BlockchainProvider):
    name = "internal"

    def __init__(self) -> None:
        self.chain_id = config.CHAIN_ID
        self.difficulty = max(1, config.POW_DIFFICULTY)
        self._lock = threading.RLock()
        self.chain: List[Dict[str, Any]] = []
        self.tx_index: Dict[str, Dict[str, Any]] = {}        # tx_id -> {block_index, tx}
        self.evidence_txs: Dict[str, List[str]] = {}         # evidence_id -> [tx_id...]
        config.ensure_dirs()
        self._load()
        if not self.chain:
            self._create_genesis()

    # ── persistence ──────────────────────────────────────────────────────────
    def _load(self) -> None:
        if not config.LEDGER_FILE.exists():
            return
        for line in config.LEDGER_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            block = json.loads(line)
            self._index_block(block)
            self.chain.append(block)

    def _append_block_to_disk(self, block: Dict[str, Any]) -> None:
        with config.LEDGER_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(block, sort_keys=True) + "\n")

    def _index_block(self, block: Dict[str, Any]) -> None:
        for tx in block["transactions"]:
            self.tx_index[tx["tx_id"]] = {"block_index": block["index"], "tx": tx}
            eid = tx.get("evidence_id")
            if eid:
                self.evidence_txs.setdefault(eid, []).append(tx["tx_id"])

    # ── block construction / mining ──────────────────────────────────────────
    def _create_genesis(self) -> None:
        genesis = {
            "index": 0,
            "timestamp": utc_now_iso(),
            "prev_hash": "0" * 64,
            "difficulty": self.difficulty,
            "nonce": 0,
            "chain_id": self.chain_id,
            "transactions": [],
            "merkle_root": _merkle_root([]),
        }
        genesis["hash"] = self._seal(genesis)
        self.chain.append(genesis)
        self._append_block_to_disk(genesis)

    @staticmethod
    def _hash_block_header(block: Dict[str, Any]) -> str:
        header = {
            "index": block["index"],
            "timestamp": block["timestamp"],
            "prev_hash": block["prev_hash"],
            "merkle_root": block["merkle_root"],
            "difficulty": block["difficulty"],
            "nonce": block["nonce"],
            "chain_id": block["chain_id"],
        }
        return sha256_of_obj(header)

    def _seal(self, block: Dict[str, Any]) -> str:
        """Proof-of-work: find a nonce whose header hash has `difficulty` leading zeros."""
        target = "0" * block["difficulty"]
        nonce = 0
        while True:
            block["nonce"] = nonce
            h = self._hash_block_header(block)
            if h.startswith(target):
                return h
            nonce += 1

    @staticmethod
    def _hash_tx(tx: Dict[str, Any]) -> str:
        body = {k: v for k, v in tx.items() if k != "hash"}
        return sha256_of_obj(body)

    def _commit(self, tx: Dict[str, Any]) -> TxReceipt:
        """Seal a single transaction into a new block and persist it."""
        with self._lock:
            tx["hash"] = self._hash_tx(tx)
            prev = self.chain[-1]
            block = {
                "index": prev["index"] + 1,
                "timestamp": utc_now_iso(),
                "prev_hash": prev["hash"],
                "difficulty": self.difficulty,
                "nonce": 0,
                "chain_id": self.chain_id,
                "transactions": [tx],
                "merkle_root": _merkle_root([tx["hash"]]),
            }
            block["hash"] = self._seal(block)
            self.chain.append(block)
            self._index_block(block)
            self._append_block_to_disk(block)
            return TxReceipt(
                tx_id=tx["tx_id"],
                tx_type=tx["type"],
                evidence_id=tx.get("evidence_id", ""),
                block_index=block["index"],
                block_hash=block["hash"],
                timestamp=block["timestamp"],
                confirmations=1,
                provider=self.name,
                chain_id=self.chain_id,
                anchored_hash=tx.get("anchored_hash", ""),
            )

    @staticmethod
    def _new_tx(tx_type: str, evidence_id: str, payload: Dict[str, Any], anchored_hash: str) -> Dict[str, Any]:
        return {
            "tx_id": "0x" + uuid.uuid4().hex,
            "type": tx_type,
            "evidence_id": evidence_id,
            "timestamp": utc_now_iso(),
            "anchored_hash": anchored_hash,
            "payload": payload,
        }

    # ── writes ────────────────────────────────────────────────────────────────
    def register_evidence(self, evidence_id, file_hash, case_id, owner, metadata_hash,
                          signature, signer_key_id, extra=None) -> TxReceipt:
        payload = {
            "file_hash": file_hash,
            "case_id": case_id,
            "owner": owner,
            "metadata_hash": metadata_hash,
            "signature": signature,
            "signer_key_id": signer_key_id,
            "extra": extra or {},
        }
        tx = self._new_tx("REGISTER", evidence_id, payload, anchored_hash=file_hash)
        return self._commit(tx)

    def update_custody(self, evidence_id, action, actor, detail, signature) -> TxReceipt:
        payload = {"action": action, "actor": actor, "detail": detail, "signature": signature}
        anchored = sha256_of_obj({"e": evidence_id, **payload})
        tx = self._new_tx("CUSTODY", evidence_id, payload, anchored_hash=anchored)
        return self._commit(tx)

    def record_verification(self, evidence_id, outcome, actor, computed_hash) -> TxReceipt:
        payload = {"outcome": outcome, "actor": actor, "computed_hash": computed_hash}
        anchored = sha256_of_obj({"e": evidence_id, **payload})
        tx = self._new_tx("VERIFY", evidence_id, payload, anchored_hash=anchored)
        return self._commit(tx)

    # ── reads ─────────────────────────────────────────────────────────────────
    def _txs_for(self, evidence_id: str) -> List[Dict[str, Any]]:
        return [self.tx_index[t]["tx"] for t in self.evidence_txs.get(evidence_id, [])]

    def get_record(self, evidence_id: str) -> Optional[OnChainRecord]:
        txs = self._txs_for(evidence_id)
        if not txs:
            return None
        reg = next((t for t in txs if t["type"] == "REGISTER"), None)
        if reg is None:
            return None
        p = reg["payload"]
        verifications = [t for t in txs if t["type"] == "VERIFY"]
        custody = [t for t in txs if t["type"] == "CUSTODY"]

        # Derive status from the event history (TAMPERED is sticky once observed).
        status = "REGISTERED"
        if any(t["payload"].get("outcome") == "VERIFIED" for t in verifications):
            status = "VERIFIED"
        if any(c["payload"].get("action") == "ARCHIVE" for c in custody):
            status = "ARCHIVED"
        if any(t["payload"].get("outcome") in ("TAMPERED", "CORRUPTED") for t in verifications):
            status = "TAMPERED"

        return OnChainRecord(
            evidence_id=evidence_id,
            file_hash=p["file_hash"],
            case_id=p["case_id"],
            owner=p["owner"],
            status=status,
            timestamp=reg["timestamp"],
            metadata_hash=p.get("metadata_hash", ""),
            verification_count=len(verifications),
            custody_event_count=len(custody),
            last_tx_id=txs[-1]["tx_id"],
            signature=p.get("signature", ""),
            signer_key_id=p.get("signer_key_id", ""),
            extra=p.get("extra", {}),
        )

    def get_audit_trail(self, evidence_id: str) -> List[Dict[str, Any]]:
        trail = []
        for t in self._txs_for(evidence_id):
            loc = self.tx_index[t["tx_id"]]
            trail.append({
                "tx_id": t["tx_id"],
                "type": t["type"],
                "timestamp": t["timestamp"],
                "block_index": loc["block_index"],
                "block_hash": self.chain[loc["block_index"]]["hash"],
                "anchored_hash": t.get("anchored_hash", ""),
                "payload": t["payload"],
            })
        return trail

    def get_transaction(self, tx_id: str) -> Optional[Dict[str, Any]]:
        loc = self.tx_index.get(tx_id)
        if not loc:
            return None
        block = self.chain[loc["block_index"]]
        return {
            "tx_id": tx_id,
            "block_index": block["index"],
            "block_hash": block["hash"],
            "block_timestamp": block["timestamp"],
            "confirmations": len(self.chain) - block["index"],
            "transaction": loc["tx"],
        }

    def list_evidence_ids(self) -> List[str]:
        return list(self.evidence_txs.keys())

    def status(self) -> Dict[str, Any]:
        head = self.chain[-1]
        return {
            "provider": self.name,
            "chain_id": self.chain_id,
            "height": head["index"],
            "blocks": len(self.chain),
            "difficulty": self.difficulty,
            "head_hash": head["hash"],
            "total_evidence": len(self.evidence_txs),
            "total_transactions": len(self.tx_index),
        }

    def verify_integrity(self) -> Dict[str, Any]:
        """Re-validate the entire chain: links, Merkle roots and proof-of-work."""
        with self._lock:
            for i, block in enumerate(self.chain):
                # 1. block hash + PoW
                recomputed = self._hash_block_header(block)
                if recomputed != block["hash"]:
                    return self._broken(i, "block hash mismatch (record altered)")
                if not block["hash"].startswith("0" * block["difficulty"]):
                    return self._broken(i, "proof-of-work invalid")
                # 2. merkle root
                tx_hashes = [self._hash_tx(t) for t in block["transactions"]]
                if _merkle_root(tx_hashes) != block["merkle_root"]:
                    return self._broken(i, "merkle root mismatch (transaction altered)")
                # 3. link to previous
                if i > 0 and block["prev_hash"] != self.chain[i - 1]["hash"]:
                    return self._broken(i, "broken hash link to previous block")
            return {
                "valid": True,
                "blocks": len(self.chain),
                "head_hash": self.chain[-1]["hash"],
                "message": "Ledger intact: all blocks hash-linked and proof-of-work valid.",
            }

    @staticmethod
    def _broken(index: int, why: str) -> Dict[str, Any]:
        return {"valid": False, "broken_at_block": index, "message": f"Integrity failure: {why}."}
