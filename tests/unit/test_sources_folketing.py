"""Tests for the Folketing (Danish Parliament) structured policy source."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.folketing import DEFAULT_DOCUMENT_TYPE_IDS, FolketingSource


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
    @pytest.mark.medium
    async def test_happy_path(self):
        payload = {
            "value": [
                {
                    "id": 42,
                    "titel": "Forslag om overskudsvarme",
                    "resume": "Et forslag om anvendelse af overskudsvarme.",
                    "typeid": 3,
                }
            ]
        }
        search_resp = _mock_response(json_data=payload)
        # No documents attached to this case, so the case page is the URL.
        expand_resp = _mock_response(json_data={"SagDokument": []})
        client = _mock_client([search_resp, expand_resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = FolketingSource()
            results = await source.fetch({"source_params": {"terms": ["overskudsvarme"]}})

        assert len(results) == 1
        assert results[0].url == "https://www.ft.dk/samling/oversigt/sag.htm?sagId=42"
        assert results[0].status == PageStatus.SUCCESS
        assert results[0].lifecycle_stage == "proposed"
        assert "overskudsvarme" in results[0].content.lower()

    @pytest.mark.asyncio
    @pytest.mark.medium
    async def test_malformed_payload_returns_empty(self):
        resp = _mock_response(json_data={"unexpected": "shape"})
        client = _mock_client([resp, resp, resp, resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = FolketingSource()
            results = await source.fetch({"source_params": {}})

        assert results == []

    @pytest.mark.asyncio
    @pytest.mark.medium
    async def test_cap_respected(self):
        payload = {
            "value": [
                {"id": i, "titel": f"Sag {i}", "resume": "resume", "typeid": 3}
                for i in range(10)
            ]
        }
        resp = _mock_response(json_data=payload)
        # Every kept case has no attached documents, so each spends exactly
        # one extra (expand) call before falling back to the case page.
        expand_resp = _mock_response(json_data={"SagDokument": []})
        client = _mock_client([resp] + [expand_resp] * 4)

        with patch("httpx.AsyncClient", return_value=client):
            source = FolketingSource()
            results = await source.fetch(
                {"source_params": {"terms": ["fjernvarme"], "max_documents": 4}}
            )

        assert len(results) == 4

    @pytest.mark.asyncio
    @pytest.mark.medium
    async def test_dedupe_within_fetch(self):
        case = {"id": 7, "titel": "Sag om varmeforsyning", "resume": "resume", "typeid": 3}
        search_resp = _mock_response(json_data={"value": [case]})
        expand_resp = _mock_response(json_data={"SagDokument": []})
        # search(term1) -> case 7; expand for case 7; search(term2) -> case 7
        # again, but it is skipped on sag_id before any further call.
        client = _mock_client([search_resp, expand_resp, search_resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = FolketingSource()
            results = await source.fetch(
                {"source_params": {"terms": ["varmeforsyning", "datacenter"]}}
            )

        urls = [r.url for r in results]
        assert len(urls) == 1
        assert len(urls) == len(set(urls))


class TestDocumentTypeFilter:
    def test_default_ids_are_bill_resolution_and_motion(self):
        assert DEFAULT_DOCUMENT_TYPE_IDS == [3, 5, 9]

    @pytest.mark.asyncio
    @pytest.mark.medium
    async def test_paragraph_20_question_is_dropped_and_counted(self):
        """A § 20-spørgsmål (typeid 10) is a written question to a
        minister, not a policy: the reviewer's rule, WP-3."""
        case = {
            "id": 900,
            "titel": "Spørgsmål om overskudsvarme",
            "resume": "resume",
            "typeid": 10,
        }
        search_resp = _mock_response(json_data={"value": [case]})
        client = _mock_client([search_resp])

        source = FolketingSource()
        with patch("httpx.AsyncClient", return_value=client):
            results = await source.fetch({"source_params": {"terms": ["overskudsvarme"]}})

        assert results == []
        assert source.dropped_doc_type == 1

    @pytest.mark.asyncio
    @pytest.mark.medium
    async def test_kept_case_uses_the_fil_url(self):
        """A Lovforslag (typeid 3) is kept, and its document URL is the
        bill's actual file, not the case-overview page."""
        case = {
            "id": 36985,
            "titel": "Forslag til lov om overskudsvarme",
            "resume": "resume",
            "typeid": 3,
        }
        search_resp = _mock_response(json_data={"value": [case]})
        expand_resp = _mock_response(json_data={
            "SagDokument": [
                {"Dokument": {"id": 555, "typeid": 21, "titel": "Lovforslag som fremsat"}},
            ]
        })
        fil_resp = _mock_response(json_data={
            "value": [
                {"filurl": "https://www.ft.dk/ripdf/samling/20251/lovforslag/L80/"
                            "20251_L80_som_fremsat.pdf", "format": "pdf"},
            ]
        })
        client = _mock_client([search_resp, expand_resp, fil_resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = FolketingSource()
            results = await source.fetch({"source_params": {"terms": ["overskudsvarme"]}})

        assert len(results) == 1
        assert results[0].url == (
            "https://www.ft.dk/ripdf/samling/20251/lovforslag/L80/20251_L80_som_fremsat.pdf"
        )
        assert source.dropped_doc_type == 0

    @pytest.mark.asyncio
    @pytest.mark.medium
    async def test_empty_fil_falls_back_to_case_page(self):
        """A document with no filurl (format empty, per the recorded live
        shape) falls back to the case page rather than a broken link."""
        case = {
            "id": 36986,
            "titel": "Forslag til lov uden fil",
            "resume": "resume",
            "typeid": 3,
        }
        search_resp = _mock_response(json_data={"value": [case]})
        expand_resp = _mock_response(json_data={
            "SagDokument": [
                {"Dokument": {"id": 556, "typeid": 21, "titel": "Lovforslag som fremsat"}},
            ]
        })
        fil_resp = _mock_response(json_data={"value": []})
        client = _mock_client([search_resp, expand_resp, fil_resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = FolketingSource()
            results = await source.fetch({"source_params": {"terms": ["overskudsvarme"]}})

        assert len(results) == 1
        assert results[0].url == "https://www.ft.dk/samling/oversigt/sag.htm?sagId=36986"

    @pytest.mark.asyncio
    @pytest.mark.medium
    async def test_document_types_override_keeps_otherwise_dropped_type(self):
        case = {
            "id": 901,
            "titel": "Spørgsmål om overskudsvarme",
            "resume": "resume",
            "typeid": 10,
        }
        search_resp = _mock_response(json_data={"value": [case]})
        expand_resp = _mock_response(json_data={"SagDokument": []})
        client = _mock_client([search_resp, expand_resp])

        source = FolketingSource()
        with patch("httpx.AsyncClient", return_value=client):
            results = await source.fetch(
                {"source_params": {
                    "terms": ["overskudsvarme"],
                    "document_types": [10],
                }}
            )

        assert len(results) == 1
        assert source.dropped_doc_type == 0
