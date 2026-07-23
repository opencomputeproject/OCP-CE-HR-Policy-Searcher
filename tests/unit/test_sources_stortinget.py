"""Tests for the Norway Stortinget structured policy source.

Norway matters disproportionately for heat reuse: district heating is
mainstream and the Storting is actively amending the Energy Act to cover
surplus heat from data centres.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.stortinget import StortingetSource, _parse_wcf_date


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


TITLE = "Endringer i energiloven (utnyttelse av overskuddsvarme og krav til automatiske styringssystemer)"


def _sak(*, sak_id=200132, tittel=TITLE, korttittel="Endringer i energiloven",
         status=1, updated="/Date(1782338400000+0200)/"):
    return {
        "id": sak_id,
        "tittel": tittel,
        "korttittel": korttittel,
        "status": status,
        "type": 3,
        "sist_oppdatert_dato": updated,
        "emne_liste": [{"navn": "Energi"}, {"navn": "Industri"}],
        "komite": {"navn": "Energi- og miljøkomiteen"},
    }


def _liste(saker):
    return {"versjon": "1.6", "saker_liste": saker}


def _detail(*, ferdigbehandlet=True,
            kortvedtak="Stortinget har behandlet et forslag fra regjeringen om endringer i energiloven. "
                       "Forslaget handlet om utnyttelse av overskuddsvarme fra datasentre.",
            innstillingstekst="Innstilling fra energi- og miljøkomiteen om Endringer i energiloven."):
    return {
        "id": 200132,
        "tittel": TITLE,
        "ferdigbehandlet": ferdigbehandlet,
        "status": 1,
        "kortvedtak": kortvedtak,
        "innstillingstekst": innstillingstekst,
        "vedtakstekst": None,
        "emne_liste": [{"navn": "Energi"}],
    }


class TestParseWcfDate:
    def test_parses_wcf_epoch_millis(self):
        """Stortinget serves .NET WCF dates, not ISO 8601."""
        assert _parse_wcf_date("/Date(1782338400000+0200)/") == "2026-06-25"

    def test_returns_empty_for_garbage(self):
        assert _parse_wcf_date("not a date") == ""
        assert _parse_wcf_date(None) == ""


class TestStortingetSource:
    def test_registered(self):
        assert SOURCE_REGISTRY["stortinget"] is StortingetSource

    def test_is_keyless(self):
        assert StortingetSource.api_key_env is None

    def test_default_terms_are_broad_not_domain_phrases(self):
        """Regression, same lesson as Ireland. Measured on all 650 saker of
        session 2025-2026: the catalog's suggested "spillvarme" and
        "fjernvarme" matched 0 each, while "energi" matched 7 including
        "Endringer i energiloven (utnyttelse av overskuddsvarme...)".
        Norwegian says overskuddsvarme, not spillvarme."""
        from src.sources.stortinget import DEFAULT_TERMS
        assert "energi" in DEFAULT_TERMS
        assert "overskuddsvarme" in DEFAULT_TERMS
        assert "spillvarme" not in DEFAULT_TERMS

    @pytest.mark.asyncio
    async def test_happy_path(self):
        client = _mock_client([
            _mock_response(json_data=_liste([_sak()])),
            _mock_response(json_data=_detail()),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await StortingetSource().fetch(
                {"source_params": {"terms": ["energi"]}}
            )

        assert len(results) == 1
        r = results[0]
        assert r.status == PageStatus.SUCCESS
        assert r.url == "https://www.stortinget.no/no/Saker-og-publikasjoner/Saker/Sak/?p=200132"
        assert r.title == TITLE
        assert "overskuddsvarme" in r.content

    @pytest.mark.asyncio
    async def test_non_matching_sak_is_skipped(self):
        client = _mock_client([
            _mock_response(json_data=_liste([
                _sak(tittel="Riksrevisjonens undersøkelse av Bane NORs eiendomsvirksomhet",
                     korttittel="Bane NOR eiendom")
            ]))
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await StortingetSource().fetch(
                {"source_params": {"terms": ["energi"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_unfinished_case_is_proposed(self):
        client = _mock_client([
            _mock_response(json_data=_liste([_sak()])),
            _mock_response(json_data=_detail(ferdigbehandlet=False)),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await StortingetSource().fetch(
                {"source_params": {"terms": ["energi"]}}
            )
        assert results[0].lifecycle_stage == "proposed"

    @pytest.mark.asyncio
    async def test_finished_case_leaves_stage_for_the_model(self):
        """ferdigbehandlet means "processed", not "adopted" — the Storting
        can process a proposal by rejecting it. kortvedtak says which, so
        let the analysis model read it rather than guess here."""
        client = _mock_client([
            _mock_response(json_data=_liste([_sak()])),
            _mock_response(json_data=_detail(ferdigbehandlet=True)),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await StortingetSource().fetch(
                {"source_params": {"terms": ["energi"]}}
            )
        assert results[0].lifecycle_stage in (None, "")

    @pytest.mark.asyncio
    async def test_wcf_date_appears_in_content_as_iso(self):
        client = _mock_client([
            _mock_response(json_data=_liste([_sak()])),
            _mock_response(json_data=_detail()),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await StortingetSource().fetch(
                {"source_params": {"terms": ["energi"]}}
            )
        assert "2026-06-25" in results[0].content
        assert "/Date(" not in results[0].content

    @pytest.mark.asyncio
    async def test_session_param_is_sent(self):
        client = _mock_client([_mock_response(json_data=_liste([]))])
        with patch("httpx.AsyncClient", return_value=client):
            await StortingetSource().fetch(
                {"source_params": {"terms": ["energi"], "session": "2024-2025"}}
            )
        assert client.get.call_args.kwargs["params"]["sesjonid"] == "2024-2025"

    @pytest.mark.asyncio
    async def test_max_documents_caps_results(self):
        saker = [_sak(sak_id=n) for n in range(8)]
        client = _mock_client(
            [_mock_response(json_data=_liste(saker))]
            + [_mock_response(json_data=_detail())] * 8
        )
        with patch("httpx.AsyncClient", return_value=client):
            results = await StortingetSource().fetch(
                {"source_params": {"terms": ["energi"], "max_documents": 3}}
            )
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_detail_failure_falls_back_to_list_metadata(self):
        import httpx as _httpx
        client = _mock_client([
            _mock_response(json_data=_liste([_sak()])),
            _httpx.ConnectError("detail down"),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await StortingetSource().fetch(
                {"source_params": {"terms": ["energi"]}}
            )
        assert len(results) == 1
        assert TITLE in results[0].content

    @pytest.mark.asyncio
    async def test_http_error_returns_empty_not_raise(self):
        import httpx as _httpx
        client = _mock_client(_httpx.ConnectError("boom"))
        with patch("httpx.AsyncClient", return_value=client):
            results = await StortingetSource().fetch(
                {"source_params": {"terms": ["energi"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_malformed_payload_returns_empty(self):
        client = _mock_client([_mock_response(json_data={"nope": 1})])
        with patch("httpx.AsyncClient", return_value=client):
            results = await StortingetSource().fetch(
                {"source_params": {"terms": ["energi"]}}
            )
        assert results == []
