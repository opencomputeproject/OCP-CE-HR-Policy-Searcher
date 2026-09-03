"""Record the screening windows the cheap screener sees, for the reviewer's rows.

Reads the reviewer's column export (``tests/fixtures/review_column_*.csv``),
fetches each decided row's source page the way a scan would (httpx first,
Playwright when the page is a script shell, PDFs through the same text
extraction), and writes the head window ``screening_excerpt`` would hand the
model to ``tests/fixtures/screening/<slug>.txt`` plus an ``index.json``
describing every row, fetched or failed.

Rows whose source is DIP, Folketing or Kokkai are skipped: those are now
filtered at the source (WP-3) and their links were case-overview pages.

Run from the repo root with the app venv. Network access only; no model
calls, no writes outside ``tests/fixtures/screening/``::

    .venv\\Scripts\\python.exe scripts\\record_screening_fixtures.py

``record_screening_responses.py`` (the second step) sends these windows to
the screening model once and records the raw answers for the replay test.
"""

from __future__ import annotations

import asyncio
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.crawler import AsyncCrawler  # noqa: E402
from src.core.extractor import HtmlExtractor  # noqa: E402
from src.core.llm import screening_excerpt  # noqa: E402
from src.eval.sheet_labels import parse_verdict  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "tests" / "fixtures" / "review_column_2026-09-02.csv"
OUT_DIR = ROOT / "tests" / "fixtures" / "screening"
SOURCE_FILTERED_HOSTS = ("dip.bundestag.de", "ft.dk", "kokkai.ndl.go.jp", "ndl.go.jp")
MIN_WORDS_BEFORE_PLAYWRIGHT = 50


def _slug(row: str, url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    host = "".join(ch if ch.isalnum() else "-" for ch in host).strip("-")
    return f"r{int(row):03d}-{host[:40]}"


def _wanted(row: dict) -> tuple[bool, str]:
    parsed = parse_verdict(row["anna_review"])
    if parsed.verdict not in ("keep", "remove"):
        return False, parsed.verdict
    host = urlparse(row["link"]).netloc.lower()
    if any(host.endswith(h) for h in SOURCE_FILTERED_HOSTS):
        return False, "source_filtered"
    return True, parsed.verdict


async def _fetch_text(crawler: AsyncCrawler, client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    """(text, how): the extracted text and which fetch path produced it."""
    result = await crawler._fetch_with_retry(client, url)
    text = ""
    how = "httpx"
    if result.is_success and result.content:
        if result.content_type == "application/pdf":
            text = result.content
            how = "httpx-pdf"
        else:
            text = HtmlExtractor().extract(result.content, url).text or ""
    if len(text.split()) < MIN_WORDS_BEFORE_PLAYWRIGHT and result.content_type != "application/pdf":
        try:
            pw = await crawler._fetch_playwright(url)
            if pw.is_success and pw.content:
                pw_text = HtmlExtractor().extract(pw.content, url).text or ""
                if len(pw_text.split()) > len(text.split()):
                    text, how = pw_text, "playwright"
        except Exception as exc:  # a JS shell that also fails in a browser is a failed row
            how = f"{how}; playwright failed: {type(exc).__name__}"
    return text, how


async def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    crawler = AsyncCrawler(delay_seconds=1.0, timeout_seconds=30)
    index: list[dict] = []
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    async with httpx.AsyncClient(
        headers={"User-Agent": crawler.user_agent}, follow_redirects=True, timeout=30,
    ) as client:
        for row in rows:
            wanted, verdict = _wanted(row)
            if not wanted:
                continue
            parsed = parse_verdict(row["anna_review"])
            slug = _slug(row["row"], row["link"])
            entry = {
                "slug": slug, "row": int(row["row"]), "url": row["link"], "verdict": verdict,
                "reason": parsed.categories[0] if parsed.categories else "",
                "reason_text": parsed.reason_text, "chars": 0, "fetch": "", "fetched_at": fetched_at,
            }
            try:
                text, how = await _fetch_text(crawler, client, row["link"])
            except Exception as exc:
                text, how = "", f"failed: {type(exc).__name__}: {exc}"
            window = screening_excerpt(text, None) if text else ""
            entry["fetch"] = how
            entry["chars"] = len(window)
            if window:
                (OUT_DIR / f"{slug}.txt").write_text(window, encoding="utf-8", newline="\n")
            index.append(entry)
            print(f"{slug:<48} {verdict:<6} {len(window):>6} chars  {how}")
    (OUT_DIR / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n",
    )
    ok = sum(1 for e in index if e["chars"] > 0)
    print(f"\n{ok} of {len(index)} rows recorded to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
