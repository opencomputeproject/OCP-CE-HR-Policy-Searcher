<!-- proofmark-ship head=de2e9be51af749ae0f030b1a317b000f8a15fbda -->
# Report - OCP-CE-HR-Policy-Searcher, ocp/main..HEAD

## What shipped
- de2e9be docs(license): name the actual copyright holders

1 file changed, 1 insertion(+), 1 deletion(-)

## Test floor
2735 -> 2735  (unchanged)

## Coverage (reported fact, never a gate)
TOTAL 11319 1333 88%  measured 2026-09-11T08:12:44+00:00

## What the gates did
passes 14, bound 4, blocks 1, overrides 0, exceptions 1
    exception ship-report: skipped via PROOFMARK_SKIP_SHIP_REPORT
    block     ship-report: no report for 2 commit(s)

## Rollback
    git revert --no-edit cfe09ee71e12..HEAD

## To be written by a person - the tool cannot know these
- What you found and did NOT fix: (1) This repo's CLAUDE.md says `git push origin main` pushes to BOTH via dual push URLs; `git remote -v` shows one push URL each, `origin` to the personal mirror and `ocp` to the org, so that line is stale. (2) CLAUDE.md does not say the opencomputeproject org enforces DCO, so nothing warns a session to use `git commit -s`. Both are doc fixes outside a licence PR; both are recorded in the session's memory note so they do not bite again.
- The diagnosis you got wrong first, and what corrected it: This branch replaces PR #60, whose first two commits I made without `-s`. I then tried a DCO remediation commit, which this repo cannot accept - the probot DCO app defaults `allowRemediationCommits` to false and there is no `.github/dco.yml` in the repo or an `opencomputeproject/.github` org repo (both GitHub API lookups 404). Rebasing was ruled out by the owner, so the correct fix was to redo the one-line change on a fresh branch with every commit signed from the start. Cheaper than untangling three commits and two stale reports.
- Numbered open questions: (1) The copyright line now names Ahliana Byrd and the PolicyPulse contributors. This repo lives in the opencomputeproject org and Ahliana holds Maintain, not Admin, so whether OCP wants its own name on the MIT notice is theirs to say; the PR is the place to ask. (2) The four Uppsala University contributors (Valdemar Jeirud, Elliot Loewenhielm, David Fors, Alexander Stephanson) are covered by "the PolicyPulse contributors" rather than named individually - naming them is more explicit but goes stale the moment anyone else commits. (3) Whether to ask the OCP org admin to enable DCO remediation commits, or simply keep every commit signed - the latter is simpler.
- Verified live by fetching real content (not a status code)? what, and what did it say: No network content was fetched for the change itself. Live checks against real state: `git fetch ocp` then `main` and `ocp/main` both at `cfe09ee` with a clean tree, so this branch is cut from current org main; `git fetch origin` then `0 0` divergence against `ocp/main`, so the personal mirror is level and a tag push is a plain fast-forward; the DCO check-run body pulled from the GitHub API on PR #60 named commits fc8f07b and ac04f0f by sha and said "The sign-off is missing", which is what identified the real blocker; `git log --format=%(trailers)` on de2e9be shows `Signed-off-by: Ahliana Byrd <ahliana.byrd@gmail.com>` present.
