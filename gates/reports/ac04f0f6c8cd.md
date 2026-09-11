<!-- proofmark-ship head=ac04f0f6c8cdac144d636401c554dfdcfe8cbd9e -->
# Report - OCP-CE-HR-Policy-Searcher, ocp/main..HEAD

## What shipped
- ac04f0f docs(report): end-of-work report for the licence copyright change
- fc8f07b docs(license): name the actual copyright holders

2 files changed, 28 insertions(+), 1 deletion(-)

## Test floor
2735 -> 2735  (unchanged)

## Coverage (reported fact, never a gate)
TOTAL 11319 1333 88%  measured 2026-09-11T08:00:10+00:00

## What the gates did
passes 9, bound 2, blocks 1, overrides 0, exceptions 1
    exception ship-report: skipped via PROOFMARK_SKIP_SHIP_REPORT
    block     ship-report: no report for 2 commit(s)

## Rollback
    git revert --no-edit cfe09ee71e12..HEAD

## To be written by a person - the tool cannot know these
- What you found and did NOT fix: This repo's CLAUDE.md says `git push origin main` pushes to BOTH via dual push URLs. That is no longer true - `git remote -v` shows one push URL each, `origin` to the personal mirror and `ocp` to the org. Left alone because a documentation fix does not belong in a licence PR, but a future session trusting that line will believe one push reaches both repos. CLAUDE.md also does not mention that this org enforces DCO, which is what made this third commit necessary.
- The diagnosis you got wrong first, and what corrected it: Two. (1) I reported on 2 September that the dual-push hazard was gone, then read the opposite in CLAUDE.md and briefly assumed the earlier read had been wrong; re-running `git remote -v` settled it, the doc is stale, not the check. (2) I assumed the personal mirror was far behind and would need the logged PROOFMARK_SKIP_SHIP_REPORT escape to sync; `git rev-list --left-right --count ocp/main...origin/main` returned `0 0`, so the mirror is level at cfe09ee and a tag push is a plain fast-forward. Both errors were trusting notes over the repository.
- Numbered open questions: (1) The copyright line now names Ahliana Byrd and the PolicyPulse contributors. This repo lives in the opencomputeproject org and Ahliana holds Maintain, not Admin, so whether OCP wants its own name on the MIT notice is theirs to say; PR #60 is the place to ask. (2) The four Uppsala University contributors (Valdemar Jeirud, Elliot Loewenhielm, David Fors, Alexander Stephanson) are covered by "the PolicyPulse contributors" rather than named individually - naming them is more explicit but goes stale the moment anyone else commits. (3) CLAUDE.md should gain a line saying every commit needs `git commit -s` because the org's DCO check blocks the merge without it; not done here to keep a licence PR to one concern.
- Verified live by fetching real content (not a status code)? what, and what did it say: No network content was fetched for the change itself. Three live checks against real state, not status codes: `git fetch ocp` then local `main` and `ocp/main` both at `cfe09ee` with a clean tree, so the branch is cut from current org main; `git fetch origin` then `0 0` divergence against `ocp/main`, so the mirror is level; and the DCO check-run body pulled from the GitHub API, which named both commits by sha and said "The sign-off is missing" - that is what identified the real blocker rather than the CI checks, which were green in 1m and 44s.
