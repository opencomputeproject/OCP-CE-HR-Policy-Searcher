# How PolicyPulse works, and why it filters what it filters

This page is for a person who needs to understand what the tool does to a
document between "a government published it" and "a reviewer sees it", and
why each step is there. It is also the page an AI session reads before
changing any of those steps, so that a rule which cost real review time to
learn is not quietly undone.

Companion pages:

- [`decisions/`](decisions/README.md): one record per decision, with the
  evidence that led to it. Never edited after the fact; a changed mind is a
  new record that supersedes the old one.
- [`LESSONS.md`](LESSONS.md): one entry per defect that cost time, with the
  test that now fails if it comes back.
- [`OPERATIONS.md`](OPERATIONS.md): the runbook for the server.
- [`CHANGELOG.md`](CHANGELOG.md): what changed, for whoever reads the output.

## How this page stays true

Prose alone does not hold. Three things must point at each other for a
lesson to count as recorded, and a test checks that they do:

1. **A human-readable explanation** here or in a decision record.
2. **A test that goes red if the lesson is undone**, named in `LESSONS.md`.
3. **A line in the file an AI session reads first** (`CLAUDE.md`), pointing
   at the first two.

`tests/unit/test_lessons_traceability.py` fails a commit when a lesson names
a test that does not exist, when a test cites a decision record that does not
exist, or when a link on these pages points nowhere. The Proofmark gate refuses
a `feat:` commit that changes source without a `CHANGELOG.md` entry. The pull
request template asks, on every PR, which of these pages the change touched.
That is the maintenance mechanism: not a promise to keep documents current,
but a commit that cannot land if they are not.

## The pipeline in one picture

Numbers are from the first real monthly scan, 1 September 2026 (scan
`86463134`, 402 sources, 9 hours 43 minutes, $9.05).

```
 35,402  pages fetched                                  free
  9,347  passed the keyword gate (crawled pages only)   free
  7,909  dropped by the scope gate: no data centre      free
    636  screened by the cheap model (Haiku)            $1.26
    445  analysed by the strong model (Sonnet)          $7.74
    102  policies found, before duplicate removal
     71  policies stored and appended to the sheet
```

Everything above the screening line is free and did almost all of the
cutting. The strong model took 86 percent of the money, and 285 of its 445
calls produced no policy. The cheapest improvement is never a stronger model;
it is a better question asked earlier.

## Stage by stage

Each stage says what it does, what it drops, why, the reviewed row that
justified it where one exists, where to change it, and the test that guards it.

### 1. Finding pages

Two kinds of source, called *channels*:

- **Crawl domains** (`config/domains/*.yaml`, about 380): a start URL, a page
  budget (`max_pages_per_domain`), URL filters (`config/url_filters.yaml`),
  optional Playwright for JavaScript sites. Pages are fetched and read.
- **Structured sources** (`src/sources/*.py`, listed in
  `config/domains/api_sources.yaml`, 24 of them): legislation APIs and bulk
  files (LegiScan, EUR-Lex, DIP, Folketing, Virginia LIS, and so on). Each
  returns records, not pages, and each record arrives already tagged with
  what the publisher knows about it: a bill number, a status, sometimes a
  document type.

The mapping from source type to channel: `crawl` is the crawl channel,
`eurlex_nim` is the transposition channel, everything else is `law_apis`.

Structured sources produce most of what reaches the database (about 104 of
the 143 rows the reviewer saw came from them; about 9 came from crawled
pages). That fact decides where every precision rule has to sit; see
[ADR-0002](decisions/ADR-0002-structured-sources-bypass-the-keyword-gate.md).

**Document types at the source.** DIP and Folketing both tag every record
with the publisher's own document-type field, and both now check it before
returning anything: `source_params.document_types` in
`config/domains/api_sources.yaml` is an allow-list, defaulting to
`DEFAULT_DOCUMENT_TYPES` (`Gesetzgebung`, `Rechtsverordnung`, `Verordnung`,
`Antrag`) in `src/sources/dip_bundestag.py` for DIP's `vorgangstyp`, and to
`DEFAULT_DOCUMENT_TYPE_IDS` (`[3, 5, 9]`, Lovforslag, Beslutningsforslag,
Forslag til vedtagelse) in `src/sources/folketing.py` for Folketing's
`typeid`. A record whose type is not on the list is dropped before any page
is fetched or any model is called, and counted as `filtered_doc_type` on
the domain's progress rather than folded into a total that would hide it.
Both sources also now cite the underlying document (a PDF where one is
found) instead of the case-overview page, falling back to the overview page
only when no document URL resolves.

### 2. Extracting text

HTML and PDF become plain text (`src/core/extractor.py`). A page under fifty
words is skipped for crawled pages only; structured records are often short
by nature and go through.

#### The link check

Before that short-content check, `src/core/soft404.py` asks whether a
crawled page is a soft 404: a missing-page placeholder answered with an
HTTP 200, so nothing upstream ever sees an error to catch. When the
extracted text is under 400 words, a title or the first 300 characters
matching a pattern from a table covering nine languages ("page not found",
"Seite nicht gefunden", "ページが見つかりません", and others), or a bare
"404" / "Not Found" / "Error" title on a page under thirty words, drops the
page before any model call and counts it as `filtered_link`. It never fires
on a long page, even one that happens to contain the word "404" somewhere.
Structured records are API records, never pages, so they skip this
entirely, the same way they skip the keyword gate. Costs nothing: it runs
on already-extracted text, before the cache check and before either model
call.

Deliberately narrow: a genuine landing page can be just as short as a soft
404, so the signals require an actual not-found phrase, or a bare
error-shaped title, rather than short length alone - one of her kept rows
is a bare host, and a length-only rule would have dropped it.

Why: the reviewer's rows, read 2 September 2026 - "not a real website" and
"link is an error page" among the 39 rows grouped below as "Link is a
general site, an error page, not the document". Guarded by
`tests/unit/test_soft404.py` and the wiring tests in
`tests/unit/test_scanner.py`.

### 3. The keyword gate (crawled pages only)

`config/keywords.yaml` holds weighted term categories in twenty languages.
A page scores by the terms it contains; below the threshold it is dropped
and counted as `filtered_keywords`. Near misses are logged so the list can be
tuned. Admins add, remove and restore terms and adjust thresholds in the
Keywords panel (`PUT /api/keywords/overrides`).

**Structured sources skip this gate entirely.** They are marked relevant
unconditionally, because a bill returned by a legislation search already
matched a query. On 1 September the keyword gate dropped 15,578 pages and
saw none of the 25 LegiScan bills.

### 4. The cache, and why verdicts expire

`src/core/cache.py` remembers a verdict per URL and content hash, so a page
that has not changed is not analysed twice. Every entry also carries a
**rules fingerprint** (`src/core/rules_version.py`), a hash of the keyword
list, the scope setting and both prompts. When any rule changes, every
verdict written under the old rules is treated as stale and the page is
re-judged. Without this, a rule change would apply only to pages nobody had
seen before, and a reviewer would conclude the change did nothing.

Guarded by `tests/unit/test_rules_version.py`.

### 5. The scope gate: no data centre, no row

`src/core/scope.py`, setting `analysis.data_center_required` in
`config/settings.yaml`, default `required`. A document whose text never
mentions a data centre, in any of about twenty languages and any spelling
(center, centre, data-center, Rechenzentrum, datacenter), is dropped before
any model call and counted as `filtered_out_of_scope`.

Why: the reviewer's rule, 2026-08-28. Thermal energy network bills that
never mention a data centre are not what the tool is for. Her review of the
first 143 rows removed 14 for exactly this reason (rows 13, 14, 15, 18, 23,
28, 30, 31, 52, 100, 103, 104, 105, 129 of the Staging tab).

**The gate reads source text, never a stored summary.** The analysis model
writes summaries in English and, for bills adjacent to the subject, writes
"data centers" into summaries of bills that never say it. NJ A4490's stored
summary reads "could incorporate waste heat sources including data centers";
the bill does not. A rule evaluated on summaries silently stops working.
This is [lesson PL-001](LESSONS.md#pl-001) and
[ADR-0001](decisions/ADR-0001-scope-requires-a-data-centre-on-source-text.md).

The same setting generates the scope sentence in the screening prompt, so the
gate and the model cannot be told different things.

Where it sits: after the cache check, where the crawl and structured lanes
have rejoined, and before the screener. Guarded by
`tests/unit/test_scope.py` (the rule, the settings, and the placement).

### 6. The cheap screener

`SCREENING_PROMPT` in `src/core/llm.py`, model
`analysis.screening_model` (Haiku). One question today: is this page
plausibly government policy touching data-centre heat reuse? It is written
recall-first: "when in doubt, keep it". A rejection only sticks when the
screener's confidence is at least `screening_min_confidence`; below that the
page escalates to the strong model.

Measured 1 September: 636 screened, 445 passed (70 percent), and the strong
model then found nothing in 285 of those 445. One Pennsylvania domain
(`pa_dep`) passed 199 pages through screening and produced zero rows.

Planned change (work package WP-5 in the September plan): three narrow
questions instead of one wide one. What kind of document is this, from a
fixed list (act, bill, regulation, consultation, grant, plan, index, report,
article, speech, question)? Quote the sentence that names a data centre.
Quote the sentence about reusing or recovering heat. A report or an article
stops there; under `required`, no data-centre quote stops there. The quotes
are stored so a reviewer can see why a row exists. Same model, same price.
See [ADR-0003](decisions/ADR-0003-recall-first-screening.md).

### 7. The strong model

`ANALYSIS_PROMPT` in `src/core/llm.py`, model `analysis.analysis_model`
(Sonnet). Extracts the policy name in the original language, an English
name, an English summary, jurisdiction, type, dates, key requirements,
referenced legislation and a lifecycle stage. Index pages can yield several
policies. Measured 1 September: 3,129 input tokens per call on average,
against the 20,000 the cost estimator assumed (see
[lesson PL-004](LESSONS.md#pl-004)).

### 8. Verification, deduplication, storage

The deterministic verifier (`src/core/verifier.py`) raises specific flags
(for example `jurisdiction_mismatch`) that a reviewer can check; flags never
reject. Rows are deduplicated by URL against the database and against the
sheet's Link column. Everything is stored in `data/policypulse.db`, and each
domain's finds are appended to the Staging tab as the domain completes, so a
crash mid-scan loses nothing already found.

#### Same instrument, one row

Deduplication by URL only catches the same link seen twice. It does not
catch the same instrument reached by two different links - a news story
about a policy already kept, a second structured-source copy of one act.
`src/core/instruments.py` turns a policy name into a small set of keys (the
normalised full name, plus a parenthesised abbreviation like "EnEfG" when
one is present) and `InstrumentIndex` looks a page's own title, and
separately every policy the analysis model extracts from it, up against
every policy already kept. A match folds the new page in instead of
creating a second row: a title match before screening is counted as
`filtered_duplicate` and dropped outright, for free; a policy that matches
an existing row after analysis is dropped from the batch instead of stored.
Either way the fold is recorded on the kept row's `related_urls`
(`PolicyStore.add_related_url`), so a reviewer can see what folded into it.
Costs nothing: name matching, no model call, and it runs before the
screener would otherwise have been asked to look at the page at all.

Why: the reviewer's rows, read 2 September 2026 - three news stories about
EnEfG (the German data-centre energy efficiency act, kept under
`https://www.gesetze-im-internet.de/enefg/`) and one repeat of a row
already above it, grouped below as "Duplicate, or news about a policy
already kept".

Deliberately name-key and abbreviation matching only for now; matching on
referenced/cited legislation is a separate, later idea. See
[ADR-0010](decisions/ADR-0010-same-instrument-folds-into-the-existing-row.md).
A genuinely new instrument whose abbreviation happens to collide with an
existing one would be folded too, wrongly - the "Folded into `<url>`" log
line at INFO is what makes that visible to catch.

### 9. Review

The reviewer works in the Google Sheet, not the app. The sheet of record is
"Heat Reuse Policies Database" (Google Sheets id
`1Az2Pz14eAGhre68BWmrpegg1PJ27decO0HRClKejJE8`), Staging tab. Column AC,
headed *Review (Is website trustworthy? Is the policy focused on data center
heat reuse explicitly? Is it duplicative? Is it actually a policy? Are
proposed and enacted policies differentiated?)*, is the review record: a
verdict word, a hyphen, a reason, in her words.

The writer aligns every export to the sheet's actual header row and never
overwrites a column it did not create, so her column - or any other reviewer
addition to the header row - is safe across scans, wherever it sits
([ADR-0009](decisions/ADR-0009-one-row-per-document-both-languages.md)).

Review states in the app are `new`, `reviewed`, `promoted`, `rejected`. Who
sees which is set by the public visibility posture; see
[Who sees unreviewed records](../README.md#who-sees-unreviewed-records).
Reading her column into the app is
[ADR-0005](decisions/ADR-0005-the-reviewers-column-is-the-review-record.md),
proposed.

## The reviewer's vocabulary, and which gate answers each reason

From her review of 143 rows on the Staging tab, read 2 September 2026: 32
keep, 88 remove, 14 to be decided (10 of them "only in Dutch"), 9 blank. Her
88 reasons, grouped, with the earliest and cheapest point that can act on
each:

| Her reason | Rows | Where it can be caught | Cost | State |
|---|---|---|---|---|
| Not a policy: parliamentary question, written answer, transcript | 46 | At the source. DIP and Folketing already send a document-type field; Kokkai is Diet speeches by design | free | built, WP-3 |
| Link is a general site, an error page, not the document | 39 | At the source (emit the document URL) and a fetch check before screening | free | built, WP-3 (source) and WP-4 (fetch check) |
| No data centre in the bill | 14 | The scope gate, on source text | free | built |
| Not a policy: report, article, opinion, private initiative | 12 | The screener's document-kind question | about $0.002 per page | planned, WP-5 |
| Data centre present, no heat-reuse substance | 6 | The screener's quote question | about $0.002 per page | planned, WP-5 |
| Duplicate, or news about a policy already kept | 4 | Same-instrument check against kept rows | free | built, WP-4 |
| Only in Dutch (to be decided, not removed) | 10 | English title backfill, translated-page link | cents | built, not applied |
| No reason given | 4 | A fixed reason list in the sheet, so the next round can be counted | free | planned, WP-2 |

Rows carry two reasons where she gave two, so the column does not sum to 88.
The full mapping, row by row, is in the working document "What Anna's
Column Teaches" (2 September 2026).

## How sources are found and added

- **Discover mode**: `python -m src.agent --discover Poland` web-searches for
  government sites for a place, drafts domain configs, and adds them. Every
  draft starts `enabled: false`; a person turns it on.
- **The source catalog** (strategy documents outside this repo) ranks
  candidates. A catalog entry is a hypothesis until probed.
- **The source-build doctrine**, learned the hard way across 24 structured
  sources:
  1. Live re-probe the day you build; endpoints drift.
  2. **HTTP 200 means nothing.** Assert the content type first, then that a
     nonsense query returns zero, then that `total("A B") < total("A")` and
     `total("nonsense A") != total("A")`, to catch search endpoints that
     OR their terms or drop tokens. Then read the hits. Seven trap classes
     have been confirmed: silent no-op filters, single-page-app shells,
     soft-404s, byte-identical error pages, ignored format directives,
     firewalls that answer instead of refusing, and token-dropping OR-search
     that passes the nonsense test.
  3. Measure term yields in the native language; broad stems beat domain
     phrases in inflected languages, and wildcard semantics differ per
     engine.
  4. Tests first.
  5. Claim lifecycle stages conservatively: finished is not adopted.
  6. Wire the source everywhere: the registry in `src/sources/__init__.py`,
     `config/domains/api_sources.yaml`, a jurisdiction row in
     `config/jurisdictions.yaml` (`test_every_domain_slug_resolves` fails CI
     without it), the example env, the catalog.
  7. Smoke-test end to end before committing.
- **Bulk files beat per-record crawling** where a legislature publishes them.
  Virginia's session CSVs give 3,646 bills in one keyless fetch; per-bill
  Playwright crawling never fetched HB 323 at all. See
  [ADR-0004](decisions/ADR-0004-virginia-from-the-lis-session-files.md) and
  [lesson PL-002](LESSONS.md#pl-002) on the two files disagreeing about the
  same bill number.
- Every source explains itself: `explain()` on a source returns a sentence an
  administrator can read, shown in Admin under Sources.

## How scans run, and what they cost

- **The in-app schedule** ("Monthly full scan", 1st of the month, 06:00 UTC,
  ceiling $50) is the owner of the monthly run; it records the estimate and
  the actual. Admin, Schedules, has **Run now**. The proposal to make it the
  only trigger is [ADR-0006](decisions/ADR-0006-one-monthly-trigger.md).
- **By hand, scoped**: pick a group in the scanner panel (`us`, `us_federal`,
  `us_states`, `eu`, `nordic`, and the rest of `config/groups.yaml`), tick the
  channels, read the estimate, start. Or on the server:
  `docker compose exec -T policypulse python -m src.agent "Scan the us_states group"`.
  Or `POST /api/scans` with `domains`, `channels` and `deep`.
- **The estimate** (`ScanManager.estimate_cost`, defaults in
  `config/pricing.yaml`) multiplies assumptions; once two scans have
  completed it prefers measured rates. On 1 September it said $188.46 and
  the scan cost $9.05, because two assumptions were off in the same
  direction, and a third stage - the scope gate - was not modeled at all.
  The static defaults now come from that same scan (measured, not guessed):
  token sizes per call, and pass rates for the keyword gate (26%), the
  scope gate (15% of keyword-gate passes), and screening (70%). See
  [lesson PL-004](LESSONS.md#pl-004) and
  [ADR-0008](decisions/ADR-0008-every-scan-has-a-budget-by-default.md).
- **The last actual, beside the estimate.** Every estimate also carries
  `last_actual` - the most recently completed run for the same scope, when
  one exists - and `warnings`: a plain sentence when the fresh estimate
  disagrees with that actual by more than 3x either way ("the measured
  number is usually the better guide"), and one whenever a scan started
  from this estimate will stop itself at the default budget. The CLI agent
  prints both under the dollar figure it already shows before a scan
  starts.
- **Every scan has a budget by default.** `analysis.default_scan_budget_usd`
  (`config/settings.yaml`, $25) applies to any scan whose request omits
  `budget_usd` - the same running-cost stop `start_scan` already had
  (WP-22b), just filled in by default instead of left uncapped. Pass
  `no_budget: true` for one deliberately uncapped run, or set the setting
  to `0` to turn the default off everywhere. `POST /api/scans` and the
  agent's `start_scan` tool both apply it and report the `budget_usd` that
  actually applied. Schedules are unaffected - they keep their own ceiling.
  See [ADR-0008](decisions/ADR-0008-every-scan-has-a-budget-by-default.md).
- **Cost per stored policy** on 1 September: $0.13. At the reviewer's 27
  percent keep rate, about $0.47 per kept policy.
  `ScanHistoryStore.stats()` now tracks this per scope over time too -
  `cost_per_policy_usd` (total completed cost over total completed
  policies) and `last_cost_per_policy_usd`, both shown in
  `GET /api/cost-projection`.

## Assumptions

What has to be true for the output to mean what it appears to mean.

**Sources**

- Official government endpoints only. Restrictively-licensed commercial
  legislation databases are deliberately excluded from republication.
- 400+ sources across 40+ countries, 24 of them structured legislation
  sources queried directly. Coverage is uneven by design; see
  [Geographic Coverage](../README.md#geographic-coverage).

**Screening**

- **Recall-first.** The pipeline deliberately over-collects at the screener.
  Policies that merely *affect* heat reuse (district heating mandates,
  building codes, EED transpositions, permitting rules) are kept, not only
  pages that name data centres. Low-confidence rejections escalate to the
  stronger model.
- The scope rule requires a data centre reference in the source text. A
  small protected list of known-good policies is checked by name after every
  change so a rule cannot drop them quietly.

**Language**

- 20 languages. Eleven of them (German, Dutch, Swedish, Danish, Norwegian,
  Finnish, Icelandic, Hungarian, Japanese, Korean, Arabic) match on substrings
  rather than word boundaries, to handle compound words and scripts without
  word separators. That raises false positives in those languages.
- Every row keeps its original-language name and its original link, an
  English summary written by the analysis model, and an optional English
  name (`policy_name_en`) filled by the analysis model or by
  `python -m src.output.backfill_english`. One row per document, never one
  per language. Free-text search matches the English name as well as the
  original-language one, and a source that is not in English gets a
  computed "Read in English" link (Google's website-translator proxy,
  never fetched or stored by this tool) alongside it. See
  [ADR-0009](decisions/ADR-0009-one-row-per-document-both-languages.md).

**Retrieval**

- JavaScript-rendered pages return a keyword score of 0.0 unless Playwright
  is enabled for that domain. This is a silent miss, not an error.

**Human review**

- Nothing is promoted without a person. The tool proposes; curators decide.

**Measurement**

- Precision and recall are **not yet measured in the deployed tool**: the
  evaluation harness lives in `src/eval/`, but nothing has scored a live scan
  against it yet. What changed on 2 September 2026 (work package WP-1): the
  golden set now exists, built from the reviewer's own column
  (`tests/fixtures/golden/v1.jsonl`, 120 decided rows, her 32 keeps and 88
  removes, each reject carrying a reason category; her 13 to-be-decided rows,
  9 blank cells and 1 unreachable link are counted but not labelled, since
  none of those is yet a decision). Rebuild it from the live sheet with
  `python -m src.eval.golden --from-sheet --out data/golden/v1.jsonl` once
  production points at the sheet of record rather than the copy (see
  [ADR-0005](decisions/ADR-0005-the-reviewers-column-is-the-review-record.md)),
  or from a fresh CSV export with `--from-csv PATH`. Score the live store
  against a golden set with `python -m src.eval.score`, or against the
  committed one with `python -m src.eval.score --golden-dir
  tests/fixtures/golden`. Until a scan has been scored this way, treat any
  quality claim about this tool as unquantified.

## Reading the output

### What a record means, by stage

| Stage | What it means |
|-------|---------------|
| Discovered | A crawler or legislation source returned this URL |
| Scored | Keyword matching put it above the relevance threshold (crawled pages only) |
| In scope | The source text mentions a data centre |
| Extracted | The model parsed a policy name, jurisdiction, dates and summary from the page |
| Flagged | The deterministic verifier raised a specific, checkable concern |
| `reviewed` / `promoted` | A human read it and kept it |
| Exported | It reached the Staging worksheet |

### What the score is

An ordering heuristic for reviewer attention. It is **not** a probability
that a document is relevant, and not a confidence measure. The formula and
threshold are under [Scoring](../README.md#scoring) in the README. A higher
score means more and better-weighted keyword evidence was found on the page.
Nothing more. On the reviewer's first 120 decided rows, keeps and removals
were spread across the same score range, 4 to 9, so the score does not
separate them.

### What the verification flags are for

See [Verification Flags](../README.md#verification-flags). Each flag marks a
record that survived extraction but looks wrong in one specific way. They
are prompts for a reviewer, not rejections.

### What this tool does not tell you

- **Not a compliance determination.** A record is not a statement that a
  policy applies to you.
- **Not legal advice.**
- **Not exhaustive.** The absence of a policy from the results is not
  evidence that none exists.
- **Machine-extracted.** A model parsed the structured fields. Follow the
  source URL before relying on any date, threshold or obligation.

### Known gaps

- Reviewer rejection reasons are free text, so review rounds cannot be
  counted without reading every cell (work package WP-2).

## Glossary

- **ADR**, architecture decision record: one file per decision, with context,
  the decision, and its consequences. Not edited later; superseded instead.
- **Lesson**: a defect that cost time, recorded with the test that now
  catches it. The register is `LESSONS.md`.
- **Golden set**: a fixed list of documents with human verdicts, used to
  measure precision and recall before and after a change.
- **Protected recall**: a short list of documents the tool must keep
  finding; a change that loses one fails.
- **Rules fingerprint**: a hash of the rules in force when a verdict was
  cached, so changing a rule expires the verdict.
- **Precision**: of what the tool kept, the share a reviewer also kept.
  **Recall**: of what a reviewer would keep, the share the tool found.
- **Channel**: which kind of source a document came from (`crawl`,
  `law_apis`, `transposition`).
