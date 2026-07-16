"""Admin-settable cost controls.

The admin picks a cost level; it decides which models paid jobs use and
how much of the free-for-readers ask endpoint the server will serve per
day. Persisted to data/cost_settings.json so cron-triggered and
API-triggered jobs share the same level.

Levels:
- low:      Haiku everywhere. Cheapest possible scans and answers.
- standard: Haiku screening + Sonnet analysis (the pipeline default).
- high:     Sonnet everywhere. Best quality, most expensive.
"""

import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ..core.models import DEFAULT_ANALYSIS_MODEL, DEFAULT_SCREENING_MODEL

logger = logging.getLogger(__name__)

_HAIKU = DEFAULT_SCREENING_MODEL
_SONNET = DEFAULT_ANALYSIS_MODEL

COST_LEVELS: dict[str, dict[str, str]] = {
    "low": {
        "screening_model": _HAIKU,
        "analysis_model": _HAIKU,
        "ask_model": _HAIKU,
    },
    "standard": {
        "screening_model": _HAIKU,
        "analysis_model": _SONNET,
        "ask_model": _HAIKU,
    },
    "high": {
        "screening_model": _SONNET,
        "analysis_model": _SONNET,
        "ask_model": _SONNET,
    },
}


class CostSettings(BaseModel):
    cost_level: Literal["low", "standard", "high"] = "standard"
    ask_enabled: bool = True
    ask_rate_per_minute: int = Field(default=5, ge=1, le=60)
    ask_daily_limit: int = Field(default=200, ge=0, le=10000)


class CostSettingsStore:
    """Atomic JSON persistence for cost settings."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.settings_file = self.data_dir / "cost_settings.json"
        self._settings = self._load()

    def _load(self) -> CostSettings:
        if not self.settings_file.exists():
            return CostSettings()
        try:
            raw = json.loads(self.settings_file.read_text(encoding="utf-8"))
            return CostSettings(**raw)
        except Exception as e:
            logger.error("Failed to load cost settings (%s); using defaults", e)
            return CostSettings()

    def get(self) -> CostSettings:
        return self._settings

    def update(self, settings: CostSettings) -> CostSettings:
        self._settings = settings
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.settings_file.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(settings.model_dump(), indent=2), encoding="utf-8"
        )
        tmp.replace(self.settings_file)
        return self._settings

    def resolved_models(self) -> dict[str, str]:
        return COST_LEVELS[self._settings.cost_level]

    def apply_to_config(self, config) -> None:
        """Push the level's models into a ConfigLoader's analysis settings.

        Scans read their models from config.settings.analysis, so applying
        here makes every subsequent scan (API, agent, or cron via server)
        run at the admin's chosen cost level.
        """
        models = self.resolved_models()
        config.settings.analysis.screening_model = models["screening_model"]
        config.settings.analysis.analysis_model = models["analysis_model"]
