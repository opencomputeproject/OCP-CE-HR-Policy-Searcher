"""The one clock for the codebase's naive-UTC convention.

Timestamps here are naive datetimes that mean UTC (`ScanJob.started_at`,
`Schedule.next_run_at`, digest and mailer windows). `datetime.utcnow()` gave
exactly that and is deprecated since Python 3.12: the full suite emitted
2,400 warnings about it. Switching the codebase to aware datetimes would
change every stored ISO string and every comparison against stored rows, so
the convention stays and this is the drop-in replacement for it.

`tests/unit/test_clock.py` fails if `datetime.utcnow()` reappears under src/.
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Now, in UTC, as a naive datetime - what `datetime.utcnow()` returned."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
