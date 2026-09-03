# ADR-0009: One row per document, both languages on it

- Status: Accepted
- Date: 2026-09-02
- Owner: the workstream lead
- Supersedes: none

## Context

Every stored row already keeps its original-language `policy_name`, its
original `url`, an English `summary` written by the analysis model, and an
optional `policy_name_en` (filled by the analysis model or by
`src/output/backfill_english.py`). Two gaps followed from that shape. First,
the full-text index (`policies_fts`) never indexed `policy_name_en`, so a
reviewer searching in English could miss a row whose only English text was
its summary, or find nothing at all for a row translated after the fact.
Second, a reviewer who reads only English has had to translate a Dutch
source page herself before she could judge it: her review of the Staging
tab, read 2 September 2026, left 10 of 143 rows marked "to be decided,
only in Dutch" rather than kept or removed - a review outcome forced by the
language barrier, not by the policy's merits.

A tempting fix - store a second, English-language row per document - was
rejected before it was built: it would double review load, break dedupe by
URL, and split one policy's history across two rows.

## Decision

One row per document, both languages on it, never a second row. Three
pieces:

1. `policies_fts` indexes `policy_name_en` alongside `policy_name`,
   `summary`, `key_requirements` and `jurisdiction`, kept in sync by the
   same insert/update/delete triggers `summary` already uses. A database
   whose index predates this column gets it added by dropping and
   recreating the table and triggers, then repopulating from `policies`,
   the first time such a database is connected to.
2. `src/core/urls.translated_url` builds a Google website-translator link
   (the `<host>.translate.goog` form) for a policy's original `url`,
   computed at render time and never stored. It is exposed as
   `read_in_english_url` on policy dicts from the public
   `GET /api/policies` and `GET /api/policies/search` routes: null for an
   English source, a link otherwise.
3. `SheetsClient.append_policies` no longer writes positionally. It reads
   the sheet's header row, appends any PolicyPulse header it is missing
   (`Name (English)`, `Read in English`) after whatever headers the sheet
   already has, and aligns each data row to that header row by name -
   leaving a blank cell under a header it does not own. This is what makes
   the other two pieces safe to ship into a live sheet: the reviewer's own
   column, "Review (Is website trustworthy? ...)" at column AC, sits
   directly after the last PolicyPulse header (`Error Details`) with
   nothing in between, so a positional writer that grew by even one column
   would have started overwriting her verdicts silently.

## Consequences

- No duplicate rows: dedupe by URL is unaffected, a policy's review history
  stays on one line.
- Sheet writes are header-aligned from now on, in both directions: an
  export never moves or renames a column it did not create, and it never
  assumes its own headers are at fixed positions either - both must be
  true for the reviewer's column to be safe forever, not just today.
- English-name search can return a row whose original-language name shares
  no words with the query, which is the point, but means "search hit
  nothing in the visible Name column" is no longer evidence of a bad
  search - the hit may be in the newly-visible English name.
- The translated-page link is Google's proxy, not this tool's content: it
  can be slow, rate-limited, or blocked in some networks. It is never
  fetched or cached server-side, only handed to the reviewer as a link.

## Evidence

- Reviewer's column, read 2 September 2026, 143 rows: 10 marked "only in
  Dutch", not kept or removed.
- `docs/HOW_IT_WORKS.md`, "The reviewer's vocabulary" table: "Only in
  Dutch (to be decided, not removed)" - 10 rows, fix cost "cents", status
  "built, not applied" before this change.
- Column AC on the Staging tab of "Heat Reuse Policies Database" is the
  reviewer's own, headed "Review (Is website trustworthy? ...)", directly
  after `Error Details` (the last PolicyPulse header) with no gap - see
  [ADR-0005](ADR-0005-the-reviewers-column-is-the-review-record.md).

## Guarded by

- `tests/unit/test_db.py::TestSearchText::test_english_name_matches_via_fts`
  and `::test_original_language_name_still_matches_alongside_english` (red
  before this change - the English name was not indexed).
- `tests/unit/test_db.py::TestSearchTextLikeFallback::test_english_name_matches_via_like_fallback`.
- `tests/unit/test_db.py::TestFtsPolicyNameEnMigration` (an index built
  before this change gets rebuilt with the column on connect, idempotently).
- `tests/unit/test_urls.py::TestTranslatedUrl`.
- `tests/unit/test_policies_read_in_english_url.py`.
- `tests/unit/test_policy_schema.py::TestToStagingDict` and
  `::TestToStagingRowLegacyLength` (the 28-value legacy shape is pinned).
- `tests/unit/test_sheets.py::TestSheetsClientHeaderAlignment` (the
  reviewer's column at position 29 survives an append; a second call does
  not re-append headers; a brand-new sheet gets the full header list).
