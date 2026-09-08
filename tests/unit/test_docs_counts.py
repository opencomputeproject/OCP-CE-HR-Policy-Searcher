"""README.md and CLAUDE.md must not quote a test count as a bare number.

Both said "1085+ tests" and "153 frontend tests across 18 suites" long after
the floor had passed 2,600 and the frontend 500 (fixed 2026-09-08). A count
in prose is stale the day after it is written; the durable form is either
the file that holds the live number (`gates/min_test_count.txt`) or a value
with the date it was measured. This test refuses the bare form.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# "1085+ tests", "153 frontend tests", "across 18 suites" - with no date on
# the same line. A date (YYYY-MM-DD) on the line makes the number honest.
BARE_COUNT = re.compile(
    r"\b\d{2,5}\+?\s+(?:backend\s+|frontend\s+|unit\s+)?tests?\b|\bacross\s+\d+\s+suites?\b",
    re.IGNORECASE,
)
DATED = re.compile(r"\b20\d\d-\d\d-\d\d\b")


def _bare_count_lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    # CLAUDE.md's proofmark block is ring-distributed and not this repo's to edit.
    text = re.sub(r"<!-- proofmark:begin -->.*?<!-- proofmark:end -->", "", text, flags=re.S)
    return [
        ln.strip() for ln in text.splitlines()
        if BARE_COUNT.search(ln) and not DATED.search(ln)
    ]


class TestNoBareTestCounts:
    @pytest.mark.small
    @pytest.mark.parametrize("name", ["README.md", "CLAUDE.md", "docs/SESSION_BRIEF.md"])
    def test_a_test_count_carries_its_date_or_points_at_the_floor_file(self, name):
        offenders = _bare_count_lines(ROOT / name)
        assert offenders == [], (
            f"{name} quotes a test count with no date: {offenders}. Either add the "
            f"measurement date to the line or point at gates/min_test_count.txt."
        )
