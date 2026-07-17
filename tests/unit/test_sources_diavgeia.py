"""Tests for the Greece Diavgeia structured policy source.

Diavgeia is unusual among our sources: it is not a parliament API but the
statutory transparency register — by law every Greek government act is
invalid until posted there, which makes it same-day early by statute.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.diavgeia import DiavgeiaSource, _epoch_ms_to_iso


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


SUBJECT = (
    "Έγκριση σύνδεσης του δικτύου τηλεθέρμανσης με μονάδα ανάκτησης "
    "θερμότητας κέντρου δεδομένων"
)


def _decision(*, ada="9ΑΜΞ46Ψ842-ΑΧΟ", subject=SUBJECT,
              issue_date=1784210937000, status="PUBLISHED"):
    return {
        "protocolNumber": "2038082",
        "subject": subject,
        "issueDate": issue_date,
        "organizationId": "99201077",
        "decisionTypeId": "2.4.6.1",
        "thematicCategoryIds": ["52"],
        "ada": ada,
        "status": status,
        "url": f"https://diavgeia.gov.gr/luminapi/api/decisions/{ada}",
        "documentUrl": f"https://diavgeia.gov.gr/doc/{ada}",
    }


def _payload(decisions, total=None):
    return {
        "decisions": decisions,
        "info": {
            "query": 'subject:"τηλεθέρμανση"',
            "page": 0,
            "size": 10,
            "actualSize": len(decisions),
            "total": total if total is not None else len(decisions),
        },
    }


class TestEpochMsToIso:
    def test_converts_epoch_millis(self):
        assert _epoch_ms_to_iso(1784210937000) == "2026-07-16"

    def test_returns_empty_for_garbage(self):
        assert _epoch_ms_to_iso(None) == ""
        assert _epoch_ms_to_iso("not a number") == ""

    def test_returns_empty_for_absurd_values(self):
        # Way out of range epoch values must not raise.
        assert _epoch_ms_to_iso(10**20) == ""


class TestDiavgeiaSource:
    def test_registered(self):
        assert SOURCE_REGISTRY["diavgeia"] is DiavgeiaSource

    def test_is_keyless(self):
        assert DiavgeiaSource.api_key_env is None

    def test_uses_advanced_search_not_plain_q(self):
        """Regression pin for the trap that killed Retsinformation: the
        plain /opendata/search `q` parameter is a NO-OP (a nonsense query
        returns the same 3.1M results as a real one). Only
        /opendata/search/advanced with subject:"..." syntax filters —
        verified live 2026-07-17."""
        from src.sources.diavgeia import SEARCH_URL
        assert SEARCH_URL.endswith("/opendata/search/advanced")

    @pytest.mark.asyncio
    async def test_query_is_quoted_subject_syntax(self):
        client = _mock_client([_mock_response(json_data=_payload([]))])
        with patch("httpx.AsyncClient", return_value=client):
            await DiavgeiaSource().fetch(
                {"source_params": {"terms": ["τηλεθέρμανση"]}}
            )
        params = client.get.call_args.kwargs["params"]
        assert params["q"] == 'subject:"τηλεθέρμανση"'

    @pytest.mark.asyncio
    async def test_sends_json_accept_header(self):
        """Without Accept: application/json Diavgeia answers in XML."""
        client = _mock_client([_mock_response(json_data=_payload([]))])
        with patch("httpx.AsyncClient", return_value=client):
            await DiavgeiaSource().fetch(
                {"source_params": {"terms": ["τηλεθέρμανση"]}}
            )
        headers = client.get.call_args.kwargs["headers"]
        assert headers["Accept"] == "application/json"

    @pytest.mark.asyncio
    async def test_happy_path(self):
        client = _mock_client([_mock_response(json_data=_payload([_decision()]))])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.diavgeia.fetch_document_text",
                new=AsyncMock(return_value=("Το πλήρες κείμενο της απόφασης.", "application/pdf")),
            ),
        ):
            results = await DiavgeiaSource().fetch(
                {"source_params": {"terms": ["τηλεθέρμανση"]}}
            )

        assert len(results) == 1
        r = results[0]
        assert r.status == PageStatus.SUCCESS
        assert r.url == "https://diavgeia.gov.gr/doc/9ΑΜΞ46Ψ842-ΑΧΟ"
        assert r.title == SUBJECT
        assert SUBJECT in r.content
        assert "Το πλήρες κείμενο της απόφασης." in r.content

    @pytest.mark.asyncio
    async def test_issue_date_appears_as_iso_not_epoch(self):
        client = _mock_client([_mock_response(json_data=_payload([_decision()]))])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.diavgeia.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await DiavgeiaSource().fetch(
                {"source_params": {"terms": ["τηλεθέρμανση"]}}
            )
        assert "2026-07-16" in results[0].content
        assert "1784210937000" not in results[0].content

    @pytest.mark.asyncio
    async def test_document_fetch_failure_falls_back_to_metadata(self):
        client = _mock_client([_mock_response(json_data=_payload([_decision()]))])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.diavgeia.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await DiavgeiaSource().fetch(
                {"source_params": {"terms": ["τηλεθέρμανση"]}}
            )
        assert len(results) == 1
        assert SUBJECT in results[0].content

    @pytest.mark.asyncio
    async def test_decision_without_ada_is_skipped(self):
        bad = _decision()
        del bad["ada"]
        client = _mock_client([_mock_response(json_data=_payload([bad]))])
        with patch("httpx.AsyncClient", return_value=client):
            results = await DiavgeiaSource().fetch(
                {"source_params": {"terms": ["τηλεθέρμανση"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_duplicate_ada_across_terms_deduped(self):
        client = _mock_client([
            _mock_response(json_data=_payload([_decision()])),
            _mock_response(json_data=_payload([_decision()])),
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.diavgeia.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await DiavgeiaSource().fetch(
                {"source_params": {"terms": ["τηλεθέρμανση", "ανάκτηση θερμότητας"]}}
            )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_max_documents_caps_results(self):
        decisions = [_decision(ada=f"ADA-{n}") for n in range(10)]
        client = _mock_client([_mock_response(json_data=_payload(decisions))])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.diavgeia.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await DiavgeiaSource().fetch(
                {"source_params": {"terms": ["τηλεθέρμανση"], "max_documents": 4}}
            )
        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_http_error_returns_empty_not_raise(self):
        import httpx as _httpx
        client = _mock_client(_httpx.ConnectError("boom"))
        with patch("httpx.AsyncClient", return_value=client):
            results = await DiavgeiaSource().fetch(
                {"source_params": {"terms": ["τηλεθέρμανση"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_malformed_payload_returns_empty(self):
        client = _mock_client([_mock_response(json_data={"nope": 1})])
        with patch("httpx.AsyncClient", return_value=client):
            results = await DiavgeiaSource().fetch(
                {"source_params": {"terms": ["τηλεθέρμανση"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_non_dict_decision_entries_are_skipped(self):
        client = _mock_client([
            _mock_response(json_data=_payload(["garbage", None, _decision()]))
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.diavgeia.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await DiavgeiaSource().fetch(
                {"source_params": {"terms": ["τηλεθέρμανση"]}}
            )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_no_lifecycle_stage_claimed(self):
        """Diavgeia posts executive acts, not bills — the register says
        nothing about where an act sits in a legislative pipeline, so the
        client must not invent a stage."""
        client = _mock_client([_mock_response(json_data=_payload([_decision()]))])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.diavgeia.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await DiavgeiaSource().fetch(
                {"source_params": {"terms": ["τηλεθέρμανση"]}}
            )
        assert results[0].lifecycle_stage is None
