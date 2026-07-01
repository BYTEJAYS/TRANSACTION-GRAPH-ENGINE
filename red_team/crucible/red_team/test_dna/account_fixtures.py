"""Account fixture metadata for the 3 test DNA chains.
Account IDs match the acc_<10hex> format used in test DNA JSON files.
"""

DNA_001_FIXTURES = {
    "acc_4001a1b2c3": {"account_age_days": 220, "account_type": "SAVINGS", "is_merchant": False, "avg_amount_30d": 5000.0, "prior_monthly_txn_count": 8},
    "acc_4002f5a6b7": {"account_age_days": 235, "account_type": "SAVINGS", "is_merchant": False, "avg_amount_30d": 4800.0, "prior_monthly_txn_count": 7},
    "acc_4003c8d9e0": {"account_age_days": 210, "account_type": "SAVINGS", "is_merchant": False, "avg_amount_30d": 5500.0, "prior_monthly_txn_count": 9},
    "acc_4004b2c3d4": {"account_age_days": 245, "account_type": "SAVINGS", "is_merchant": False, "avg_amount_30d": 5200.0, "prior_monthly_txn_count": 8},
    "acc_4005e5f6a7": {"account_age_days": 230, "account_type": "SAVINGS", "is_merchant": False, "avg_amount_30d": 4900.0, "prior_monthly_txn_count": 7},
    "acc_4006d9e0f1": {"account_age_days": 215, "account_type": "SAVINGS", "is_merchant": False, "avg_amount_30d": 4700.0, "prior_monthly_txn_count": 6},
    "acc_merch01d4e": {"account_age_days": 365, "account_type": "CURRENT", "is_merchant": True, "avg_amount_30d": 15000.0, "prior_monthly_txn_count": 25},
    "acc_merch02f1a": {"account_age_days": 420, "account_type": "CURRENT", "is_merchant": True, "avg_amount_30d": 18000.0, "prior_monthly_txn_count": 30},
    "acc_merch03b8c": {"account_age_days": 390, "account_type": "CURRENT", "is_merchant": True, "avg_amount_30d": 16000.0, "prior_monthly_txn_count": 28},
    "acc_sink01a2b3": {"account_age_days": 200, "account_type": "SAVINGS", "is_merchant": False, "avg_amount_30d": 2000.0, "prior_monthly_txn_count": 5},
}

DNA_002_FIXTURES = {
    "acc_4007c1d2e3": {"account_age_days": 320, "account_type": "SAVINGS", "is_merchant": False, "avg_amount_30d": 3000.0, "prior_monthly_txn_count": 5},
    "acc_4008a4b5c6": {"account_age_days": 310, "account_type": "SAVINGS", "is_merchant": False, "avg_amount_30d": 2800.0, "prior_monthly_txn_count": 4},
    "acc_4009d7e8f9": {"account_age_days": 335, "account_type": "SAVINGS", "is_merchant": False, "avg_amount_30d": 3200.0, "prior_monthly_txn_count": 6},
    "acc_4010a0b1c2": {"account_age_days": 305, "account_type": "SAVINGS", "is_merchant": False, "avg_amount_30d": 2900.0, "prior_monthly_txn_count": 5},
    "acc_collect01f": {"account_age_days": 400, "account_type": "SAVINGS", "is_merchant": False, "avg_amount_30d": 1500.0, "prior_monthly_txn_count": 3},
}

DNA_003_FIXTURES = {
    "acc_4011d3e4f5": {"account_age_days": 210, "account_type": "SAVINGS", "is_merchant": False, "avg_amount_30d": 3500.0, "has_festival_gifting_history": True, "prior_monthly_txn_count": 10},
    "acc_rcp01a6b7": {"account_age_days": 220, "account_type": "SAVINGS", "is_merchant": False, "avg_amount_30d": 2000.0, "prior_monthly_txn_count": 5},
    "acc_rcp02c8d9": {"account_age_days": 200, "account_type": "SAVINGS", "is_merchant": False, "avg_amount_30d": 1800.0, "prior_monthly_txn_count": 4},
    "acc_rcp03e0f1": {"account_age_days": 215, "account_type": "SAVINGS", "is_merchant": False, "avg_amount_30d": 2200.0, "prior_monthly_txn_count": 6},
    "acc_rcp04a2b3": {"account_age_days": 205, "account_type": "SAVINGS", "is_merchant": False, "avg_amount_30d": 1900.0, "prior_monthly_txn_count": 5},
    "acc_rcp05c4d5": {"account_age_days": 225, "account_type": "SAVINGS", "is_merchant": False, "avg_amount_30d": 2100.0, "prior_monthly_txn_count": 5},
}
