<!-- proofmark-ship head=ccaf66a0fe71d663b8d4018b7121f349d9e93b85 -->
# Report - agent-a764021192efb5c22, ocp/main..HEAD

## What shipped
- ccaf66a chore(deps): patch 12 dependabot alerts via frontend overrides

2 files changed, 44 insertions(+), 33 deletions(-)

## Test floor
2394 -> 2394  (unchanged)

## Coverage (reported fact, never a gate)
never measured in this clone - run `gate.py coverage` (reported fact, blocks nothing)

## What the gates did
passes 1, bound 1, blocks 0, overrides 0, exceptions 0

## Rollback
    git revert --no-edit 2cbc145d9260..HEAD

## To be written by a person - the tool cannot know these
- What you found and did NOT fix: the 6 webpack-dev-server moderate alerts (react-scripts 5.0.1 pins webpack-dev-server ^4.6.0; the patch is 5.2.6, `npm view webpack-dev-server versions` shows no patched 4.x release exists, and CRA does not support the 5.x line) - reported, not fixed, same call PR #14 made for the prior two CRA dev-server advisories. Also left alone: the top-level postcss-selector-parser 6.1.2 instance (required as ^6.x by roughly 20 other postcss plugins in the tree; outside Dependabot's open 7.1.0-7.1.3 alert range, so out of scope and a major-bump risk to touch). `npm audit` additionally flags qs/body-parser/express (one shared `qs` chain) and browserslist as vulnerable, but none of those four had an open Dependabot alert (`gh api .../dependabot/alerts` scoped to those names returns exactly one `qs` alert, state `fixed`, and zero rows for the other three) - left untouched as outside the task's actual scope, the 18 open Dependabot alerts.
- The diagnosis you got wrong first, and what corrected it: the first post-bump run of `CI=true npx react-scripts test --watchAll=false` printed "No tests found" (0/103 files matched testMatch) and looked like the override bump had broken test discovery. It is a pre-existing Jest-on-Windows bug, unrelated to the dependency change: jest-util's replacePathSepForGlob (`path.replace(/\\(?![{}()+?.^$])/g, '/')`) preserves the backslash immediately before this worktree's `.claude` path segment, producing a mixed-separator glob that matches nothing. Corrected by running the identical command against a clean-path scratch copy of the pre-change tree (under the session scratchpad, no dot-segment in the path) - 42 suites / 531 tests passed there - then getting the same 531/531 on the post-change tree via a small in-process Jest invocation that substitutes a relative, backslash-free testMatch pattern.
- Numbered open questions:
    1. Do we want a tracked follow-up for the CRA-to-Vite migration that would let the remaining 6 webpack-dev-server alerts actually close, or keep accepting them per-PR indefinitely?
    2. Should the qs/body-parser/express/browserslist findings that `npm audit` reports but Dependabot has never opened (or already marked `fixed`, for qs) be raised with GitHub as a possible dependency-graph gap, or is npm's audit registry just broader than GitHub's advisory set by design?
- Verified live by fetching real content (not a status code)? what, and what did it say: yes - `gh api repos/opencomputeproject/OCP-CE-HR-Policy-Searcher/dependabot/alerts --paginate` returned the real 18-row alert payload (severities, ranges, patched versions) used to scope this fix, and a second scoped `gh api` call for qs/express/body-parser/browserslist returned their actual state (one qs alert, state fixed; zero rows for the other three) rather than trusting npm audit's broader vulnerability set at face value. Also fetched the real body of `gh pr view 14` and the real `.github/PULL_REQUEST_TEMPLATE.md` content off the still-open PR #38 branch (`gh api .../contents/...?ref=docs/lessons-and-decisions`) to match this PR's body to the org's actual template instead of guessing its shape.
