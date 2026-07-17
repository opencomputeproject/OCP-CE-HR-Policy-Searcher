"""Tests for the Poland Sejm structured policy source.

The Sejm API has no keyword search: /prints returns the term's full print
list (~3100 for term 10, one 1.7 MB request), so the client filters titles
locally with Polish stems — Polish inflects heavily, and stems are what
match (ciepł caught 19 prints where full words would have missed cases).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.sejm import SejmSource

TITLE = (
    "Rządowy projekt ustawy o zmianie ustawy o efektywności energetycznej "
    "oraz wykorzystaniu ciepła odpadowego z centrów danych"
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


def _print(*, number="123", title=TITLE, attachments=None, process=True):
    p = {
        "number": number,
        "title": title,
        "term": 10,
        "documentDate": "2026-05-12",
        "deliveryDate": "2026-05-12",
        "changeDate": "2026-05-14T10:00:00",
        "attachments": attachments if attachments is not None else [f"{number}.pdf"],
    }
    if process:
        p["processPrint"] = [number]
    return p


def _process(*, number="123", passed=None, closure_date=None):
    proc = {
        "number": number,
        "title": TITLE,
        "documentType": "projekt ustawy",
        "documentTypeEnum": "BILL",
        "processStartDate": "2026-05-12",
        "stages": [
            {"date": "2026-05-12", "stageName": "Projekt wpłynął do Sejmu", "stageType": "Start"},
            {"date": "2026-06-01", "stageName": "I czytanie na posiedzeniu Sejmu", "stageType": "Reading"},
        ],
    }
    if passed is not None:
        proc["passed"] = passed
    if closure_date:
        proc["closureDate"] = closure_date
    return proc


class TestSejmSource:
    def test_registered(self):
        assert SOURCE_REGISTRY["sejm"] is SejmSource

    def test_is_keyless(self):
        assert SejmSource.api_key_env is None

    def test_default_terms_are_polish_stems(self):
        """Measured on all 3107 term-10 prints (2026-07-17): stem ciepł 19,
        energ 97, klimat 64; full phrases like "centrum danych" matched 0.
        Polish declension means stems, not words."""
        from src.sources.sejm import DEFAULT_TERMS
        assert "ciepł" in DEFAULT_TERMS
        assert "energ" in DEFAULT_TERMS

    @pytest.mark.asyncio
    async def test_happy_path(self):
        client = _mock_client([
            _mock_response(json_data=[_print()]),
            _mock_response(json_data=_process()),
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.sejm.fetch_document_text",
                new=AsyncMock(return_value=("Pełny tekst projektu ustawy.", "application/pdf")),
            ),
        ):
            results = await SejmSource().fetch(
                {"source_params": {"terms": ["ciepł"]}}
            )

        assert len(results) == 1
        r = results[0]
        assert r.status == PageStatus.SUCCESS
        assert r.url == "https://api.sejm.gov.pl/sejm/term10/prints/123/123.pdf"
        assert r.title == TITLE
        assert "Pełny tekst projektu ustawy." in r.content

    @pytest.mark.asyncio
    async def test_matching_is_case_insensitive(self):
        client = _mock_client([
            _mock_response(json_data=[_print(title=TITLE.upper())]),
            _mock_response(json_data=_process()),
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.sejm.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await SejmSource().fetch(
                {"source_params": {"terms": ["ciepł"]}}
            )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_non_matching_print_is_skipped(self):
        client = _mock_client([
            _mock_response(json_data=[
                _print(title="Poselski projekt uchwały w sprawie liczby wicemarszałków Sejmu")
            ]),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await SejmSource().fetch(
                {"source_params": {"terms": ["ciepł"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_newest_prints_processed_first(self):
        """The prints list arrives in ascending print-number order (oldest
        first); with a cap in play the newest prints must win, or the cap
        would spend itself on 2023 leftovers."""
        prints = [_print(number=str(n)) for n in (1, 2, 3)]
        client = _mock_client(
            [_mock_response(json_data=prints)]
            + [_mock_response(json_data=_process(number="3"))]
        )
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.sejm.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await SejmSource().fetch(
                {"source_params": {"terms": ["ciepł"], "max_documents": 1}}
            )
        assert len(results) == 1
        assert results[0].url.startswith("https://api.sejm.gov.pl/sejm/term10/prints/3/")

    @pytest.mark.asyncio
    async def test_open_process_is_proposed(self):
        client = _mock_client([
            _mock_response(json_data=[_print()]),
            _mock_response(json_data=_process()),
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.sejm.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await SejmSource().fetch(
                {"source_params": {"terms": ["ciepł"]}}
            )
        assert results[0].lifecycle_stage == "proposed"

    @pytest.mark.asyncio
    async def test_closed_and_passed_process_is_passed(self):
        client = _mock_client([
            _mock_response(json_data=[_print()]),
            _mock_response(json_data=_process(passed=True, closure_date="2026-06-20")),
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.sejm.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await SejmSource().fetch(
                {"source_params": {"terms": ["ciepł"]}}
            )
        assert results[0].lifecycle_stage == "passed"

    @pytest.mark.asyncio
    async def test_closed_without_passage_leaves_stage_for_the_model(self):
        """A closed process without passed=true may have been rejected or
        withdrawn — the same finished-is-not-adopted lesson as Stortinget's
        ferdigbehandlet. Claim nothing."""
        client = _mock_client([
            _mock_response(json_data=[_print()]),
            _mock_response(json_data=_process(passed=False, closure_date="2026-06-20")),
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.sejm.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await SejmSource().fetch(
                {"source_params": {"terms": ["ciepł"]}}
            )
        assert results[0].lifecycle_stage is None

    @pytest.mark.asyncio
    async def test_print_without_attachment_uses_process_page(self):
        client = _mock_client([
            _mock_response(json_data=[_print(attachments=[])]),
            _mock_response(json_data=_process()),
        ])
        with patch("httpx.AsyncClient", return_value=client):
            results = await SejmSource().fetch(
                {"source_params": {"terms": ["ciepł"]}}
            )
        assert len(results) == 1
        assert results[0].url == "https://api.sejm.gov.pl/sejm/term10/prints/123"

    @pytest.mark.asyncio
    async def test_process_detail_failure_still_yields_result(self):
        import httpx as _httpx
        client = _mock_client([
            _mock_response(json_data=[_print()]),
            _httpx.ConnectError("process down"),
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.sejm.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await SejmSource().fetch(
                {"source_params": {"terms": ["ciepł"]}}
            )
        assert len(results) == 1
        assert results[0].lifecycle_stage is None

    @pytest.mark.asyncio
    async def test_term_param_configurable(self):
        client = _mock_client([_mock_response(json_data=[])])
        with patch("httpx.AsyncClient", return_value=client):
            await SejmSource().fetch(
                {"source_params": {"terms": ["ciepł"], "term": 11}}
            )
        assert "term11" in str(client.get.call_args.args[0])

    @pytest.mark.asyncio
    async def test_max_documents_caps_results(self):
        prints = [_print(number=str(n)) for n in range(8)]
        client = _mock_client(
            [_mock_response(json_data=prints)]
            + [_mock_response(json_data=_process())] * 8
        )
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.sejm.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await SejmSource().fetch(
                {"source_params": {"terms": ["ciepł"], "max_documents": 3}}
            )
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_http_error_returns_empty_not_raise(self):
        import httpx as _httpx
        client = _mock_client(_httpx.ConnectError("boom"))
        with patch("httpx.AsyncClient", return_value=client):
            results = await SejmSource().fetch(
                {"source_params": {"terms": ["ciepł"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_malformed_payload_returns_empty(self):
        client = _mock_client([_mock_response(json_data={"not": "a list"})])
        with patch("httpx.AsyncClient", return_value=client):
            results = await SejmSource().fetch(
                {"source_params": {"terms": ["ciepł"]}}
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_duplicate_print_numbers_deduped(self):
        client = _mock_client([
            _mock_response(json_data=[_print(), _print()]),
            _mock_response(json_data=_process()),
        ])
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch(
                "src.sources.sejm.fetch_document_text",
                new=AsyncMock(return_value=("", "")),
            ),
        ):
            results = await SejmSource().fetch(
                {"source_params": {"terms": ["ciepł"]}}
            )
        assert len(results) == 1
