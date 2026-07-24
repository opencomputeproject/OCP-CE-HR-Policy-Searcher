"""Tests for the Austria RIS (Rechtsinformationssystem) structured policy source.

RIS OGD Bundesrecht API: enacted federal law + Bundesgesetzblatt (official
gazette). No auth, JSON, genuine server-side full-text filter over
`Suchworte=` (verified live 2026-07-24: nonsense=0, Fernwärme=103,
Abwärme=28, Rechenzentrum=8, Energieeffizienz=150, baseline=18821).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.ris_austria import RisAustriaSource, SEARCH_URL


def _mock_response(*, json_data=None, text="", status_code=200, raise_exc=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.headers = {"content-type": "text/html"}
    resp.json = MagicMock(return_value=json_data)
    if raise_exc:
        resp.raise_for_status = MagicMock(side_effect=raise_exc)
    else:
        resp.raise_for_status = MagicMock()
    return resp


def _mock_client(get_side_effect):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.get = AsyncMock(side_effect=get_side_effect)
    return client


def _reference(
    *,
    doc_id="NOR40123456",
    kurztitel="Bundesgesetz über die Nutzung von Abwärme aus Rechenzentren",
    titel=None,
    url="https://www.ris.bka.gv.at/eli/bgbl/I/2026/45",
    bgblnummer="45/2026",
    ausgabedatum="15.03.2026",
    eli="https://www.ris.bka.gv.at/eli/bgbl/I/2026/45",
):
    return {
        "Data": {
            "Metadaten": {
                "Technisch": {
                    "ID": doc_id,
                    "Applikation": "Bundesrecht",
                    "Organ": "BR",
                },
                "Allgemein": {
                    "DokumentUrl": url,
                },
                "Bundesrecht": {
                    "Kurztitel": kurztitel,
                    "Titel": titel or kurztitel,
                    "Eli": eli,
                    "BgblAuth": {
                        "Bgblnummer": bgblnummer,
                        "Teil": "I",
                        "Ausgabedatum": ausgabedatum,
                        "Typ": "BG",
                    },
                },
            }
        }
    }


def _payload(references, hits=None):
    return {
        "OgdSearchResult": {
            "OgdDocumentResults": {
                "Hits": {
                    "@pageNumber": "1",
                    "@pageSize": "20",
                    "#text": str(hits if hits is not None else len(references)),
                },
                "OgdDocumentReference": references,
            }
        }
    }


class TestRisAustriaSource:
    def test_registered(self):
        assert SOURCE_REGISTRY["ris_austria"] is RisAustriaSource

    def test_is_keyless(self):
        assert RisAustriaSource.api_key_env is None

    def test_search_url_targets_bundesrecht(self):
        assert SEARCH_URL.endswith("/Bundesrecht")

    @pytest.mark.asyncio
    async def test_query_uses_suchworte_param(self):
        """Regression pin: RIS's genuine filter param is `Suchworte`, not
        `q`/`query`/`text` — using the wrong name would silently return the
        full ~18,821-document Bundesrecht corpus instead of filtering."""
        client = _mock_client([_mock_response(json_data=_payload([]))])
        with patch("httpx.AsyncClient", return_value=client):
            await RisAustriaSource().fetch(
                {"source_params": {"terms": ["Fernwärme"]}}
            )
        params = client.get.call_args.kwargs["params"]
        assert params["Suchworte"] == "Fernwärme"

    @pytest.mark.asyncio
    async def test_happy_path(self):
        client = _mock_client([
            _mock_response(json_data=_payload([_reference()])),
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.ris_austria.fetch_document_text",
                new=AsyncMock(return_value=(
                    "Volltext des Bundesgesetzes über Abwärme.", "text/html",
                )),
            ),
        ):
            results = await RisAustriaSource().fetch(
                {"source_params": {"terms": ["Abwärme"]}}
            )

        assert len(results) == 1
        r = results[0]
        assert r.status == PageStatus.SUCCESS
        assert r.url == "https://www.ris.bka.gv.at/eli/bgbl/I/2026/45"
        assert r.title == "Bundesgesetz über die Nutzung von Abwärme aus Rechenzentren"
        assert "Abwärme" in r.content
        assert "Volltext des Bundesgesetzes über Abwärme." in r.content

    @pytest.mark.asyncio
    async def test_umlauts_survive_into_content(self):
        """Umlaut characters (ä/ö/ü) in titles and BGBl metadata must not be
        mangled when folded into CrawlResult content."""
        ref = _reference(
            kurztitel="Verordnung über Fernwärme und Rechenzentrumsabwärme",
        )
        client = _mock_client([_mock_response(json_data=_payload([ref]))])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.ris_austria.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await RisAustriaSource().fetch(
                {"source_params": {"terms": ["Fernwärme"]}}
            )
        assert "Verordnung über Fernwärme und Rechenzentrumsabwärme" in results[0].content
        assert "15.03.2026" in results[0].content

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_list(self):
        """A genuine zero-hit search (e.g. the nonsense-query check) must
        yield an empty result list, not an error."""
        client = _mock_client([
            _mock_response(json_data=_payload([], hits=0)),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await RisAustriaSource().fetch(
                {"source_params": {"terms": ["zzznonsensexyz123qqq"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_missing_document_reference_key_returns_empty(self):
        """At zero hits RIS may omit OgdDocumentReference entirely rather
        than sending an empty list."""
        payload = {
            "OgdSearchResult": {
                "OgdDocumentResults": {
                    "Hits": {"@pageNumber": "1", "@pageSize": "20", "#text": "0"},
                }
            }
        }
        client = _mock_client([_mock_response(json_data=payload)])
        with patch("httpx.AsyncClient", return_value=client):
            results = await RisAustriaSource().fetch(
                {"source_params": {"terms": ["zzznonsensexyz123qqq"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_single_reference_as_dict_not_list_is_handled(self):
        """RIS may return OgdDocumentReference as a bare dict (not wrapped
        in a list) when there is exactly one hit — same pattern as
        Riksdagen's dokumentlista."""
        ref = _reference()
        payload = {
            "OgdSearchResult": {
                "OgdDocumentResults": {
                    "Hits": {"@pageNumber": "1", "@pageSize": "20", "#text": "1"},
                    "OgdDocumentReference": ref,
                }
            }
        }
        client = _mock_client([_mock_response(json_data=payload)])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.ris_austria.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await RisAustriaSource().fetch(
                {"source_params": {"terms": ["Rechenzentrum"]}}
            )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_malformed_payload_returns_empty(self):
        client = _mock_client([_mock_response(json_data={"unexpected": "shape"})])
        with patch("httpx.AsyncClient", return_value=client):
            results = await RisAustriaSource().fetch(
                {"source_params": {"terms": ["Fernwärme"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_non_dict_reference_entries_are_skipped(self):
        client = _mock_client([
            _mock_response(json_data=_payload(["garbage", None, _reference()]))
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.ris_austria.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await RisAustriaSource().fetch(
                {"source_params": {"terms": ["Fernwärme"]}}
            )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_reference_without_url_is_skipped(self):
        ref = _reference()
        del ref["Data"]["Metadaten"]["Allgemein"]["DokumentUrl"]
        client = _mock_client([_mock_response(json_data=_payload([ref]))])
        with patch("httpx.AsyncClient", return_value=client):
            results = await RisAustriaSource().fetch(
                {"source_params": {"terms": ["Fernwärme"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_http_error_returns_empty_not_raise(self):
        import httpx as _httpx
        client = _mock_client(_httpx.ConnectError("boom"))
        with patch("httpx.AsyncClient", return_value=client):
            results = await RisAustriaSource().fetch(
                {"source_params": {"terms": ["Fernwärme"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_duplicate_url_across_terms_deduped(self):
        client = _mock_client([
            _mock_response(json_data=_payload([_reference()])),
            _mock_response(json_data=_payload([_reference()])),
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.ris_austria.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await RisAustriaSource().fetch(
                {"source_params": {"terms": ["Fernwärme", "Abwärme"]}}
            )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_max_documents_caps_results(self):
        refs = [
            _reference(
                doc_id=f"NOR{n}",
                url=f"https://www.ris.bka.gv.at/eli/bgbl/I/2026/{n}",
            )
            for n in range(10)
        ]
        client = _mock_client([_mock_response(json_data=_payload(refs))])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.ris_austria.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await RisAustriaSource().fetch(
                {"source_params": {"terms": ["Rechenzentrum"], "max_documents": 3}}
            )
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_lifecycle_stage_is_enacted(self):
        """Bundesrecht is enacted federal law (post-promulgation), unlike
        bill-tracking sources — the client must claim "enacted", not None
        or "proposed"."""
        client = _mock_client([_mock_response(json_data=_payload([_reference()]))])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.ris_austria.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await RisAustriaSource().fetch(
                {"source_params": {"terms": ["Abwärme"]}}
            )
        assert results[0].lifecycle_stage == "enacted"

    @pytest.mark.asyncio
    async def test_default_terms_used_when_not_configured(self):
        client = _mock_client([_mock_response(json_data=_payload([]))] * 10)
        with patch("httpx.AsyncClient", return_value=client):
            await RisAustriaSource().fetch({"source_params": {}})
        queried_terms = [
            call.kwargs["params"]["Suchworte"] for call in client.get.call_args_list
        ]
        assert "Fernwärme" in queried_terms
        assert "Abwärme" in queried_terms
        assert "Rechenzentrum" in queried_terms
