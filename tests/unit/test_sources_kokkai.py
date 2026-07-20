"""Tests for the Japan NDL Kokkai (Diet proceedings) structured source.

Kokkai is a LEADING INDICATOR, not a law register: it carries what the Diet
is saying, months or years before anything is enacted. Its documents are
speeches, so most will correctly fail the downstream screening gate — the
value is catching the moment a minister first signals intent.

NDL publishes rate rules: no bursts, space requests seconds apart, no
parallel calls. That politeness is enforced in code, not just documented.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.kokkai import KokkaiSource


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


# Abridged from the real 2026-06-12 House Environment Committee exchange.
# Live speeches run 171-4900 chars (median 544), so a realistic fixture
# must clear the MIN_SPEECH_LENGTH floor comfortably.
SPEECH_TEXT = (
    "○伯野政府参考人　お答えいたします。現在、環境法制におきましては、現時点で"
    "排熱を規制する仕組みはございませんが、我が国において多くのデータセンターが"
    "建設されている状況を踏まえ、その環境影響について実態の把握に努めてまいります。"
    "データセンターの立地に関しましては、関係省庁とも連携しながら、必要な対応を"
    "検討してまいりたいと考えております。引き続き、事業者に対する情報提供及び"
    "指導助言を行ってまいります。"
)


def _speech(*, speech_id="122104006X01320260612_071", speech=SPEECH_TEXT,
            url="https://kokkai.ndl.go.jp/txt/122104006X01320260612/71"):
    return {
        "speechID": speech_id,
        "issueID": "122104006X01320260612",
        "date": "2026-06-12",
        "session": 217,
        "nameOfHouse": "衆議院",
        "nameOfMeeting": "環境委員会",
        "speaker": "伯野春彦",
        "speakerPosition": "環境省大臣官房環境保健部長",
        "speakerGroup": "",
        "speech": speech,
        "speechURL": url,
        "meetingURL": "https://kokkai.ndl.go.jp/txt/122104006X01320260612",
    }


def _payload(speeches):
    return {
        "numberOfRecords": len(speeches),
        "numberOfReturn": len(speeches),
        "startRecord": 1,
        "nextRecordPosition": None,
        "speechRecord": speeches,
    }


class TestKokkaiSource:
    def test_registered(self):
        assert SOURCE_REGISTRY["kokkai"] is KokkaiSource

    def test_is_keyless(self):
        assert KokkaiSource.api_key_env is None

    def test_default_terms_include_both_waste_heat_kanji(self):
        from src.sources.kokkai import DEFAULT_TERMS
        assert "排熱" in DEFAULT_TERMS
        assert "廃熱" in DEFAULT_TERMS

    @pytest.mark.asyncio
    async def test_happy_path(self):
        client = _mock_client([_mock_response(json_data=_payload([_speech()]))])
        with patch("httpx.AsyncClient", return_value=client), \
             patch("asyncio.sleep", new=AsyncMock()):
            results = await KokkaiSource().fetch({"source_params": {"terms": ["排熱"]}})

        assert len(results) == 1
        r = results[0]
        assert r.status == PageStatus.SUCCESS
        assert r.url == "https://kokkai.ndl.go.jp/txt/122104006X01320260612/71"
        assert "環境委員会" in r.title
        assert "排熱を規制する仕組みはございません" in r.content

    @pytest.mark.asyncio
    async def test_speaker_and_meeting_context_are_in_content(self):
        """Who said it and where decides whether a remark carries weight."""
        client = _mock_client([_mock_response(json_data=_payload([_speech()]))])
        with patch("httpx.AsyncClient", return_value=client), \
             patch("asyncio.sleep", new=AsyncMock()):
            results = await KokkaiSource().fetch({"source_params": {"terms": ["排熱"]}})

        content = results[0].content
        assert "伯野春彦" in content
        assert "環境省大臣官房環境保健部長" in content
        assert "2026-06-12" in content

    @pytest.mark.asyncio
    async def test_lifecycle_stage_is_left_unset(self):
        """A speech has no lifecycle. Declaring one would override the
        analysis model with a claim this source cannot support."""
        client = _mock_client([_mock_response(json_data=_payload([_speech()]))])
        with patch("httpx.AsyncClient", return_value=client), \
             patch("asyncio.sleep", new=AsyncMock()):
            results = await KokkaiSource().fetch({"source_params": {"terms": ["排熱"]}})
        assert results[0].lifecycle_stage in (None, "")

    @pytest.mark.asyncio
    async def test_requests_are_spaced_not_bursted(self):
        """NDL asks for seconds between calls and no parallelism. Two terms
        must therefore sleep at least once between them."""
        sleep = AsyncMock()
        client = _mock_client([
            _mock_response(json_data=_payload([])),
            _mock_response(json_data=_payload([])),
        ])
        with patch("httpx.AsyncClient", return_value=client), \
             patch("asyncio.sleep", new=sleep):
            await KokkaiSource().fetch({"source_params": {"terms": ["排熱", "廃熱"]}})

        assert sleep.await_count >= 1
        assert sleep.await_args[0][0] >= 1.0

    @pytest.mark.asyncio
    async def test_short_speech_is_skipped(self):
        """Procedural one-liners ("次に、○○君") are noise, not signal."""
        client = _mock_client([
            _mock_response(json_data=_payload([_speech(speech="○委員長　次に、田中君。")]))
        ])
        with patch("httpx.AsyncClient", return_value=client), \
             patch("asyncio.sleep", new=AsyncMock()):
            results = await KokkaiSource().fetch({"source_params": {"terms": ["排熱"]}})
        assert results == []

    @pytest.mark.asyncio
    async def test_dedupes_same_speech_across_terms(self):
        client = _mock_client([
            _mock_response(json_data=_payload([_speech()])),
            _mock_response(json_data=_payload([_speech()])),
        ])
        with patch("httpx.AsyncClient", return_value=client), \
             patch("asyncio.sleep", new=AsyncMock()):
            results = await KokkaiSource().fetch(
                {"source_params": {"terms": ["排熱", "廃熱"]}}
            )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_max_documents_caps_results(self):
        speeches = [
            _speech(speech_id=f"S{n}", url=f"https://kokkai.ndl.go.jp/txt/x/{n}")
            for n in range(8)
        ]
        client = _mock_client([_mock_response(json_data=_payload(speeches))])
        with patch("httpx.AsyncClient", return_value=client), \
             patch("asyncio.sleep", new=AsyncMock()):
            results = await KokkaiSource().fetch(
                {"source_params": {"terms": ["排熱"], "max_documents": 3}}
            )
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_speech_without_url_is_skipped(self):
        client = _mock_client([
            _mock_response(json_data=_payload([_speech(url="")]))
        ])
        with patch("httpx.AsyncClient", return_value=client), \
             patch("asyncio.sleep", new=AsyncMock()):
            results = await KokkaiSource().fetch({"source_params": {"terms": ["排熱"]}})
        assert results == []

    @pytest.mark.asyncio
    async def test_http_error_returns_empty_not_raise(self):
        import httpx as _httpx
        client = _mock_client(_httpx.ConnectError("boom"))
        with patch("httpx.AsyncClient", return_value=client), \
             patch("asyncio.sleep", new=AsyncMock()):
            results = await KokkaiSource().fetch({"source_params": {"terms": ["排熱"]}})
        assert results == []

    @pytest.mark.asyncio
    async def test_malformed_payload_returns_empty(self):
        client = _mock_client([_mock_response(json_data={"nope": 1})])
        with patch("httpx.AsyncClient", return_value=client), \
             patch("asyncio.sleep", new=AsyncMock()):
            results = await KokkaiSource().fetch({"source_params": {"terms": ["排熱"]}})
        assert results == []
