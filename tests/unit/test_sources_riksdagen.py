"""Tests for the Riksdagen structured policy source."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.riksdagen import RiksdagenSource


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


def _search_payload(docs):
    return {"dokumentlista": {"dokument": docs}}


class TestRiksdagenSource:
    def test_registered(self):
        assert SOURCE_REGISTRY["riksdagen"] is RiksdagenSource

    @pytest.mark.asyncio
    async def test_happy_path(self):
        search_resp = _mock_response(json_data=_search_payload([
            {
                "id": "1",
                "titel": "Motion om spillvärme",
                "dokument_url_html": "//data.riksdagen.se/dok/H1234.html",
                "doktyp": "mot",
            }
        ]))
        doc_resp = _mock_response(text="<html><body>Spillvärme innehåll</body></html>")
        client = _mock_client([search_resp, doc_resp, doc_resp, doc_resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = RiksdagenSource()
            results = await source.fetch({"source_params": {"terms": ["spillvärme"]}})

        assert len(results) == 1
        assert results[0].url == "https://data.riksdagen.se/dok/H1234.html"
        assert results[0].status == PageStatus.SUCCESS
        assert results[0].lifecycle_stage == "proposed"
        assert "Spillvärme" in results[0].content

    @pytest.mark.asyncio
    async def test_malformed_payload_returns_empty(self):
        search_resp = _mock_response(json_data={"unexpected": "shape"})
        client = _mock_client([search_resp, search_resp, search_resp, search_resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = RiksdagenSource()
            results = await source.fetch({"source_params": {}})

        assert results == []

    @pytest.mark.asyncio
    async def test_cap_respected(self):
        docs = [
            {
                "id": str(i),
                "titel": f"Doc {i}",
                "dokument_url_html": f"//data.riksdagen.se/dok/H{i}.html",
                "doktyp": "prop",
            }
            for i in range(10)
        ]
        search_resp = _mock_response(json_data=_search_payload(docs))
        doc_resp = _mock_response(text="<html><body>Content here</body></html>")

        def side_effect(*args, **kwargs):
            return search_resp if kwargs.get("params") else doc_resp

        client = _mock_client(side_effect)

        with patch("httpx.AsyncClient", return_value=client):
            source = RiksdagenSource()
            results = await source.fetch(
                {"source_params": {"terms": ["x"], "max_documents": 3}}
            )

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_dedupe_within_fetch(self):
        doc = {
            "id": "1",
            "titel": "Motion om fjärrvärme",
            "dokument_url_html": "//data.riksdagen.se/dok/H1.html",
            "doktyp": "sfs",
        }
        search_resp = _mock_response(json_data=_search_payload([doc]))
        doc_resp = _mock_response(text="<html><body>Text</body></html>")

        def side_effect(*args, **kwargs):
            if kwargs.get("params") and "sok" in kwargs["params"]:
                return search_resp
            return doc_resp

        client = _mock_client(side_effect)

        with patch("httpx.AsyncClient", return_value=client):
            source = RiksdagenSource()
            results = await source.fetch(
                {"source_params": {"terms": ["spillvärme", "fjärrvärme"]}}
            )

        urls = [r.url for r in results]
        assert len(urls) == len(set(urls))
        assert results[0].lifecycle_stage == "enacted"
