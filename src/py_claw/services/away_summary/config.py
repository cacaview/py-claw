"""AwaySummary service configuration."""
from __future__ import annotations

from pathlib import Path

from .types import AwaySummaryConfig

# Cache the config
_config: AwaySummaryConfig | None = None


def get_away_summary_config() -> AwaySummaryConfig:
    """Get the away summary configuration.

    Currently uses defaults. In the future this could read from
    settings or environment variables.
    """
    global _config
    if _config is None:
        _config = AwaySummaryConfig()
    return _config
