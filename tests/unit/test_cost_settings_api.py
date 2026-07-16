"""Tests for the cost settings endpoints (GET/PUT /api/settings/costs)."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.core.models import AppSettings
from src.storage.cost_settings import COST_LEVELS, CostSettingsStore


@pytest.fixture
def cost_store(tmp_path):
    return CostSettingsStore(data_dir=str(tmp_path))


@pytest.fixture
def fake_config():
    config = MagicMock()
    config.settings = AppSettings()
    return config


@pytest.fixture
def client(cost_store, fake_config, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)

    from src.api.app import app
    from src.api import deps

    app.dependency_overrides[deps.get_cost_settings_store] = lambda: cost_store
    app.dependency_overrides[deps.get_config] = lambda: fake_config
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestGetCosts:
    def test_get_returns_settings_and_models(self, client):
        response = client.get("/api/settings/costs")
        assert response.status_code == 200
        body = response.json()
        assert body["cost_level"] == "standard"
        assert body["models"] == COST_LEVELS["standard"]
        assert body["ask_enabled"] is True

    def test_get_open_without_token(self, cost_store, fake_config, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "secret")
        from src.api.app import app
        from src.api import deps

        app.dependency_overrides[deps.get_cost_settings_store] = lambda: cost_store
        app.dependency_overrides[deps.get_config] = lambda: fake_config
        with TestClient(app) as c:
            assert c.get("/api/settings/costs").status_code == 200
        app.dependency_overrides.clear()


class TestPutCosts:
    def test_put_updates_and_applies_models(self, client, cost_store, fake_config):
        response = client.put(
            "/api/settings/costs",
            json={"cost_level": "low", "ask_daily_limit": 50},
        )
        assert response.status_code == 200
        assert cost_store.get().cost_level == "low"
        assert cost_store.get().ask_daily_limit == 50
        # Applied to live config so the next scan uses cheap models
        assert (
            fake_config.settings.analysis.analysis_model
            == COST_LEVELS["low"]["analysis_model"]
        )

    def test_put_rejects_bad_level(self, client):
        response = client.put("/api/settings/costs", json={"cost_level": "platinum"})
        assert response.status_code == 422

    def test_put_requires_admin_token_when_gate_active(
        self, cost_store, fake_config, monkeypatch
    ):
        monkeypatch.setenv("ADMIN_TOKEN", "secret")
        from src.api.app import app
        from src.api import deps

        app.dependency_overrides[deps.get_cost_settings_store] = lambda: cost_store
        app.dependency_overrides[deps.get_config] = lambda: fake_config
        with TestClient(app) as c:
            denied = c.put("/api/settings/costs", json={"cost_level": "low"})
            allowed = c.put(
                "/api/settings/costs",
                json={"cost_level": "low"},
                headers={"X-Admin-Token": "secret"},
            )
        app.dependency_overrides.clear()
        assert denied.status_code == 401
        assert allowed.status_code == 200

    def test_partial_update_keeps_other_fields(self, client, cost_store):
        client.put("/api/settings/costs", json={"ask_daily_limit": 42})
        settings = cost_store.get()
        assert settings.ask_daily_limit == 42
        assert settings.cost_level == "standard"
        assert settings.ask_enabled is True
