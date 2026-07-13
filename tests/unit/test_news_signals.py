"""Tests for the news tripwire channel (src/signals/news.py)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.signals.news import (
    dedupe_items,
    parse_gdelt,
    parse_rss,
    run_news_signals,
    NewsItem,
)
from src.storage.leads import LeadStore


GDELT_PAYLOAD = json.dumps({
    "articles": [
        {
            "url": "https://example.dk/nyhed/overskudsvarme-lov",
            "title": "Ny lov om overskudsvarme fra datacentre",
            "sourcecountry": "Denmark",
            "seendate": "20260710T120000Z",
        },
        {
            "url": "https://example.dk/nyhed/overskudsvarme-lov",
            "title": "Duplicate of the same article",
        },
    ],
})

RSS_PAYLOAD = """<?xml version="1.0"?>
<rss><channel>
  <item>
    <title>Germany tightens data centre heat reuse rules</title>
    <link>https://news.example.com/germany-heat</link>
    <description>The EnEfG amendment raises reuse quotas.</description>
  </item>
  <item>
    <title>Unrelated sports story</title>
    <link>https://news.example.com/sports</link>
  </item>
</channel></rss>
"""


class TestParsers:
    def test_parse_gdelt(self):
        items = parse_gdelt(GDELT_PAYLOAD, origin_query="overskudsvarme")
        assert len(items) == 2
        assert items[0].url.startswith("https://example.dk")
        assert "overskudsvarme" in items[0].title.lower()

    def test_parse_gdelt_malformed(self):
        assert parse_gdelt("not json", origin_query="x") == []

    def test_parse_rss(self):
        items = parse_rss(RSS_PAYLOAD, origin_query="feed:test")
        assert len(items) == 2
        assert items[0].title == "Germany tightens data centre heat reuse rules"
        assert items[0].snippet.startswith("The EnEfG")

    def test_parse_rss_malformed(self):
        assert parse_rss("<not-rss>", origin_query="feed:test") == []


class TestDedupe:
    def test_dedupes_by_url_and_title(self):
        items = [
            NewsItem(title="A story", url="https://a.example/x"),
            NewsItem(title="A story", url="https://a.example/x"),
            NewsItem(title="A STORY  ", url="https://b.example/y"),  # same title, diff url
            NewsItem(title="Different", url="https://c.example/z"),
        ]
        deduped = dedupe_items(items)
        assert len(deduped) == 2


@pytest.fixture
def signals_config():
    return {
        "enabled": True,
        "max_leads_per_run": 10,
        "gdelt": {"enabled": True, "queries": [{"q": '"overskudsvarme"', "timespan": "1w"}]},
        "google_news": {"enabled": True, "queries": [{"q": "fernwärme gesetz", "hl": "de", "gl": "DE"}]},
        "rss_feeds": [{"name": "DCD", "url": "https://feeds.example/rss"}],
        "watch_pages": [],
    }


def _mock_http(gdelt=GDELT_PAYLOAD, rss=RSS_PAYLOAD):
    async def fake_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = gdelt if "gdeltproject" in url else rss
        return resp

    client = MagicMock()
    client.get = AsyncMock(side_effect=fake_get)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


class TestRunNewsSignals:
    @pytest.mark.asyncio
    async def test_produces_leads_without_api_key(self, signals_config, tmp_path):
        """No key = no triage spend; items still become leads for humans."""
        store = LeadStore(data_dir=str(tmp_path))
        with patch("src.signals.news.httpx.AsyncClient", return_value=_mock_http()):
            summary = await run_news_signals(
                signals_config, store, api_key=None,
            )
        assert summary["leads_added"] > 0
        assert len(store.list(status="new")) == summary["leads_added"]

    @pytest.mark.asyncio
    async def test_cap_respected(self, signals_config, tmp_path):
        signals_config["max_leads_per_run"] = 1
        store = LeadStore(data_dir=str(tmp_path))
        with patch("src.signals.news.httpx.AsyncClient", return_value=_mock_http()):
            summary = await run_news_signals(signals_config, store, api_key=None)
        assert summary["leads_added"] == 1

    @pytest.mark.asyncio
    async def test_disabled_config_is_noop(self, tmp_path):
        store = LeadStore(data_dir=str(tmp_path))
        summary = await run_news_signals({"enabled": False}, store, api_key=None)
        assert summary["leads_added"] == 0

    @pytest.mark.asyncio
    async def test_triage_filters_with_api_key(self, signals_config, tmp_path):
        """With a key, Haiku triage keeps only policy-flavored items."""
        store = LeadStore(data_dir=str(tmp_path))

        triage_response = MagicMock()
        triage_response.content = [MagicMock(text=json.dumps([
            {"index": 0, "relevant": True, "policy_name": "Overskudsvarme Act",
             "jurisdiction": "Denmark"},
        ]))]
        triage_response.usage = MagicMock(input_tokens=10, output_tokens=10)

        mock_anthropic = MagicMock()
        mock_anthropic.messages.create = AsyncMock(return_value=triage_response)

        with patch("src.signals.news.httpx.AsyncClient", return_value=_mock_http()), \
                patch("src.signals.news.anthropic.AsyncAnthropic", return_value=mock_anthropic):
            summary = await run_news_signals(
                signals_config, store, api_key="test-key",
            )
        leads = store.list(status="new")
        assert summary["leads_added"] == len(leads)
        assert all(lead.jurisdiction_guess for lead in leads)

    @pytest.mark.asyncio
    async def test_reruns_do_not_duplicate_leads(self, signals_config, tmp_path):
        store = LeadStore(data_dir=str(tmp_path))
        with patch("src.signals.news.httpx.AsyncClient", return_value=_mock_http()):
            first = await run_news_signals(signals_config, store, api_key=None)
            second = await run_news_signals(signals_config, store, api_key=None)
        assert first["leads_added"] > 0
        assert second["leads_added"] == 0
