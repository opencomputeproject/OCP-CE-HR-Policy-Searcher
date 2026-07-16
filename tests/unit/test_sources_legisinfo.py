"""Tests for the LEGISinfo (Parliament of Canada) structured policy source."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.legisinfo import LegisInfoSource


def _mock_response(*, json_data=None, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    return resp


def _mock_client(get_side_effect):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.get = AsyncMock(side_effect=get_side_effect)
    return client


class TestLegisInfoSource:
    def test_registered(self):
        assert SOURCE_REGISTRY["legisinfo"] is LegisInfoSource

    @pytest.mark.asyncio
    async def test_happy_path(self):
        bills = [
            {
                "NumberCode": "C-10",
                "LongTitle": "An Act respecting energy efficiency in data centres",
                "ShortTitle": "Energy Efficiency Act",
                "LatestCompletedMajorStageName": "Second reading",
                "ParliamentNumber": 44,
                "SessionNumber": 1,
            },
            {
                "NumberCode": "C-99",
                "LongTitle": "An Act respecting unrelated matters",
                "ShortTitle": "Unrelated Act",
                "LatestCompletedMajorStageName": "First reading",
                "ParliamentNumber": 44,
                "SessionNumber": 1,
            },
        ]
        resp = _mock_response(json_data=bills)
        client = _mock_client([resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = LegisInfoSource()
            results = await source.fetch({"source_params": {"terms": ["energy efficiency"]}})

        assert len(results) == 1
        assert results[0].url == "https://www.parl.ca/legisinfo/en/bill/44-1/c-10"
        assert results[0].status == PageStatus.SUCCESS
        assert results[0].lifecycle_stage == "proposed"

    @pytest.mark.asyncio
    async def test_live_payload_shape(self):
        """The real API uses language-suffixed fields (LongTitleEn,
        BillNumberFormatted, CurrentStatusEn) — verified live 2026-07-12."""
        bills = [{
            "BillNumberFormatted": "S-4",
            "LongTitleEn": "An Act to amend the Energy Efficiency Act",
            "ShortTitleEn": "",
            "CurrentStatusEn": "At second reading in the Senate",
            "ParliamentNumber": 45,
            "SessionNumber": 1,
        }]
        resp = _mock_response(json_data=bills)
        client = _mock_client([resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = LegisInfoSource()
            results = await source.fetch({"source_params": {"terms": ["energy"]}})

        assert len(results) == 1
        assert results[0].url == "https://www.parl.ca/legisinfo/en/bill/45-1/s-4"
        assert "Energy Efficiency Act" in results[0].content

    @pytest.mark.asyncio
    async def test_fallback_url_when_fields_missing(self):
        bills = [
            {
                "LongTitle": "An Act respecting data centre energy",
                "LatestCompletedMajorStageName": "Royal Assent",
            }
        ]
        resp = _mock_response(json_data=bills)
        client = _mock_client([resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = LegisInfoSource()
            results = await source.fetch({"source_params": {"terms": ["data centre"]}})

        assert len(results) == 1
        assert results[0].url == "https://www.parl.ca/legisinfo/en/bills"
        assert results[0].lifecycle_stage == "enacted"

    @pytest.mark.asyncio
    async def test_malformed_payload_returns_empty(self):
        resp = _mock_response(json_data={"unexpected": "shape"})
        client = _mock_client([resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = LegisInfoSource()
            results = await source.fetch({"source_params": {}})

        assert results == []

    @pytest.mark.asyncio
    async def test_cap_respected(self):
        bills = [
            {
                "NumberCode": f"C-{i}",
                "LongTitle": "An Act respecting district energy systems",
                "LatestCompletedMajorStageName": "Committee stage",
                "ParliamentNumber": 44,
                "SessionNumber": 1,
            }
            for i in range(10)
        ]
        resp = _mock_response(json_data=bills)
        client = _mock_client([resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = LegisInfoSource()
            results = await source.fetch(
                {"source_params": {"terms": ["district energy"], "max_documents": 3}}
            )

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_dedupe_within_fetch(self):
        bill = {
            "NumberCode": "C-10",
            "LongTitle": "An Act respecting heat recovery",
            "LatestCompletedMajorStageName": "First reading",
            "ParliamentNumber": 44,
            "SessionNumber": 1,
        }
        resp = _mock_response(json_data=[bill, dict(bill)])
        client = _mock_client([resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = LegisInfoSource()
            results = await source.fetch({"source_params": {"terms": ["heat"]}})

        urls = [r.url for r in results]
        assert len(urls) == 1
