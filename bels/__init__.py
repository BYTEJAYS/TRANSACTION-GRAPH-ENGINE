"""
BELS — TGIE Blockchain Evidence Ledger System.

An immutable evidence registration and verification platform that cryptographically
anchors fraud evidence to a blockchain. Files are NEVER stored on-chain — only their
SHA-256 hash, timestamp, case/evidence IDs, metadata digest, signatures and chain-of-
custody events are anchored. Actual files live in a content-addressed storage layer.

The blockchain layer is abstracted behind `BlockchainProvider` so the bundled internal
ledger (used for demonstration) can be replaced by an Ethereum/Polygon/Hyperledger or a
bank-owned/RBI-approved private network with minimal code changes.
"""

__version__ = "1.0.0"
