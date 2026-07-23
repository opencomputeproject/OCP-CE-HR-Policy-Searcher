"""Tests for the Netherlands Tweede Kamer structured policy source.

Best-in-class of the keyless sources: the gegevensmagazijn OData service
does SERVER-SIDE keyword search, so unlike Oireachtas we do not have to
page the whole corpus and filter locally.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.tweede_kamer import TweedeKamerSource

DOC_ID = "3c207e41-faec-4c6d-b4fd-517db2c923c5"


def _mock_response(*, json_data=None, content=b"", content_type="application/json",
                   text="", status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.content = content
    resp.headers = {"content-type": content_type}
    resp.json = MagicMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    return resp


def _mock_client(get_side_effect):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.get = AsyncMock(side_effect=get_side_effect)
    return client


def _zaak(*, nummer="2025Z12846", soort="Motie", afgedaan=False,
          onderwerp="Motie van het lid Kroger over een heffing op het lozen van restwarmte",
          titel="Regels omtrent productie, transport en levering van warmte",
          doc_id=DOC_ID):
    return {
        "Id": "0e9471a7-7af3-437e-b58e-be742fb49100",
        "Nummer": nummer,
        "Soort": soort,
        "Status": "Vrijgegeven",
        "Onderwerp": onderwerp,
        "Titel": titel,
        "GestartOp": "2025-06-19T00:00:00+02:00",
        "Afgedaan": afgedaan,
        "Vergaderjaar": "2024-2025",
        "Document": [{"Id": doc_id, "DocumentNummer": "2025D25931", "Soort": soort}],
    }


def _odata(items):
    return {"@odata.context": "...", "value": items}


LONG_HTML = "<html><body>" + ("Restwarmte bepalingen. " * 30) + "</body></html>"


class TestTweedeKamerSource:
    def test_registered(self):
        assert SOURCE_REGISTRY["tweede_kamer"] is TweedeKamerSource

    def test_is_keyless(self):
        assert TweedeKamerSource.api_key_env is None

    def test_default_terms_are_dutch(self):
        """English terms match nothing in a Dutch corpus."""
        from src.sources.tweede_kamer import DEFAULT_TERMS
        assert "restwarmte" in DEFAULT_TERMS
        assert "warmtenet" in DEFAULT_TERMS

    @pytest.mark.asyncio
    async def test_search_is_server_side_contains(self):
        client = _mock_client([_mock_response(json_data=_odata([]))])
        with patch("httpx.AsyncClient", return_value=client):
            await TweedeKamerSource().fetch(
                {"source_params": {"terms": ["restwarmte"]}}
            )
        params = client.get.call_args.kwargs["params"]
        assert "contains(Onderwerp,'restwarmte')" in params["$filter"]
        assert params["$expand"] == "Document"

    @pytest.mark.asyncio
    async def test_happy_path(self):
        client = _mock_client([
            _mock_response(json_data=_odata([_zaak()])),
            _mock_response(text=LONG_HTML, content_type="text/html"),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await TweedeKamerSource().fetch(
                {"source_params": {"terms": ["restwarmte"]}}
            )

        assert len(results) == 1
        r = results[0]
        assert r.status == PageStatus.SUCCESS
        # Citation is the parliament's own document resource.
        assert r.url == (
            f"https://gegevensmagazijn.tweedekamer.nl/OData/v4/2.0/Document({DOC_ID})/resource"
        )
        assert "Restwarmte bepalingen." in r.content

    @pytest.mark.asyncio
    async def test_pending_case_is_proposed(self):
        client = _mock_client([
            _mock_response(json_data=_odata([_zaak(afgedaan=False)])),
            _mock_response(text=LONG_HTML, content_type="text/html"),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await TweedeKamerSource().fetch(
                {"source_params": {"terms": ["restwarmte"]}}
            )
        assert results[0].lifecycle_stage == "proposed"

    @pytest.mark.asyncio
    async def test_finished_case_leaves_stage_unset_for_the_model(self):
        """Afgedaan means "handled", not "enacted" — the API cannot tell us
        which. A source-declared stage OVERRIDES the analysis model, so
        guessing here would actively destroy a correct inference."""
        client = _mock_client([
            _mock_response(json_data=_odata([_zaak(afgedaan=True)])),
            _mock_response(text=LONG_HTML, content_type="text/html"),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await TweedeKamerSource().fetch(
                {"source_params": {"terms": ["restwarmte"]}}
            )
        assert results[0].lifecycle_stage in (None, "")

    @pytest.mark.asyncio
    async def test_default_soorten_exclude_written_questions(self):
        """Schriftelijke vragen are questions, not policy. Including them by
        default floods the library with non-legislation."""
        from src.sources.tweede_kamer import DEFAULT_SOORTEN
        assert "Wetgeving" in DEFAULT_SOORTEN
        assert "Schriftelijke vragen" not in DEFAULT_SOORTEN

    @pytest.mark.asyncio
    async def test_soort_outside_allowlist_is_skipped(self):
        client = _mock_client([
            _mock_response(json_data=_odata([_zaak(soort="Schriftelijke vragen")])),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await TweedeKamerSource().fetch(
                {"source_params": {"terms": ["restwarmte"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_zaak_without_document_is_skipped(self):
        zaak = _zaak()
        zaak["Document"] = []
        client = _mock_client([_mock_response(json_data=_odata([zaak]))])
        with patch("httpx.AsyncClient", return_value=client):
            results = await TweedeKamerSource().fetch(
                {"source_params": {"terms": ["restwarmte"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_dedupes_same_document_across_terms(self):
        client = _mock_client([
            _mock_response(json_data=_odata([_zaak()])),
            _mock_response(text=LONG_HTML, content_type="text/html"),
            _mock_response(json_data=_odata([_zaak()])),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await TweedeKamerSource().fetch(
                {"source_params": {"terms": ["restwarmte", "warmtenet"]}}
            )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_max_documents_caps_results(self):
        zaken = [_zaak(nummer=f"2025Z{n}", doc_id=f"doc-{n}") for n in range(8)]
        client = _mock_client(
            [_mock_response(json_data=_odata(zaken))]
            + [_mock_response(text=LONG_HTML, content_type="text/html")] * 8
        )
        with patch("httpx.AsyncClient", return_value=client):
            results = await TweedeKamerSource().fetch(
                {"source_params": {"terms": ["restwarmte"], "max_documents": 3}}
            )
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_falls_back_to_metadata_when_pdf_fails(self):
        client = _mock_client([
            _mock_response(json_data=_odata([_zaak()])),
            _mock_response(text="", content_type="text/html"),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await TweedeKamerSource().fetch(
                {"source_params": {"terms": ["restwarmte"]}}
            )
        assert len(results) == 1
        assert "restwarmte" in results[0].content.lower()

    @pytest.mark.asyncio
    async def test_http_error_returns_empty_not_raise(self):
        import httpx as _httpx
        client = _mock_client(_httpx.ConnectError("boom"))
        with patch("httpx.AsyncClient", return_value=client):
            results = await TweedeKamerSource().fetch(
                {"source_params": {"terms": ["restwarmte"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_malformed_payload_returns_empty(self):
        client = _mock_client([_mock_response(json_data={"nope": 1})])
        with patch("httpx.AsyncClient", return_value=client):
            results = await TweedeKamerSource().fetch(
                {"source_params": {"terms": ["restwarmte"]}}
            )
        assert results == []
