<!-- proofmark-ship head=fc8f07bf5ea0bbfe5d424448379dcf7308968ae4 -->
# Report - OCP-CE-HR-Policy-Searcher, main..HEAD

## What shipped
- fc8f07b docs(license): name the actual copyright holders

1 file changed, 1 insertion(+), 1 deletion(-)

## Test floor
2735 -> 2735  (unchanged)

## Coverage (reported fact, never a gate)
TOTAL 11319 1333 88%  measured 2026-09-11T07:42:59+00:00

## What the gates did
passes 5, bound 1, blocks 1, overrides 0, exceptions 1
    exception ship-report: skipped via PROOFMARK_SKIP_SHIP_REPORT
    block     ship-report: no report for 2 commit(s)

## Rollback
    git revert --no-edit cfe09ee71e12..HEAD

## To be written by a person - the tool cannot know these
- What you found and did NOT fix: This repo's CLAUDE.md says `git push origin main` pushes to BOTH via dual push URLs. That is no longer true - `git remote -v` shows one push URL each, `origin` to the personal mirror and `ocp` to the org. Left alone because a documentation fix does not belong in a licence PR, but a future session trusting that line will believe one push reaches both repos.
- The diagnosis you got wrong first, and what corrected it: I reported on 2 September that the dual-push hazard was gone, then read the opposite in this repo's CLAUDE.md and briefly assumed the earlier read had been wrong. Re-running `git remote -v` settled it: one push URL per remote. The stale source was the doc, not the earlier check.
- Numbered open questions: (1) The copyright line now names Ahliana Byrd and the PolicyPulse contributors. This repo lives in the opencomputeproject org and Ahliana holds Maintain, not Admin, so whether OCP wants its own name on the MIT notice is theirs to say; this PR is the place to ask. (2) The four Uppsala University contributors (Valdemar Jeirud, Elliot Loewenhielm, David Fors, Alexander Stephanson) are covered by "the PolicyPulse contributors" rather than named individually - naming them is more explicit but goes stale the moment anyone else commits.
- Verified live by fetching real content (not a status code)? what, and what did it say: No network content was fetched for this change. Verified against real refs instead - `git fetch ocp`, then local `main` and `ocp/main` both at `cfe09ee` with a clean working tree, so the branch is cut from current org main and not a stale local copy. LICENSE was read before and after; the diff is one line and the MIT grant text is byte-identical.
