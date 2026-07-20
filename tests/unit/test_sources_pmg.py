"""Tests for the South Africa PMG structured policy source.

PMG's call-for-comment feed carries open comment windows — the class of
early signal this project prizes. Bills and CFCs are separate endpoints,
both paged newest-first with per_page capped at 50 server-side.
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.pmg import PMGSource

FUTURE = (date.today() + timedelta(days=21)).isoformat()
PAST = (date.today() - timedelta(days=21)).isoformat()


def _mock_response(*, json_data=None, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {"content-type": "application/json"}
    resp.json = MagicMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    return resp


def _mock_client(get_side_effect):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.get = AsyncMock(side_effect=get_side_effect)
    return client


def _cfc(*, cfc_id=1743, title="Gas Bill", end_date=FUTURE, body=None):
    if body is None:
        body = (
            "<p>The Portfolio Committee on Electricity and Energy invites "
            "written comments on the <a href='https://pmg.org.za/files/B6-2026_Gas.pdf'>"
            "Gas Bill [B6 - 2026]</a>. The Bill provides for gas infrastructure "
            "development and energy regulation.</p>"
        )
    return {
        "id": cfc_id,
        "title": title,
        "start_date": "2026-07-16",
        "end_date": end_date,
        "committee_id": 3,
        "body": body,
    }


def _bill(*, bill_id=1319, title="Energy Efficiency Amendment Bill",
          assent=None, intro="2026-01-15"):
    return {
        "id": bill_id,
        "title": title,
        "year": 2026,
        "date_of_introduction": intro,
        "date_of_assent": assent,
        "introduced_by": "Minister of Electricity and Energy",
        "type": {"id": 1, "name": "Draft", "prefix": "X"},
        "url": f"http://api.pmg.org.za/bill/{bill_id}/",
    }


def _page(results, *, count=None, next_url=None):
    return {
        "count": count if count is not None else len(results),
        "next": next_url,
        "results": results,
    }


class TestPMGSource:
    def test_registered(self):
        assert SOURCE_REGISTRY["pmg"] is PMGSource

    def test_is_keyless(self):
        assert PMGSource.api_key_env is None

    @pytest.mark.asyncio
    async def test_open_cfc_is_consultation_with_deadline_in_content(self):
        client = _mock_client([
            _mock_response(json_data=_page([_cfc()])),   # call-for-comment
            _mock_response(json_data=_page([])),          # bills
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await PMGSource().fetch(
                {"source_params": {"terms": ["gas"]}}
            )

        assert len(results) == 1
        r = results[0]
        assert r.status == PageStatus.SUCCESS
        assert r.url == "https://pmg.org.za/call-for-comment/1743/"
        assert r.lifecycle_stage == "consultation"
        assert FUTURE in r.content
        # HTML must be stripped, not shipped.
        assert "<p>" not in r.content
        assert "gas infrastructure" in r.content

    @pytest.mark.asyncio
    async def test_closed_cfc_leaves_stage_for_the_model(self):
        """A closed window is history, not an open consultation. The bill
        behind it may be anywhere in the pipeline, so claim nothing."""
        client = _mock_client([
            _mock_response(json_data=_page([_cfc(end_date=PAST)])),
            _mock_response(json_data=_page([])),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await PMGSource().fetch(
                {"source_params": {"terms": ["gas"]}}
            )
        assert results[0].lifecycle_stage is None

    @pytest.mark.asyncio
    async def test_cfc_without_end_date_leaves_stage_for_the_model(self):
        client = _mock_client([
            _mock_response(json_data=_page([_cfc(end_date=None)])),
            _mock_response(json_data=_page([])),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await PMGSource().fetch(
                {"source_params": {"terms": ["gas"]}}
            )
        assert results[0].lifecycle_stage is None

    @pytest.mark.asyncio
    async def test_bill_without_assent_is_proposed(self):
        client = _mock_client([
            _mock_response(json_data=_page([])),
            _mock_response(json_data=_page([_bill()])),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await PMGSource().fetch(
                {"source_params": {"terms": ["energy"]}}
            )
        assert len(results) == 1
        r = results[0]
        assert r.url == "https://pmg.org.za/bill/1319/"
        assert r.lifecycle_stage == "proposed"

    @pytest.mark.asyncio
    async def test_assented_bill_is_enacted(self):
        client = _mock_client([
            _mock_response(json_data=_page([])),
            _mock_response(json_data=_page([_bill(assent="2026-06-01")])),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await PMGSource().fetch(
                {"source_params": {"terms": ["energy"]}}
            )
        assert results[0].lifecycle_stage == "enacted"

    @pytest.mark.asyncio
    async def test_cfc_matches_on_body_not_just_title(self):
        """CFC titles are terse ("Gas Bill"); the body carries the meat.
        A term that only appears in the body must still match."""
        client = _mock_client([
            _mock_response(json_data=_page([_cfc(title="B6-2026")])),
            _mock_response(json_data=_page([])),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await PMGSource().fetch(
                {"source_params": {"terms": ["energy regulation"]}}
            )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_non_matching_items_are_skipped(self):
        client = _mock_client([
            _mock_response(json_data=_page([_cfc(title="Liquor Amendment Bill")])),
            _mock_response(json_data=_page([_bill(title="Public Procurement Amendment Bill")])),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await PMGSource().fetch(
                {"source_params": {"terms": ["district heating"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_pagination_follows_next_up_to_max_pages(self):
        page1 = _page(
            [_cfc(cfc_id=1, title="Water Bill", body="<p>Water services comments.</p>")],
            count=100,
            next_url="https://api.pmg.org.za/call-for-comment/?page=1",
        )
        page2 = _page([_cfc(cfc_id=2, title="Gas Bill")], count=100)
        client = _mock_client([
            _mock_response(json_data=page1),
            _mock_response(json_data=page2),
            _mock_response(json_data=_page([])),  # bills
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await PMGSource().fetch(
                {"source_params": {"terms": ["gas"], "max_pages": 2}}
            )
        assert len(results) == 1
        assert results[0].url == "https://pmg.org.za/call-for-comment/2/"

    @pytest.mark.asyncio
    async def test_max_pages_stops_even_if_next_continues(self):
        page = _page([_cfc(cfc_id=1, title="Water Bill")], count=1000,
                     next_url="https://api.pmg.org.za/call-for-comment/?page=1")
        client = _mock_client([
            _mock_response(json_data=page),
            _mock_response(json_data=_page([])),  # bills
        ])
        with patch("httpx.AsyncClient", return_value=client):
            await PMGSource().fetch(
                {"source_params": {"terms": ["gas"], "max_pages": 1}}
            )
        # 1 CFC page + 1 bill page = exactly 2 requests.
        assert client.get.await_count == 2

    @pytest.mark.asyncio
    async def test_max_documents_caps_across_endpoints(self):
        cfcs = [_cfc(cfc_id=n, title=f"Energy Bill {n}") for n in range(5)]
        bills = [_bill(bill_id=n, title=f"Energy Act {n}") for n in range(5)]
        client = _mock_client([
            _mock_response(json_data=_page(cfcs)),
            _mock_response(json_data=_page(bills)),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await PMGSource().fetch(
                {"source_params": {"terms": ["energy"], "max_documents": 4}}
            )
        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_http_error_returns_empty_not_raise(self):
        import httpx as _httpx
        client = _mock_client(_httpx.ConnectError("boom"))
        with patch("httpx.AsyncClient", return_value=client):
            results = await PMGSource().fetch(
                {"source_params": {"terms": ["energy"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_one_endpoint_down_does_not_kill_the_other(self):
        import httpx as _httpx
        client = _mock_client([
            _httpx.ConnectError("cfc down"),
            _mock_response(json_data=_page([_bill()])),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await PMGSource().fetch(
                {"source_params": {"terms": ["energy"]}}
            )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_malformed_payload_returns_empty(self):
        client = _mock_client([
            _mock_response(json_data={"nope": 1}),
            _mock_response(json_data={"nope": 1}),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await PMGSource().fetch(
                {"source_params": {"terms": ["energy"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_items_without_id_are_skipped(self):
        cfc = _cfc()
        del cfc["id"]
        bill = _bill()
        del bill["id"]
        client = _mock_client([
            _mock_response(json_data=_page([cfc])),
            _mock_response(json_data=_page([bill])),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await PMGSource().fetch(
                {"source_params": {"terms": ["energy", "gas"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_garbage_end_date_does_not_crash(self):
        client = _mock_client([
            _mock_response(json_data=_page([_cfc(end_date="not-a-date")])),
            _mock_response(json_data=_page([])),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await PMGSource().fetch(
                {"source_params": {"terms": ["gas"]}}
            )
        assert len(results) == 1
        assert results[0].lifecycle_stage is None
