# What changed

For whoever reads the output: reviewers, visitors, the OCP workstream. Say
what changed and why it matters to them, not what the code does. Newest
first. The Proofmark gate refuses a `feat:` commit that changes source
without a line here (see `proofmark.toml`, `[proofmark.changelog]`).

<!-- proofmark:changelog -->
## Unreleased

- 2026-09-02 The admin scan panel now shows what the last measured run of
  the same scope actually cost beside the estimate, says in plain words when
  the two disagree, has a budget box prefilled with the default cap and a
  "No budget" option that asks for a second click, and after a scan lists
  what happened as sentences rather than counters.
- 2026-09-02 In the app, a non-English policy now shows a "Read in English"
  link beside its source link, opening a machine translation of the original
  page in a new tab. The original link stays the link of record.
- 2026-09-02 The first golden set exists: 120 of the reviewer's own
  decisions (32 keeps, 88 removes, each with a reason), turned into a
  labelled set the pipeline can be scored against
  (`tests/fixtures/golden/v1.jsonl`). Two documents she has since marked
  Remove came off the protected-recall floor; her 32 keeps joined it.
  Nothing a visitor sees changes today; this is the measurement the tool
  has been missing, not a change to what it finds.
- 2026-09-02 A reviewer who reads only English can now find and read a
  non-English policy without translating it by hand: searching the English
  name now finds the row, and a non-English row carries a "Read in English"
  link to a translated copy of the source page. Still one row per document,
  never one per language.
- 2026-09-02 Sheet exports now align to whatever header row the sheet
  actually has and only ever add columns at the end, so a reviewer's own
  column added to the Staging sheet is never moved, renamed, or overwritten
  by a scan.
- 2026-09-02 The reasoning behind every filter is now written down where a
  person can read it (`docs/HOW_IT_WORKS.md`), with decision records and a
  lessons register that a test keeps honest. Nothing about scan behaviour
  changed.
- 2026-09-02 The pre-scan cost estimate is now measured, not guessed: its
  token sizes and pass rates come from the first real monthly scan instead
  of unmeasured assumptions that had priced the same 402-domain scope at
  $188.46 against a $9.05 actual. The estimate now also shows the last
  completed run for the same scope alongside the fresh number, with a
  plain warning when the two disagree by more than 3x either way.
- 2026-09-02 A scan that doesn't set its own budget now stops itself at $25
  by default, instead of running uncapped - pass `no_budget: true` for an
  explicitly uncapped run. Both the API and the CLI agent report which
  budget actually applied.
- 2026-09-02 Cost projections (`GET /api/cost-projection`) now show cost
  per policy found, alongside mean and last-run cost.
- 2026-09-02 A completed scan's detail view now includes a plain-English
  summary of what happened to documents at each stage - pages fetched,
  dropped and why, screened, analysed, found.

## 2026-08-31

- Virginia bills now come from the state's own session files: every 2026
  bill in one fetch, HB 323 included.
- A document that never mentions a data centre is dropped before any model
  spend. The setting is `analysis.data_center_required`, default `required`.
- Cached verdicts expire when a rule changes, so a rule change applies to
  every page, not only new ones.
- Every source explains itself in Admin under Sources.
<!-- /proofmark:changelog -->
