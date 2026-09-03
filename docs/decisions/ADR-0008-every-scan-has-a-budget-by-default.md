# ADR-0008: Every scan has a budget by default

- Status: Accepted
- Date: 2026-09-02
- Owner: the workstream lead
- Supersedes: none

## Context

The estimator priced the 402-domain `all` scope at $188.46 before the first
real monthly scan ran. The actual, scan `86463134` on 1 September 2026, cost
$9.05 - twenty times less, because two of the estimator's assumptions had
never been measured against a real run (lesson PL-004). A person deciding
whether to start a scan, or whether to let a schedule keep running one, had
only that unmeasured number to go on, and no cap stopped a scan that turned
out to cost far more than expected. The owner's instruction: protect users
from a cost overrun, not just report one after it happens.

Fixing the estimator's static defaults (this same work package, pieces 1
and 2) narrows the gap between estimate and actual, but a formula built from
assumptions - however recently measured - can still be wrong for a scope
nobody has run before, or after a source or a prompt changes what a page
costs to process. An estimate is a guess with a currency symbol on it; it
should never be the only thing standing between a mistake and a bill.

## Decision

Two changes, independent but complementary:

1. **Show the measured number next to the guess.** `ScanManager.estimate_cost`
   returns `last_actual` - the most recent completed run for the same scope,
   from `ScanHistoryStore.last_completed` - and `warnings`, plain sentences
   that fire when the fresh estimate disagrees with that actual by more than
   3x either way. The CLI agent prints both under the estimate it already
   shows before a scan starts.
2. **Cap every scan unless told not to.** `analysis.default_scan_budget_usd`
   (`config/settings.yaml`, $25) applies to a scan whose request omits
   `budget_usd`, using the running-cost stop `ScanManager.start_scan` already
   had (WP-22b) - this only decides what value fills that parameter when the
   caller doesn't. `POST /api/scans` and the agent's `start_scan` tool both
   apply it the same way, and both report the `budget_usd` that actually
   applied. `no_budget: true` on a request opts out for one explicitly
   uncapped run; setting the default to `0` disables it everywhere.

Schedules keep their own ceiling (`schedule_runner.py`) untouched - it
already caps a monthly run and predates this change.

## Consequences

- A scan started without thinking about cost stops itself at $25 instead of
  running to completion at whatever the estimate undersold. The real
  402-domain scan cost $9.05, so $25 leaves headroom for a bigger scope
  while still catching a genuine runaway.
- An admin who wants a large uncapped run must say so explicitly
  (`no_budget: true`), a small deliberate friction in exchange for the
  default no longer being "unlimited."
- The estimate shown before a scan now carries its own doubt: when it and
  the last real run disagree sharply, the warning says so in plain words
  instead of leaving a person to trust two decimal places that were never
  measured.
- One more setting to know about (`default_scan_budget_usd`), documented in
  `config/settings.yaml` and `docs/HOW_IT_WORKS.md`.

## Evidence

- Scan `86463134`, 1 September 2026: 402 domains, $9.05 actual against a
  $188.46 pre-scan estimate.
- `docs/LESSONS.md`, PL-004.

## Guarded by

- `tests/unit/test_scan_manager.py::TestEstimateDefaults::test_estimate_for_all_is_in_the_decade_of_the_last_actual`
- `tests/unit/test_scan_manager.py::TestEstimateLastActualAndWarnings::test_last_actual_is_present_after_one_completed_run_and_absent_with_none`
- `tests/unit/test_scan_manager.py::TestEstimateLastActualAndWarnings::test_a_warning_names_the_ratio_when_estimate_and_actual_disagree`
- `tests/unit/test_scan_manager.py::TestEstimateLastActualAndWarnings::test_no_warning_when_they_agree`
- `tests/unit/test_api.py::TestScanRoutes::test_default_budget_applies_when_omitted_and_not_when_no_budget_is_set`
