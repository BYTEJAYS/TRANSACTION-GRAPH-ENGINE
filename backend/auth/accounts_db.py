"""
Synthetic account / case / evidence registry powering the investigator search.

The live graph is per-session and starts empty, so the global "search by account
number" workflow needs its own durable intelligence dataset. This module builds a
deterministic, realistic registry once at import time and exposes lookup + search.

Identifiers that resolve to an account:
  * Account number        ACC-XXXXXXXX
  * Customer ID           CUST-XXXXX
  * Transaction ID        TXN-XXXXXXXX  (any of the account's recent activity)
  * Case ID               CASE-2026-XXX
  * Evidence ID           EVD-XXXXXX
"""

from __future__ import annotations

import hashlib
import random
from typing import Dict, List, Optional

_FIRST = ["Aarav", "Vivaan", "Ananya", "Diya", "Kabir", "Ishaan", "Saanvi", "Aditya",
          "Myra", "Reyansh", "Anaya", "Vihaan", "Riya", "Arjun", "Zara", "Devansh",
          "Kiara", "Rohan", "Naina", "Yuvraj", "Meera", "Karthik", "Sara", "Aryan"]
_LAST = ["Sharma", "Verma", "Patel", "Reddy", "Nair", "Iyer", "Gupta", "Mehta",
         "Khanna", "Bose", "Das", "Joshi", "Malhotra", "Chopra", "Rao", "Sinha"]
_BANKS = ["HDFC Bank", "ICICI Bank", "State Bank of India", "Axis Bank",
          "Kotak Mahindra", "Punjab National Bank", "Yes Bank", "IndusInd Bank"]
_STATUS = ["Active", "Active", "Active", "Frozen", "Under Watch", "Dormant"]
_INV_STATUS = ["Open", "Under Investigation", "Escalated", "Monitoring", "Cleared"]
_ACTIVITY = [
    ("Inbound transfer", "credit"),
    ("Outbound transfer", "debit"),
    ("Cash deposit", "credit"),
    ("Cash withdrawal", "debit"),
    ("UPI payment", "debit"),
    ("IMPS settlement", "credit"),
    ("NEFT transfer", "debit"),
    ("Merchant payout", "credit"),
]
_RAILS = ["UPI", "IMPS", "NEFT", "RTGS", "CARD"]


def _rng(seed: str) -> random.Random:
    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    return random.Random(h)


def _risk_band(score: int) -> str:
    if score >= 80:
        return "Critical"
    if score >= 60:
        return "High"
    if score >= 35:
        return "Medium"
    return "Low"


class AccountRegistry:
    def __init__(self, n: int = 48) -> None:
        self.accounts: Dict[str, dict] = {}
        self._by_customer: Dict[str, str] = {}
        self._by_txn: Dict[str, str] = {}
        self._by_case: Dict[str, str] = {}
        self._by_evidence: Dict[str, str] = {}
        self._build(n)

    def _build(self, n: int) -> None:
        numbers = [f"ACC-{10_000_000 + i * 137:08d}" for i in range(n)]
        for idx, acc_no in enumerate(numbers):
            r = _rng(acc_no)
            name = f"{r.choice(_FIRST)} {r.choice(_LAST)}"
            score = r.randint(8, 97)
            cust_id = f"CUST-{20000 + idx:05d}"

            # recent activity + transaction ids
            activity = []
            txn_ids = []
            for k in range(r.randint(6, 14)):
                label, direction = r.choice(_ACTIVITY)
                txn_id = f"TXN-{r.randint(10_000_000, 99_999_999):08d}"
                txn_ids.append(txn_id)
                amount = r.choice([2_500, 9_900, 24_000, 49_999, 75_000, 1_20_000,
                                   2_40_000, 4_90_000, 9_50_000])
                activity.append({
                    "txn_id": txn_id,
                    "label": label,
                    "direction": direction,
                    "amount": amount,
                    "rail": r.choice(_RAILS),
                    "counterparty": r.choice(numbers),
                    "hours_ago": k * r.randint(2, 9) + r.randint(0, 3),
                })

            linked = r.sample([x for x in numbers if x != acc_no], r.randint(2, 6))

            # cases / evidence only for elevated risk
            cases, evidence = [], []
            if score >= 45:
                for c in range(r.randint(1, 2)):
                    case_id = f"CASE-2026-{r.randint(100, 999):03d}"
                    cases.append({
                        "case_id": case_id,
                        "title": r.choice([
                            "Suspected layering ring", "Mule account network",
                            "Structuring / smurfing", "Trade-based laundering",
                            "Account takeover fraud", "Rapid movement of funds",
                        ]),
                        "opened": f"2026-{r.randint(1, 6):02d}-{r.randint(1, 28):02d}",
                    })
                    self._by_case[case_id] = acc_no
                for e in range(r.randint(1, 3)):
                    evd_id = f"EVD-{r.randint(100000, 999999):06d}"
                    evidence.append({
                        "evidence_id": evd_id,
                        "type": r.choice(["Graph snapshot", "Transaction trail",
                                          "KYC record", "Device fingerprint"]),
                        "anchored": r.random() > 0.4,
                    })
                    self._by_evidence[evd_id] = acc_no

            rec = {
                "account_number": acc_no,
                "customer_name": name,
                "customer_id": cust_id,
                "bank": r.choice(_BANKS),
                "ifsc": f"{r.choice(['HDFC','ICIC','SBIN','UTIB','KKBK'])}0{r.randint(100000,999999)}",
                "risk_score": score,
                "risk_band": _risk_band(score),
                "status": "Frozen" if score >= 88 else r.choice(_STATUS),
                "investigation_status": (
                    "Escalated" if score >= 80 else
                    "Under Investigation" if score >= 55 else
                    r.choice(_INV_STATUS)
                ),
                "linked_accounts": linked,
                "linked_count": len(linked),
                "transaction_count": r.randint(140, 4200),
                "balance": r.randint(5_000, 9_00_00_000),
                "opened_on": f"20{r.randint(15,24):02d}-{r.randint(1,12):02d}-{r.randint(1,28):02d}",
                "flags": r.sample(
                    ["High-velocity transfers", "Cross-border exposure",
                     "Cash-intensive", "New beneficiary surge", "Round-number deposits",
                     "Night-time activity", "Dormant-then-active"],
                    r.randint(0, 3) if score < 45 else r.randint(2, 4),
                ),
                "recent_activity": activity,
                "cases": cases,
                "evidence": evidence,
            }
            self.accounts[acc_no] = rec
            self._by_customer[cust_id] = acc_no
            for t in txn_ids:
                self._by_txn[t] = acc_no

    # ── resolution ──────────────────────────────────────────────────────────
    def resolve(self, query: str) -> Optional[str]:
        """Map any supported identifier to an account number."""
        if not query:
            return None
        q = query.strip().upper()
        if q in self.accounts:
            return q
        for table in (self._by_customer, self._by_txn, self._by_case, self._by_evidence):
            if q in table:
                return table[q]
        # bare digits → ACC-<digits>
        digits = "".join(ch for ch in q if ch.isdigit())
        if digits:
            cand = f"ACC-{int(digits):08d}" if digits.isdigit() else None
            if cand and cand in self.accounts:
                return cand
        return None

    def get(self, account_number: str) -> Optional[dict]:
        return self.accounts.get((account_number or "").strip().upper())

    def summary(self, rec: dict) -> dict:
        """Lightweight card for search-result lists."""
        return {
            "account_number": rec["account_number"],
            "customer_name": rec["customer_name"],
            "customer_id": rec["customer_id"],
            "bank": rec["bank"],
            "risk_score": rec["risk_score"],
            "risk_band": rec["risk_band"],
            "status": rec["status"],
            "investigation_status": rec["investigation_status"],
            "transaction_count": rec["transaction_count"],
            "linked_count": rec["linked_count"],
        }

    def search(self, query: str, limit: int = 12) -> List[dict]:
        """Resolve an exact identifier, else fuzzy-match name / account substring."""
        exact = self.resolve(query)
        if exact:
            return [self.summary(self.accounts[exact])]
        q = (query or "").strip().lower()
        if not q:
            return []
        hits = []
        for rec in self.accounts.values():
            if (q in rec["account_number"].lower()
                    or q in rec["customer_name"].lower()
                    or q in rec["customer_id"].lower()
                    or q in rec["bank"].lower()):
                hits.append(self.summary(rec))
        hits.sort(key=lambda r: r["risk_score"], reverse=True)
        return hits[:limit]


registry = AccountRegistry()
