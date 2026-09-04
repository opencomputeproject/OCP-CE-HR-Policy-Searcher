"""Tests for the DIP (Bundestag) structured policy source."""

from unittest.mock import patch

import pytest

from src.sources.dip_bundestag import DipBundestagSource


class _FakeResponse:
    def __init__(self, json_data=None, json_exc=None):
        self._json_data = json_data
        self._json_exc = json_exc

    def raise_for_status(self):
        pass

    def json(self):
        if self._json_exc:
            raise self._json_exc
        return self._json_data


class _FakeAsyncClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def get(self, url, params=None, **kwargs):
        self.calls.append(params)
        if not self._responses:
            raise AssertionError("no more fake responses queued")
        return self._responses.pop(0)


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setenv("DIP_API_KEY", "test-key")


class TestKeyMissing:
    @pytest.mark.asyncio
    async def test_missing_key_returns_empty_and_makes_no_call(self, monkeypatch):
        monkeypatch.delenv("DIP_API_KEY", raising=False)
        with patch("httpx.AsyncClient") as mock_client_cls:
            result = await DipBundestagSource().fetch({})
        assert result == []
        mock_client_cls.assert_not_called()


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_enacted_lifecycle_and_content(self):
        item = {
            "id": "12345",
            "titel": "Gesetz zur Nutzung von Abwärme aus Rechenzentren",
            "vorgangstyp": "Gesetzgebung",
            "beratungsstand": "Gesetz verkündet",
        }
        # Search response, then the per-vorgang vorgangsposition lookup
        # (no linked document here, so the vorgang page is the fallback URL).
        fake_client = _FakeAsyncClient([
            _FakeResponse(json_data={"documents": [item]}),
            _FakeResponse(json_data={"documents": []}),
        ])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await DipBundestagSource().fetch(
                {"source_params": {"terms": ["Abwärme"]}}
            )

        assert len(results) == 1
        r = results[0]
        assert r.url == "https://dip.bundestag.de/vorgang/12345"
        assert r.lifecycle_stage == "enacted"
        assert r.content and "Abwärme" in r.content
        assert "Vorgang: https://dip.bundestag.de/vorgang/12345" in r.content

    @pytest.mark.asyncio
    async def test_committee_lifecycle(self):
        item = {
            "id": "999",
            "titel": "Wärmeplanungsgesetz",
            "vorgangstyp": "Gesetzgebung",
            "beratungsstand": "Überweisung an Ausschuss",
        }
        fake_client = _FakeAsyncClient([
            _FakeResponse(json_data={"documents": [item]}),
            _FakeResponse(json_data={"documents": []}),
        ])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await DipBundestagSource().fetch({"source_params": {"terms": ["x"]}})

        assert results[0].lifecycle_stage == "in_committee"


class TestMalformed:
    @pytest.mark.asyncio
    async def test_malformed_response_returns_empty(self):
        fake_client = _FakeAsyncClient([_FakeResponse(json_data={"documents": "not-a-list"})])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await DipBundestagSource().fetch({"source_params": {"terms": ["x"]}})
        assert results == []

    @pytest.mark.asyncio
    async def test_json_parse_error_returns_empty(self):
        fake_client = _FakeAsyncClient([_FakeResponse(json_exc=ValueError("bad json"))])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await DipBundestagSource().fetch({"source_params": {"terms": ["x"]}})
        assert results == []


class TestDocumentTypeFilter:
    @pytest.mark.asyncio
    @pytest.mark.medium
    async def test_kleine_anfrage_is_dropped_and_counted(self):
        """A parliamentary question is not a policy (reviewer's rule, WP-3):
        DIP already tells us the vorgangstyp, so this is dropped at the
        source rather than spent on a model call."""
        item = {
            "id": "500",
            "titel": "Frage zur Nutzung von Abwärme aus Rechenzentren",
            "vorgangstyp": "Kleine Anfrage",
            "beratungsstand": "Antwort liegt vor",
        }
        fake_client = _FakeAsyncClient([_FakeResponse(json_data={"documents": [item]})])
        source = DipBundestagSource()
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await source.fetch({"source_params": {"terms": ["Abwärme"]}})
        assert results == []
        assert source.dropped_doc_type == 1


class TestDocumentUrl:
    @pytest.mark.asyncio
    @pytest.mark.medium
    async def test_pdf_url_used_when_present_vorgang_page_referenced(self):
        item = {
            "id": "700",
            "titel": "Gesetz zur Abwärmenutzung",
            "vorgangstyp": "Gesetzgebung",
            "beratungsstand": "eingebracht",
        }
        vorgangsposition = {
            "documents": [
                {"fundstelle": {"pdf_url": "https://dserver.bundestag.de/btd/20/115/2011501.pdf"}}
            ]
        }
        fake_client = _FakeAsyncClient([
            _FakeResponse(json_data={"documents": [item]}),
            _FakeResponse(json_data=vorgangsposition),
        ])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await DipBundestagSource().fetch(
                {"source_params": {"terms": ["Abwärme"]}}
            )
        assert len(results) == 1
        assert results[0].url == "https://dserver.bundestag.de/btd/20/115/2011501.pdf"
        assert "Vorgang: https://dip.bundestag.de/vorgang/700" in results[0].content

    @pytest.mark.asyncio
    @pytest.mark.medium
    async def test_no_pdf_url_falls_back_to_vorgang_page(self):
        item = {
            "id": "701",
            "titel": "Gesetz ohne PDF",
            "vorgangstyp": "Gesetzgebung",
            "beratungsstand": "eingebracht",
        }
        fake_client = _FakeAsyncClient([
            _FakeResponse(json_data={"documents": [item]}),
            _FakeResponse(json_data={"documents": []}),
        ])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await DipBundestagSource().fetch(
                {"source_params": {"terms": ["Abwärme"]}}
            )
        assert len(results) == 1
        assert results[0].url == "https://dip.bundestag.de/vorgang/701"


class TestDocumentTypesOverride:
    @pytest.mark.asyncio
    @pytest.mark.medium
    async def test_custom_allow_list_keeps_otherwise_dropped_type(self):
        item = {
            "id": "800",
            "titel": "Kleine Anfrage zur Abwärme",
            "vorgangstyp": "Kleine Anfrage",
            "beratungsstand": "Antwort liegt vor",
        }
        fake_client = _FakeAsyncClient([
            _FakeResponse(json_data={"documents": [item]}),
            _FakeResponse(json_data={"documents": []}),
        ])
        source = DipBundestagSource()
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await source.fetch(
                {"source_params": {
                    "terms": ["Abwärme"],
                    "document_types": ["Kleine Anfrage"],
                }}
            )
        assert len(results) == 1
        assert source.dropped_doc_type == 0


class TestCap:
    @pytest.mark.asyncio
    async def test_max_documents_respected(self):
        items = [
            {"id": "1", "titel": "A", "vorgangstyp": "Gesetzgebung", "beratungsstand": "eingebracht"},
            {"id": "2", "titel": "B", "vorgangstyp": "Gesetzgebung", "beratungsstand": "eingebracht"},
        ]
        # Only one vorgang is kept before the cap stops the loop, so only
        # one vorgangsposition lookup happens.
        fake_client = _FakeAsyncClient([
            _FakeResponse(json_data={"documents": items}),
            _FakeResponse(json_data={"documents": []}),
        ])
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await DipBundestagSource().fetch(
                {"source_params": {"terms": ["x"], "max_documents": 1}}
            )
        assert len(results) == 1

    @pytest.mark.asyncio
    @pytest.mark.medium
    async def test_max_documents_counts_kept_only(self):
        """A dropped question must not spend a slot in the cap: the cap is
        on kept, policy-shaped vorgänge, not on raw API rows."""
        items = [
            {"id": "1", "titel": "Frage", "vorgangstyp": "Kleine Anfrage",
             "beratungsstand": "x"},
            {"id": "2", "titel": "Gesetz A", "vorgangstyp": "Gesetzgebung",
             "beratungsstand": "x"},
            {"id": "3", "titel": "Gesetz B", "vorgangstyp": "Gesetzgebung",
             "beratungsstand": "x"},
        ]
        fake_client = _FakeAsyncClient([
            _FakeResponse(json_data={"documents": items}),
            _FakeResponse(json_data={"documents": []}),  # vorgangsposition for id=2
            _FakeResponse(json_data={"documents": []}),  # vorgangsposition for id=3
        ])
        source = DipBundestagSource()
        with patch("httpx.AsyncClient", return_value=fake_client):
            results = await source.fetch(
                {"source_params": {"terms": ["x"], "max_documents": 2}}
            )
        assert len(results) == 2
        assert source.dropped_doc_type == 1
