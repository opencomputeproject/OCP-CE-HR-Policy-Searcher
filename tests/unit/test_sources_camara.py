"""Tests for the Brazil Câmara dos Deputados structured policy source.

The Câmara API has real server-side keyword search (a nonsense keyword
returns zero rows, verified live 2026-07-17), but it matches INDEXED
keywords rather than full text, so several complementary terms are needed.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.camara import CamaraSource

EMENTA = (
    "Dispõe sobre o reaproveitamento do calor residual de centros de dados "
    "em redes de aquecimento e dá outras providências."
)


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


def _prop(*, prop_id=2500252, ementa=EMENTA):
    return {
        "id": prop_id,
        "uri": f"https://dadosabertos.camara.leg.br/api/v2/proposicoes/{prop_id}",
        "siglaTipo": "PL",
        "numero": 1854,
        "ano": 2025,
        "ementa": ementa,
        "dataApresentacao": "2025-04-24T17:37",
    }


def _detail(*, prop_id=2500252, situacao="Pronta para Pauta",
            ementa=EMENTA):
    return {
        "dados": {
            "id": prop_id,
            "siglaTipo": "PL",
            "numero": 1854,
            "ano": 2025,
            "ementa": ementa,
            "ementaDetalhada": "Estabelece requisitos de eficiência energética.",
            "keywords": "calor residual, centro de dados, eficiência energética",
            "dataApresentacao": "2025-04-24T17:37",
            "descricaoTipo": "Projeto de Lei",
            "statusProposicao": {
                "dataHora": "2026-04-27T11:52",
                "siglaOrgao": "CME",
                "descricaoTramitacao": "Parecer do Relator",
                "descricaoSituacao": situacao,
                "despacho": "Parecer da Relatora, pela aprovação.",
            },
        }
    }


def _listing(props):
    return {"dados": props, "links": []}


class TestCamaraSource:
    def test_registered(self):
        assert SOURCE_REGISTRY["camara"] is CamaraSource

    def test_is_keyless(self):
        assert CamaraSource.api_key_env is None

    def test_default_terms_measured_live(self):
        """Measured 2026-07-17 against the indexed-keyword search:
        "eficiência energética" 17, "centro de dados" 2, "datacenter" 1,
        "calor residual" 0 today (kept — it is the exact domain phrase and
        costs nothing). Plain "calor" is poisoned: it returns workplace-heat
        allowance bills (insalubridade por calor)."""
        from src.sources.camara import DEFAULT_TERMS
        assert "centro de dados" in DEFAULT_TERMS
        assert "eficiência energética" in DEFAULT_TERMS
        assert "calor" not in DEFAULT_TERMS

    @pytest.mark.asyncio
    async def test_happy_path(self):
        client = _mock_client([
            _mock_response(json_data=_listing([_prop()])),
            _mock_response(json_data=_detail()),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await CamaraSource().fetch(
                {"source_params": {"terms": ["centro de dados"]}}
            )

        assert len(results) == 1
        r = results[0]
        assert r.status == PageStatus.SUCCESS
        assert r.url == (
            "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao"
            "?idProposicao=2500252"
        )
        assert r.title == "PL 1854/2025"
        assert EMENTA in r.content
        assert "eficiência energética" in r.content  # detail keywords folded in

    @pytest.mark.asyncio
    async def test_active_proposal_is_proposed(self):
        client = _mock_client([
            _mock_response(json_data=_listing([_prop()])),
            _mock_response(json_data=_detail(situacao="Pronta para Pauta")),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await CamaraSource().fetch(
                {"source_params": {"terms": ["centro de dados"]}}
            )
        assert results[0].lifecycle_stage == "proposed"

    @pytest.mark.asyncio
    async def test_transformed_into_law_is_enacted(self):
        client = _mock_client([
            _mock_response(json_data=_listing([_prop()])),
            _mock_response(json_data=_detail(
                situacao="Transformado em Norma Jurídica"
            )),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await CamaraSource().fetch(
                {"source_params": {"terms": ["centro de dados"]}}
            )
        assert results[0].lifecycle_stage == "enacted"

    @pytest.mark.asyncio
    async def test_archived_leaves_stage_for_the_model(self):
        """Arquivada can mean rejected, superseded, or shelved — the
        finished-is-not-adopted lesson again. Claim nothing."""
        client = _mock_client([
            _mock_response(json_data=_listing([_prop()])),
            _mock_response(json_data=_detail(situacao="Arquivada")),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await CamaraSource().fetch(
                {"source_params": {"terms": ["centro de dados"]}}
            )
        assert results[0].lifecycle_stage is None

    @pytest.mark.asyncio
    async def test_missing_status_leaves_stage_for_the_model(self):
        detail = _detail()
        del detail["dados"]["statusProposicao"]
        client = _mock_client([
            _mock_response(json_data=_listing([_prop()])),
            _mock_response(json_data=detail),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await CamaraSource().fetch(
                {"source_params": {"terms": ["centro de dados"]}}
            )
        assert results[0].lifecycle_stage is None

    @pytest.mark.asyncio
    async def test_detail_failure_falls_back_to_list_metadata(self):
        import httpx as _httpx
        client = _mock_client([
            _mock_response(json_data=_listing([_prop()])),
            _httpx.ConnectError("detail down"),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await CamaraSource().fetch(
                {"source_params": {"terms": ["centro de dados"]}}
            )
        assert len(results) == 1
        assert EMENTA in results[0].content
        assert results[0].lifecycle_stage is None

    @pytest.mark.asyncio
    async def test_duplicate_id_across_terms_deduped(self):
        client = _mock_client([
            _mock_response(json_data=_listing([_prop()])),
            _mock_response(json_data=_detail()),
            _mock_response(json_data=_listing([_prop()])),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await CamaraSource().fetch(
                {"source_params": {"terms": ["centro de dados", "datacenter"]}}
            )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_max_documents_caps_results(self):
        props = [_prop(prop_id=n) for n in range(8)]
        client = _mock_client(
            [_mock_response(json_data=_listing(props))]
            + [_mock_response(json_data=_detail())] * 8
        )
        with patch("httpx.AsyncClient", return_value=client):
            results = await CamaraSource().fetch(
                {"source_params": {"terms": ["centro de dados"], "max_documents": 3}}
            )
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_proposal_without_id_is_skipped(self):
        prop = _prop()
        del prop["id"]
        client = _mock_client([_mock_response(json_data=_listing([prop]))])
        with patch("httpx.AsyncClient", return_value=client):
            results = await CamaraSource().fetch(
                {"source_params": {"terms": ["centro de dados"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_http_error_returns_empty_not_raise(self):
        import httpx as _httpx
        client = _mock_client(_httpx.ConnectError("boom"))
        with patch("httpx.AsyncClient", return_value=client):
            results = await CamaraSource().fetch(
                {"source_params": {"terms": ["centro de dados"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_malformed_payload_returns_empty(self):
        client = _mock_client([_mock_response(json_data={"nope": 1})])
        with patch("httpx.AsyncClient", return_value=client):
            results = await CamaraSource().fetch(
                {"source_params": {"terms": ["centro de dados"]}}
            )
        assert results == []
