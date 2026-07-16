"""Tests for the public reader ask endpoint (POST /api/ask)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.storage.cost_settings import CostSettings, CostSettingsStore


@pytest.fixture
def cost_store(tmp_path):
    return CostSettingsStore(data_dir=str(tmp_path))


@pytest.fixture
def client(tmp_path, cost_store, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)

    from src.api.app import app
    from src.api import deps
    from src.api.routes import ask as ask_route

    app.dependency_overrides[deps.get_cost_settings_store] = lambda: cost_store
    app.dependency_overrides[deps.get_config] = lambda: MagicMock()
    app.dependency_overrides[deps.get_scan_manager] = lambda: MagicMock()
    ask_route.reset_limits_for_tests(data_dir=str(tmp_path))
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _mock_answer(answer="Here are the policies.", tool_calls=1):
    return AsyncMock(return_value={"answer": answer, "tool_calls": tool_calls})


class TestAskValidation:
    def test_question_too_short_rejected(self, client):
        assert client.post("/api/ask", json={"question": "hi"}).status_code == 422

    def test_question_too_long_rejected(self, client):
        assert client.post("/api/ask", json={"question": "x" * 501}).status_code == 422

    def test_missing_question_rejected(self, client):
        assert client.post("/api/ask", json={}).status_code == 422


class TestAskAccess:
    def test_open_without_admin_token_even_when_gate_active(
        self, tmp_path, cost_store, monkeypatch
    ):
        """Readers must be able to ask with the admin gate on — that is the point."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("ADMIN_TOKEN", "secret-admin-token")

        from src.api.app import app
        from src.api import deps
        from src.api.routes import ask as ask_route

        app.dependency_overrides[deps.get_cost_settings_store] = lambda: cost_store
        app.dependency_overrides[deps.get_config] = lambda: MagicMock()
        app.dependency_overrides[deps.get_scan_manager] = lambda: MagicMock()
        ask_route.reset_limits_for_tests(data_dir=str(tmp_path))
        with (
            patch("src.api.routes.ask.answer_question", new=_mock_answer()),
            TestClient(app) as c,
        ):
            response = c.post("/api/ask", json={"question": "What has Germany passed?"})
        app.dependency_overrides.clear()
        assert response.status_code == 200

    def test_503_when_disabled(self, client, cost_store):
        cost_store.update(CostSettings(ask_enabled=False))
        response = client.post("/api/ask", json={"question": "What has Germany passed?"})
        assert response.status_code == 503
        assert "disabled" in response.json()["detail"].lower()

    def test_503_without_api_key(self, client, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        response = client.post("/api/ask", json={"question": "What has Germany passed?"})
        assert response.status_code == 503


class TestAskAnswers:
    def test_success_returns_answer(self, client):
        with patch(
            "src.api.routes.ask.answer_question",
            new=_mock_answer("Germany requires heat reuse plans."),
        ):
            response = client.post("/api/ask", json={"question": "What about Germany?"})
        assert response.status_code == 200
        body = response.json()
        assert body["answer"] == "Germany requires heat reuse plans."
        assert "remaining_today" in body

    def test_agent_failure_returns_500_without_internals(self, client):
        with patch(
            "src.api.routes.ask.answer_question",
            new=AsyncMock(side_effect=RuntimeError("boom internal")),
        ):
            response = client.post("/api/ask", json={"question": "What about Germany?"})
        assert response.status_code == 500
        assert "boom" not in response.json()["detail"]


class TestClientIp:
    def test_prefers_forwarded_for_leftmost(self):
        from src.api.routes.ask import _client_ip

        class _Req:
            headers = {"x-forwarded-for": "203.0.113.7, 10.0.0.1, 10.0.0.2"}
            class client:  # noqa: N801
                host = "10.0.0.1"

        assert _client_ip(_Req()) == "203.0.113.7"

    def test_falls_back_to_client_host(self):
        from src.api.routes.ask import _client_ip

        class _Req:
            headers = {}
            class client:  # noqa: N801
                host = "198.51.100.9"

        assert _client_ip(_Req()) == "198.51.100.9"

    def test_distinct_forwarded_ips_get_separate_buckets(self, client, cost_store):
        """Behind a proxy, two real users must not share one rate bucket."""
        cost_store.update(CostSettings(ask_rate_per_minute=1, ask_daily_limit=100))
        with patch("src.api.routes.ask.answer_question", new=_mock_answer()):
            r1 = client.post(
                "/api/ask", json={"question": "German policies?"},
                headers={"X-Forwarded-For": "203.0.113.1"},
            )
            r2 = client.post(
                "/api/ask", json={"question": "German policies?"},
                headers={"X-Forwarded-For": "203.0.113.2"},
            )
        assert r1.status_code == 200
        assert r2.status_code == 200  # different client, not throttled


class TestAskLimits:
    def test_per_minute_rate_limit(self, client, cost_store):
        cost_store.update(CostSettings(ask_rate_per_minute=2, ask_daily_limit=100))
        with patch("src.api.routes.ask.answer_question", new=_mock_answer()):
            for _ in range(2):
                assert (
                    client.post("/api/ask", json={"question": "German policies?"}).status_code
                    == 200
                )
            response = client.post("/api/ask", json={"question": "German policies?"})
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    def test_daily_limit(self, client, cost_store):
        cost_store.update(CostSettings(ask_rate_per_minute=60, ask_daily_limit=1))
        with patch("src.api.routes.ask.answer_question", new=_mock_answer()):
            assert (
                client.post("/api/ask", json={"question": "German policies?"}).status_code
                == 200
            )
            response = client.post("/api/ask", json={"question": "German policies?"})
        assert response.status_code == 429
        assert "daily" in response.json()["detail"].lower()

    def test_daily_usage_persists_across_restart(self, client, cost_store, tmp_path):
        from src.api.routes import ask as ask_route

        cost_store.update(CostSettings(ask_rate_per_minute=60, ask_daily_limit=1))
        with patch("src.api.routes.ask.answer_question", new=_mock_answer()):
            assert (
                client.post("/api/ask", json={"question": "German policies?"}).status_code
                == 200
            )
            # Simulate restart: reload limiter state from disk
            ask_route.reset_limits_for_tests(data_dir=str(tmp_path), keep_usage_file=True)
            response = client.post("/api/ask", json={"question": "German policies?"})
        assert response.status_code == 429
