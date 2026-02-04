# Fixing the focused crawler: APIs beat crawling, and when you must crawl, prioritize ruthlessly

**The Virginia HB323 discovery failure has an immediate bypass and several architectural fixes.** The React SPA crawl explosion wasted 93% of the page budget on developer docs and login flows, while the keyword threshold penalized terse legislative text. Three complementary solutions emerge: use Virginia's hidden CSV/API exports (bypasses crawling entirely), implement aggressive URL pattern filtering with content-aware link extraction, and tune BM25 parameters for short documents while adding recall-preserving fallbacks.

The most impactful finding: Virginia LIS provides **hourly-updated CSV files via Azure Blob Storage** that contain complete bill data including HB323. Professional policy monitoring tools like LegiScan, GovTrack, and OpenStates already use APIs and bulk data rather than HTML crawling. For the crawler improvements specifically, research identifies OPIC-based link prioritization, adaptive depth control via "Fish-Search" algorithms, and tiered filtering with LLM scoring only for borderline URLs.

---

## Virginia LIS offers complete API and bulk data access

The most direct solution bypasses crawling entirely. Virginia's Legislative Information System provides extensive programmatic access that professional policy tools already exploit:

**CSV bulk data files** update hourly during legislative sessions via Azure Blob Storage at predictable URLs:
```
https://lis.blob.core.windows.net/lisfiles/{YEAR}{SESSION}/{FILE}.CSV
```
For 2026 Regular Session: `https://lis.blob.core.windows.net/lisfiles/20261/BILLS.CSV`

The Bills.csv file contains **41 fields** including Bill_description (searchable for "data center heat"), full text document versions, sponsor information, and action history. Session type codes: 1=Regular, 2=Special Session I, 3=Special Session II.

**API registration** at lis.virginia.gov/apiregistration provides access to 40+ endpoints documented via Swagger at lis.virginia.gov/developers. The OpenStates Virginia scraper uses `VaCSVBillScraper` rather than HTML scraping for exactly this reason.

**Aggregator alternatives** provide multi-state coverage: LegiScan offers 30,000 free API queries monthly with full-text search across all 50 states. OpenStates provides standardized data via v3.openstates.org with monthly PostgreSQL dumps. Both discovered HB323 without crawling the React SPA.

---

## URL pattern filtering stops crawl explosion before it starts

The crawler followed `/developers/*`, `/session-details/*`, and `/login` because it extracted links from global navigation rather than main content. Three filters working in sequence prevent this:

**Path pattern blocklists** should reject URLs immediately based on structure:
```python
BLOCKED_PATTERNS = [
    r'/developer[s]?/', r'/api/', r'/docs?/', r'/login',
    r'/session[s]?/', r'/auth/', r'/forgot-password',
    r'\.(css|js|png|jpg|svg|woff|ico)$'
]

BILL_PATTERNS = [
    r'/bill[s]?/', r'/legislation/', r'/[hs][br]-?\d+',
    r'/act[s]?/', r'/statute[s]?/', r'/measure[s]?/'
]
```

**Content-area link extraction** using trafilatura or BeautifulSoup removes navigation chrome before link harvesting:
```python
# Remove nav elements before extracting links
for selector in ['nav', 'header', 'footer', '[role="navigation"]']:
    for elem in soup.select(selector):
        elem.decompose()
main = soup.select_one('main, article, [role="main"]')
```

**Anchor text scoring** predicts destination relevance before fetching. Links with text containing "bill," "legislation," or bill numbers (HB323) receive priority; links containing "sign in," "developer," or "API" receive negative scores. The OPIC algorithm distributes "cash" credits through the link graph, giving bonus cash to URLs matching bill patterns.

---

## Adaptive depth control allocates budget to productive paths

The crawler spent 7 minutes on 14 developer API page timeouts because breadth-first traversal treated all paths equally. **Fish-Search** and bandit-based allocation solve this:

**Fish-Search adaptive depth** assigns depth budgets based on parent relevance:
- Relevant parent page → children get depth = 3 (explore further)
- Irrelevant parent → children get depth = parent - 1 (prune quickly)
- Depth reaches 0 → abandon path entirely

**Rolling harvest rate monitoring** terminates unproductive subtrees early:
```python
def should_continue_path(path_history, window=5, threshold=0.15):
    recent_scores = path_history[-window:]
    return sum(recent_scores) / len(recent_scores) > threshold
```
After crawling 5 pages from `/developers/`, if average relevance < 0.15, stop exploring that path.

**Multi-armed bandit budget allocation** using Thompson Sampling or UCB balances exploration versus exploitation. Allocate 20% of the 100-page budget for initial exploration across all paths, measure relevance per path, then allocate remaining 80% proportionally to observed quality.

---

## BM25 parameter tuning prevents false negatives on terse text

The bill text "waste heat generated by data centers" scored **4.0 against a threshold of 5.0** because standard BM25 parameters penalize short documents. Three adjustments recover these false negatives:

**Lower the `b` parameter** from default 0.75 to **0.3-0.4** for legislative text. The `b` parameter controls document length normalization—at `b=1.0`, short documents are heavily penalized; at `b=0.0`, length is ignored entirely. For consistently terse government text, moderate normalization prevents false negatives while still distinguishing content from boilerplate.

**Adjust `k1` for term frequency saturation** from default 1.2 to **0.8-1.0**. Lower `k1` reduces the importance of repeated terms, appropriate when legislative language uses precise single mentions rather than repetition.

**Length-adaptive thresholds** compensate for document brevity:
```python
def adaptive_threshold(doc_length, base=5.0):
    if doc_length < 100: return base * 0.5   # 2.5
    elif doc_length < 300: return base * 0.7 # 3.5
    elif doc_length < 500: return base * 0.85 # 4.25
    return base
```
HB323's short text would qualify under the 4.25 threshold at 300-500 words.

**Multi-signal scoring** adds URL patterns (+1-2 points for `.gov`, `/bill`), legal entity detection (+2 points for bill numbers like HB323), and anchor text matches (+1 point per keyword) to the raw BM25 score. Combined scoring would push HB323 well above threshold.

---

## Cascading filters balance speed with recall preservation

A **multi-stage pipeline** applies cheap filters first, expensive filters only when needed:

| Stage | Method | Speed | Target recall |
|-------|--------|-------|---------------|
| 1 | URL pattern matching | Microseconds | 99% |
| 2 | Domain allowlist (.gov) | Microseconds | 98% |
| 3 | HEAD request content-type | ~100ms | 95% |
| 4 | Partial fetch (first 4KB) | ~200ms | 90% |
| 5 | Keyword matching | ~1ms | 85% |
| 6 | BM25 with tuned params | ~5ms | 80% |
| 7 | LLM scoring (borderline only) | ~500ms | 75% final precision |

Early stages reject obvious non-matches (CSS files, login pages); later stages handle borderline cases. URLs scoring **0.2-0.8** on embedding similarity go to the LLM tier; clear accepts (>0.8) and rejects (<0.2) skip expensive processing.

**Semantic embeddings** using sentence-transformers (`all-MiniLM-L6-v2`) provide length-insensitive similarity scoring. Pre-compute embeddings for policy topics ("data center energy efficiency legislation", "heat reuse waste heat recovery policy"), then score incoming pages against these vectors. Embedding similarity complements BM25 for short documents where keyword overlap is sparse.

---

## LLM integration should be tiered and batched for cost efficiency

With Claude API access available, **use LLMs only for borderline classifications** where pattern matching and embeddings are uncertain:

**Tiered architecture** minimizes API costs:
1. Pattern matching → auto-accept bill URLs, auto-reject /login, /developer
2. Embedding similarity → route clear cases (>0.8, <0.2) directly
3. LLM scoring → batch 10-20 borderline URLs per API call

**Batched prompting** reduces per-URL cost:
```
Rate each URL's relevance to data center/energy policy (0-100):
1. lis.virginia.gov/bill-details/20261/HB323
2. lis.virginia.gov/developers/api-reference
...
Respond as JSON: {"1": 85, "2": 5, ...}
```

**Cost estimate**: ~$0.23 per 1,000 URL classifications with batching. For a 100-page crawl budget, borderline URLs (perhaps 30%) cost under $0.01 total.

**Semantic caching** avoids redundant LLM calls by checking cosine similarity against previous queries—if a new URL/title embedding matches a cached query at >0.85 similarity, reuse the cached score.

---

## Allowlisting and fallback mechanisms preserve recall

When **missing a relevant page is the worst outcome**, implement explicit bypass mechanisms:

**Legislative allowlists** should bypass scoring entirely for known-good paths:
```python
ALLOWLIST_DOMAINS = {
    "lis.virginia.gov": {"min_score": 0.0},  # Always crawl
    "legislature.gov": {"min_score": 0.1},
}

ALLOWLIST_PATTERNS = [
    r"lis\.virginia\.gov/.*",
    r".*legislature\.\w{2}\.gov/.*bill.*",
    r".*leg\d?\.state\.\w{2}\.us/.*"
]
```

**Multi-pass crawling** with relaxed thresholds catches false negatives:
1. First pass: standard thresholds (5.0)
2. Second pass: 50% threshold (2.5) on rejected URLs
3. Third pass: manual review queue for remaining borderline cases

**Graph-based neighborhood expansion** crawls sibling pages when a relevant bill is found. If HB323 is discovered, crawl all pages linked from the same parent with minimal filtering—policy content clusters together on legislative sites.

---

## SPA content extraction requires explicit wait strategies

For sites where APIs aren't available, **Playwright-based extraction** must wait for React/Vue/Angular to render:

**Selector-based waiting** beats `networkidle` (which times out on analytics polling):
```python
await page.goto(url, wait_until='domcontentloaded')
await page.wait_for_selector('article.bill-content', timeout=10000)
```

**MutationObserver stabilization** detects when the DOM stops changing—useful when content selectors are unknown. Wait until 500ms passes with no DOM mutations, then extract.

**API response interception** captures data directly from XHR calls:
```python
async with page.expect_response(lambda r: 'api/bills' in r.url):
    await page.goto(url)
    # Extract JSON from API response, not rendered HTML
```

The React SPA often loads data via internal APIs that are more reliable than scraping the rendered DOM.

---

## Recommended implementation architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         POLICY CRAWLER                           │
├─────────────────────────────────────────────────────────────────┤
│  STAGE 1: Data Source Selection                                  │
│  ├── Check for API/CSV (Virginia LIS, LegiScan, OpenStates)     │
│  └── Fall back to crawling only when necessary                   │
├─────────────────────────────────────────────────────────────────┤
│  STAGE 2: URL Filtering (before fetch)                           │
│  ├── Blocklist patterns (/developer/, /login/, /api/)           │
│  ├── Allowlist bypass (*.gov bill paths)                        │
│  └── OPIC priority scoring                                       │
├─────────────────────────────────────────────────────────────────┤
│  STAGE 3: Content Extraction (SPA-aware)                        │
│  ├── Wait for content selectors, not networkidle                │
│  ├── trafilatura boilerplate removal                            │
│  └── Extract links from main content only                        │
├─────────────────────────────────────────────────────────────────┤
│  STAGE 4: Relevance Scoring (tuned for recall)                  │
│  ├── BM25 with b=0.4, k1=0.8                                    │
│  ├── Length-adaptive thresholds                                  │
│  ├── Multi-signal: URL + anchor + legal entities                │
│  └── Embedding similarity for borderline                        │
├─────────────────────────────────────────────────────────────────┤
│  STAGE 5: Fallback Mechanisms                                    │
│  ├── Second pass at 50% threshold                               │
│  ├── LLM scoring for 0.2-0.8 range                              │
│  └── Graph neighborhood expansion                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Conclusion

The HB323 discovery failure stemmed from three fixable issues: crawling an SPA when APIs exist, following navigation links instead of content links, and applying thresholds calibrated for verbose documents to terse legislative text.

**Immediate action**: Download Virginia's BILLS.CSV from Azure Blob Storage. HB323 appears in the Bill_description field searchable for "data center heat." This takes minutes instead of wrestling with React rendering.

**Crawler improvements** for sites without APIs should implement: (1) URL pattern filtering with explicit allowlists for legislative paths, (2) content-area link extraction using trafilatura, (3) BM25 parameter tuning (b=0.4, k1=0.8) with length-adaptive thresholds, and (4) multi-pass architecture preserving recall through fallback mechanisms.

The highest-leverage open source tools are **trafilatura** for boilerplate removal, **sentence-transformers** for embedding-based similarity, and **Crawl4AI** for its BestFirstCrawlingStrategy implementation. For multi-state coverage, LegiScan's API (30K free queries/month) or OpenStates' bulk data eliminate the need to crawl most legislative sites directly.