"""src/core/clock.py: the naive-UTC clock that replaced datetime.utcnow()."""

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.core.clock import utcnow

SRC = Path(__file__).resolve().parents[2] / "src"


class TestUtcnow:
    @pytest.mark.small
    def test_is_naive_and_means_utc(self):
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        got = utcnow()
        after = datetime.now(timezone.utc).replace(tzinfo=None)
        assert got.tzinfo is None
        assert before <= got <= after

    @pytest.mark.small
    def test_the_deprecated_call_does_not_come_back(self):
        """One clock. A new `datetime.utcnow()` under src/ is a warning per
        call in the suite and a naive/aware mix waiting to happen."""
        offenders = [
            str(p.relative_to(SRC.parent))
            for p in SRC.rglob("*.py")
            if p.name != "clock.py"  # the one file allowed to name what it replaced
            and re.search(r"\bdatetime\.utcnow\(\)", p.read_text(encoding="utf-8"))
        ]
        assert offenders == [], f"use src.core.clock.utcnow() instead: {offenders}"
