"""Provider factory — selects the anchoring backend from configuration."""
from __future__ import annotations

from functools import lru_cache

from .. import config
from .provider import BlockchainProvider


@lru_cache(maxsize=1)
def get_provider() -> BlockchainProvider:
    """Return the process-wide blockchain provider chosen by BELS_PROVIDER."""
    choice = (config.BLOCKCHAIN_PROVIDER or "internal").lower()
    if choice in ("ethereum", "polygon", "evm"):
        from .ethereum_provider import EthereumProvider
        return EthereumProvider()
    # Default: the bundled, dependency-free, tamper-evident ledger.
    from .internal_chain import InternalChainProvider
    return InternalChainProvider()
