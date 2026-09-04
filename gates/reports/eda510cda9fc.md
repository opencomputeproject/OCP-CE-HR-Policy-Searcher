<!-- proofmark-ship head=eda510cda9fc87bc4d208232cb70ae911c783a52 -->
# Report - OCP-CE-HR-Policy-Searcher, ocp/main..HEAD

## What shipped
- eda510c docs(report): end-of-work report for the test hermeticity fix
- 100003a fix(tests): keep the project .env out of every test, whatever imports it

6 files changed, 122 insertions(+), 4 deletions(-)

## Test floor
2687 -> 2689  (ratcheted)

## Coverage (reported fact, never a gate)
TOTAL 11224 1351 88%  measured 2026-09-04T04:12:08+00:00

## What the gates did
passes 0, bound 0, blocks 0, overrides 2, exceptions 0
    override  post-commit: 100003a0579d landed without matching gate evidence (--no-verify, or the tree changed after the gate ran: TOCTO
    override  post-commit: eda510cda9fc landed without matching gate evidence (--no-verify, or the tree changed after the gate ran: TOCTO
  NOTE: an override means a commit landed without matching gate evidence. Say so in the report rather than letting it sit in the ledger.

## Rollback
    git revert --no-edit 7500aaa02314..HEAD
    # then restore gates/min_test_count.txt to 2687; the floor does not fall on its own

## To be written by a person - the tool cannot know these
- What you found and did NOT fix: src/api/app.py still calls load_dotenv(override=True) at import time, which is what made the leak possible; left as is because the deployed container relies on env_file and local development relies on this line. The test harness now blocks the leak instead. Rebased onto the current main after the branch below it was squash-merged, so every commit id changed and this report replaces the one written for the pre-rebase commits; the findings are unchanged.
- The diagnosis you got wrong first, and what corrected it: I first assumed the conftest fixture did not exist and planned to add one; reading conftest showed it already cleared ADMIN_TOKEN, and the real cause was import-time re-injection after the clearing. A second miss: neutralising the loader broke two tests that deliberately exercise dotenv's real override semantics; they now call dotenv.main.load_dotenv directly.
- Numbered open questions: 1. Should src.api.app stop loading .env at import in favour of an explicit startup call, so test hermeticity does not depend on a fixture? 2. Should the ambient-variable list in conftest gain ANTHROPIC_API_KEY?
- Verified live by fetching real content (not a status code)? what, and what did it say: Not applicable to a test-harness change; verified by the original symptom instead: `pytest tests/unit/test_api.py -k budget` run alone now passes 5 of 5 where it failed 1 before, and the new guard test writes a .env with a secret, calls the loader and finds nothing in the environment.
