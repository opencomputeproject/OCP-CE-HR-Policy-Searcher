"""Tests for the UK Parliament Bills structured policy source."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.uk_bills import UKBillsSource


def _mock_response(*, json_data=None, text="", status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.headers = {"content-type": "text/html"}
    resp.json = MagicMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    return resp


def _mock_client(get_side_effect):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.get = AsyncMock(side_effect=get_side_effect)
    return client


def _search_payload(items):
    return {"items": items}


class TestUKBillsSource:
    def test_registered(self):
        assert SOURCE_REGISTRY["uk_bills"] is UKBillsSource

    def test_default_terms_include_broad_heat_word(self):
        # Regression: phrase-only defaults ("heat networks") matched no live
        # UK bills. A broad single word must be present so a scan isn't empty.
        from src.sources.uk_bills import DEFAULT_TERMS
        assert "heat" in DEFAULT_TERMS

    @pytest.mark.asyncio
    async def test_happy_path(self):
        search_resp = _mock_response(json_data=_search_payload([
            {
                "billId": 123,
                "shortTitle": "Heat Networks Bill",
                "currentHouse": "Commons",
                "currentStage": {"description": "Committee stage"},
            }
        ]))
        long_html = "<html><body>" + ("Heat networks content. " * 30) + "</body></html>"
        doc_resp = _mock_response(text=long_html)
        client = _mock_client([search_resp, doc_resp, doc_resp, doc_resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = UKBillsSource()
            results = await source.fetch({"source_params": {"terms": ["heat networks"]}})

        assert len(results) == 1
        assert results[0].url == "https://bills.parliament.uk/bills/123"
        assert results[0].status == PageStatus.SUCCESS
        assert results[0].lifecycle_stage == "in_committee"

    @pytest.mark.asyncio
    async def test_thin_content_falls_back_to_metadata(self):
        search_resp = _mock_response(json_data=_search_payload([
            {
                "billId": 456,
                "shortTitle": "District Heating Bill",
                "currentStage": {"description": "Royal Assent"},
            }
        ]))
        doc_resp = _mock_response(text="<html><body>x</body></html>")
        client = _mock_client([search_resp, doc_resp, doc_resp, doc_resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = UKBillsSource()
            results = await source.fetch({"source_params": {"terms": ["district heating"]}})

        assert len(results) == 1
        assert "District Heating Bill" in results[0].content
        assert results[0].lifecycle_stage == "enacted"

    @pytest.mark.asyncio
    async def test_malformed_payload_returns_empty(self):
        search_resp = _mock_response(json_data={"unexpected": "shape"})
        client = _mock_client([search_resp, search_resp, search_resp, search_resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = UKBillsSource()
            results = await source.fetch({"source_params": {}})

        assert results == []

    @pytest.mark.asyncio
    async def test_cap_respected(self):
        items = [
            {
                "billId": i,
                "shortTitle": f"Bill {i}",
                "currentStage": {"description": "2nd reading"},
            }
            for i in range(10)
        ]
        search_resp = _mock_response(json_data=_search_payload(items))
        long_html = "<html><body>" + ("Content. " * 40) + "</body></html>"
        doc_resp = _mock_response(text=long_html)

        def side_effect(*args, **kwargs):
            return search_resp if kwargs.get("params") else doc_resp

        client = _mock_client(side_effect)

        with patch("httpx.AsyncClient", return_value=client):
            source = UKBillsSource()
            results = await source.fetch(
                {"source_params": {"terms": ["x"], "max_documents": 4}}
            )

        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_dedupe_within_fetch(self):
        item = {
            "billId": 789,
            "shortTitle": "Waste Heat Bill",
            "currentStage": {"description": "1st reading"},
        }
        search_resp = _mock_response(json_data=_search_payload([item]))
        long_html = "<html><body>" + ("Content. " * 40) + "</body></html>"
        doc_resp = _mock_response(text=long_html)

        def side_effect(*args, **kwargs):
            return search_resp if kwargs.get("params") else doc_resp

        client = _mock_client(side_effect)

        with patch("httpx.AsyncClient", return_value=client):
            source = UKBillsSource()
            results = await source.fetch(
                {"source_params": {"terms": ["heat networks", "waste heat"]}}
            )

        urls = [r.url for r in results]
        assert len(urls) == len(set(urls))
