"""Tests for the New Zealand PCO Legislation API structured policy source.

The first keyed source added since the original four: full-text content
search with real filters (a nonsense term returns total=0, verified live
2026-07-17 with the production key), official legislation.govt.nz format
URLs per hit, and NZ legislation is public domain.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.nz_pco import NZPCOSource

TITLE = "Climate Change Response (Data Centre Heat Reuse) Amendment Bill"
HTML_URL = "https://www.legislation.govt.nz/bill/government/2026/330/en/latest/"


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


def _work(*, work_id="bill_government_2026_330", legislation_type="bill",
          bill_status="current", title=TITLE, formats=None, **extra):
    if formats is None:
        formats = [
            {"type": "html", "url": HTML_URL},
            {"type": "pdf", "url": HTML_URL.rstrip("/") + ".pdf"},
            {"type": "xml", "url": HTML_URL.rstrip("/") + ".xml"},
        ]
    work = {
        "work_id": work_id,
        "legislation_type": legislation_type,
        "publisher": "Parliamentary Counsel Office",
        "administering_agencies": ["Ministry for the Environment"],
        "latest_matching_version": {
            "version_id": f"{work_id}_en_2026-06-29",
            "title": title,
            "is_latest_version": True,
            "formats": formats,
        },
    }
    if legislation_type == "bill":
        work["bill_status"] = bill_status
        work["bill_type"] = "government"
        work["legislation_status"] = None
    return {**work, **extra}


def _payload(results, total=None):
    return {
        "results": results,
        "page": 1,
        "per_page": 10,
        "total": total if total is not None else len(results),
    }


@pytest.fixture()
def _with_key(monkeypatch):
    monkeypatch.setenv("NZ_PCO_API_KEY", "test-key-value")


class TestNZPCOSource:
    def test_registered(self):
        assert SOURCE_REGISTRY["nz_pco"] is NZPCOSource

    def test_declares_key_env(self):
        assert NZPCOSource.api_key_env == "NZ_PCO_API_KEY"

    @pytest.mark.asyncio
    async def test_disabled_without_key(self, monkeypatch):
        monkeypatch.delenv("NZ_PCO_API_KEY", raising=False)
        client = _mock_client([])
        with patch("httpx.AsyncClient", return_value=client):
            results = await NZPCOSource().fetch({"source_params": {}})
        assert results == []
        client.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_key_sent_in_header_never_in_url(self, _with_key):
        client = _mock_client([_mock_response(json_data=_payload([]))])
        with patch("httpx.AsyncClient", return_value=client):
            await NZPCOSource().fetch(
                {"source_params": {"terms": ["waste heat"]}}
            )
        headers = client.get.call_args.kwargs["headers"]
        assert headers["X-Api-Key"] == "test-key-value"
        params = client.get.call_args.kwargs["params"]
        assert "test-key-value" not in str(params.values())

    @pytest.mark.asyncio
    async def test_multiword_terms_are_phrase_quoted(self, _with_key):
        """Unquoted "waste heat" would match every act containing "waste"
        and "heat" separately (same lesson as gov.uk)."""
        client = _mock_client([_mock_response(json_data=_payload([]))])
        with patch("httpx.AsyncClient", return_value=client):
            await NZPCOSource().fetch(
                {"source_params": {"terms": ["waste heat"]}}
            )
        assert client.get.call_args.kwargs["params"]["search_term"] == '"waste heat"'

    @pytest.mark.asyncio
    async def test_searches_content_not_title(self, _with_key):
        """Full-text is why this source earns precise domain phrases; a
        title search would repeat the Oireachtas zero-yield mistake."""
        client = _mock_client([_mock_response(json_data=_payload([]))])
        with patch("httpx.AsyncClient", return_value=client):
            await NZPCOSource().fetch(
                {"source_params": {"terms": ["waste heat"]}}
            )
        assert client.get.call_args.kwargs["params"]["search_field"] == "content"

    @pytest.mark.asyncio
    async def test_happy_path(self, _with_key):
        client = _mock_client([_mock_response(json_data=_payload([_work()]))])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.nz_pco.fetch_document_text",
                new=AsyncMock(return_value=("Full text of the bill.", "text/html")),
            ),
        ):
            results = await NZPCOSource().fetch(
                {"source_params": {"terms": ["waste heat"]}}
            )

        assert len(results) == 1
        r = results[0]
        assert r.status == PageStatus.SUCCESS
        assert r.url == HTML_URL
        assert r.title == TITLE
        assert "Full text of the bill." in r.content
        assert "Ministry for the Environment" in r.content

    @pytest.mark.asyncio
    async def test_matched_term_is_written_into_content(self, _with_key):
        """The document body is WAF-blocked (www.legislation.govt.nz
        answers scripts with an empty 202 challenge), so the fact that the
        server's full-text index matched the term IS the content signal
        the screening gate needs."""
        client = _mock_client([_mock_response(json_data=_payload([_work()]))])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.nz_pco.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await NZPCOSource().fetch(
                {"source_params": {"terms": ["waste heat"]}}
            )
        assert 'matched "waste heat"' in results[0].content

    @pytest.mark.asyncio
    async def test_current_bill_is_proposed(self, _with_key):
        client = _mock_client([_mock_response(json_data=_payload([_work()]))])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.nz_pco.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await NZPCOSource().fetch(
                {"source_params": {"terms": ["waste heat"]}}
            )
        assert results[0].lifecycle_stage == "proposed"

    @pytest.mark.asyncio
    async def test_enacted_bill_is_enacted(self, _with_key):
        client = _mock_client([
            _mock_response(json_data=_payload([_work(bill_status="enacted")]))
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.nz_pco.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await NZPCOSource().fetch(
                {"source_params": {"terms": ["waste heat"]}}
            )
        assert results[0].lifecycle_stage == "enacted"

    @pytest.mark.asyncio
    async def test_terminated_bill_leaves_stage_for_the_model(self, _with_key):
        """Terminated covers defeated, withdrawn and lapsed - finished is
        not adopted, the recurring lesson."""
        client = _mock_client([
            _mock_response(json_data=_payload([_work(bill_status="terminated")]))
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.nz_pco.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await NZPCOSource().fetch(
                {"source_params": {"terms": ["waste heat"]}}
            )
        assert results[0].lifecycle_stage is None

    @pytest.mark.asyncio
    async def test_in_force_act_is_enacted(self, _with_key):
        client = _mock_client([
            _mock_response(json_data=_payload([_work(
                legislation_type="act",
                legislation_status="in_force",
                act_status="in_force",
                bill_status=None,
            )]))
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.nz_pco.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await NZPCOSource().fetch(
                {"source_params": {"terms": ["waste heat"]}}
            )
        assert results[0].lifecycle_stage == "enacted"

    @pytest.mark.asyncio
    async def test_not_in_force_act_leaves_stage_for_the_model(self, _with_key):
        """not_in_force is ambiguous: repealed and not-yet-commenced look
        identical. Claim nothing."""
        client = _mock_client([
            _mock_response(json_data=_payload([_work(
                legislation_type="act",
                legislation_status="not_in_force",
                bill_status=None,
            )]))
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.nz_pco.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await NZPCOSource().fetch(
                {"source_params": {"terms": ["waste heat"]}}
            )
        assert results[0].lifecycle_stage is None

    @pytest.mark.asyncio
    async def test_work_without_html_format_falls_back_to_pdf(self, _with_key):
        formats = [{"type": "pdf", "url": "https://www.legislation.govt.nz/x.pdf"}]
        client = _mock_client([
            _mock_response(json_data=_payload([_work(formats=formats)]))
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.nz_pco.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await NZPCOSource().fetch(
                {"source_params": {"terms": ["waste heat"]}}
            )
        assert results[0].url == "https://www.legislation.govt.nz/x.pdf"

    @pytest.mark.asyncio
    async def test_work_without_any_format_url_is_skipped(self, _with_key):
        client = _mock_client([
            _mock_response(json_data=_payload([_work(formats=[])]))
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await NZPCOSource().fetch(
                {"source_params": {"terms": ["waste heat"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_duplicate_work_across_terms_deduped(self, _with_key):
        client = _mock_client([
            _mock_response(json_data=_payload([_work()])),
            _mock_response(json_data=_payload([_work()])),
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.nz_pco.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await NZPCOSource().fetch(
                {"source_params": {"terms": ["waste heat", "heat recovery"]}}
            )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_max_documents_caps_results(self, _with_key):
        works = [_work(work_id=f"bill_government_2026_{n}") for n in range(8)]
        client = _mock_client([_mock_response(json_data=_payload(works))])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.nz_pco.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await NZPCOSource().fetch(
                {"source_params": {"terms": ["waste heat"], "max_documents": 3}}
            )
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_http_error_returns_empty_not_raise(self, _with_key):
        import httpx as _httpx
        client = _mock_client(_httpx.ConnectError("boom"))
        with patch("httpx.AsyncClient", return_value=client):
            results = await NZPCOSource().fetch(
                {"source_params": {"terms": ["waste heat"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_malformed_payload_returns_empty(self, _with_key):
        client = _mock_client([_mock_response(json_data={"nope": 1})])
        with patch("httpx.AsyncClient", return_value=client):
            results = await NZPCOSource().fetch(
                {"source_params": {"terms": ["waste heat"]}}
            )
        assert results == []
