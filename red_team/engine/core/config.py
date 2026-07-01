"""
Red Team configuration.

Self-contained settings with sane defaults. No values are read from the Blue
Team environment; the Red Team owns its own configuration surface so the two
systems can never share state through a config file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    return Path(raw) if raw else default


_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class RedTeamConfig:
    """Platform-wide configuration for synthetic scenario generation."""

    # Reproducibility — every run is seedable.
    seed: int = field(default_factory=lambda: _env_int("REDTEAM_SEED", 1337))

    # Output location for generated datasets.
    output_dir: Path = field(
        default_factory=lambda: _env_path("REDTEAM_OUTPUT_DIR", _PACKAGE_ROOT / "datasets")
    )

    # Locale used by the synthetic identity generator (Union Bank context = India).
    locale: str = field(default_factory=lambda: os.getenv("REDTEAM_LOCALE", "en_IN"))

    # Default population sizes for ad-hoc scenarios.
    default_identity_count: int = 40
    default_account_count: int = 60

    # Indian metropolitan cities used for synthetic geolocation.
    cities: List[str] = field(
        default_factory=lambda: [
            "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai",
            "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Surat",
            "Lucknow", "Nagpur", "Bhopal", "Indore", "Coimbatore",
        ]
    )

    # Hard isolation switch — must remain False. The safety module asserts on it.
    allow_blue_team_integration: bool = False

    def ensure_output_dir(self) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir


# A module-level default instance for convenience.
config = RedTeamConfig()
