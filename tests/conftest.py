"""Shared test fixtures.

src/api/app.py used to load the project .env at import time (override=True),
so a developer's real credentials leaked into the test process and broke tests
that assume a clean environment (the admin gate flips on; Sheets/keys look
configured) - lesson PL-009. The root cause is gone (loading moved to
`python -m src.api`); the ambient config is still stripped by default and the
loader still neutralised, so no future import can bring the leak back
quietly. Tests that need a value set it themselves via monkeypatch.setenv.
"""

import sys
from pathlib import Path

import pytest

# Env vars a developer may have in .env that tests assume are unset unless the
# test sets them explicitly. Keep this list to config that changes behavior.
_AMBIENT_ENV = (
    "ADMIN_TOKEN",
    "SPREADSHEET_ID",
    "GOOGLE_CREDENTIALS",
)


@pytest.fixture(autouse=True)
def _no_ambient_env(monkeypatch):
    for name in _AMBIENT_ENV:
        monkeypatch.delenv(name, raising=False)
    # Deleting the variables was not enough on its own: src.api.app used to
    # call load_dotenv(override=True) at import, so the first test in a process
    # to import the app re-injected the developer's .env AFTER this fixture had
    # cleared it (lesson PL-009). That call is gone; the loader stays
    # neutralised for the whole test as the second lock, so an import made
    # during a test can never reach .env even if someone adds the call back.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)

# Proofmark size taxonomy: importing the autouse fixture registers it
# suite-wide. The plugin lives in gates/ (distributed file, never edited here),
# so gates/ must be on sys.path before the import - hence the noqa'd position.
_pm_gates = str(Path(__file__).resolve().parents[1] / "gates")
if _pm_gates not in sys.path:
    sys.path.insert(0, _pm_gates)
from proofmark_sizes import _proofmark_size_guard  # noqa: E402,F401


def pytest_addoption(parser):
    parser.addoption(
        "--live", action="store_true", default=False,
        help="run the tests marked `live`; they reach the public internet",
    )


def pytest_collection_modifyitems(config, items):
    """`live` tests stay COLLECTED - the test-count floor counts them, and
    they do run, in .github/workflows/live-probes.yml every Monday - but skip
    in every ordinary run, so pre-push, CI and a contributor's `pytest` never
    depend on a remote server being up. `pytest -m live --live` runs them by
    hand. See docs/SESSION_BRIEF.md, Hermeticity."""
    if config.getoption("--live"):
        return
    skip = pytest.mark.skip(reason="needs the public internet: run with --live")
    for item in items:
        if item.get_closest_marker("live"):
            item.add_marker(skip)
