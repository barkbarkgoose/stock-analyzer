"""Dip-rebound research engine.

The package is intentionally dependency-light and Django-free.  The Django app
in ``backend/apps/market`` owns persistence, rate-limited ingestion and the API;
this package owns features, signals, labels, statistics and the profile JSON.
"""

from .config import AnalysisConfig
from .profile import build_profile
from .types import Bar, TradeOutcome

__all__ = ["AnalysisConfig", "Bar", "TradeOutcome", "build_profile"]
