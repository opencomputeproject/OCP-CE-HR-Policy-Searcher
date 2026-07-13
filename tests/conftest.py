"""Shared test fixtures.

src/api/app.py loads the project .env at import time (override=True), so a
developer's real credentials leak into the test process and break tests that
assume a clean environment (the admin gate flips on; Sheets/keys look
configured). Strip the ambient config by default; tests that need a value set
it themselves via monkeypatch.setenv.
"""

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
