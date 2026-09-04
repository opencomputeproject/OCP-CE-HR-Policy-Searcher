"""Shared test fixtures.

src/api/app.py loads the project .env at import time (override=True), so a
developer's real credentials leak into the test process and break tests that
assume a clean environment (the admin gate flips on; Sheets/keys look
configured). Strip the ambient config by default; tests that need a value set
it themselves via monkeypatch.setenv.
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
    # Deleting the variables is not enough on its own: src.api.app calls
    # load_dotenv(override=True) at import, so the first test in a process to
    # import the app re-injected the developer's .env AFTER this fixture had
    # cleared it, and any non-GET route test run alone got a 401 from the
    # admin gate while the same test passed inside the full file (where an
    # earlier test had already paid the import). Lesson PL-009. Neutralise the
    # loader for the whole test, so an import during a test cannot reach .env.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)

# Proofmark size taxonomy: importing the autouse fixture registers it
# suite-wide. The plugin lives in gates/ (distributed file, never edited here),
# so gates/ must be on sys.path before the import - hence the noqa'd position.
_pm_gates = str(Path(__file__).resolve().parents[1] / "gates")
if _pm_gates not in sys.path:
    sys.path.insert(0, _pm_gates)
from proofmark_sizes import _proofmark_size_guard  # noqa: E402,F401
