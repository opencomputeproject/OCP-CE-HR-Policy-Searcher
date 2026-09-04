# ADR-0010: Same instrument folds into the existing row

- Status: Accepted
- Date: 2026-09-02
- Owner: the workstream lead
- Supersedes: none

## Context

Deduplication by URL (section 8 of `docs/HOW_IT_WORKS.md`) only catches the
same link seen twice. It does nothing for the same instrument reached by
two different links, and the reviewer's review of the Staging tab, read 2
September 2026, found exactly that: three separate rows were news stories
about EnEfG (the German data-centre energy efficiency act, `Energy
Efficiency Act (EnEfG)`, kept under
`https://www.gesetze-im-internet.de/enefg/`), and one more row was a repeat
of a row already above it. None of the four needed a model to recognise -
each names the same instrument a kept row already names, in words a person
reads at a glance. Sending them through screening and analysis anyway costs
money and adds noise a reviewer then has to clear by hand.

A name-based check is inherently approximate: the same instrument is named
differently by a bill's own site, a news outlet, and a second legislation
database, and no single field reliably ties them together the way a URL
ties together the same link.

## Decision

A page or an extracted policy whose name shares a key with a policy already
kept folds into it rather than becoming a second row. Three pieces:

1. `src/core/instruments.py`'s `instrument_keys()` turns a name into a
   small set of keys: the normalised full name (lowercased, Unicode-folded,
   punctuation stripped, a trailing " - "/" – "/": " qualifier and a
   trailing parenthesised year or session removed), plus - when a trailing
   parenthetical is 3 to 12 characters and contains a letter - the
   normalised abbreviation on its own. `"Energy Efficiency Act (EnEfG)"`
   and `"Energieeffizienzgesetz (EnEfG)"` share the `"enefg"` key even
   though they share almost no other words.
2. `InstrumentIndex` maps every key to the URL of the policy that first
   registered it, seeded at scan start from every non-rejected policy
   already in the store and grown during the scan as new policies survive,
   so a second structured-source copy of one act folds into the first
   within the same scan, not just against history.
3. `DomainScanner` checks twice: a page's own title against the index
   before it would otherwise reach screening (free, before any model
   call), and each policy the analysis model extracts against the index
   after analysis, in case the extracted name reveals a match the raw
   title did not. Either way the fold is recorded as a `(existing_url,
   new_url)` pair, drained by `ScanManager` into
   `PolicyStore.add_related_url` so it survives on the kept row.

Deliberately name-key and abbreviation matching only. Matching on a
policy's `referenced_policies`/`referenced_urls` (an act's own citations)
is a different, later idea, held back because a citation graph can chain
two policies that are related without being the same instrument, and that
needs its own evaluation against real rows before it ships.

## Consequences

- A news page about a kept policy attaches to it as a `related_urls` entry
  instead of becoming its own row - a reviewer sees it as context on the
  kept policy, not as a separate item to re-judge.
- A genuinely new instrument whose abbreviation happens to collide with an
  already-kept one (two unrelated acts both abbreviated, say, "EEA") would
  be folded too, wrongly. The `"Folded into <url> (same instrument): <url>"`
  log line at INFO is what makes a wrongful fold visible to catch, the same
  way a wrongful drop at any other gate is caught today.
- The landing-page case is deliberately not affected by this decision at
  all: the link check ([above](../HOW_IT_WORKS.md#the-link-check)) and this
  fold are two different mechanisms, and neither drops a page merely for
  being short - one of the reviewer's kept rows is a bare host, and a
  length-only rule anywhere in this pipeline would have dropped it.
- No cost either way: this is name matching against an in-memory index, not
  a model call, and it runs before the screener would otherwise have looked
  at the page.

## Evidence

- Reviewer's Staging-tab review, read 2 September 2026: three rows were
  EnEfG news stories, one row was a repeat of a row already above it -
  `docs/HOW_IT_WORKS.md`, "The reviewer's vocabulary" table, "Duplicate, or
  news about a policy already kept", 4 rows.
- `Energy Efficiency Act (EnEfG)`, `https://www.gesetze-im-internet.de/enefg/`,
  is the kept row those four rows should have folded into instead of
  appearing separately.

## Guarded by

- `tests/unit/test_instruments.py` (key normalisation table, `InstrumentIndex`).
- `tests/unit/test_scanner.py::TestDomainScannerScan::test_same_instrument_duplicate_is_folded_before_screening`
  (red before this change - the page reached Sonnet analysis; green after).
- `tests/unit/test_scanner.py::TestDomainScannerScan::test_instrument_index_off_by_default_keeps_old_behavior`.
- `tests/unit/test_scanner.py::TestDomainScannerScan::test_two_policies_from_one_page_with_same_keys_fold_into_one`.
- `tests/unit/test_scanner.py::TestDomainScannerScan::test_policy_matching_an_existing_row_is_dropped_and_recorded`.
- `tests/unit/test_scanner.py::TestDomainScannerScan::test_surviving_policy_is_added_so_a_later_page_folds_into_it`.
- `tests/unit/test_store.py::TestAddRelatedUrl`.
- `tests/unit/test_scan_manager.py::TestInstrumentIndexWiring`.
