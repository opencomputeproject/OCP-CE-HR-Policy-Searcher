"""Tests for the EU "Have Your Say" (Better Regulation portal) source.

The highest-value early-signal source probed: it exposes Commission
initiatives with explicit feedback windows, so an OPEN window means the
community can still influence the outcome. The API is undocumented and
internal, so these tests pin the quirks that broke live probes.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.eu_have_your_say import EUHaveYourSaySource


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


def _initiative(
    *,
    ini_id=14628.0,
    short_title="Cloud and AI Development Act",
    feedback_status="OPEN",
    start="2026/07/15 00:00:00",
    end="2026/09/11 23:59:59",
    stage="OPC_LAUNCHED",
):
    return {
        "id": ini_id,
        "shortTitle": short_title,
        "initiativeStatus": "ACTIVE",
        "reference": "Ares(2025)2876603",
        "foreseenActType": "REGUL",
        "snippet": "<em>cloud</em> and AI",
        "currentStatuses": [{
            "frontEndStage": stage,
            "receivingFeedbackStatus": feedback_status,
            "feedbackStartDate": start,
            "feedbackEndDate": end,
        }],
        "topics": [{"code": "ENER", "label": "Energy"}],
    }


def _search(items):
    return {
        "exactMatch": False,
        "initiativeResultDtoPage": {
            "content": items,
            "totalElements": len(items),
            "totalPages": 1,
        },
    }


def _detail(summary="The Act addresses the EU's cloud and AI infrastructure gap. " * 6):
    return {
        "id": 14628.0,
        "shortTitle": "Cloud and AI Development Act",
        "dossierSummary": summary,
        "dg": "CNECT",
        "initiativeStatus": "ACTIVE",
        "policyAreas": [{"label": "Energy"}],
        "publications": [{"type": "CFE_IMPACT_ASSESS", "totalFeedback": 193}],
    }


class TestEUHaveYourSaySource:
    def test_registered(self):
        assert SOURCE_REGISTRY["eu_have_your_say"] is EUHaveYourSaySource

    def test_is_keyless(self):
        assert EUHaveYourSaySource.api_key_env is None

    @pytest.mark.asyncio
    async def test_search_always_sends_language_and_page(self):
        """Regression: omitting language=EN or page returns HTTP 500
        general_error. Both are effectively required."""
        client = _mock_client([_mock_response(json_data=_search([]))])
        with patch("httpx.AsyncClient", return_value=client):
            await EUHaveYourSaySource().fetch({"source_params": {"terms": ["heat"]}})

        params = client.get.call_args.kwargs["params"]
        assert params["language"] == "EN"
        assert params["page"] == 0

    @pytest.mark.asyncio
    async def test_happy_path(self):
        client = _mock_client([
            _mock_response(json_data=_search([_initiative()])),
            _mock_response(json_data=_detail()),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EUHaveYourSaySource().fetch(
                {"source_params": {"terms": ["data centre"]}}
            )

        assert len(results) == 1
        r = results[0]
        assert r.status == PageStatus.SUCCESS
        assert r.title == "Cloud and AI Development Act"
        assert "cloud and AI infrastructure gap" in r.content

    @pytest.mark.asyncio
    async def test_float_id_becomes_integer_url(self):
        """Regression: id arrives as a float (14628.0). A naive str() would
        build .../initiatives/14628.0 and 404."""
        client = _mock_client([
            _mock_response(json_data=_search([_initiative(ini_id=14628.0)])),
            _mock_response(json_data=_detail()),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EUHaveYourSaySource().fetch(
                {"source_params": {"terms": ["heat"]}}
            )

        assert results[0].url.endswith("/initiatives/14628")
        assert "14628.0" not in results[0].url

    @pytest.mark.asyncio
    async def test_detail_request_omits_text_param(self):
        """Regression: the detail endpoint 500s if ?text= is passed through."""
        client = _mock_client([
            _mock_response(json_data=_search([_initiative()])),
            _mock_response(json_data=_detail()),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            await EUHaveYourSaySource().fetch({"source_params": {"terms": ["heat"]}})

        detail_params = client.get.call_args_list[1].kwargs["params"]
        assert "text" not in detail_params

    @pytest.mark.asyncio
    async def test_open_feedback_is_consultation_stage(self):
        client = _mock_client([
            _mock_response(json_data=_search([_initiative(feedback_status="OPEN")])),
            _mock_response(json_data=_detail()),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EUHaveYourSaySource().fetch(
                {"source_params": {"terms": ["heat"]}}
            )
        assert results[0].lifecycle_stage == "consultation"

    @pytest.mark.asyncio
    async def test_closed_feedback_is_proposed(self):
        client = _mock_client([
            _mock_response(json_data=_search([_initiative(feedback_status="CLOSED")])),
            _mock_response(json_data=_detail()),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EUHaveYourSaySource().fetch(
                {"source_params": {"terms": ["heat"]}}
            )
        assert results[0].lifecycle_stage == "proposed"

    @pytest.mark.asyncio
    async def test_disabled_feedback_is_proposed(self):
        client = _mock_client([
            _mock_response(json_data=_search([_initiative(feedback_status="DISABLED")])),
            _mock_response(json_data=_detail()),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EUHaveYourSaySource().fetch(
                {"source_params": {"terms": ["heat"]}}
            )
        assert results[0].lifecycle_stage == "proposed"

    @pytest.mark.asyncio
    async def test_feedback_deadline_is_in_content(self):
        """An open window is only actionable if the reader sees the deadline."""
        client = _mock_client([
            _mock_response(json_data=_search([_initiative(end="2026/09/11 23:59:59")])),
            _mock_response(json_data=_detail()),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EUHaveYourSaySource().fetch(
                {"source_params": {"terms": ["heat"]}}
            )
        assert "2026/09/11" in results[0].content

    @pytest.mark.asyncio
    async def test_open_only_filter_drops_closed_windows(self):
        client = _mock_client([
            _mock_response(json_data=_search([
                _initiative(ini_id=1.0, feedback_status="CLOSED"),
                _initiative(ini_id=2.0, feedback_status="OPEN"),
            ])),
            _mock_response(json_data=_detail()),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EUHaveYourSaySource().fetch(
                {"source_params": {"terms": ["heat"], "open_only": True}}
            )
        assert len(results) == 1
        assert results[0].url.endswith("/2")

    @pytest.mark.asyncio
    async def test_dedupes_across_terms(self):
        client = _mock_client([
            _mock_response(json_data=_search([_initiative()])),
            _mock_response(json_data=_detail()),
            _mock_response(json_data=_search([_initiative()])),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EUHaveYourSaySource().fetch(
                {"source_params": {"terms": ["heat", "waste heat"]}}
            )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_max_documents_caps_results(self):
        items = [_initiative(ini_id=float(n)) for n in range(8)]
        client = _mock_client(
            [_mock_response(json_data=_search(items))]
            + [_mock_response(json_data=_detail())] * 8
        )
        with patch("httpx.AsyncClient", return_value=client):
            results = await EUHaveYourSaySource().fetch(
                {"source_params": {"terms": ["heat"], "max_documents": 3}}
            )
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_missing_summary_falls_back_to_title(self):
        client = _mock_client([
            _mock_response(json_data=_search([_initiative()])),
            _mock_response(json_data=_detail(summary="")),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EUHaveYourSaySource().fetch(
                {"source_params": {"terms": ["heat"]}}
            )
        assert len(results) == 1
        assert "Cloud and AI Development Act" in results[0].content

    @pytest.mark.asyncio
    async def test_initiative_without_id_is_skipped(self):
        client = _mock_client([
            _mock_response(json_data=_search([{"shortTitle": "No id"}])),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EUHaveYourSaySource().fetch(
                {"source_params": {"terms": ["heat"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_http_error_returns_empty_not_raise(self):
        import httpx as _httpx
        client = _mock_client(_httpx.ConnectError("boom"))
        with patch("httpx.AsyncClient", return_value=client):
            results = await EUHaveYourSaySource().fetch(
                {"source_params": {"terms": ["heat"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_malformed_payload_returns_empty(self):
        client = _mock_client([_mock_response(json_data={"nope": True})])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EUHaveYourSaySource().fetch(
                {"source_params": {"terms": ["heat"]}}
            )
        assert results == []
