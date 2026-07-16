"""Tests for the Regulations.gov structured policy source."""

from unittest.mock import patch

import pytest

from src.sources.regulations_gov import RegulationsGovSource


class _FakeResponse:
    def __init__(self, json_data=None, json_exc=None, status_code=200, headers=None):
        self._json_data = json_data
        self._json_exc = json_exc
        self.status_code = status_code
        self.headers = headers or {}

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


def _doc(doc_id: str, **attrs) -> dict:
    return {"id": doc_id, "attributes": attrs}


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setenv("REGULATIONSGOV_API_KEY", "test-key")


class TestKeyMissing:
    @pytest.mark.asyncio
    async def test_missing_key_returns_empty_and_makes_no_call(self, monkeypatch):
        monkeypatch.delenv("REGULATIONSGOV_API_KEY", raising=False)
        with patch("httpx.AsyncClient") as mock_client_cls:
            result = await RegulationsGovSource().fetch({})
        assert result == []
        mock_client_cls.assert_not_called()


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_open_comment_period_is_consultation(self):
        item = _doc(
            "EPA-2026-0001",
            title="Data Center Energy Efficiency Rule",
            documentType="Proposed Rule",
            docketId="EPA-2026-0001",
            postedDate="2026-01-01T00:00:00Z",
            commentEndDate="2099-01-01T00:00:00Z",
        )
        fake_client = _FakeAsyncClient([_FakeResponse(json_data={"data": [item]})])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await RegulationsGovSource().fetch(
                {"source_params": {"terms": ["data center energy efficiency"]}}
            )

        assert len(results) == 1
        r = results[0]
        assert r.url == "https://www.regulations.gov/document/EPA-2026-0001"
        assert r.lifecycle_stage == "consultation"
        assert "2099-01-01" in r.content

    @pytest.mark.asyncio
    async def test_closed_comment_period_is_proposed(self):
        item = _doc(
            "EPA-2020-0001",
            title="Old Rule",
            documentType="Rule",
            docketId="EPA-2020-0001",
            postedDate="2020-01-01T00:00:00Z",
            commentEndDate="2020-02-01T00:00:00Z",
        )
        fake_client = _FakeAsyncClient([_FakeResponse(json_data={"data": [item]})])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await RegulationsGovSource().fetch({"source_params": {"terms": ["x"]}})

        assert len(results) == 1
        assert results[0].lifecycle_stage == "proposed"


class TestMalformed:
    @pytest.mark.asyncio
    async def test_malformed_response_returns_empty(self):
        fake_client = _FakeAsyncClient([_FakeResponse(json_data={"data": "not-a-list"})])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await RegulationsGovSource().fetch({"source_params": {"terms": ["x"]}})
        assert results == []

    @pytest.mark.asyncio
    async def test_json_parse_error_returns_empty(self):
        fake_client = _FakeAsyncClient([_FakeResponse(json_exc=ValueError("bad json"))])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await RegulationsGovSource().fetch({"source_params": {"terms": ["x"]}})
        assert results == []


class TestCap:
    @pytest.mark.asyncio
    async def test_max_documents_respected(self):
        items = [
            _doc("A", title="A", documentType="Rule", postedDate="2026-01-01"),
            _doc("B", title="B", documentType="Rule", postedDate="2026-01-02"),
        ]
        fake_client = _FakeAsyncClient([_FakeResponse(json_data={"data": items})])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await RegulationsGovSource().fetch(
                {"source_params": {"terms": ["x"], "max_documents": 1}}
            )
        assert len(results) == 1


class TestRateLimit:
    @pytest.mark.asyncio
    async def test_429_stops_fetch_without_trying_more_terms(self):
        """On a 429 the client must stop, not keep hammering the API with
        the remaining search terms (api.data.gov: 1000 GET/hour)."""
        first = _doc("A", title="A", documentType="Rule", postedDate="2026-01-01")
        responses = [
            _FakeResponse(json_data={"data": [first]}),          # term 1 ok
            _FakeResponse(status_code=429, headers={"Retry-After": "60"}),  # term 2 throttled
            _FakeResponse(json_data={"data": [_doc("C", title="C")]}),  # must NOT be reached
        ]
        fake_client = _FakeAsyncClient(responses)
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await RegulationsGovSource().fetch(
                {"source_params": {"terms": ["t1", "t2", "t3"], "max_documents": 25}}
            )
        # Kept the first term's result; stopped at the 429 (2 calls, not 3)
        assert len(results) == 1
        assert len(fake_client.calls) == 2
