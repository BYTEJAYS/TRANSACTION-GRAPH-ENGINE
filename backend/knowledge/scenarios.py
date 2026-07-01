"""
Synthetic cross-product scenarios (Phase 11 — data).

Realistic heterogeneous fraud + legitimate graphs so the XP detectors and the
customer-risk graph have genuine multi-product data to bite on (the live A2A
simulator can't produce this). Each builder returns the standard component dict;
`SCENARIOS` indexes them for the generator endpoint and tests.
"""
from __future__ import annotations

from typing import Any, Callable

from .entities import EntityType
from .hetero import HeteroGraph

_TS = "2026-01-01T{h:02d}:{m:02d}:00"


def _t(h: int, m: int = 0) -> str:
    return _TS.format(h=h, m=m)


def wallet_layering() -> dict[str, Any]:
    """Salary → 2 wallets → merchant → cash-out, one device, structured amounts."""
    g = HeteroGraph("XP_WALLET_LAYERING")
    g.customer("CUST_100")
    g.product("SAL_100", EntityType.SALARY_ACCOUNT, owner="CUST_100")
    g.product("WALLET_1", EntityType.WALLET, owner="CUST_100")
    g.product("WALLET_2", EntityType.WALLET, owner="CUST_100")
    g.add_entity("MERCHANT_9", EntityType.MERCHANT)
    g.add_entity("CASH_OUT_1", EntityType.CASH_ENDPOINT)
    g.has_device("SAL_100", "DEV_A")
    g.transfer("SAL_100", "WALLET_1", 48000, "UPI", _t(10, 0), "DEV_A")
    g.transfer("SAL_100", "WALLET_2", 47000, "IMPS", _t(10, 30), "DEV_A")
    g.transfer("WALLET_1", "MERCHANT_9", 47500, "UPI", _t(11, 0), "DEV_A")
    g.transfer("WALLET_2", "MERCHANT_9", 46500, "RTGS", _t(11, 15), "DEV_A")
    g.transfer("MERCHANT_9", "CASH_OUT_1", 92000, "CASH_OUT", _t(12, 0), "DEV_A")
    return g.component()


def shared_device_ring() -> dict[str, Any]:
    """One device controls four unrelated accounts funnelling to a collector→cash-out."""
    g = HeteroGraph("XP_SHARED_DEVICE")
    mules = ["SAV_201", "SAV_202", "SAV_203", "SAV_204"]
    for i, m in enumerate(mules):
        g.customer(f"CUST_2{i}")
        g.product(m, EntityType.SAVINGS_ACCOUNT, owner=f"CUST_2{i}")
        g.has_device(m, "DEV_RING")
        g.transfer(m, "SAV_COLLECT", 24000, "UPI", _t(9, i * 5), "DEV_RING")
    g.product("SAV_COLLECT", EntityType.SAVINGS_ACCOUNT, owner="CUST_2X")
    g.add_entity("CASH_OUT_2", EntityType.CASH_ENDPOINT)
    g.transfer("SAV_COLLECT", "CASH_OUT_2", 92000, "CASH_OUT", _t(13, 0), "DEV_RING")
    return g.component()


def loan_laundering() -> dict[str, Any]:
    """Loan disbursement → savings → shell company → foreign bank."""
    g = HeteroGraph("XP_LOAN_LAUNDERING")
    g.customer("CUST_300")
    g.product("LOAN_300", EntityType.LOAN, owner="CUST_300")
    g.product("SAV_300", EntityType.SAVINGS_ACCOUNT, owner="CUST_300")
    g.add_entity("CORP_SHELL", EntityType.CORPORATE_ACCOUNT)
    g.add_entity("FBANK_1", EntityType.FOREIGN_BANK)
    g.transfer("LOAN_300", "SAV_300", 1000000, "NEFT", _t(10, 0), "DEV_L")
    g.transfer("SAV_300", "CORP_SHELL", 480000, "RTGS", _t(10, 30), "DEV_L")
    g.transfer("SAV_300", "CORP_SHELL", 470000, "IMPS", _t(11, 0), "DEV_L")
    g.transfer("CORP_SHELL", "FBANK_1", 900000, "RTGS", _t(12, 0), "DEV_L")
    return g.component()


def shared_identity_ring() -> dict[str, Any]:
    """Three customers share one PAN + mobile; each account funnels to a cash-out."""
    g = HeteroGraph("XP_SHARED_IDENTITY")
    for i in range(3):
        c, a = f"CUST_4{i}", f"SAV_4{i}"
        g.customer(c)
        g.product(a, EntityType.SAVINGS_ACCOUNT, owner=c)
        g.has_pan(c, "PAN_SYNTH")
        g.has_phone(c, "PHONE_SYNTH")
        g.transfer(a, "SAV_SINK", 30000, "UPI", _t(9, i * 4), f"DEV_{i}")
    g.product("SAV_SINK", EntityType.SAVINGS_ACCOUNT)
    g.add_entity("CASH_OUT_4", EntityType.CASH_ENDPOINT)
    g.transfer("SAV_SINK", "CASH_OUT_4", 88000, "CASH_OUT", _t(14, 0))
    return g.component()


def legit_customer() -> dict[str, Any]:
    """A normal customer: salary in, a couple of modest transfers, distinct device."""
    g = HeteroGraph("LEGIT_CUSTOMER")
    g.customer("CUST_900")
    g.product("SAL_900", EntityType.SALARY_ACCOUNT, owner="CUST_900")
    g.product("SAV_900", EntityType.SAVINGS_ACCOUNT, owner="CUST_900")
    g.has_device("SAL_900", "DEV_OWN")
    g.has_device("SAV_900", "DEV_OWN")  # same person's own two accounts → only 2, no XP009
    g.transfer("SAL_900", "SAV_900", 35000, "IMPS", _t(10, 0), "DEV_OWN")
    g.transfer("SAV_900", "MERCHANT_GROCERY", 2500, "UPI", _t(18, 0), "DEV_OWN")
    g.add_entity("MERCHANT_GROCERY", EntityType.MERCHANT)
    return g.component()


def evasive_structuring() -> dict[str, Any]:
    """
    EVASIVE attack: 3 accounts each push ONE structured amount (just under ₹50k)
    over a DIFFERENT rail into a common sink, with distinct devices and no shared
    identity. Tuned to slip under Blue Team's defaults — XP012 needs ≥4 structured
    txns, and no single account switches rails or shares a device — so nothing
    fires. The learning loop must adapt to catch it.
    """
    g = HeteroGraph("XP_EVASIVE_STRUCTURING")
    amts, rails = [48000, 49000, 47000], ["UPI", "IMPS", "NEFT"]
    for i in range(3):
        a = f"SAV_5{i}"
        g.customer(f"CUST_5{i}")
        g.product(a, EntityType.SAVINGS_ACCOUNT, owner=f"CUST_5{i}")
        g.has_device(a, f"DEV_5{i}")  # distinct devices → no shared-device signal
        g.transfer(a, "SAV_SINK5", amts[i], rails[i], _t(10, i * 5), f"DEV_5{i}")
    g.product("SAV_SINK5", EntityType.SAVINGS_ACCOUNT)
    return g.component()


SCENARIOS: dict[str, Callable[[], dict[str, Any]]] = {
    "wallet_layering": wallet_layering,
    "shared_device_ring": shared_device_ring,
    "loan_laundering": loan_laundering,
    "shared_identity_ring": shared_identity_ring,
    "evasive_structuring": evasive_structuring,
    "legit_customer": legit_customer,
}


def generate(name: str) -> dict[str, Any]:
    builder = SCENARIOS.get(name)
    if not builder:
        raise KeyError(name)
    return builder()


def generate_all() -> dict[str, dict[str, Any]]:
    return {name: builder() for name, builder in SCENARIOS.items()}
