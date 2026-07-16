"""Tests for the LegiScan structured policy source."""

import json
from unittest.mock import patch

import pytest

from src.sources import legiscan
from src.sources.legiscan import LegiscanSource


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


def _search_response(hits) -> _FakeResponse:
    """Build a getSearchRaw response in the REAL live shape.

    The live API returns {"searchresult": {"summary": {...}, "results": [ ... ]}}
    where results is a LIST of hit dicts — not numbered dict keys. Accepts a
    list of hits, or a legacy {"0": hit, ...} dict for existing call sites.
    """
    if isinstance(hits, dict):
        hits = [v for k, v in hits.items() if k != "summary"]
    return _FakeResponse(
        json_data={"searchresult": {"summary": {"count": len(hits)}, "results": hits}}
    )


def _bill_response(bill: dict | None) -> _FakeResponse:
    return _FakeResponse(json_data={"bill": bill} if bill is not None else {})


@pytest.fixture(autouse=True)
def _seen_file(tmp_path, monkeypatch):
    monkeypatch.setattr(legiscan, "SEEN_FILE", tmp_path / "legiscan_seen.json")
    monkeypatch.setattr(legiscan, "USAGE_FILE", tmp_path / "legiscan_usage.json")


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setenv("LEGISCAN_API_KEY", "test-key")


class TestKeyMissing:
    @pytest.mark.asyncio
    async def test_missing_key_returns_empty_and_makes_no_call(self, monkeypatch):
        monkeypatch.delenv("LEGISCAN_API_KEY", raising=False)
        with patch("httpx.AsyncClient") as mock_client_cls:
            result = await LegiscanSource().fetch({})
        assert result == []
        mock_client_cls.assert_not_called()


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_official_url_lifecycle_and_content(self):
        hit = {
            "bill_id": 101,
            "change_hash": "hashA",
            "title": "SB 1",
            "last_action": "Signed by Governor",
        }
        bill = {
            "title": "SB 1 -- Waste Heat Recovery",
            "description": "Requires waste heat recovery at data centers.",
            "state_link": "https://legislature.state.gov/bills/sb1",
            "status_text": "",
        }
        fake_client = _FakeAsyncClient([_search_response({"0": hit}), _bill_response(bill)])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await LegiscanSource().fetch(
                {"source_params": {"terms": ["waste heat"]}}
            )

        assert len(results) == 1
        r = results[0]
        assert r.url == "https://legislature.state.gov/bills/sb1"
        assert "legiscan.com" not in r.url
        assert r.lifecycle_stage == "enacted"
        assert r.content and "Waste Heat Recovery" in r.content


class TestMalformed:
    @pytest.mark.asyncio
    async def test_results_list_shape_is_parsed(self):
        """Regression: live getSearchRaw wraps hits in a 'results' LIST.

        The client previously expected numbered dict keys and silently
        dropped every hit, returning 0 despite thousands of matches.
        """
        hit = {"relevance": 95, "bill_id": 2070805, "change_hash": "abc123"}
        bill = {
            "title": "Waste Heat Recovery Act",
            "description": "Requires CBA for data center waste heat",
            "state_link": "https://leginfo.legislature.ca.gov/bill/AB123",
            "status_text": "In committee",
        }
        fake = _FakeAsyncClient([_search_response([hit]), _bill_response(bill)])
        with patch("httpx.AsyncClient", return_value=fake):
            results = await LegiscanSource().fetch({"source_params": {"terms": ["waste heat"]}})
        assert len(results) == 1
        assert results[0].url == "https://leginfo.legislature.ca.gov/bill/AB123"
        assert results[0].lifecycle_stage == "in_committee"

    async def test_malformed_search_response_returns_empty(self):
        fake_client = _FakeAsyncClient([_FakeResponse(json_exc=json.JSONDecodeError("bad", "", 0))])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await LegiscanSource().fetch({"source_params": {"terms": ["x"]}})
        assert results == []


class TestCap:
    @pytest.mark.asyncio
    async def test_max_documents_respected(self):
        hits = {
            "0": {"bill_id": 1, "change_hash": "h1", "title": "A", "last_action": ""},
            "1": {"bill_id": 2, "change_hash": "h2", "title": "B", "last_action": ""},
        }
        bill = {
            "title": "Bill",
            "description": "desc",
            "state_link": "https://legislature.state.gov/bills/x",
            "status_text": "",
        }
        fake_client = _FakeAsyncClient(
            [_search_response(hits), _bill_response(bill), _bill_response(bill)]
        )
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await LegiscanSource().fetch(
                {"source_params": {"terms": ["x"], "max_documents": 1}}
            )
        assert len(results) == 1


class TestNoStateLinkSkipped:
    @pytest.mark.asyncio
    async def test_bill_without_state_link_is_skipped(self):
        hit = {"bill_id": 5, "change_hash": "h5", "title": "C", "last_action": ""}
        bill = {"title": "C", "description": "desc", "status_text": ""}  # no state_link
        fake_client = _FakeAsyncClient([_search_response({"0": hit}), _bill_response(bill)])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await LegiscanSource().fetch({"source_params": {"terms": ["x"]}})
        assert results == []


class TestUnchangedSkipped:
    @pytest.mark.asyncio
    async def test_unchanged_change_hash_skips_getbill_call(self, tmp_path):
        seen_file = tmp_path / "legiscan_seen.json"
        seen_file.write_text(json.dumps({"9": "same-hash"}), encoding="utf-8")
        legiscan.SEEN_FILE = seen_file

        hit = {"bill_id": 9, "change_hash": "same-hash", "title": "D", "last_action": ""}
        fake_client = _FakeAsyncClient([_search_response({"0": hit})])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await LegiscanSource().fetch({"source_params": {"terms": ["x"]}})

        assert results == []
        assert len(fake_client.calls) == 1  # only the search call, getBill never called


class TestApiCallBudget:
    @pytest.mark.asyncio
    async def test_budget_stops_cleanly(self):
        hit = {"bill_id": 11, "change_hash": "h11", "title": "E", "last_action": ""}
        fake_client = _FakeAsyncClient([_search_response({"0": hit})])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await LegiscanSource().fetch(
                {"source_params": {"terms": ["term1", "term2"], "max_api_calls": 1}}
            )
        assert results == []
        assert len(fake_client.calls) == 1


class TestMonthlyBudget:
    """The 30,000-query/month public limit is enforced with a persistent
    per-calendar-month ledger, so big scans cannot silently overspend."""

    @pytest.mark.asyncio
    async def test_usage_recorded_after_run(self):
        hit = {"bill_id": 7, "change_hash": "h7", "title": "T", "last_action": ""}
        bill = {"title": "T", "description": "d", "state_link": "https://x.gov/b", "status_text": ""}
        fake = _FakeAsyncClient([_search_response({"0": hit}), _bill_response(bill)])
        with patch("httpx.AsyncClient", return_value=fake):
            await LegiscanSource().fetch({"source_params": {"terms": ["t"]}})
        usage = legiscan.monthly_usage()
        assert usage["used"] == 2          # one search + one getBill
        assert usage["remaining"] == legiscan.MONTHLY_QUERY_LIMIT - 2

    @pytest.mark.asyncio
    async def test_run_capped_by_monthly_remaining(self):
        # Pre-seed near the limit: only 1 query left this month
        legiscan._record_usage(legiscan.MONTHLY_QUERY_LIMIT - 1)
        hit = {"bill_id": 7, "change_hash": "h7", "title": "T", "last_action": ""}
        fake = _FakeAsyncClient([_search_response({"0": hit}), _bill_response({})])
        with patch("httpx.AsyncClient", return_value=fake):
            await LegiscanSource().fetch(
                {"source_params": {"terms": ["a", "b"], "max_api_calls": 40}}
            )
        assert len(fake.calls) == 1        # stopped at the 1 remaining query

    @pytest.mark.asyncio
    async def test_at_limit_makes_no_calls(self):
        legiscan._record_usage(legiscan.MONTHLY_QUERY_LIMIT)
        fake = _FakeAsyncClient([_search_response({"0": {"bill_id": 1}})])
        with patch("httpx.AsyncClient", return_value=fake):
            results = await LegiscanSource().fetch({"source_params": {"terms": ["t"]}})
        assert results == []
        assert len(fake.calls) == 0

    def test_month_rollover_resets(self, monkeypatch):
        legiscan.USAGE_FILE.write_text('{"month": "2000-01", "queries": 12345}', encoding="utf-8")
        usage = legiscan.monthly_usage()
        assert usage["used"] == 0          # stale month is ignored


class TestApiStatusError:
    """The Crash Course requires checking the JSON 'status' field. An ERROR
    (e.g. monthly limit exhausted or bad key) returns HTTP 200, so it must be
    detected explicitly and the run must stop rather than burn more queries."""

    @pytest.mark.asyncio
    async def test_error_status_stops_run_without_more_calls(self):
        error = _FakeResponse(json_data={
            "status": "ERROR",
            "alert": {"message": "Query limit exceeded"},
        })
        # A second term's response is queued but must NOT be reached.
        fake_client = _FakeAsyncClient([error, _search_response({"0": {"bill_id": 1}})])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await LegiscanSource().fetch(
                {"source_params": {"terms": ["term1", "term2"], "max_api_calls": 40}}
            )
        assert results == []
        assert len(fake_client.calls) == 1


class TestStateScoping:
    @pytest.mark.asyncio
    async def test_default_searches_all_states(self):
        fake = _FakeAsyncClient([_search_response([])])
        with patch("httpx.AsyncClient", return_value=fake):
            await LegiscanSource().fetch({"source_params": {"terms": ["waste heat"]}})
        assert fake.calls[0]["state"] == "ALL"

    @pytest.mark.asyncio
    async def test_state_param_scopes_search(self):
        fake = _FakeAsyncClient([_search_response([])])
        with patch("httpx.AsyncClient", return_value=fake):
            await LegiscanSource().fetch(
                {"source_params": {"terms": ["waste heat"], "state": "CA"}}
            )
        assert fake.calls[0]["state"] == "CA"

    @pytest.mark.asyncio
    async def test_state_param_normalized_upper(self):
        fake = _FakeAsyncClient([_search_response([])])
        with patch("httpx.AsyncClient", return_value=fake):
            await LegiscanSource().fetch(
                {"source_params": {"terms": ["waste heat"], "state": "ca"}}
            )
        assert fake.calls[0]["state"] == "CA"


class TestEarlySignalTerms:
    def test_default_terms_cover_early_us_bill_vocabulary(self):
        # Real early-stage US bills (NJ A4490, CT HB05337, MN HF4348) are
        # titled "thermal energy network", not "waste heat" — the defaults
        # must speak the language bills actually use.
        assert "thermal energy network" in legiscan.DEFAULT_TERMS
        assert "heat reuse" in legiscan.DEFAULT_TERMS
        assert "waste heat" in legiscan.DEFAULT_TERMS
