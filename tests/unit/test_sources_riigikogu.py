"""Tests for the Estonia Riigikogu structured policy source.

The Riigikogu API is the rare keyless source with a working server-side
title filter (a nonsense title returns totalElements=0, verified live
2026-07-17), but it rate-limits aggressively (429 at 2 requests/second),
so the client must space its calls.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.riigikogu import RiigikoguSource

DOC_UUID = "3d7ea2a0-a23f-4bb2-b629-0f49263018bd"
PDF_UUID = "24cbe2d2-2c04-40ce-8387-eee743b033f0"
TITLE = (
    "Riigikogu seisukoht Euroopa Liidu 2030. aasta järgse energiatõhususe "
    "õigusraamistiku avaliku konsultatsiooni kohta"
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


def _doc(*, uuid=DOC_UUID, title=TITLE, doc_type="riigikoguSeisukoht",
         created="2026-06-15T12:03:42.201"):
    return {
        "uuid": uuid,
        "reference": "1-2/26-329/3",
        "title": title,
        "documentType": doc_type,
        "created": created,
        "_links": {"self": {"href": f"https://api.riigikogu.ee/api/documents/{uuid}"}},
    }


def _listing(docs):
    return {
        "_embedded": {"content": docs},
        "page": {"size": 50, "totalElements": len(docs), "totalPages": 1, "number": 0},
    }


def _detail(*, uuid=DOC_UUID, files=None):
    if files is None:
        files = [
            {
                "uuid": "2fe0552c-371a-4cbb-adad-39b516f60a6c",
                "fileName": "seisukoht.asice",
                "fileExtension": "asice",
                "accessRestrictionType": "PUBLIC",
                "_links": {"download": {"href": "https://api.riigikogu.ee/api/files/asice/download"}},
            },
            {
                "uuid": PDF_UUID,
                "fileName": "Riigikogu_seisukoht.pdf",
                "fileExtension": "pdf",
                "accessRestrictionType": "PUBLIC",
                "_links": {"download": {"href": f"https://api.riigikogu.ee/api/files/{PDF_UUID}/download"}},
            },
        ]
    return {
        "uuid": uuid,
        "reference": "1-2/26-329/3",
        "title": TITLE,
        "documentType": "riigikoguSeisukoht",
        "created": "2026-06-15T12:03:42.201",
        "committee": {"name": "Euroopa Liidu asjade komisjon"},
        "volume": {"title": "Eesti seisukohad energiatõhususe konsultatsiooni kohta"},
        "files": files,
    }


@pytest.fixture(autouse=True)
def _no_sleep():
    """Request spacing is real politeness, not something tests should wait on."""
    with patch("src.sources.riigikogu.asyncio.sleep", new=AsyncMock()) as sleeper:
        yield sleeper


class TestRiigikoguSource:
    def test_registered(self):
        assert SOURCE_REGISTRY["riigikogu"] is RiigikoguSource

    def test_is_keyless(self):
        assert RiigikoguSource.api_key_env is None

    def test_default_terms_use_substring_stems(self):
        """Estonian inflects: kaugküte (nominative) matched 0 titles while
        the stem kaugküt matched 61 (catching genitive kaugkütte), measured
        live 2026-07-17. Defaults must be stems, not dictionary forms."""
        from src.sources.riigikogu import DEFAULT_TERMS
        assert "kaugküt" in DEFAULT_TERMS
        assert "kaugküte" not in DEFAULT_TERMS
        assert "soojus" in DEFAULT_TERMS

    @pytest.mark.asyncio
    async def test_happy_path_prefers_public_pdf(self):
        client = _mock_client([
            _mock_response(json_data=_listing([_doc()])),
            _mock_response(json_data=_detail()),
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.riigikogu.fetch_document_text",
                new=AsyncMock(return_value=("Dokumendi täistekst.", "application/pdf")),
            ),
        ):
            results = await RiigikoguSource().fetch(
                {"source_params": {"terms": ["energia"]}}
            )

        assert len(results) == 1
        r = results[0]
        assert r.status == PageStatus.SUCCESS
        assert r.url == f"https://api.riigikogu.ee/api/files/{PDF_UUID}/download"
        assert r.title == TITLE
        assert "Dokumendi täistekst." in r.content
        assert "Euroopa Liidu asjade komisjon" in r.content

    @pytest.mark.asyncio
    async def test_no_pdf_falls_back_to_document_api_url(self):
        client = _mock_client([
            _mock_response(json_data=_listing([_doc()])),
            _mock_response(json_data=_detail(files=[])),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await RiigikoguSource().fetch(
                {"source_params": {"terms": ["energia"]}}
            )
        assert results[0].url == f"https://api.riigikogu.ee/api/documents/{DOC_UUID}"
        assert TITLE in results[0].content

    @pytest.mark.asyncio
    async def test_restricted_pdf_is_not_used(self):
        """accessRestrictionType != PUBLIC means the download link will not
        serve anonymous users — citing it would give readers a dead link."""
        files = [{
            "uuid": PDF_UUID,
            "fileName": "piiratud.pdf",
            "fileExtension": "pdf",
            "accessRestrictionType": "RESTRICTED",
            "_links": {"download": {"href": "https://api.riigikogu.ee/api/files/x/download"}},
        }]
        client = _mock_client([
            _mock_response(json_data=_listing([_doc()])),
            _mock_response(json_data=_detail(files=files)),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await RiigikoguSource().fetch(
                {"source_params": {"terms": ["energia"]}}
            )
        assert results[0].url == f"https://api.riigikogu.ee/api/documents/{DOC_UUID}"

    @pytest.mark.asyncio
    async def test_requests_are_spaced(self, _no_sleep):
        """429 at 2 req/s measured on this API; the client must sleep
        between consecutive requests."""
        client = _mock_client([
            _mock_response(json_data=_listing([_doc()])),
            _mock_response(json_data=_detail()),
            _mock_response(json_data=_listing([])),
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.riigikogu.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            await RiigikoguSource().fetch(
                {"source_params": {"terms": ["energia", "soojus"]}}
            )
        assert _no_sleep.await_count >= 2

    @pytest.mark.asyncio
    async def test_title_param_is_sent(self):
        client = _mock_client([_mock_response(json_data=_listing([]))])
        with patch("httpx.AsyncClient", return_value=client):
            await RiigikoguSource().fetch(
                {"source_params": {"terms": ["soojus"]}}
            )
        assert client.get.call_args.kwargs["params"]["title"] == "soojus"

    @pytest.mark.asyncio
    async def test_duplicate_uuid_across_terms_deduped(self):
        client = _mock_client([
            _mock_response(json_data=_listing([_doc()])),
            _mock_response(json_data=_detail()),
            _mock_response(json_data=_listing([_doc()])),
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.riigikogu.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await RiigikoguSource().fetch(
                {"source_params": {"terms": ["energia", "soojus"]}}
            )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_max_documents_caps_results(self):
        docs = [_doc(uuid=f"uuid-{n}") for n in range(8)]
        client = _mock_client(
            [_mock_response(json_data=_listing(docs))]
            + [_mock_response(json_data=_detail(files=[]))] * 8
        )
        with patch("httpx.AsyncClient", return_value=client):
            results = await RiigikoguSource().fetch(
                {"source_params": {"terms": ["energia"], "max_documents": 3}}
            )
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_detail_failure_falls_back_to_list_metadata(self):
        import httpx as _httpx
        client = _mock_client([
            _mock_response(json_data=_listing([_doc()])),
            _httpx.ConnectError("detail down"),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await RiigikoguSource().fetch(
                {"source_params": {"terms": ["energia"]}}
            )
        assert len(results) == 1
        assert TITLE in results[0].content

    @pytest.mark.asyncio
    async def test_http_error_returns_empty_not_raise(self):
        import httpx as _httpx
        client = _mock_client(_httpx.ConnectError("boom"))
        with patch("httpx.AsyncClient", return_value=client):
            results = await RiigikoguSource().fetch(
                {"source_params": {"terms": ["energia"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_malformed_payload_returns_empty(self):
        client = _mock_client([_mock_response(json_data={"nope": 1})])
        with patch("httpx.AsyncClient", return_value=client):
            results = await RiigikoguSource().fetch(
                {"source_params": {"terms": ["energia"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_document_without_uuid_is_skipped(self):
        doc = _doc()
        del doc["uuid"]
        client = _mock_client([_mock_response(json_data=_listing([doc]))])
        with patch("httpx.AsyncClient", return_value=client):
            results = await RiigikoguSource().fetch(
                {"source_params": {"terms": ["energia"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_no_lifecycle_stage_claimed(self):
        """The documents index mixes bills, EU positions, letters and
        statements; documentType does not map cleanly onto a bill pipeline,
        so the client claims nothing and lets the analysis model read."""
        client = _mock_client([
            _mock_response(json_data=_listing([_doc()])),
            _mock_response(json_data=_detail(files=[])),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await RiigikoguSource().fetch(
                {"source_params": {"terms": ["energia"]}}
            )
        assert results[0].lifecycle_stage is None
