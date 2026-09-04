"""Same-instrument keys: when two different pages describe the same law.

Four of the reviewer's removals were news stories about EnEfG (the German
data-centre energy efficiency act), a policy already kept under a different
URL, and one more was a repeat of a row already above it. Neither is a
content problem the model should be asked to judge - the second sighting of
an instrument is not a new document. This module turns a policy name into a
small set of keys two spellings of the same instrument are likely to share,
so a lookup index (:class:`InstrumentIndex`) can find the existing row
before a duplicate is ever screened. See docs/HOW_IT_WORKS.md, "Same
instrument, one row", and
docs/decisions/ADR-0010-same-instrument-folds-into-the-existing-row.md.

Deliberately name-key and abbreviation matching only - no reference to
referenced/cited legislation, which is a separate and later idea (see the
ADR's Consequences). Plain dicts and sets; no dependency on the Policy
model, so a scanner can hand this either a raw store row or a live Policy
object.
"""

import re
import unicodedata
from typing import Iterable, Optional

# A name is cut at the first of these when what comes before is long enough
# to trust on its own - "Act Name - Explanatory Notes" and "Act Name:
# Second Reading" are the same instrument as "Act Name", but "A - B" is too
# short a prefix to cut down further without becoming too generic to key on.
_QUALIFIER_SEPARATORS = (" - ", " – ", ": ")
_MIN_QUALIFIER_PREFIX = 12

# A trailing "(...)" is read as a possible abbreviation, not as part of the
# name itself - true whether it turns out to hold an abbreviation ("EnEfG"),
# a year ("2024"), or a description too long to be either.
_TRAILING_PARENTHETICAL = re.compile(r"^(.*?)\s*\(([^()]+)\)\s*$")

_ABBREVIATION_MIN = 3
_ABBREVIATION_MAX = 12
_MIN_KEY_LENGTH = 3

_HAS_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
_NOT_WORD_OR_SPACE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def _strip_trailing_qualifier(name: str) -> str:
    cut_at: Optional[int] = None
    for sep in _QUALIFIER_SEPARATORS:
        idx = name.find(sep)
        if idx != -1 and (cut_at is None or idx < cut_at):
            cut_at = idx
    if cut_at is not None and cut_at > _MIN_QUALIFIER_PREFIX:
        return name[:cut_at]
    return name


def _split_trailing_parenthetical(name: str) -> tuple[str, Optional[str]]:
    match = _TRAILING_PARENTHETICAL.match(name)
    if not match:
        return name, None
    return match.group(1), match.group(2)


def _fold(text: str) -> str:
    """lowercase, Unicode-fold, punctuation to spaces, whitespace collapsed."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = _NOT_WORD_OR_SPACE.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def instrument_keys(*names: Optional[str]) -> set[str]:
    """Keys two spellings of the same instrument are likely to share.

    For each non-empty name: the normalised full name, with a trailing
    qualifier tail and a trailing parenthetical removed first, plus - when
    that trailing parenthetical is 3 to 12 characters and contains a letter
    - the normalised abbreviation on its own. Keys under 3 characters are
    discarded, whichever kind they are.
    """
    keys: set[str] = set()
    for name in names:
        if not name or not name.strip():
            continue

        trimmed = _strip_trailing_qualifier(name.strip())
        base, parenthetical = _split_trailing_parenthetical(trimmed)

        full_key = _fold(base)
        if len(full_key) >= _MIN_KEY_LENGTH:
            keys.add(full_key)

        if parenthetical:
            candidate = parenthetical.strip()
            if (
                _ABBREVIATION_MIN <= len(candidate) <= _ABBREVIATION_MAX
                and _HAS_LETTER.search(candidate)
            ):
                abbreviation_key = _fold(candidate)
                if len(abbreviation_key) >= _MIN_KEY_LENGTH:
                    keys.add(abbreviation_key)

    return keys


def _name_and_url(policy) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """(policy_name, policy_name_en, url) from a dict or an object (Policy)."""
    if isinstance(policy, dict):
        return (
            policy.get("policy_name"),
            policy.get("policy_name_en"),
            policy.get("url"),
        )
    return (
        getattr(policy, "policy_name", None),
        getattr(policy, "policy_name_en", None),
        getattr(policy, "url", None),
    )


class InstrumentIndex:
    """Looks up an already-kept policy by the instrument it names.

    Built once per scan from every policy already in the store (via
    :meth:`from_rows`), and grown during the scan with :meth:`add` as new
    policies are found, so a second sighting of the same instrument later
    in the same scan folds too.
    """

    def __init__(self) -> None:
        self._key_to_url: dict[str, str] = {}

    @classmethod
    def from_rows(cls, rows: Iterable) -> "InstrumentIndex":
        index = cls()
        for row in rows:
            index.add(row)
        return index

    def add(self, policy) -> None:
        """Register a policy (a store row dict, or a Policy object) so a
        later :meth:`match` can find it. A policy with no url is ignored -
        there is nothing useful to return for it."""
        name, name_en, url = _name_and_url(policy)
        if not url:
            return
        for key in instrument_keys(name, name_en):
            self._key_to_url.setdefault(key, url)

    def match(self, keys: set[str], exclude_url: Optional[str] = None) -> Optional[str]:
        """The URL of an existing policy sharing one of ``keys``, or None.

        ``exclude_url`` excludes a URL from counting as its own match - a
        page checking itself against the index it is about to be added to.
        """
        for key in keys:
            url = self._key_to_url.get(key)
            if url and url != exclude_url:
                return url
        return None
