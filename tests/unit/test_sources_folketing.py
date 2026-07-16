"""Tests for the Folketing (Danish Parliament) structured policy source."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.folketing import FolketingSource


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


class TestFolketingSource:
    def test_registered(self):
        assert SOURCE_REGISTRY["folketing"] is FolketingSource

    @pytest.mark.asyncio
    async def test_happy_path(self):
        payload = {
            "value": [
                {
                    "id": 42,
                    "titel": "Forslag om overskudsvarme",
                    "resume": "Et forslag om anvendelse af overskudsvarme.",
                    "statusid": 1,
                }
            ]
        }
        resp = _mock_response(json_data=payload)
        client = _mock_client([resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = FolketingSource()
            results = await source.fetch({"source_params": {"terms": ["overskudsvarme"]}})

        assert len(results) == 1
        assert results[0].url == "https://www.ft.dk/samling/oversigt/sag.htm?sagId=42"
        assert results[0].status == PageStatus.SUCCESS
        assert results[0].lifecycle_stage == "proposed"
        assert "overskudsvarme" in results[0].content.lower()

    @pytest.mark.asyncio
    async def test_malformed_payload_returns_empty(self):
        resp = _mock_response(json_data={"unexpected": "shape"})
        client = _mock_client([resp, resp, resp, resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = FolketingSource()
            results = await source.fetch({"source_params": {}})

        assert results == []

    @pytest.mark.asyncio
    async def test_cap_respected(self):
        payload = {
            "value": [
                {"id": i, "titel": f"Sag {i}", "resume": "resume", "statusid": 1}
                for i in range(10)
            ]
        }
        resp = _mock_response(json_data=payload)
        client = _mock_client([resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = FolketingSource()
            results = await source.fetch(
                {"source_params": {"terms": ["fjernvarme"], "max_documents": 4}}
            )

        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_dedupe_within_fetch(self):
        case = {"id": 7, "titel": "Sag om varmeforsyning", "resume": "resume", "statusid": 1}
        resp = _mock_response(json_data={"value": [case]})
        client = _mock_client([resp, resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = FolketingSource()
            results = await source.fetch(
                {"source_params": {"terms": ["varmeforsyning", "datacenter"]}}
            )

        urls = [r.url for r in results]
        assert len(urls) == len(set(urls))
