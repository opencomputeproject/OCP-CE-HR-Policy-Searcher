"""Turning the reviewer's free-text verdict column into golden-set labels.

The review surface is the Google Sheet, not the app (see
`docs/decisions/ADR-0005-the-reviewers-column-is-the-review-record.md`). She
writes `Verdict - reason` in her own words in one column; nothing parses it.
This module is the parser: it finds that column by its header, reads her
verdict and reason out of the free text, buckets the reason into a fixed set
of categories, and turns the result into rows `src.eval.golden.load_golden`
can load.

Two inputs produce the same header-keyed row shape, so both run through the
same functions: `SheetsClient.read_staging_rows` (the live sheet) and a CSV
export of just her column, adapted by `staging_rows_from_csv_export`.
"""

import re
from dataclasses import dataclass

from ..core.urls import normalize_url
from .golden import GoldenSetError

#: The reviewer's column header starts with this; the rest is her own
#: standing set of review questions, which is free to change without
#: breaking anything that only needs to find the column.
REVIEW_HEADER_PREFIX = "Review ("

#: Her column, verbatim, on the Staging tab of "Heat Reuse Policies
#: Database" (column AC as of 2026-09-02). Used only to adapt a CSV export
#: (which carries the short field name `anna_review`, not her real header)
#: into the same header-keyed shape the live sheet returns.
REVIEW_HEADER_TEXT = (
    "Review (Is website trustworthy? Is the policy focused on data center "
    "heat reuse explicitly? Is it duplicative? Is it actually a policy? "
    "Are proposed and enacted policies differentiated?)"
)

#: The fixed vocabulary a rejection or a to-be-decided reason is sorted
#: into. Deliberately closed: a reason that matches none of these is left
#: uncategorized (an empty tuple) rather than forced into the nearest bucket.
CATEGORIES = (
    "not_a_policy_question",
    "not_a_policy_article",
    "bad_link",
    "no_data_centre",
    "no_heat_reuse",
    "duplicate",
    "private_initiative",
    "language",
    "judgement",
    "unexplained",
)


def find_review_header(headers: list) -> str:
    """The first header that is her review column, or a named failure.

    Matched by prefix rather than the full text because her parenthesised
    list of review questions is hers to edit; the column is still the
    column.
    """
    for header in headers:
        if header.startswith(REVIEW_HEADER_PREFIX):
            return header
    raise GoldenSetError(
        f"No header starts with {REVIEW_HEADER_PREFIX!r}. Headers seen: {headers}"
    )


@dataclass(frozen=True)
class ParsedVerdict:
    """One cell of her column, taken apart."""

    verdict: str  # keep | remove | tbd | blank | unreachable
    reason_text: str
    categories: tuple


_UNREACHABLE_PATTERN = re.compile(r"not able to access", re.IGNORECASE)

# Reason text -> category, checked in this order against her free text
# lower-cased. Several can match one reason (she sometimes gives two, as in
# "not a policy, also the link does not work"), so every row is tested
# rather than stopping at the first hit. A readable table, not nested ifs,
# because the next pattern she introduces is a one-line addition here.
_CATEGORY_PATTERNS = (
    (r"kleine anfrage|parliamentary|transcript|question", "not_a_policy_question"),
    (r"article|blog|report|opinion|project|not a policy", "not_a_policy_article"),
    (r"link|website|error page|not a real", "bad_link"),
    (r"heat reuse|waste heat to electricity|heat from data", "no_heat_reuse"),
    (r"repeat|already included|duplic", "duplicate"),
    (r"private sector", "private_initiative"),
    (r"\btens\b", "no_data_centre"),  # thermal energy network, her shorthand
)

# A bare mention of a data centre only counts as its own category
# (no_data_centre) when no_heat_reuse did not already fire: "no reference to
# heat from data centers" is about the heat link being absent, not the data
# centre; "no reference to data centers" has no heat phrase at all and is
# squarely no_data_centre.
_DATA_CENTRE_MENTION_PATTERN = re.compile(r"data centre|data center")

_TBD_LANGUAGE_PATTERN = re.compile(r"dutch|language|only in")


def _categorize_remove(reason_text: str) -> tuple:
    lowered = reason_text.lower()
    categories = [
        category for pattern, category in _CATEGORY_PATTERNS
        if re.search(pattern, lowered)
    ]
    if (
        _DATA_CENTRE_MENTION_PATTERN.search(lowered)
        and "no_heat_reuse" not in categories
        and "no_data_centre" not in categories
    ):
        categories.append("no_data_centre")
    return tuple(categories)


def parse_verdict(text: str) -> ParsedVerdict:
    """Take apart one cell of her column.

    Format is `Verdict - reason`, her words, case-insensitive on the verdict.
    "Not able to access the article" is its own outcome (`unreachable`): not
    a judgement on the policy, so it gets no category. An empty cell is
    `blank`. Categories are only ever assigned to `remove` (from the reason,
    or `unexplained` when she gave none) and `tbd` (`language` for "only in
    Dutch"-style deferrals, `judgement` otherwise) - a `keep` needs no
    reason and its free-text commentary is not a rejection category, so
    running the same matcher on it would risk mislabelling a keep as a
    rejection (e.g. "reporting requirements" contains "report").
    """
    raw = (text or "").strip()
    if not raw:
        return ParsedVerdict(verdict="blank", reason_text="", categories=())
    if _UNREACHABLE_PATTERN.search(raw):
        return ParsedVerdict(verdict="unreachable", reason_text=raw, categories=())

    head, sep, tail = raw.partition("-")
    prefix = head.strip().lower()
    reason_text = tail.strip() if sep else ""

    if prefix == "keep":
        return ParsedVerdict(verdict="keep", reason_text=reason_text, categories=())
    if prefix == "remove":
        categories = _categorize_remove(reason_text) if reason_text else ("unexplained",)
        return ParsedVerdict(verdict="remove", reason_text=reason_text, categories=categories)
    if prefix == "tbd":
        category = "language" if _TBD_LANGUAGE_PATTERN.search(reason_text.lower()) else "judgement"
        return ParsedVerdict(verdict="tbd", reason_text=reason_text, categories=(category,))

    raise GoldenSetError(f"unrecognised review verdict (not keep/remove/tbd): {raw!r}")


@dataclass(frozen=True)
class ReviewLabel:
    """One row's review, keyed by URL rather than sheet position."""

    url: str
    verdict: str
    categories: tuple
    reason_text: str
    row_number: int


def read_review_labels(rows: list, link_header: str = "Link") -> list:
    """Turn header-keyed Staging rows into `ReviewLabel`s.

    `rows` is what `SheetsClient.read_staging_rows` returns from the live
    sheet, or `csv.DictReader` over a CSV export adapted by
    `staging_rows_from_csv_export` - both are lists of header-keyed dicts,
    so one function reads both. A row with no URL is skipped: there is
    nothing to key a label to. Row numbers count from 2 (the header is row
    1), matching the Staging sheet's own numbering, so a diagnostic can name
    the row without re-deriving the offset.
    """
    if not rows:
        return []
    review_header = find_review_header(list(rows[0].keys()))
    labels = []
    for row_number, row in enumerate(rows, start=2):
        url = (row.get(link_header) or "").strip()
        if not url:
            continue
        parsed = parse_verdict(row.get(review_header) or "")
        labels.append(
            ReviewLabel(
                url=normalize_url(url),
                verdict=parsed.verdict,
                categories=parsed.categories,
                reason_text=parsed.reason_text,
                row_number=row_number,
            )
        )
    return labels


def staging_rows_from_csv_export(csv_rows: list) -> list:
    """Adapt a `row,country,name,link,discovered_at,review_status,anna_review`
    CSV export (a verbatim export of her column, see
    `tests/fixtures/review_column_2026-09-02.csv`) into the header-keyed
    shape `read_review_labels` expects - the same shape the live sheet
    returns - so the CLI's `--from-csv` path and the live `--from-sheet`
    path run through identical parsing code.
    """
    return [
        {"Link": row.get("link", ""), REVIEW_HEADER_TEXT: row.get("anna_review", "")}
        for row in csv_rows
    ]


#: Category -> the `golden.REJECTION_REASONS` entry it is written as. Reuses
#: an existing name where one already means the same thing so the two
#: vocabularies do not diverge; the categories with no prior equivalent
#: (bad_link, no_data_centre, no_heat_reuse, private_initiative,
#: unexplained) are new entries added to REJECTION_REASONS for this work.
#: `language` and `judgement` are not here: they only ever label a `tbd`
#: row, and tbd rows are never written as golden rows.
_CATEGORY_TO_REJECTION_REASON = {
    "not_a_policy_question": "proceedings_or_transcript",
    "not_a_policy_article": "report_about_policy",
    "bad_link": "bad_link",
    "no_data_centre": "no_data_centre",
    "no_heat_reuse": "no_heat_reuse",
    "duplicate": "duplicate",
    "private_initiative": "private_initiative",
    "unexplained": "unexplained",
}


def labels_to_golden(labels: list, reviewer: str, read_on: str) -> list:
    """Turn `ReviewLabel`s into rows `golden.load_golden` can load.

    Only `keep` and `remove` become golden rows - a `tbd`, `blank` or
    `unreachable` verdict is not yet a decision, so it is counted by the
    caller and reported, never written as a label. Sorted by row number so
    building the set twice from the same input is byte-identical.

    A `remove` row can carry more than one category (she sometimes gives
    two reasons); the first one found is what gets written, since a golden
    row has exactly one `reason`. When a `remove` reason matched none of the
    fixed categories - not seen in the reviewed set this was built from, but
    possible from a live sheet that has moved on - it falls back to
    `REJECTION_REASONS`' own catch-all, `"other"`.
    """
    rows = []
    for label in sorted(labels, key=lambda label: label.row_number):
        if label.verdict == "keep":
            rows.append(
                {
                    "url": label.url,
                    "keep": True,
                    "reason": "",
                    "labelled_by": reviewer,
                    "labelled_on": read_on,
                }
            )
        elif label.verdict == "remove":
            category = label.categories[0] if label.categories else None
            if category is not None and category not in CATEGORIES:
                raise GoldenSetError(
                    f"row {label.row_number}: category {category!r} is not one of "
                    f"{CATEGORIES}; the pattern table and the vocabulary have drifted"
                )
            reason = _CATEGORY_TO_REJECTION_REASON.get(category, "other")
            rows.append(
                {
                    "url": label.url,
                    "keep": False,
                    "reason": reason,
                    "labelled_by": reviewer,
                    "labelled_on": read_on,
                }
            )
        # tbd / blank / unreachable: not a decision yet, not a golden row.
    return rows
