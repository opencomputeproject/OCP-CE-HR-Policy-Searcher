"""Tests for the admin cost settings store (src/storage/cost_settings.py)."""

import json

import pytest

from src.core.models import DEFAULT_ANALYSIS_MODEL, DEFAULT_SCREENING_MODEL
from src.storage.cost_settings import (
    COST_LEVELS,
    CostSettings,
    CostSettingsStore,
)


class TestCostSettingsModel:
    def test_defaults_match_current_behavior(self):
        s = CostSettings()
        assert s.cost_level == "standard"
        assert s.ask_enabled is True
        assert s.ask_rate_per_minute == 5
        assert s.ask_daily_limit == 200

    def test_invalid_cost_level_rejected(self):
        with pytest.raises(ValueError):
            CostSettings(cost_level="platinum")

    def test_limits_bounded(self):
        with pytest.raises(ValueError):
            CostSettings(ask_rate_per_minute=0)
        with pytest.raises(ValueError):
            CostSettings(ask_daily_limit=-1)


class TestCostLevels:
    def test_standard_matches_pipeline_defaults(self):
        models = COST_LEVELS["standard"]
        assert models["screening_model"] == DEFAULT_SCREENING_MODEL
        assert models["analysis_model"] == DEFAULT_ANALYSIS_MODEL

    def test_low_is_all_haiku(self):
        models = COST_LEVELS["low"]
        assert "haiku" in models["screening_model"]
        assert "haiku" in models["analysis_model"]
        assert "haiku" in models["ask_model"]

    def test_every_level_defines_all_three_models(self):
        for level, models in COST_LEVELS.items():
            assert set(models) == {"screening_model", "analysis_model", "ask_model"}, level


class TestCostSettingsStore:
    def test_missing_file_yields_defaults(self, tmp_path):
        store = CostSettingsStore(data_dir=str(tmp_path))
        assert store.get() == CostSettings()

    def test_update_persists_and_reloads(self, tmp_path):
        store = CostSettingsStore(data_dir=str(tmp_path))
        store.update(CostSettings(cost_level="low", ask_daily_limit=50))

        reloaded = CostSettingsStore(data_dir=str(tmp_path)).get()
        assert reloaded.cost_level == "low"
        assert reloaded.ask_daily_limit == 50

    def test_corrupt_file_falls_back_to_defaults(self, tmp_path):
        (tmp_path / "cost_settings.json").write_text("{not json", encoding="utf-8")
        store = CostSettingsStore(data_dir=str(tmp_path))
        assert store.get() == CostSettings()

    def test_saved_file_is_valid_json(self, tmp_path):
        store = CostSettingsStore(data_dir=str(tmp_path))
        store.update(CostSettings(cost_level="high"))
        raw = json.loads((tmp_path / "cost_settings.json").read_text(encoding="utf-8"))
        assert raw["cost_level"] == "high"

    def test_resolved_models_follow_level(self, tmp_path):
        store = CostSettingsStore(data_dir=str(tmp_path))
        store.update(CostSettings(cost_level="low"))
        models = store.resolved_models()
        assert models == COST_LEVELS["low"]


class TestApplyToConfig:
    def test_apply_sets_analysis_models(self, tmp_path):
        from src.core.models import AppSettings

        store = CostSettingsStore(data_dir=str(tmp_path))
        store.update(CostSettings(cost_level="low"))

        class _FakeConfig:
            settings = AppSettings()

        config = _FakeConfig()
        store.apply_to_config(config)
        assert config.settings.analysis.screening_model == COST_LEVELS["low"]["screening_model"]
        assert config.settings.analysis.analysis_model == COST_LEVELS["low"]["analysis_model"]
