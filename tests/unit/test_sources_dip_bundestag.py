"""Tests for the DIP (Bundestag) structured policy source."""

from unittest.mock import patch

import pytest

from src.sources.dip_bundestag import DipBundestagSource


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

    async def get(self, url, params=None, **kwargs):
        self.calls.append(params)
        if not self._responses:
            raise AssertionError("no more fake responses queued")
        return self._responses.pop(0)


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setenv("DIP_API_KEY", "test-key")


class TestKeyMissing:
    @pytest.mark.asyncio
    async def test_missing_key_returns_empty_and_makes_no_call(self, monkeypatch):
        monkeypatch.delenv("DIP_API_KEY", raising=False)
        with patch("httpx.AsyncClient") as mock_client_cls:
            result = await DipBundestagSource().fetch({})
        assert result == []
        mock_client_cls.assert_not_called()


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_enacted_lifecycle_and_content(self):
        item = {
            "id": "12345",
            "titel": "Gesetz zur Nutzung von Abwärme aus Rechenzentren",
            "vorgangstyp": "Gesetzgebung",
            "beratungsstand": "Gesetz verkündet",
        }
        fake_client = _FakeAsyncClient([_FakeResponse(json_data={"documents": [item]})])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await DipBundestagSource().fetch(
                {"source_params": {"terms": ["Abwärme"]}}
            )

        assert len(results) == 1
        r = results[0]
        assert r.url == "https://dip.bundestag.de/vorgang/12345"
        assert r.lifecycle_stage == "enacted"
        assert r.content and "Abwärme" in r.content

    @pytest.mark.asyncio
    async def test_committee_lifecycle(self):
        item = {
            "id": "999",
            "titel": "Wärmeplanungsgesetz",
            "vorgangstyp": "Gesetzgebung",
            "beratungsstand": "Überweisung an Ausschuss",
        }
        fake_client = _FakeAsyncClient([_FakeResponse(json_data={"documents": [item]})])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await DipBundestagSource().fetch({"source_params": {"terms": ["x"]}})

        assert results[0].lifecycle_stage == "in_committee"


class TestMalformed:
    @pytest.mark.asyncio
    async def test_malformed_response_returns_empty(self):
        fake_client = _FakeAsyncClient([_FakeResponse(json_data={"documents": "not-a-list"})])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await DipBundestagSource().fetch({"source_params": {"terms": ["x"]}})
        assert results == []

    @pytest.mark.asyncio
    async def test_json_parse_error_returns_empty(self):
        fake_client = _FakeAsyncClient([_FakeResponse(json_exc=ValueError("bad json"))])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await DipBundestagSource().fetch({"source_params": {"terms": ["x"]}})
        assert results == []


class TestCap:
    @pytest.mark.asyncio
    async def test_max_documents_respected(self):
        items = [
            {"id": "1", "titel": "A", "vorgangstyp": "t", "beratungsstand": "eingebracht"},
            {"id": "2", "titel": "B", "vorgangstyp": "t", "beratungsstand": "eingebracht"},
        ]
        fake_client = _FakeAsyncClient([_FakeResponse(json_data={"documents": items})])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await DipBundestagSource().fetch(
                {"source_params": {"terms": ["x"], "max_documents": 1}}
            )
        assert len(results) == 1
