"""Tests for the UK gov.uk consultations structured policy source.

Complements the existing uk_bills source: consultations and policy papers
appear well before a bill exists, and an open consultation is the one
window where outside input can still shape the outcome.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.govuk import GovUKSource


def _mock_response(*, json_data=None, text="", status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
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


def _search(results, total=None):
    return {"results": results, "total": total if total is not None else len(results)}


def _hit(*, title="Heat network technical standards",
         link="/government/consultations/heat-network-technical-standards",
         fmt="open_consultation", ts="2026-01-21T13:13:11Z"):
    return {"title": title, "link": link, "format": fmt,
            "description": "About heat networks", "public_timestamp": ts}


def _content(*, body="<p>" + ("Heat network standards body. " * 30) + "</p>",
             closing_date=None, opening_date=None):
    details = {"body": body}
    if closing_date:
        details["closing_date"] = closing_date
    if opening_date:
        details["opening_date"] = opening_date
    return {
        "base_path": "/government/consultations/heat-network-technical-standards",
        "first_published_at": "2026-01-21T13:13:11+00:00",
        "details": details,
    }


class TestGovUKSource:
    def test_registered(self):
        assert SOURCE_REGISTRY["govuk"] is GovUKSource

    def test_is_keyless(self):
        assert GovUKSource.api_key_env is None

    def test_default_terms_use_british_spelling(self):
        from src.sources.govuk import DEFAULT_TERMS
        joined = " ".join(DEFAULT_TERMS)
        assert "data centre" in joined
        assert "data center" not in joined

    @pytest.mark.asyncio
    async def test_happy_path(self):
        client = _mock_client([
            _mock_response(json_data=_search([_hit()])),
            _mock_response(json_data=_content()),
        ])

        with patch("httpx.AsyncClient", return_value=client):
            results = await GovUKSource().fetch(
                {"source_params": {"terms": ["heat network"]}}
            )

        assert len(results) == 1
        r = results[0]
        assert r.status == PageStatus.SUCCESS
        # Search returns a path; the citation must be an absolute gov.uk URL.
        assert r.url == (
            "https://www.gov.uk/government/consultations/heat-network-technical-standards"
        )
        assert r.title == "Heat network technical standards"
        assert "Heat network standards body." in r.content
        # HTML must be stripped, not passed through raw.
        assert "<p>" not in r.content

    @pytest.mark.asyncio
    async def test_open_consultation_is_consultation_stage(self):
        client = _mock_client([
            _mock_response(json_data=_search([_hit(fmt="open_consultation")])),
            _mock_response(json_data=_content()),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await GovUKSource().fetch({"source_params": {"terms": ["heat"]}})
        assert results[0].lifecycle_stage == "consultation"

    @pytest.mark.asyncio
    async def test_open_call_for_evidence_is_consultation_stage(self):
        client = _mock_client([
            _mock_response(json_data=_search([_hit(fmt="open_call_for_evidence")])),
            _mock_response(json_data=_content()),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await GovUKSource().fetch({"source_params": {"terms": ["heat"]}})
        assert results[0].lifecycle_stage == "consultation"

    @pytest.mark.asyncio
    async def test_closed_consultation_is_proposed_not_consultation(self):
        """A closed window is not an opportunity; it must not read as one."""
        client = _mock_client([
            _mock_response(json_data=_search([_hit(fmt="closed_consultation")])),
            _mock_response(json_data=_content()),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await GovUKSource().fetch({"source_params": {"terms": ["heat"]}})
        assert results[0].lifecycle_stage == "proposed"

    @pytest.mark.asyncio
    async def test_closing_date_is_folded_into_content(self):
        """The deadline is the whole point of an open consultation, so the
        analysis model must see it in the text."""
        client = _mock_client([
            _mock_response(json_data=_search([_hit(fmt="open_consultation")])),
            _mock_response(json_data=_content(closing_date="2026-09-30T23:45:00+00:00")),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await GovUKSource().fetch({"source_params": {"terms": ["heat"]}})
        assert "2026-09-30" in results[0].content

    @pytest.mark.asyncio
    async def test_dedupes_same_link_across_terms(self):
        client = _mock_client([
            _mock_response(json_data=_search([_hit()])),
            _mock_response(json_data=_content()),
            _mock_response(json_data=_search([_hit()])),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await GovUKSource().fetch(
                {"source_params": {"terms": ["heat network", "waste heat"]}}
            )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_max_documents_caps_results(self):
        hits = [_hit(link=f"/government/consultations/c{n}") for n in range(8)]
        client = _mock_client(
            [_mock_response(json_data=_search(hits))]
            + [_mock_response(json_data=_content())] * 8
        )
        with patch("httpx.AsyncClient", return_value=client):
            results = await GovUKSource().fetch(
                {"source_params": {"terms": ["heat"], "max_documents": 3}}
            )
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_falls_back_to_description_when_body_empty(self):
        client = _mock_client([
            _mock_response(json_data=_search([_hit()])),
            _mock_response(json_data=_content(body="")),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await GovUKSource().fetch({"source_params": {"terms": ["heat"]}})
        assert len(results) == 1
        assert "About heat networks" in results[0].content

    @pytest.mark.asyncio
    async def test_hit_without_link_is_skipped(self):
        client = _mock_client([
            _mock_response(json_data=_search([{"title": "No link", "format": "policy_paper"}])),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await GovUKSource().fetch({"source_params": {"terms": ["heat"]}})
        assert results == []

    @pytest.mark.asyncio
    async def test_http_error_returns_empty_not_raise(self):
        import httpx as _httpx
        client = _mock_client(_httpx.ConnectError("boom"))
        with patch("httpx.AsyncClient", return_value=client):
            results = await GovUKSource().fetch({"source_params": {"terms": ["heat"]}})
        assert results == []

    @pytest.mark.asyncio
    async def test_malformed_search_payload_returns_empty(self):
        client = _mock_client([_mock_response(json_data={"nope": 1})])
        with patch("httpx.AsyncClient", return_value=client):
            results = await GovUKSource().fetch({"source_params": {"terms": ["heat"]}})
        assert results == []
