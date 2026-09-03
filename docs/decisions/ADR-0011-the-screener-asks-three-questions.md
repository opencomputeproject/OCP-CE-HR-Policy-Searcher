# ADR-0011: The screener asks three questions

- Status: Accepted
- Date: 2026-09-03
- Owner: the workstream lead
- Supersedes: ADR-0003

## Context

On 1 September 2026 the screener passed 445 of 636 pages and the strong
model then found nothing in 285 of them; one Pennsylvania domain
(`pa_dep`) passed 199 pages for zero rows. The screening prompt asked one
wide question - "is this plausibly government policy touching data-centre
heat reuse?" - written recall-first, "when in doubt, keep it".

The reviewer's removals, read 2 September 2026, show what that one
question lets through: 12 of her 88 removals are reports, articles,
opinion pieces or a private initiative; 6 are bills that mention a data
centre but contain no heat-reuse substance. A wide yes/no question cannot
tell those apart from a real policy; a narrower one can.

## Decision

Two cheap calls, not one.

1. **The gate stays exactly as it was.** `SCREENING_PROMPT`, the original
   recall-first yes/no with its confidence, is unchanged: every row in the
   store passed it, so it is the one screening rule with a proven recall
   record. A confident no drops the page (`filtered_screening`); an
   unconfident no goes to the strong model.
2. **A classifier call for pages that pass**, `CLASSIFY_PROMPT`, asks the
   same cheap model three narrow questions: what kind of document is this,
   from a fixed list (act, bill, regulation, consultation, grant, plan,
   index, report, article, speech, question, other); quote, verbatim, the
   sentence that names a data centre, or say there is none; quote, verbatim,
   the sentence about reusing or recovering heat, or say there is none.

The document kind is the second gate; the quotes are evidence. Two lists live
in `config/settings.yaml`: `analysis.screener_reject_kinds` (default
`question`, `speech`; dropped even with both quotes) and
`analysis.screener_soft_reject_kinds` (default `report`, `article`; dropped
only when the classifier found neither sentence, otherwise the strong model
decides). Every other kind proceeds. A missing quote is never a reason to
drop: the deterministic scope gate on source text (ADR-0001) is the
data-centre rule.

Why two calls rather than one. Three single-call designs were replayed
against the reviewer's rows with recorded model answers on 2026-09-03: a
quote-as-gate rule lost 12 of her 23 kept pages; folding the yes/no into
the three-question prompt lost 8, and with the original recall-first wording
restored still lost 5, because asking for quotes in the same breath changed
the model's relevance answers. Keeping the gate as a separate, unchanged
call costs about one extra Haiku call per page that passes (roughly $0.85
at the 1 September volume) and keeps the proven recall untouched. Lesson
PL-008.

Every fallback (a malformed answer, an exhausted rate limit, a missing
model, any other API error) still falls open on both calls; the classifier's
fallback is `kind=None`, which always proceeds. The kind and both quotes are
stored as `evidence` on every policy the page produces.

See `src/core/llm.py` (`SCREENING_PROMPT`, `CLASSIFY_PROMPT`,
`ClaudeClient.screen_relevance`, `ClaudeClient.classify_document`,
`parse_relevance_json`, `parse_screening_json`) and `src/core/scanner.py`
(`screening_decision`).

## Consequences

- One more cheap call per page that passes the gate: about $0.85 at the
  1 September volume (445 pages, about 1,900 input tokens each). The
  classifier's prompt joins the rules fingerprint, so the first scan after
  this deploys re-screens every cached page, about $1.30 more, once.
- Parliamentary questions and transcripts that reach the screener are
  dropped there; reports and articles without any quoted evidence are
  dropped there; reports and articles with evidence go to the strong
  model, so the saving on articles is smaller than a hard drop would give.
  The replay showed that hard drop losing three of her keeps.
- A reviewer can read the kind and both quotes behind a row (`evidence`).
- The `filtered_screening` counter keeps its meaning from before this
  change; `screened_kind` counts the classifier's drops separately.

## Evidence

- Scan `86463134`, 1 September 2026: 636 screened, 445 passed, 285 of
  those produced nothing.
- Reviewer's column, read 2 September 2026.
- Recorded replays, 3 September 2026 (`tests/fixtures/screening/`, 58
  usable rows, 23 keeps; the recording names the classifier prompt hash it
  was made for): quote-as-gate 12 keeps lost; combined prompt 8 lost;
  combined prompt with the original wording 5 lost; classifier-only kind
  rules 0 lost.

## Guarded by

`tests/unit/test_llm.py` (the prompt content, `parse_screening_response`,
`parse_screening_json`, every fallback path), `tests/unit/test_scanner.py`
(`screening_decision`'s full rule table, the gate wired into Stage 5a,
`evidence` on the produced policy, the rules-fingerprint change), and
`tests/unit/test_screening_replay.py` (recorded fixtures, once the
integrator records them: zero lost keeps on the reviewer's keeps, and at
least 60 percent of her "not a policy article" removals caught at
screening).
