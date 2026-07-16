"""Tests for the GovInfo structured policy source."""

from unittest.mock import patch

import pytest

from src.sources.govinfo import GovinfoSource


class _FakeResponse:
    def __init__(self, json_data=None, json_exc=None):
        self._json_data = json_data
        self._json_exc = json_exc

    def raise_for_status(self):
        pass

    def json(self):
        if self._json_exc:
            raise self._json_exc
        return self._json_data


class _FakeAsyncClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url, json=None, **kwargs):
        self.calls.append(json)
        if not self._responses:
            raise AssertionError("no more fake responses queued")
        return self._responses.pop(0)


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setenv("GOVINFO_API_KEY", "test-key")


class TestKeyMissing:
    @pytest.mark.asyncio
    async def test_missing_key_returns_empty_and_makes_no_call(self, monkeypatch):
        monkeypatch.delenv("GOVINFO_API_KEY", raising=False)
        with patch("httpx.AsyncClient") as mock_client_cls:
            result = await GovinfoSource().fetch({})
        assert result == []
        mock_client_cls.assert_not_called()


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_official_url_lifecycle_and_content(self):
        item = {
            "title": "A Bill To Promote Waste Heat Recovery",
            "packageId": "BILLS-119hr1ih",
            "dateIssued": "2026-01-05",
            "summary": "Requires federal data centers to reuse waste heat.",
        }
        fake_client = _FakeAsyncClient([_FakeResponse(json_data={"results": [item]})])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await GovinfoSource().fetch(
                {"source_params": {"terms": ['"waste heat"']}}
            )

        assert len(results) == 1
        r = results[0]
        assert r.url == "https://www.govinfo.gov/app/details/BILLS-119hr1ih"
        assert r.lifecycle_stage == "proposed"
        assert r.content and "Waste Heat Recovery" in r.content


class TestMalformed:
    @pytest.mark.asyncio
    async def test_malformed_response_returns_empty(self):
        fake_client = _FakeAsyncClient([_FakeResponse(json_data={"results": "not-a-list"})])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await GovinfoSource().fetch({"source_params": {"terms": ["x"]}})
        assert results == []

    @pytest.mark.asyncio
    async def test_json_parse_error_returns_empty(self):
        fake_client = _FakeAsyncClient([_FakeResponse(json_exc=ValueError("bad json"))])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await GovinfoSource().fetch({"source_params": {"terms": ["x"]}})
        assert results == []


class TestCap:
    @pytest.mark.asyncio
    async def test_max_documents_respected(self):
        items = [
            {"title": "A", "packageId": "BILLS-1", "dateIssued": "2026-01-01"},
            {"title": "B", "packageId": "BILLS-2", "dateIssued": "2026-01-02"},
        ]
        fake_client = _FakeAsyncClient([_FakeResponse(json_data={"results": items})])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await GovinfoSource().fetch(
                {"source_params": {"terms": ["x"], "max_documents": 1}}
            )
        assert len(results) == 1
