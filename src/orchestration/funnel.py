"""Plain-English funnel sentences (WP-6a).

Turns a scan's summed per-stage counters into the sentences a curator or
admin actually wants: what happened to documents at each pipeline stage,
in the order the pipeline actually runs them through. This module has no
knowledge of scans, domains, jobs, or storage - it only formats numbers a
caller already summed. See ``GET /api/scans/{scan_id}``'s ``funnel_summary``
(``src/api/routes/scans.py``) for the caller that sums a scan's
``DomainProgress``/``scan_domains`` counters into the ``totals`` this takes.
"""

from __future__ import annotations

# (totals key, sentence template) in the order each stage actually runs -
# see docs/HOW_IT_WORKS.md's "Stage by stage" section. Every stage before
# screening costs nothing, hence ", free"; screening_calls and
# analysis_calls are the two stages that call a paid model, so they carry
# no such suffix.
_STAGES: list[tuple[str, str]] = [
    ("pages_crawled", "{n} pages fetched"),
    ("filtered_short_content", "{n} dropped for too little text, free"),
    ("filtered_excluded", "{n} dropped by an exclusion rule, free"),
    ("filtered_doc_type", "{n} dropped by a source's document-type rule, free"),
    ("filtered_keywords", "{n} dropped by the keyword gate, free"),
    ("filtered_out_of_scope", "{n} dropped for no data-centre mention, free"),
    ("filtered_link", "{n} dropped by the link check, free"),
    ("screening_calls", "{n} screened by the cheap model"),
    ("screened_kind", "{n} dropped by the document-kind question"),
    ("filtered_screening", "{n} dropped by the cheap model"),
    ("analysis_calls", "{n} analysed by the strong model"),
    ("filtered_duplicate", "{n} folded into an already-kept policy"),
    ("policies_found", "{n} policies found"),
]


def funnel_sentences(totals: dict) -> list[str]:
    """Plain sentences for a scan's summed funnel counters.

    ``totals`` maps stage names (a subset of the keys above) to summed
    counts across every domain in a scan. A stage that is absent or zero
    is skipped entirely - a scan has nothing to say about a stage nothing
    reached. Sentences come back in pipeline order with thousands
    separators; an empty (or all-zero) ``totals`` returns ``[]``.
    """
    sentences = []
    for key, template in _STAGES:
        n = totals.get(key) or 0
        if n:
            sentences.append(template.format(n=f"{n:,}"))
    return sentences
