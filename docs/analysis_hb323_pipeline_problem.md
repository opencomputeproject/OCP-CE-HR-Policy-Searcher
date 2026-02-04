# Pipeline Analysis: Why HB323 (Gold Example) Fails to Surface

## Executive Summary

Virginia HB323 ("Data Center Heat Reuse Study") is exactly the kind of policy this tool was built to find. It directs the Virginia Department of Energy to study ways to utilize data center waste heat for surrounding buildings. Del. Rip Sullivan (D-Fairfax) is the sponsor -- a known OCP ally who participated in the OCP Heat Reuse webinar.

**It should be the easiest possible find. It isn't found.**

The domain `us_va_hb323_2026` was configured with `start_paths: ["/bill-details/20261/HB323"]` pointing directly at the bill. A scan on 2026-02-03 crawled 100 pages, found the bill page, fetched the bill text -- and still returned 0 policies. Three separate problems compound to create a total failure.

---

## Problem 1: Crawl Explosion (7% Signal, 93% Noise)

### What Happened

The crawler started at `/bill-details/20261/HB323` with `max_depth: 2`. The bill detail page is a React SPA with a full site navigation bar linking to the entire Virginia Legislature Information System. At depth 1, the crawler followed every link on the page -- not just bill-related links (text versions, votes, amendments) but also the global nav links (home, bill search, developers, session details, member directory, etc.).

At depth 2, it followed links from THOSE pages -- expanding into committee rosters, member profiles, API documentation pages, docket listings, and more.

### The Numbers

| Category | Pages | % of Budget | What They Are |
|----------|-------|-------------|---------------|
| **HB323-related** | **7** | **7%** | Bill detail, 4 text versions, 2 vote records |
| `/session-details/*` | 38 | 38% | Committee rosters, member profiles, dockets, statistics |
| Navigation/auth | 22 | 22% | `/login`, `/privacy`, `/tos`, `/home`, `/bill-search` (x5), `/forgot-password`, etc. |
| `/developers/*` | 18 fetched + 14 timeouts | 32% | API documentation pages |
| **Total** | **100** | **100%** | Hit `max_pages_per_domain` hard limit |

The 14 developer API page timeouts (30s each) alone wasted **7 minutes** of the 11.7-minute run.

### Why It Happened

1. **No path scoping in the crawler.** The `_extract_links()` method in `async_crawler.py` (lines 147-172) follows ALL same-domain links regardless of path. There is an `allowed_path_patterns` field documented in `config/domains/_template.yaml` but it is **not implemented** in the crawler code. It's a stub.

2. **`max_depth: 2` is too deep for SPA sites.** On a static government site, depth 2 means "the bill page, then pages linked from it." On an SPA with a global nav bar, depth 2 means "the bill page, then the ENTIRE SITE's navigation, then pages linked from every nav destination." The nav bar on `lis.virginia.gov` links to ~30 top-level destinations at depth 1, each of which links to dozens more at depth 2.

3. **FIFO queue with no prioritization.** The queue processes URLs in discovery order (BFS). Bill text versions (`/bill-details/20261/HB323/text/HB323`) compete equally with `/developers/LegislationSummary` and `/session-details/20261/member-information/H0269/member-details`. Since the global nav links appear first in the HTML (header), they get queued before bill-specific links in the page body.

4. **The 100-page budget fills with junk.** `max_pages_per_domain` defaults to 100. The crawler hit this limit, stopping before it could have found additional bill-related content. Only 7 of 100 slots went to HB323 content.

### Relevant Code

- **Crawl loop:** `src/crawler/async_crawler.py:77-108`
- **Link extraction (no path filtering):** `src/crawler/async_crawler.py:147-172`
- **Max pages limit:** `config/settings.yaml:18` (`max_pages_per_domain: 100`)
- **Depth tracking:** `src/crawler/async_crawler.py:97-101`
- **Template stub (not implemented):** `config/domains/_template.yaml:21-26`

---

## Problem 2: Keyword Threshold Too High for Legislative Text

### What Happened

All 79 pages that reached the keyword stage (86 fetched - 7 URL-filtered) scored below the minimum of 5.0. **Every single page failed.** The failure reason for all 79 was identical: "Below min score (5.0)."

The run was NOT done with `--verbose`, so per-page keyword scores were not logged. We don't have the exact score for the HB323 bill text pages. But we can reason about it from the keyword configuration.

### The Keyword Scoring System

**Categories and weights:**

| Category | Weight | Example Terms |
|----------|--------|---------------|
| `subject` | 3.0 | "waste heat recovery", "data center waste heat", "district heating data center" |
| `policy_type` | 2.0 | "regulation", "legislation", "law", "act", "mandate", "statute" |
| `incentives` | 2.0 | "tax credit", "grant", "subsidy", "funding" |
| `enabling` | 1.5 | "feasibility study", "pilot program", "roadmap", "strategy" |
| `off_takers` | 1.5 | "district heating customer", "swimming pool", "greenhouse heating" |
| `context` | 1.0 | "data center", "server farm", "colocation", "hyperscale" |
| `energy` | 1.0 | "energy efficiency", "PUE", "sustainability", "net zero" |

**Formula:** `score = sum(weight * match_count)` per category, then `+boost`, then `-penalty`, floor at 0.

**To pass, a page needs ALL THREE:**
1. Score >= 5.0
2. At least 2 unique keyword matches
3. At least ONE of these category combinations satisfied (both categories must have >= 1 match):
   - `context` + `subject` (e.g., "data center" + "waste heat")
   - `context` + `policy_type` (e.g., "data center" + "legislation")
   - `subject` + `policy_type` (e.g., "waste heat" + "law")
   - `subject` + `incentives` (e.g., "waste heat" + "grant")

### Why HB323 Likely Scores Below 5.0

The HB323 bill text is short and precise. The introduced version reads approximately:

> *"That the Department of Energy shall conduct a study on ways to utilize waste heat generated by data centers for the purpose of heating surrounding buildings and facilities..."*

Estimated keyword matches:
- "waste heat" -> `subject` weight 3.0 x 1 = **3.0**
- "data center" -> `context` weight 1.0 x 1 = **1.0**
- Total: **4.0** (below 5.0 threshold)

Even with the bill detail page containing more context text:
- "data center" -> `context` 1.0 x ~2 mentions = **2.0**
- "waste heat" -> `subject` 3.0 x 1 = **3.0**
- Total: **5.0** -- barely passes IF the text is present

But to actually score 5.0+, the page needs either:
- Multiple subject keyword matches: "waste heat" + "heat recovery" = 3.0 + 3.0 = 6.0
- Subject + policy type: "waste heat" + "legislation" = 3.0 + 2.0 = 5.0
- Multiple context + subject: "data center" x2 + "waste heat" = 2.0 + 3.0 = 5.0

### The Legislative Language Problem

Legislative text uses precise, terse language. A bill about "data center waste heat" says exactly that -- it doesn't repeat "waste heat recovery" and "district heating" and "thermal energy" in the way a policy whitepaper or regulatory analysis would. The keyword system is calibrated for lengthy policy documents with rich vocabulary, not for 2-paragraph bill summaries.

### Boost Keywords Could Help But Don't

The boost keywords (each adds 3.0 points) include "data center waste heat" and "data centre waste heat." If HB323's text contains that exact phrase, the score jumps by 3.0. But:
- The bill text might say "waste heat generated by data centers" (different word order, not an exact match)
- The boost keyword system uses exact substring matching -- "data center waste heat" must appear as a contiguous phrase

### Required Combinations May Also Block

Even if the score reaches 5.0, the required_combinations check is a separate gate:
- The page needs matches from TWO specific categories
- `context` ("data center") + `subject` ("waste heat") would satisfy the first combination
- But if content extraction fails to capture the text (see Problem 3), no categories match at all

### Relevant Code and Config

- **Keyword config:** `config/keywords.yaml` (entire file, ~770 lines)
- **Scoring formula:** `src/analysis/keywords.py:162-235`
- **Threshold check:** `src/analysis/keywords.py:360-388` (`get_failure_reason()`)
- **Combination check:** `src/analysis/keywords.py:237-328` (`check_stricter_requirements()`)
- **Thresholds in config:** `config/keywords.yaml:540-554` (min_score=5.0, min_matches=2)
- **Boost keywords:** `config/keywords.yaml:672-706`

---

## Problem 3: SPA Content Extraction Uncertainty

### What the Page Actually Is

The static HTML at `https://lis.virginia.gov/bill-details/20261/HB323` contains:

```html
<title>HB323 - 2026 Regular Session | LIS</title>
<meta name="description" content="HB323 - 2026 Regular Session | LIS">
<noscript>You need to enable JavaScript to run this app.</noscript>
<div id="root"></div>
<script src="/static/js/2.2c4bfc65.chunk.js"></script>
<script src="/static/js/main.5f188fa8.chunk.js"></script>
```

**This is a pure React SPA shell.** Zero bill content in the static HTML. Everything -- bill title, description, sponsors, status, text versions -- is loaded and rendered by JavaScript after page load.

### The Rendering Chain

The domain config has `requires_playwright: true`, so:

1. Playwright launches headless Chromium
2. Navigates to the URL with `wait_until="networkidle"`
3. `networkidle` fires when there are no new network requests for 500ms
4. Playwright captures `page.content()` -- the full rendered DOM HTML
5. HTML goes through the content extraction pipeline (see below)

### Content Extraction Pipeline

Once Playwright captures the rendered HTML, it goes through 4 phases:

**Phase 1: Remove structural tags.** These are completely deleted with all children:
`nav`, `footer`, `header`, `aside`, `script`, `style`, `noscript`, `iframe`, `svg`, `canvas`, `video`, `audio`, `map`, `object`, `embed`, `form`

**Phase 2: Remove elements by class/ID pattern.** 70+ regex patterns target:
- Cookie/consent banners: `cookie`, `consent`, `gdpr`
- Navigation: `^nav$`, `^menu$`, `navigation`, `breadcrumb`, `pagination`
- Sidebars: `sidebar`, `side-bar`, `aside`
- Social widgets: `social`, `share-`, `twitter-`, `facebook-`
- Ads: `^ad$`, `^ads$`, `advert`, `banner`, `sponsor`
- Newsletter: `newsletter`, `subscribe`, `signup`
- Login: `login`, `signin`, `account`
- Related content: `related-`, `recommended`, `popular-`
- Footer content: `^footer$`, `copyright`, `legal-`

**Phase 3: Find main content area.** Priority:
1. `<main>` tag
2. `<article>` tag
3. `role="main"` attribute
4. Element with class/id matching: `content`, `article`, `main`, `post`, `body-content`, `page-content`
5. Falls back to `<body>`

**Phase 4: Extract text.** BeautifulSoup's `get_text()` with newline separators, strip whitespace, remove blank lines.

### The React SPA Extraction Risk

When Playwright renders the React app:
- The `<div id="root">` gets filled with the rendered component tree
- React components may use class names like `MuiTypography-root`, `bill-detail-card`, `nav-tabs`, etc.
- **Risk 1:** If the bill detail page has a component with class `navigation` or `nav-tabs` for switching between bill sections (Summary, Text, Votes, etc.), the pattern `^nav$` or `navigation` could strip it
- **Risk 2:** If the main content area isn't wrapped in a `<main>` or `<article>` tag (React doesn't require this), Phase 3 falls back to `<body>`, which includes everything -- potentially diluting the content with site chrome
- **Risk 3:** If the React app uses `<header>` for the bill title/summary section, Phase 1 removes it entirely
- **Risk 4:** The `banner` pattern could match a "legislative banner" or "bill status banner" component

### What We Don't Know (Critical Gaps)

We don't have visibility into:
1. **What HTML Playwright actually captured** -- the run log doesn't record the rendered HTML or extracted text
2. **What the extractor kept vs. removed** -- no diagnostic logging for extraction decisions
3. **What the keyword matcher received** -- no logging of the actual text fed to keywords
4. **The keyword score per page** -- the run wasn't done with `--verbose`, so individual page scores weren't logged

### The `networkidle` Question

`wait_until="networkidle"` means Playwright waits until there are no new network requests for 500ms. For a React SPA that fetches bill data from an API:
1. Initial page load fetches JS bundles -> renders shell -> fires API requests for bill data
2. API responses arrive -> React re-renders with data
3. `networkidle` should catch this IF the API call happens during initial load
4. But: if the page uses lazy loading, tabs, or deferred rendering, data for non-visible sections may not be fetched until user interaction

The bill detail page likely fetches bill data in the initial render (it's the main content), so `networkidle` should capture it. But the text versions (`/bill-details/20261/HB323/text/HB323`) might be more problematic if they load text content on-demand.

### Relevant Code

- **Playwright fetch:** `src/crawler/fetchers/playwright_fetcher.py:48-53` (`wait_until="networkidle"`)
- **JS detection:** `src/crawler/detection/js_required.py` (React placeholder detection)
- **Content extraction config:** `config/content_extraction.yaml`
- **Extraction code:** `src/crawler/extractors/html_extractor.py:107-157`

---

## Problem 4: URL Pre-Filter Misses Site Junk

### What Was Filtered

The URL pre-filter caught 7 of the ~93 junk pages:

| Path | Skip Rule | Caught? |
|------|-----------|---------|
| `/login` (x2) | Matched `/login` | Yes |
| `/privacy` | Matched `/privacy` | Yes |
| `/register-account` | Matched `/register` | Yes |
| `/developers/Calendar` | Matched `/calendar` | Yes |
| `/developers/Contact` | Matched `/contact` | Yes |
| `/session-details/20261/calendar` | Matched `/calendar` | Yes |

### What Was NOT Filtered

| Path Category | Count | Example |
|---|---|---|
| `/developers/*` (API docs) | 32 | `/developers/LegislationVersion`, `/developers/Vote`, `/developers/Person` |
| `/session-details/*/member-*` | 12 | `/session-details/20261/member-information/H0269/member-details` |
| `/session-details/*/committee-*` | 14 | `/session-details/20261/committee-information/H14003/committee-details` |
| `/session-details/*/statistics/*` | 3 | `/session-details/20261/statistics/status` |
| `/session-details/*/dockets/*` | 6 | `/session-details/20261/committee-information/S13/dockets/20980` |
| Site navigation pages | 6 | `/home`, `/data-files`, `/forgot-password`, `/tos`, `/apiregistration`, `/schedule` |
| `/bill-search` (x5+) | 6 | Same page fetched multiple times with slightly different URLs |
| Vote search | 1 | `/vote-search/20261/H0269` |

### Why These Weren't Caught

The skip rules in `config/url_filters.yaml` target patterns common across government sites:
- `/login`, `/register`, `/contact`, `/calendar`, `/privacy` -- generic boilerplate paths
- `/careers`, `/jobs`, `/shop/`, `/cart` -- irrelevant content types

They DON'T have rules for legislature-specific patterns like:
- `/developers` (API documentation)
- `/session-details` (session navigation)
- `/member-information` (legislator profiles)
- `/committee-information` (committee pages)
- `/bill-search` (search interface)

The URL pre-filter was designed as a general-purpose filter across hundreds of government sites, not tailored to `lis.virginia.gov`'s URL structure.

### Important: URL Filters Are Post-Crawl, Not Pre-Crawl

**Critical design detail:** URL filters in `config/url_filters.yaml` are applied AFTER pages are fetched, not during link extraction. The filter prevents pages from reaching keyword analysis and LLM processing (saving API costs), but the pages are still **crawled and fetched**, consuming the `max_pages_per_domain` budget.

Even with perfect URL pre-filters, those 93 junk pages still get fetched and count toward the 100-page limit. The filters just prevent wasting LLM API calls on them.

Code flow:
```
Crawl (fetch ALL links, no path filtering)
  -> URL pre-filter (remove obvious junk from analysis pipeline)
    -> Keyword matching (score remaining pages)
      -> LLM analysis (only pages above keyword threshold)
```

### Relevant Code

- **URL filter config:** `config/url_filters.yaml` (full skip rules)
- **Filter application (post-crawl):** `src/main.py:1062-1068`
- **Filter logic:** `src/analysis/url_filter.py:128-186`

---

## The Compound Effect

Each problem alone might be survivable. Together, they create total failure:

1. **Crawl explosion** fills the 100-page budget with 93 irrelevant pages
2. **No path scoping** means the crawler can't stay focused on bill content
3. **URL pre-filter** catches only 7 of 93 junk pages (8% effectiveness on this site)
4. **Keyword threshold of 5.0** is too high for terse legislative text
5. **SPA content extraction** may be losing or diluting the actual bill text
6. **No per-page diagnostic data** (wasn't run with `--verbose`) means we can't verify what text the keyword matcher actually received

The pipeline is designed for a different use case: crawling policy-rich government websites with long-form content (ministry reports, regulatory guidance, energy plans). It works well on those. But legislative bill trackers are SPAs with short, precise text, deep navigation structures, and minimal boilerplate -- the opposite of what the pipeline is optimized for.

---

## Existing CLI Workarounds

The pipeline already has flags that could partially address these issues:

- `--min-keyword-score 3` -- Lower the threshold to let 4.0-scoring pages through
- `--no-require-combinations` -- (if it exists) Disable the combination gate
- `--min-density 0` -- Already disabled by default
- `--verbose` -- Would show per-page keyword scores for diagnosis
- `max_depth: 1` in domain YAML -- Would limit crawl to just direct links from the bill page

But these are band-aids. The structural issues remain.

---

## Data From the Actual Run

### Run: `run_20260203_181055`

```
Domain:           us_va_hb323_2026
Duration:         700s (11.7 minutes)
Pages crawled:    100 (hit max_pages_per_domain limit)
Pages fetched OK: 86
Pages timed out:  14 (all /developers/* API pages)
Pages blocked:    0
URL filtered:     7  (login, privacy, register, calendar, contact)
Keywords checked: 79
Keywords passed:  0  (ALL failed "Below min score 5.0")
Policies found:   0
LLM calls:        0  (nothing reached LLM stage)
Cost:             $0.00
```

### The 7 HB323-Related Pages That Were Fetched

| Path | Type | Fetch Time |
|------|------|------------|
| `/bill-details/20261/HB323` | Bill detail/summary page | 6620ms |
| `/bill-details/20261/HB323/text/HB323` | Introduced bill text | 1735ms |
| `/bill-details/20261/HB323/text/HB323H1` | House substitute 1 | 1521ms |
| `/bill-details/20261/HB323/text/HB323HC1` | House committee amendment 1 | 4572ms |
| `/bill-details/20261/HB323/text/HB323HC2` | House committee amendment 2 | 1484ms |
| `/vote-details/HB323/20261/H14003V2610615` | Committee vote record | 1279ms |
| `/vote-details/HB323/20261/H14V2610964` | Floor vote record | 2080ms |

All 7 of these pages were successfully fetched. All 7 reached keyword matching. **All 7 scored below 5.0.** We don't know their exact scores because `--verbose` wasn't used.

### The 14 Timed-Out Pages (All Developer API Docs)

Each one burned 30 seconds of wall-clock time:
```
/developers/LegislationSummary      - Timeout after 30s
/developers/LegislationSubject      - Timeout after 30s
/developers/Person                  - Timeout after 30s
/developers/Personnel               - Timeout after 30s
/developers/CommitteeLegislationReferral - Timeout after 30s
/developers/LegislationPatron       - Timeout after 30s
/developers/LegislationFileGeneration - Timeout after 30s
/developers/MembersByCommittee      - Timeout after 30s
/developers/Organization            - Timeout after 30s
/developers/PartnerAuthentication   - Timeout after 30s
/developers/CommunicationFileGeneration - Timeout after 30s
/developers/Committee               - Timeout after 30s
/developers/LegislationCollections  - Timeout after 30s
/developers/User                    - Timeout after 30s
```

These are API documentation pages on `lis.virginia.gov` that presumably load interactive API test consoles, taking >30s to render in headless Chromium.

---

## Pipeline Architecture Reference

### Full Data Flow

```
Domain Config (virginia.yaml)
  |
  v
Start Paths: ["/bill-details/20261/HB323"]
  |
  v
CRAWLER (async_crawler.py)
  |
  +-- Fetch start page at depth=0
  |     |
  |     +-- requires_playwright: true -> Playwright (headless Chromium)
  |     |     |
  |     |     +-- Navigate to URL
  |     |     +-- wait_until="networkidle" (waits for no network activity for 500ms)
  |     |     +-- Capture page.content() (full rendered DOM)
  |     |     +-- Return HTML + status code
  |     |
  |     +-- Content Extraction (html_extractor.py)
  |     |     |
  |     |     +-- Phase 1: Remove structural tags (nav, header, footer, script, etc.)
  |     |     +-- Phase 2: Remove elements by class/ID pattern (70+ patterns)
  |     |     +-- Phase 3: Find main content (<main>, <article>, role=main, or <body>)
  |     |     +-- Phase 4: Extract text with BeautifulSoup get_text()
  |     |     +-- Return: cleaned text string
  |     |
  |     +-- If depth < max_depth: Extract links from HTML
  |           |
  |           +-- Find all <a href> tags
  |           +-- Filter: same domain only
  |           +-- Filter: skip file extensions (.pdf, .doc, etc.)
  |           +-- NO path filtering (allowed_path_patterns not implemented)
  |           +-- Queue all links at depth+1
  |
  +-- Repeat for queued links until queue empty OR max_pages_per_domain reached
  |
  v
ANALYSIS PIPELINE (main.py)
  |
  +-- URL Pre-Filter (url_filter.py)
  |     |
  |     +-- Check skip_paths (substring match): /login, /contact, /calendar, etc.
  |     +-- Check skip_patterns (regex): date archives, pagination, UTM params
  |     +-- Check skip_extensions: .pdf, .exe, .zip, etc.
  |     +-- Applied AFTER crawling (doesn't save crawl budget)
  |     +-- Result: 7 of 86 pages filtered out
  |
  +-- Keyword Matching (keywords.py)
  |     |
  |     +-- For each remaining page (79 pages):
  |     |     +-- Run all keyword patterns against extracted text
  |     |     +-- Calculate weighted score per category
  |     |     +-- Apply boost keywords (+3.0 per match)
  |     |     +-- Apply penalty keywords (-2.0 per match)
  |     |     +-- Check: score >= 5.0? (GATE 1)
  |     |     +-- Check: unique_matches >= 2? (GATE 2)
  |     |     +-- Check: required combination satisfied? (GATE 3)
  |     |     +-- Result: 0 of 79 pages passed ALL THREE gates
  |     |
  |     +-- All 79 failed at GATE 1 ("Below min score 5.0")
  |
  +-- LLM Screening (Haiku) -- NEVER REACHED
  |     (Would screen with fast/cheap model first)
  |
  +-- LLM Analysis (Sonnet) -- NEVER REACHED
  |     (Would extract policy details, relevance score)
  |
  +-- Output to Google Sheets -- NOTHING TO OUTPUT
  |
  v
RESULT: 0 policies found. $0.00 cost. 11.7 minutes wasted.
```

### Configuration Summary

```yaml
# config/settings.yaml
crawl:
  max_depth: 3                    # Default; HB323 domain overrides to 2
  max_pages_per_domain: 100       # Hard limit per domain
  delay_seconds: 3.0              # Between requests to same domain
  timeout_seconds: 30             # Per-page fetch timeout
  force_playwright: false         # Smart detection (domain overrides to true)

analysis:
  min_keyword_score: 5.0          # Weighted score threshold (CLI: --min-keyword-score)
  min_keyword_matches: 2          # Unique keyword count minimum
  enable_two_stage: true          # Haiku screening before Sonnet
  screening_min_confidence: 5     # Haiku must rate >= 5 to proceed

# config/keywords.yaml
thresholds:
  minimum_keyword_score: 5.0
  minimum_matches: 2

stricter_requirements:
  required_combinations:
    enabled: true
    min_matches_per_category: 1
    combinations:
      - primary: "context"    secondary: "subject"       # data center + waste heat
      - primary: "context"    secondary: "policy_type"   # data center + law
      - primary: "subject"    secondary: "policy_type"   # waste heat + law
      - primary: "subject"    secondary: "incentives"    # waste heat + grant
  density:
    enabled: false              # Disabled (was too aggressive)
  boost_keywords:
    enabled: true
    boost_amount: 3.0           # Per boost keyword found
  penalty_keywords:
    enabled: true
    penalty_amount: 2.0         # Per penalty keyword found

# config/domains/us/virginia.yaml (HB323 entry)
- name: "Virginia HB323 - Data Center Heat Reuse Study"
  id: us_va_hb323_2026
  enabled: true
  base_url: "https://lis.virginia.gov"
  start_paths:
    - "/bill-details/20261/HB323"
  max_depth: 2
  requires_playwright: true
  rate_limit_seconds: 3.0
  category: "legislation"
  tags: ["pending", "study", "waste_heat", "department_of_energy", "data_center_specific"]
  policy_types: ["legislation", "waste_heat_recovery"]
```

---

## Key Design Tensions

### 1. Broad Crawling vs. Targeted Scanning

The pipeline was designed for **broad discovery**: scan a government ministry's website, follow links 3 levels deep, keyword-filter the results, and surface anything that mentions data center heat reuse. This works well on `energy.virginia.gov` or `energimyndigheten.se` where there's a lot of policy content.

But `us_va_hb323_2026` is a **targeted scan**: we already KNOW the bill exists, we're pointing directly at it. The broad-crawl mechanics (follow all links, keyword-filter everything) actively work against us here.

### 2. Keyword Filtering as Cost Control vs. Content Discovery

The keyword system's primary job is **cost control**: prevent expensive LLM calls on irrelevant pages. With 344 keywords across 7 categories and a threshold of 5.0, it's calibrated to be conservative -- better to miss a marginal page than waste $0.03 on an LLM call for a page about swimming pool schedules.

But when pointed at a known-relevant bill, this cost-control mechanism becomes a content-discovery blocker. A Virginia bill that says "data center waste heat" in exactly those words scores 4.0 (context 1.0 + subject 3.0) and gets rejected.

### 3. SPA-Aware Fetching vs. Content Extraction Assumptions

The pipeline has Playwright for rendering JavaScript SPAs -- it CAN fetch React/Vue/Angular apps. But the content extraction pipeline was designed with assumptions about traditional server-rendered HTML: semantic tags, clear content areas, standard boilerplate patterns.

React apps don't have `<article>` tags or `role="main"` attributes. They have `<div className="MuiBox-root">` nested 12 levels deep. The extraction pipeline's Phase 3 likely falls through to `<body>`, capturing the entire page including the rendered nav bar, footer, and sidebar chrome that Phase 2's patterns may not match against React's CSS class naming conventions.

### 4. Post-Crawl Filtering vs. Crawl-Time Path Scoping

URL filters apply AFTER pages are fetched, not during link discovery. This means:
- Junk pages still consume the `max_pages_per_domain` budget
- Junk pages still consume bandwidth, time, and Playwright browser sessions
- The only benefit is saving LLM API costs (which is significant for broad scans but irrelevant when 0 pages reach LLM)

The `allowed_path_patterns` template field suggests the intent to add crawl-time path scoping, but it was never implemented.

---

## Unanswered Questions

These would need investigation (likely a re-run with `--verbose` and/or content logging):

1. **What text does Playwright actually extract from the HB323 bill detail page?** Does the rendered React content include the bill title, summary, and full text? Or just navigation elements and metadata?

2. **What keyword score do the HB323 pages actually get?** Is it 4.0 (data center + waste heat), 3.0 (just subject), or even lower? A `--verbose` re-run would show this.

3. **Does the content extraction correctly identify the main content area in the React app?** Or does it fall back to `<body>` and include site chrome that dilutes keyword density?

4. **Does the boost keyword "data center waste heat" match in the bill text?** If the bill says "waste heat generated by data centers" instead of "data center waste heat", the boost doesn't fire.

5. **Are the bill TEXT pages (`/text/HB323`, `/text/HB323H1`) rendering the actual legislative text?** Or do they render a text viewer component that loads content via a separate API call that Playwright's `networkidle` might miss?

6. **Would `max_depth: 1` with `--min-keyword-score 3` be sufficient to surface HB323?** This is probably the quickest experiment to run.

---

## Appendix: Domain Config for All Virginia Entries

```yaml
# va_energy - Blocked by Cloudflare (separate issue)
- name: "Virginia Department of Energy"
  id: va_energy
  base_url: "https://www.energy.virginia.gov"
  start_paths: ["/energy-efficiency", "/renewable-energy"]
  max_depth: 2
  requires_playwright: false
  region: ["us", "us_states"]

# va_legislature - Old CGI-based LIS (legp604.exe)
- name: "Virginia General Assembly"
  id: va_legislature
  base_url: "https://lis.virginia.gov"
  start_paths:
    - "/cgi-bin/legp604.exe?ses=251&typ=bil&val=hb116"
    - "/cgi-bin/legp604.exe?ses=251&typ=bil&val=sb192"
  max_depth: 1
  requires_playwright: true
  region: ["us", "us_states"]

# us_va_hb323_2026 - New LIS React SPA (bill-details)
- name: "Virginia HB323 - Data Center Heat Reuse Study"
  id: us_va_hb323_2026
  base_url: "https://lis.virginia.gov"
  start_paths: ["/bill-details/20261/HB323"]
  max_depth: 2
  requires_playwright: true
  region: ["us", "us_states", "virginia"]
```

Note: `va_energy` and `va_legislature` do NOT have `virginia` in their region list, so `--domains virginia` only matches `us_va_hb323_2026`.
