"""Tests for the Ireland Oireachtas structured policy source.

The Oireachtas API has NO full-text search, so this source pages through
bills by status and matches terms against the titles client-side. Ireland
is a top EU data-centre market with no structured coverage before this.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.oireachtas import OireachtasSource


def _mock_response(*, json_data=None, text="", status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.headers = {"content-type": "text/html"}
    resp.json = MagicMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    return resp


def _mock_client(get_side_effect):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.get = AsyncMock(side_effect=get_side_effect)
    return client


def _bill(
    *,
    bill_no="80",
    year="2026",
    status="Current",
    short_title="Heat Networks Bill 2026",
    long_title="<p>An Act to provide for district heating networks.</p>",
    stage="Second Stage",
):
    return {
        "bill": {
            "billNo": bill_no,
            "billYear": year,
            "billType": "Public",
            "status": status,
            "shortTitleEn": short_title,
            "longTitleEn": long_title,
            "lastUpdated": "2026-07-09",
            "uri": f"https://data.oireachtas.ie/ie/oireachtas/bill/{year}/{bill_no}",
            "mostRecentStage": {"event": {"showAs": stage}},
        }
    }


def _payload(bills):
    return {
        "head": {"counts": {"billCount": len(bills), "resultCount": len(bills)}},
        "results": bills,
    }


LONG_HTML = "<html><body>" + ("District heating provisions. " * 30) + "</body></html>"


class TestOireachtasSource:
    def test_registered(self):
        assert SOURCE_REGISTRY["oireachtas"] is OireachtasSource

    def test_is_keyless(self):
        assert OireachtasSource.api_key_env is None

    def test_default_terms_use_irish_english_spelling(self):
        # Ireland writes "data centre", never "data center". A US-spelled
        # term list would silently match nothing.
        from src.sources.oireachtas import DEFAULT_TERMS
        joined = " ".join(DEFAULT_TERMS)
        assert "data centre" in joined
        assert "data center" not in joined

    def test_default_terms_are_broad_single_words(self):
        """Regression: title-only matching needs breadth, not domain phrases.

        Measured on all 1024 live bills: "waste heat" and "data centre"
        matched 0, while "energy" matched 24 including "Prevention of Energy
        Wastage Bill 2026". Narrow phrases make this source silently empty.
        """
        from src.sources.oireachtas import DEFAULT_TERMS
        assert "heat" in DEFAULT_TERMS
        assert "energy" in DEFAULT_TERMS

    def test_broad_term_catches_title_without_domain_phrase(self):
        """"Prevention of Energy Wastage Bill" must match, though it never
        says "waste heat"."""
        bill = _bill(short_title="Prevention of Energy Wastage Bill 2026",
                     long_title="<p>An Act to prevent the wastage of energy.</p>")["bill"]
        from src.sources.oireachtas import DEFAULT_TERMS
        assert OireachtasSource._matches(bill, [t.lower() for t in DEFAULT_TERMS])

    @pytest.mark.asyncio
    async def test_happy_path_matches_title_and_fetches_bill_page(self):
        list_resp = _mock_response(json_data=_payload([_bill()]))
        doc_resp = _mock_response(text=LONG_HTML)
        client = _mock_client([list_resp, doc_resp])

        with patch("httpx.AsyncClient", return_value=client):
            results = await OireachtasSource().fetch(
                {"source_params": {"terms": ["district heating"], "bill_statuses": ["Current"]}}
            )

        assert len(results) == 1
        result = results[0]
        assert result.status == PageStatus.SUCCESS
        # Citation of record is the human-readable page, not the data URI.
        assert result.url == "https://www.oireachtas.ie/en/bills/bill/2026/80/"
        assert result.title == "Heat Networks Bill 2026"
        assert "District heating provisions." in result.content

    @pytest.mark.asyncio
    async def test_non_matching_bill_is_skipped(self):
        list_resp = _mock_response(json_data=_payload([
            _bill(short_title="Aircraft Munitions Bill",
                  long_title="<p>An Act about aircraft.</p>")
        ]))
        client = _mock_client([list_resp])

        with patch("httpx.AsyncClient", return_value=client):
            results = await OireachtasSource().fetch(
                {"source_params": {"terms": ["district heating"], "bill_statuses": ["Current"]}}
            )

        assert results == []

    @pytest.mark.asyncio
    async def test_matches_long_title_when_short_title_does_not(self):
        list_resp = _mock_response(json_data=_payload([
            _bill(short_title="Miscellaneous Provisions Bill",
                  long_title="<p>An Act concerning waste heat recovery.</p>")
        ]))
        doc_resp = _mock_response(text=LONG_HTML)
        client = _mock_client([list_resp, doc_resp])

        with patch("httpx.AsyncClient", return_value=client):
            results = await OireachtasSource().fetch(
                {"source_params": {"terms": ["waste heat"], "bill_statuses": ["Current"]}}
            )

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_match_is_case_insensitive(self):
        list_resp = _mock_response(json_data=_payload([
            _bill(short_title="DISTRICT HEATING BILL")
        ]))
        doc_resp = _mock_response(text=LONG_HTML)
        client = _mock_client([list_resp, doc_resp])

        with patch("httpx.AsyncClient", return_value=client):
            results = await OireachtasSource().fetch(
                {"source_params": {"terms": ["district heating"], "bill_statuses": ["Current"]}}
            )

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_enacted_status_maps_to_enacted(self):
        list_resp = _mock_response(json_data=_payload([
            _bill(status="Enacted", stage="Enacted")
        ]))
        doc_resp = _mock_response(text=LONG_HTML)
        client = _mock_client([list_resp, doc_resp])

        with patch("httpx.AsyncClient", return_value=client):
            results = await OireachtasSource().fetch(
                {"source_params": {"terms": ["district heating"], "bill_statuses": ["Current"]}}
            )

        assert results[0].lifecycle_stage == "enacted"

    @pytest.mark.asyncio
    async def test_committee_stage_maps_to_in_committee(self):
        list_resp = _mock_response(json_data=_payload([
            _bill(stage="Committee Stage")
        ]))
        doc_resp = _mock_response(text=LONG_HTML)
        client = _mock_client([list_resp, doc_resp])

        with patch("httpx.AsyncClient", return_value=client):
            results = await OireachtasSource().fetch(
                {"source_params": {"terms": ["district heating"], "bill_statuses": ["Current"]}}
            )

        assert results[0].lifecycle_stage == "in_committee"

    @pytest.mark.asyncio
    async def test_current_bill_defaults_to_proposed(self):
        list_resp = _mock_response(json_data=_payload([_bill(stage="Second Stage")]))
        doc_resp = _mock_response(text=LONG_HTML)
        client = _mock_client([list_resp, doc_resp])

        with patch("httpx.AsyncClient", return_value=client):
            results = await OireachtasSource().fetch(
                {"source_params": {"terms": ["district heating"], "bill_statuses": ["Current"]}}
            )

        assert results[0].lifecycle_stage == "proposed"

    @pytest.mark.asyncio
    async def test_falls_back_to_titles_when_page_fetch_is_thin(self):
        """A failed page fetch must still yield the bill, not drop it."""
        list_resp = _mock_response(json_data=_payload([_bill()]))
        thin_resp = _mock_response(text="<html><body>x</body></html>")
        client = _mock_client([list_resp, thin_resp])

        with patch("httpx.AsyncClient", return_value=client):
            results = await OireachtasSource().fetch(
                {"source_params": {"terms": ["district heating"], "bill_statuses": ["Current"]}}
            )

        assert len(results) == 1
        assert "Heat Networks Bill 2026" in results[0].content
        # HTML tags from longTitleEn must not leak into content.
        assert "<p>" not in results[0].content

    @pytest.mark.asyncio
    async def test_max_documents_caps_results(self):
        bills = [_bill(bill_no=str(n)) for n in range(10)]
        list_resp = _mock_response(json_data=_payload(bills))
        doc_resp = _mock_response(text=LONG_HTML)
        client = _mock_client([list_resp] + [doc_resp] * 10)

        with patch("httpx.AsyncClient", return_value=client):
            results = await OireachtasSource().fetch({
                "source_params": {"terms": ["district heating"], "bill_statuses": ["Current"], "max_documents": 3}
            })

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_duplicate_bills_are_deduped(self):
        list_resp = _mock_response(json_data=_payload([_bill(), _bill()]))
        doc_resp = _mock_response(text=LONG_HTML)
        client = _mock_client([list_resp, doc_resp, doc_resp])

        with patch("httpx.AsyncClient", return_value=client):
            results = await OireachtasSource().fetch(
                {"source_params": {"terms": ["district heating"], "bill_statuses": ["Current"]}}
            )

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_http_error_returns_empty_not_raise(self):
        import httpx as _httpx
        client = _mock_client(_httpx.ConnectError("boom"))

        with patch("httpx.AsyncClient", return_value=client):
            results = await OireachtasSource().fetch({})

        assert results == []

    @pytest.mark.asyncio
    async def test_malformed_payload_returns_empty(self):
        # One response per default status (Current, Enacted).
        bad = _mock_response(json_data={"unexpected": True})
        client = _mock_client([bad, bad])

        with patch("httpx.AsyncClient", return_value=client):
            results = await OireachtasSource().fetch({})

        assert results == []

    @pytest.mark.asyncio
    async def test_default_queries_both_current_and_enacted(self):
        """Enacted law matters as much as pending bills; both must be asked for."""
        empty = _mock_response(json_data=_payload([]))
        client = _mock_client([empty, empty])

        with patch("httpx.AsyncClient", return_value=client):
            await OireachtasSource().fetch({})

        statuses = [c.kwargs["params"]["bill_status"] for c in client.get.call_args_list]
        assert statuses == ["Current", "Enacted"]
