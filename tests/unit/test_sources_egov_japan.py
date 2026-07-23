"""Tests for the Japan e-Gov Law API v2 structured policy source.

e-Gov holds ENACTED Japanese law with real full-text search. It pairs with
the Kokkai source: Kokkai shows what is being discussed, e-Gov shows what
actually became law.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.egov_japan import EGovJapanSource


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


def _item(
    *,
    law_id="343CO0000000329",
    law_title="大気汚染防止法施行令",
    status="CurrentEnforced",
    scheduled=None,
    sentences=("別表第一（第二条関係）一ボイラー（熱風ボイラーを含み、熱源として電気又は"
               "<span>廃熱</span>のみを使用するものを除く。）燃料の燃焼能力が重油換算",),
):
    return {
        "law_info": {
            "law_id": law_id,
            "law_type": "MinisterialOrdinance",
            "law_num": "平成二十八年経済産業省令第一号",
            "promulgation_date": "2016-01-29",
        },
        "revision_info": {
            "law_title": law_title,
            "category": "環境保全",
            "current_revision_status": status,
            "amendment_enforcement_date": "2022-10-01",
            "amendment_scheduled_enforcement_date": scheduled,
            "repeal_status": "None",
        },
        "sentences": [{"position": "relatedarticlenum", "text": s} for s in sentences],
    }


def _payload(items):
    # The live API returns "items". The source catalog wrongly documented
    # this key as "laws" — pin the real shape here.
    return {"total_count": len(items), "sentence_count": len(items), "items": items}


class TestEGovJapanSource:
    def test_registered(self):
        assert SOURCE_REGISTRY["egov_japan"] is EGovJapanSource

    def test_is_keyless(self):
        assert EGovJapanSource.api_key_env is None

    def test_default_terms_include_both_waste_heat_kanji(self):
        """Japanese writes waste heat two ways. Live counts: 排熱 -> 1 law,
        廃熱 -> 10 laws. Shipping only one silently loses most results."""
        from src.sources.egov_japan import DEFAULT_TERMS
        assert "排熱" in DEFAULT_TERMS
        assert "廃熱" in DEFAULT_TERMS

    @pytest.mark.asyncio
    async def test_happy_path(self):
        client = _mock_client([_mock_response(json_data=_payload([_item()]))])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EGovJapanSource().fetch(
                {"source_params": {"terms": ["廃熱"]}}
            )

        assert len(results) == 1
        r = results[0]
        assert r.status == PageStatus.SUCCESS
        assert r.url == "https://laws.e-gov.go.jp/law/343CO0000000329"
        assert r.title == "大気汚染防止法施行令"
        assert "廃熱" in r.content

    @pytest.mark.asyncio
    async def test_reads_items_key_not_laws(self):
        """Regression: the catalog documented the list key as "laws"; the
        live API returns "items". Reading the wrong key yields nothing."""
        client = _mock_client([
            _mock_response(json_data={"total_count": 1, "laws": [_item()]})
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EGovJapanSource().fetch(
                {"source_params": {"terms": ["廃熱"]}}
            )
        assert results == []  # "laws" is not the real key, so nothing parses

    @pytest.mark.asyncio
    async def test_span_highlights_are_stripped_from_content(self):
        client = _mock_client([_mock_response(json_data=_payload([_item()]))])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EGovJapanSource().fetch(
                {"source_params": {"terms": ["廃熱"]}}
            )
        assert "<span>" not in results[0].content
        assert "</span>" not in results[0].content

    @pytest.mark.asyncio
    async def test_enforced_law_is_enacted(self):
        client = _mock_client([
            _mock_response(json_data=_payload([_item(status="CurrentEnforced")]))
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EGovJapanSource().fetch(
                {"source_params": {"terms": ["廃熱"]}}
            )
        assert results[0].lifecycle_stage == "enacted"

    @pytest.mark.asyncio
    async def test_scheduled_enforcement_is_passed_not_enacted(self):
        """A law with a future enforcement date has passed but is not yet in
        force — a meaningfully different state for anyone planning ahead."""
        client = _mock_client([
            _mock_response(json_data=_payload([
                _item(scheduled="2027-04-01", status="CurrentEnforced")
            ]))
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EGovJapanSource().fetch(
                {"source_params": {"terms": ["廃熱"]}}
            )
        assert results[0].lifecycle_stage == "passed"
        assert "2027-04-01" in results[0].content

    @pytest.mark.asyncio
    async def test_dedupes_same_law_across_terms(self):
        client = _mock_client([
            _mock_response(json_data=_payload([_item()])),
            _mock_response(json_data=_payload([_item()])),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EGovJapanSource().fetch(
                {"source_params": {"terms": ["廃熱", "排熱"]}}
            )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_max_documents_caps_results(self):
        items = [_item(law_id=f"LAW{n}") for n in range(8)]
        client = _mock_client([_mock_response(json_data=_payload(items))])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EGovJapanSource().fetch(
                {"source_params": {"terms": ["廃熱"], "max_documents": 3}}
            )
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_item_without_law_id_is_skipped(self):
        bad = _item()
        bad["law_info"] = {}
        client = _mock_client([_mock_response(json_data=_payload([bad]))])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EGovJapanSource().fetch(
                {"source_params": {"terms": ["廃熱"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_item_without_sentences_still_yields_metadata(self):
        client = _mock_client([
            _mock_response(json_data=_payload([_item(sentences=())]))
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EGovJapanSource().fetch(
                {"source_params": {"terms": ["廃熱"]}}
            )
        assert len(results) == 1
        assert "大気汚染防止法施行令" in results[0].content

    @pytest.mark.asyncio
    async def test_zero_results_is_not_an_error(self):
        """total_count can be absent entirely on a no-hit query."""
        client = _mock_client([_mock_response(json_data={"total_count": None})])
        with patch("httpx.AsyncClient", return_value=client):
            results = await EGovJapanSource().fetch(
                {"source_params": {"terms": ["廃熱"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_http_error_returns_empty_not_raise(self):
        import httpx as _httpx
        client = _mock_client(_httpx.ConnectError("boom"))
        with patch("httpx.AsyncClient", return_value=client):
            results = await EGovJapanSource().fetch(
                {"source_params": {"terms": ["廃熱"]}}
            )
        assert results == []
