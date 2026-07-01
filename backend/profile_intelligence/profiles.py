"""
Customer Profile taxonomy + behavioural baselines.

Each profile says what is NORMAL for that kind of customer, so the Blue Team can ask
"is this behaviour unusual *for this customer*?" instead of using one absolute threshold
for everyone. A ₹25 lakh transfer is routine for a Business Owner and alarming for a
Salaried Employee — that difference lives here.

Reuses the "compare each account to its own baseline" principle proven offline in
`red_team/adversarial/common/behavioral.py`, but as a live, explainable, extensible
registry. Add a new profile by adding one entry to PROFILES — nothing else changes.

All amounts are in INR. Baselines are deliberately broad envelopes (banks calibrate
them per branch/segment later); they are policy data, not magic constants.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class CustomerProfile:
    key: str
    label: str
    segment: str                      # coarse band (retail / sme / corporate / ...)
    expected_behaviour: list[str]     # human-readable, shown in the UI / explanations
    abnormal_behaviour: list[str]
    # Behavioural envelope (the "normal" range for this customer kind):
    baseline_txn: float               # typical single-transaction size
    baseline_txn_high: float          # upper edge of a routine single transaction
    monthly_throughput: float         # typical value moved per month
    max_fan_out_expected: int         # routine number of distinct recipients
    cash_intensity: float             # expected reliance on cash, 0..1
    many_to_one_expected: bool        # is receiving from many sources normal? (NGO, merchant)
    foreign_expected: bool            # are cross-border / SWIFT flows normal?
    expected_rails: frozenset         # payment rails that are routine
    expected_products: frozenset      # Phase 9 — cross-product expectation


def _p(**kw) -> CustomerProfile:
    return CustomerProfile(**kw)


# ── The registry (extensible — add an entry to introduce a new profile) ───────
PROFILES: dict[str, CustomerProfile] = {
    "salaried_employee": _p(
        key="salaried_employee", label="Salaried Employee", segment="retail",
        expected_behaviour=["Monthly salary credit", "EMI & bill payments", "UPI spending",
                            "ATM withdrawals", "Moderate, regular activity"],
        abnormal_behaviour=["₹25L+ transfers", "Rapid fan-out to many payees",
                            "High-value cash deposits", "Foreign transfers", "Business-scale volume"],
        baseline_txn=15_000, baseline_txn_high=1_50_000, monthly_throughput=2_00_000,
        max_fan_out_expected=4, cash_intensity=0.2, many_to_one_expected=False,
        foreign_expected=False, expected_rails=frozenset({"UPI", "IMPS", "NEFT"}),
        expected_products=frozenset({"savings_account", "salary_account", "upi_id", "debit_card"})),

    "business_owner": _p(
        key="business_owner", label="Business Owner", segment="sme",
        expected_behaviour=["High daily transaction count", "Large vendor & supplier payments",
                            "GST / tax payments", "Cash deposits", "RTGS / NEFT settlements"],
        abnormal_behaviour=["Circular money movement", "Layering through shell chains",
                            "Money-mule routing", "Structuring near thresholds"],
        baseline_txn=50_000, baseline_txn_high=25_00_000, monthly_throughput=1_00_00_000,
        max_fan_out_expected=40, cash_intensity=0.4, many_to_one_expected=True,
        foreign_expected=False, expected_rails=frozenset({"NEFT", "RTGS", "IMPS", "UPI"}),
        expected_products=frozenset({"current_account", "merchant", "upi_id", "gst"})),

    "msme": _p(
        key="msme", label="MSME", segment="sme",
        expected_behaviour=["Regular vendor payments", "Payroll runs", "GST payments",
                            "Moderate cash handling"],
        abnormal_behaviour=["Sudden circular flows", "Layering", "Unexplained foreign legs"],
        baseline_txn=40_000, baseline_txn_high=10_00_000, monthly_throughput=40_00_000,
        max_fan_out_expected=25, cash_intensity=0.35, many_to_one_expected=True,
        foreign_expected=False, expected_rails=frozenset({"NEFT", "RTGS", "IMPS", "UPI"}),
        expected_products=frozenset({"current_account", "gst", "upi_id"})),

    "large_corporate": _p(
        key="large_corporate", label="Large Corporate", segment="corporate",
        expected_behaviour=["Very large RTGS / SWIFT settlements", "Bulk vendor & payroll files",
                            "Trade finance", "Treasury movements"],
        abnormal_behaviour=["Round-tripping", "Funds layered into personal wallets",
                            "Shell-company chains"],
        baseline_txn=10_00_000, baseline_txn_high=5_00_00_000, monthly_throughput=50_00_00_000,
        max_fan_out_expected=200, cash_intensity=0.1, many_to_one_expected=True,
        foreign_expected=True, expected_rails=frozenset({"RTGS", "SWIFT", "NEFT"}),
        expected_products=frozenset({"corporate_account", "gst", "swift_entity"})),

    "farmer": _p(
        key="farmer", label="Farmer", segment="retail",
        expected_behaviour=["Seasonal harvest income", "Government subsidy credits",
                            "Fertiliser / equipment purchases", "Cash-heavy local trade"],
        abnormal_behaviour=["Acting as a money distributor", "Year-round high-velocity transfers",
                            "Routing for many unrelated accounts"],
        baseline_txn=20_000, baseline_txn_high=2_00_000, monthly_throughput=1_00_000,
        max_fan_out_expected=4, cash_intensity=0.6, many_to_one_expected=False,
        foreign_expected=False, expected_rails=frozenset({"UPI", "NEFT", "CASH"}),
        expected_products=frozenset({"savings_account", "upi_id"})),

    "student": _p(
        key="student", label="Student", segment="retail",
        expected_behaviour=["Tuition & hostel fees", "Family transfers in", "Moderate UPI usage",
                            "Small debit-card spend"],
        abnormal_behaviour=["Receiving from hundreds of unrelated accounts", "Cash-out chains",
                            "Merchant-settlement behaviour", "Business-scale volume"],
        baseline_txn=3_000, baseline_txn_high=80_000, monthly_throughput=50_000,
        max_fan_out_expected=3, cash_intensity=0.15, many_to_one_expected=False,
        foreign_expected=False, expected_rails=frozenset({"UPI", "IMPS"}),
        expected_products=frozenset({"savings_account", "upi_id", "debit_card"})),

    "pensioner": _p(
        key="pensioner", label="Pensioner", segment="retail",
        expected_behaviour=["Monthly pension credit", "Bill payments", "Low, regular activity"],
        abnormal_behaviour=["Sudden high-velocity transfers", "Fan-out to many payees",
                            "Large cash movements"],
        baseline_txn=10_000, baseline_txn_high=1_00_000, monthly_throughput=80_000,
        max_fan_out_expected=3, cash_intensity=0.25, many_to_one_expected=False,
        foreign_expected=False, expected_rails=frozenset({"NEFT", "UPI"}),
        expected_products=frozenset({"savings_account", "upi_id"})),

    "freelancer": _p(
        key="freelancer", label="Freelancer", segment="retail",
        expected_behaviour=["Irregular client payments in", "UPI / IMPS receipts",
                            "Moderate spending"],
        abnormal_behaviour=["Sudden fan-out routing", "Cash-out chains", "Shell-company legs"],
        baseline_txn=25_000, baseline_txn_high=3_00_000, monthly_throughput=3_00_000,
        max_fan_out_expected=6, cash_intensity=0.2, many_to_one_expected=True,
        foreign_expected=True, expected_rails=frozenset({"UPI", "IMPS", "NEFT"}),
        expected_products=frozenset({"savings_account", "current_account", "upi_id"})),

    "government_employee": _p(
        key="government_employee", label="Government Employee", segment="retail",
        expected_behaviour=["Monthly salary credit", "EMI & bills", "Moderate UPI usage"],
        abnormal_behaviour=["Large unexplained transfers", "Fan-out routing", "Foreign legs"],
        baseline_txn=15_000, baseline_txn_high=1_50_000, monthly_throughput=2_00_000,
        max_fan_out_expected=4, cash_intensity=0.2, many_to_one_expected=False,
        foreign_expected=False, expected_rails=frozenset({"UPI", "IMPS", "NEFT"}),
        expected_products=frozenset({"salary_account", "savings_account", "upi_id"})),

    "ngo_trust": _p(
        key="ngo_trust", label="NGO / Trust", segment="institution",
        expected_behaviour=["Many small donations in (many-to-one)", "Grant disbursements out",
                            "Regular vendor payments"],
        abnormal_behaviour=["Funds layered to personal accounts", "Circular flows", "Cash-out chains"],
        baseline_txn=30_000, baseline_txn_high=10_00_000, monthly_throughput=30_00_000,
        max_fan_out_expected=50, cash_intensity=0.2, many_to_one_expected=True,
        foreign_expected=True, expected_rails=frozenset({"NEFT", "RTGS", "UPI", "IMPS"}),
        expected_products=frozenset({"current_account", "savings_account"})),

    "retail_merchant": _p(
        key="retail_merchant", label="Retail Merchant", segment="sme",
        expected_behaviour=["Many small inflows (POS / QR / UPI)", "Daily settlement out",
                            "High transaction count", "Cash deposits"],
        abnormal_behaviour=["Outbound fan-out routing", "Layering", "Circular flows"],
        baseline_txn=2_000, baseline_txn_high=5_00_000, monthly_throughput=20_00_000,
        max_fan_out_expected=10, cash_intensity=0.5, many_to_one_expected=True,
        foreign_expected=False, expected_rails=frozenset({"UPI", "IMPS", "NEFT"}),
        expected_products=frozenset({"current_account", "merchant", "upi_id"})),

    "ecommerce_seller": _p(
        key="ecommerce_seller", label="E-commerce Seller", segment="sme",
        expected_behaviour=["Marketplace settlements in", "Supplier & logistics payments out",
                            "GST payments"],
        abnormal_behaviour=["Routing for unrelated accounts", "Layering", "Wallet cash-out chains"],
        baseline_txn=5_000, baseline_txn_high=5_00_000, monthly_throughput=25_00_000,
        max_fan_out_expected=15, cash_intensity=0.15, many_to_one_expected=True,
        foreign_expected=True, expected_rails=frozenset({"IMPS", "NEFT", "UPI"}),
        expected_products=frozenset({"current_account", "merchant", "wallet"})),

    "hni": _p(
        key="hni", label="High Net Worth Individual", segment="retail",
        expected_behaviour=["Large investment & treasury movements", "RTGS transfers",
                            "Property & asset payments"],
        abnormal_behaviour=["Structuring", "Shell-company routing", "Unexplained mule patterns"],
        baseline_txn=5_00_000, baseline_txn_high=2_00_00_000, monthly_throughput=5_00_00_000,
        max_fan_out_expected=15, cash_intensity=0.15, many_to_one_expected=True,
        foreign_expected=True, expected_rails=frozenset({"RTGS", "NEFT", "SWIFT"}),
        expected_products=frozenset({"savings_account", "current_account", "fixed_deposit"})),

    "cash_intensive_business": _p(
        key="cash_intensive_business", label="Cash-Intensive Business", segment="sme",
        expected_behaviour=["Frequent cash deposits", "Daily settlements", "Vendor payments"],
        abnormal_behaviour=["Structuring deposits below thresholds", "Layering", "Circular flows"],
        baseline_txn=30_000, baseline_txn_high=8_00_000, monthly_throughput=30_00_000,
        max_fan_out_expected=20, cash_intensity=0.8, many_to_one_expected=True,
        foreign_expected=False, expected_rails=frozenset({"CASH", "UPI", "NEFT", "IMPS"}),
        expected_products=frozenset({"current_account", "merchant"})),

    "exporter_importer": _p(
        key="exporter_importer", label="Exporter / Importer", segment="corporate",
        expected_behaviour=["Cross-border SWIFT settlements", "Trade-finance flows",
                            "Large RTGS payments", "Foreign-currency legs"],
        abnormal_behaviour=["Trade-based laundering", "Over/under-invoicing patterns",
                            "Round-tripping"],
        baseline_txn=5_00_000, baseline_txn_high=5_00_00_000, monthly_throughput=20_00_00_000,
        max_fan_out_expected=60, cash_intensity=0.1, many_to_one_expected=True,
        foreign_expected=True, expected_rails=frozenset({"SWIFT", "RTGS", "NEFT"}),
        expected_products=frozenset({"current_account", "corporate_account", "swift_entity", "gst"})),

    # Neutral fallback — wide envelope, never used to mitigate or inflate strongly.
    "unknown": _p(
        key="unknown", label="Unclassified Customer", segment="unknown",
        expected_behaviour=["No established behavioural profile yet"],
        abnormal_behaviour=["Evaluated on absolute AML signals until a profile is learned"],
        baseline_txn=50_000, baseline_txn_high=5_00_000, monthly_throughput=10_00_000,
        max_fan_out_expected=10, cash_intensity=0.3, many_to_one_expected=True,
        foreign_expected=False, expected_rails=frozenset({"UPI", "IMPS", "NEFT", "RTGS"}),
        expected_products=frozenset()),
}

# Map a raw account_type (graph node) → a prior profile, when no explicit profile is known.
ACCOUNT_TYPE_PRIOR: dict[str, str] = {
    "salary_account": "salaried_employee",
    "savings": "salaried_employee",
    "savings_account": "salaried_employee",
    "current": "business_owner",
    "current_account": "business_owner",
    "corporate": "large_corporate",
    "corporate_account": "large_corporate",
    "merchant": "retail_merchant",
}


def get_profile(key: Optional[str]) -> CustomerProfile:
    return PROFILES.get(key or "unknown", PROFILES["unknown"])


def all_profiles() -> list[CustomerProfile]:
    return [p for k, p in PROFILES.items() if k != "unknown"]
