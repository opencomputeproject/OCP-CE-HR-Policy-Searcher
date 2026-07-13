"""News tripwire: headlines name a policy weeks before ministries publish it.

Sweeps GDELT (machine-translated global news), Google News RSS per
language, and trade press feeds; deduplicates; optionally triages with
the cheap screening model; and writes surviving items to the lead queue
for a human-gated chase. No expensive analysis happens here.
"""

import asyncio
import json
import logging
import re
from typing import Optional
from urllib.parse import quote_plus

import anthropic
import httpx
from pydantic import BaseModel

from ..core.models import DEFAULT_SCREENING_MODEL
from ..storage.leads import Lead, LeadStore

logger = logging.getLogger(__name__)

GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_DELAY_SECONDS = 5.0  # unpublished rate limit; stay polite
USER_AGENT = "OCP-PolicyPulse/1.0"

_RSS_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.IGNORECASE | re.DOTALL)
_RSS_FIELD_RES = {
    "title": re.compile(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>",
                        re.IGNORECASE | re.DOTALL),
    "link": re.compile(r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>",
                       re.IGNORECASE | re.DOTALL),
    "description": re.compile(
        r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>",
        re.IGNORECASE | re.DOTALL),
}

TRIAGE_PROMPT = """You screen news items for a policy-tracking tool.
For each numbered item, decide: does it describe a GOVERNMENT POLICY ACTION
(bill, law, regulation, consultation, mandate, incentive, ruling) related to
heat reuse, waste heat, district heating, or data center energy?

Items:
{items}

RESPOND WITH JSON ONLY — a list, one entry per RELEVANT item:
[{{"index": 0, "relevant": true, "policy_name": "best guess or empty",
   "jurisdiction": "country/region or empty"}}]
Omit irrelevant items entirely.
"""


class NewsItem(BaseModel):
    title: str
    url: str
    snippet: str = ""
    origin_query: str = ""
    jurisdiction_guess: str = ""


def parse_gdelt(payload: str, origin_query: str) -> list[NewsItem]:
    """Parse a GDELT DOC 2.0 artlist JSON payload."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("GDELT payload was not JSON for query %s", origin_query)
        return []
    items = []
    for article in data.get("articles", []):
        url = article.get("url", "")
        title = article.get("title", "")
        if not url or not title:
            continue
        items.append(NewsItem(
            title=title,
            url=url,
            snippet=article.get("sourcecountry", ""),
            origin_query=origin_query,
            jurisdiction_guess=article.get("sourcecountry", ""),
        ))
    return items


def parse_rss(payload: str, origin_query: str) -> list[NewsItem]:
    """Parse RSS <item> entries with regex (no XML parser attack surface)."""
    items = []
    for block in _RSS_ITEM_RE.findall(payload or ""):
        fields = {}
        for name, pattern in _RSS_FIELD_RES.items():
            match = pattern.search(block)
            fields[name] = (match.group(1).strip() if match else "")
        if not fields["title"] or not fields["link"]:
            continue
        items.append(NewsItem(
            title=fields["title"],
            url=fields["link"],
            snippet=fields["description"][:300],
            origin_query=origin_query,
        ))
    return items


def dedupe_items(items: list[NewsItem]) -> list[NewsItem]:
    """Drop repeats by URL and by normalized title."""
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    unique = []
    for item in items:
        title_key = " ".join(item.title.lower().split())
        if item.url in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(item.url)
        seen_titles.add(title_key)
        unique.append(item)
    return unique


async def _collect(config: dict) -> list[NewsItem]:
    items: list[NewsItem] = []
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        gdelt_cfg = config.get("gdelt", {})
        if gdelt_cfg.get("enabled"):
            for i, query in enumerate(gdelt_cfg.get("queries", [])):
                if i:
                    await asyncio.sleep(GDELT_DELAY_SECONDS)
                q = query.get("q", "")
                url = (
                    f"{GDELT_ENDPOINT}?query={quote_plus(q)}&mode=artlist"
                    f"&format=json&timespan={query.get('timespan', '1w')}"
                )
                try:
                    resp = await client.get(url)
                    items.extend(parse_gdelt(resp.text, origin_query=q))
                except Exception as e:
                    logger.warning("GDELT fetch failed for %s: %s", q, e)

        gn_cfg = config.get("google_news", {})
        if gn_cfg.get("enabled"):
            for query in gn_cfg.get("queries", []):
                q, hl = query.get("q", ""), query.get("hl", "en")
                gl = query.get("gl", "US")
                url = (
                    "https://news.google.com/rss/search?"
                    f"q={quote_plus(q)}&hl={hl}&gl={gl}&ceid={gl}:{hl}"
                )
                try:
                    resp = await client.get(url)
                    items.extend(parse_rss(resp.text, origin_query=q))
                except Exception as e:
                    logger.warning("Google News fetch failed for %s: %s", q, e)

        for feed in config.get("rss_feeds", []):
            try:
                resp = await client.get(feed["url"])
                items.extend(parse_rss(resp.text, origin_query=f"feed:{feed['name']}"))
            except Exception as e:
                logger.warning("Feed fetch failed for %s: %s", feed.get("name"), e)

    return items


async def _triage(
    items: list[NewsItem], api_key: str, model: str,
) -> list[NewsItem]:
    """Keep only items the screening model marks as policy actions."""
    numbered = "\n".join(
        f"{i}. {item.title} — {item.snippet[:120]}"
        for i, item in enumerate(items)
    )
    client = anthropic.AsyncAnthropic(api_key=api_key)
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=1500,
            temperature=0.0,
            messages=[{
                "role": "user",
                "content": TRIAGE_PROMPT.format(items=numbered),
            }],
        )
        raw = response.content[0].text
        start, end = raw.find("["), raw.rfind("]")
        verdicts = json.loads(raw[start:end + 1]) if start >= 0 else []
    except Exception as e:
        logger.warning("News triage failed (%s); keeping all items", e)
        return items

    kept = []
    for verdict in verdicts:
        try:
            index = int(verdict.get("index"))
        except (TypeError, ValueError):
            continue
        if not verdict.get("relevant") or not (0 <= index < len(items)):
            continue
        item = items[index]
        if verdict.get("jurisdiction"):
            item.jurisdiction_guess = verdict["jurisdiction"]
        if verdict.get("policy_name"):
            item.snippet = f"{verdict['policy_name']} — {item.snippet}"
        kept.append(item)
    return kept


async def run_news_signals(
    config: dict, lead_store: LeadStore, api_key: Optional[str],
    model: str = DEFAULT_SCREENING_MODEL,
) -> dict:
    """Run one news sweep. Returns a summary dict for logs/notifications."""
    if not config.get("enabled"):
        return {"enabled": False, "items_seen": 0, "leads_added": 0}

    items = dedupe_items(await _collect(config))
    seen = len(items)

    if items and api_key:
        items = await _triage(items, api_key, model)

    cap = config.get("max_leads_per_run", 50)
    items = items[:cap]

    leads = [
        Lead(
            title=item.title,
            source_url=item.url,
            snippet=item.snippet,
            jurisdiction_guess=item.jurisdiction_guess,
            origin="news",
        )
        for item in items
    ]
    added = lead_store.add_leads(leads)
    logger.info(
        "News signals: %d items seen, %d kept, %d new leads",
        seen, len(items), added,
    )
    return {"enabled": True, "items_seen": seen, "leads_added": added}
