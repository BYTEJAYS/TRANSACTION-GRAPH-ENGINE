"""TGIE Intelligent Risk Scoring & Threshold Engine — /api/risk."""

from .config import config  # noqa: F401
from .engine import assess, classify_score  # noqa: F401
from .router import router as risk_router  # noqa: F401
