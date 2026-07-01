"""
Synthetic identity generator.

Produces entirely fictional customers and businesses — names, addresses, KYC
profiles, device fingerprints and behavioural profiles — using the ``faker``
library. Nothing here touches real data; every record is watermarked synthetic
via :class:`red_team.core.models.Provenance`.

Synthetic-identity *fraud* is modelled at the data level only: an identity may
be flagged with ``anomaly_flags`` (e.g. "fabricated_ssn_analogue",
"thin_file_history") so detection research has ground-truth labels. The
generator never explains how to obtain or forge real documents.
"""

from __future__ import annotations

import random
from typing import List, Optional

from faker import Faker

from red_team.core.config import RedTeamConfig, config as default_config
from red_team.core.models import (
    AccountArchetype,
    BehavioralProfile,
    DeviceFingerprint,
    KYCProfile,
    PaymentRail,
    Provenance,
    SyntheticAccount,
    SyntheticIdentity,
)

_PLATFORMS = ["mobile_android", "mobile_ios", "web_browser", "desktop_app"]


class IdentityGenerator:
    """Generates synthetic identities, KYC profiles, devices and accounts."""

    def __init__(self, cfg: Optional[RedTeamConfig] = None, seed: Optional[int] = None):
        self.cfg = cfg or default_config
        self.seed = seed if seed is not None else self.cfg.seed
        self._rng = random.Random(self.seed)
        self.faker = Faker(self.cfg.locale)
        self.faker.seed_instance(self.seed)

    # ── Low-level builders ────────────────────────────────────────────────────

    def _fake_ip(self) -> str:
        r = self._rng
        return f"{r.randint(1,254)}.{r.randint(0,255)}.{r.randint(0,255)}.{r.randint(1,254)}"

    def device(self, suspicious: bool = False) -> DeviceFingerprint:
        return DeviceFingerprint(
            platform=self._rng.choice(_PLATFORMS),
            user_agent=self.faker.user_agent(),
            ip_address=self._fake_ip(),
            is_emulator=suspicious and self._rng.random() < 0.5,
            is_rooted=suspicious and self._rng.random() < 0.4,
        )

    def behavior(self, erratic: bool = False) -> BehavioralProfile:
        return BehavioralProfile(
            avg_session_minutes=round(self._rng.uniform(2, 15), 1),
            txns_per_day=round(self._rng.uniform(0.5, 8), 1),
            typical_hour_range=[self._rng.randint(5, 10), self._rng.randint(18, 23)],
            preferred_rail=self._rng.choice(list(PaymentRail)),
            velocity_baseline=round(self._rng.uniform(0.5, 2.0), 2),
            spending_dispersion=round(self._rng.uniform(0.6, 1.0) if erratic else self._rng.uniform(0.1, 0.4), 2),
        )

    def kyc(self, is_business: bool = False, synthetic_identity_fraud: bool = False) -> KYCProfile:
        city = self._rng.choice(self.cfg.cities)
        name = self.faker.company() if is_business else self.faker.name()
        flags: List[str] = []
        if synthetic_identity_fraud:
            # Research labels only — abstract markers, not a how-to.
            flags = self._rng.sample(
                [
                    "thin_file_history",
                    "document_number_pattern_anomaly",
                    "address_velocity",
                    "shared_device_cluster",
                    "age_income_mismatch",
                ],
                k=self._rng.randint(1, 3),
            )
        return KYCProfile(
            full_name=name,
            date_of_birth=str(self.faker.date_of_birth(minimum_age=18, maximum_age=80)),
            address=self.faker.address().replace("\n", ", "),
            city=city,
            document_type="synthetic_business_id" if is_business else "synthetic_id",
            risk_band="elevated" if flags else "low",
            is_verified=not synthetic_identity_fraud,
            anomaly_flags=flags,
        )

    # ── High-level entities ───────────────────────────────────────────────────

    def identity(
        self,
        is_business: bool = False,
        synthetic_identity_fraud: bool = False,
        suspicious_device: bool = False,
    ) -> SyntheticIdentity:
        device_count = self._rng.randint(1, 3)
        return SyntheticIdentity(
            kyc=self.kyc(is_business=is_business, synthetic_identity_fraud=synthetic_identity_fraud),
            behavior=self.behavior(erratic=synthetic_identity_fraud),
            devices=[self.device(suspicious=suspicious_device) for _ in range(device_count)],
            is_business=is_business,
            provenance=Provenance(seed=self.seed),
        )

    def account(
        self,
        identity: SyntheticIdentity,
        archetype: AccountArchetype = AccountArchetype.RETAIL,
    ) -> SyntheticAccount:
        ranges = {
            AccountArchetype.RETAIL: [500.0, 20_000.0],
            AccountArchetype.SALARIED: [1_000.0, 80_000.0],
            AccountArchetype.MERCHANT: [2_000.0, 200_000.0],
            AccountArchetype.BUSINESS: [10_000.0, 1_000_000.0],
            AccountArchetype.HIGH_NET_WORTH: [100_000.0, 5_000_000.0],
            AccountArchetype.MULE: [5_000.0, 150_000.0],
            AccountArchetype.SHELL: [50_000.0, 2_000_000.0],
        }
        return SyntheticAccount(
            owner_identity_id=identity.identity_id,
            archetype=archetype,
            home_city=identity.kyc.city,
            typical_amount_range=ranges.get(archetype, [500.0, 20_000.0]),
            provenance=Provenance(seed=self.seed),
        )

    def population(
        self,
        identity_count: Optional[int] = None,
        mule_fraction: float = 0.15,
        shell_fraction: float = 0.05,
    ) -> tuple[List[SyntheticIdentity], List[SyntheticAccount]]:
        """
        Generate a coherent population of identities, each with one account.
        A configurable fraction are assigned mule / shell archetypes so
        downstream pattern generators have suitable actors to work with.
        """
        n = identity_count or self.cfg.default_identity_count
        identities: List[SyntheticIdentity] = []
        accounts: List[SyntheticAccount] = []

        for _ in range(n):
            roll = self._rng.random()
            is_synth_fraud = roll < 0.08
            ident = self.identity(synthetic_identity_fraud=is_synth_fraud)
            identities.append(ident)

            r = self._rng.random()
            if r < mule_fraction:
                arch = AccountArchetype.MULE
            elif r < mule_fraction + shell_fraction:
                arch = AccountArchetype.SHELL
            else:
                arch = self._rng.choice(
                    [
                        AccountArchetype.RETAIL,
                        AccountArchetype.SALARIED,
                        AccountArchetype.MERCHANT,
                        AccountArchetype.HIGH_NET_WORTH,
                    ]
                )
            accounts.append(self.account(ident, arch))

        return identities, accounts
