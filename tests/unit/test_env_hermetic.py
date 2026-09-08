"""The project .env must never reach a test, even through an import made
during the test (lesson PL-009).

`src.api.app` used to call `load_dotenv(override=True)` at import. Clearing
the variables before a test was not enough: the first test in a process to
import the app re-injected the developer's ADMIN_TOKEN after the clearing
fixture ran, so a non-GET route test failed with 401 when run alone and
passed inside the full file. Two layers now hold it: the root cause is gone
(the module no longer reads .env; `python -m src.api` does, see
src/api/__main__.py), and the shared autouse fixture still neutralises the
loader so no future import can bring it back quietly. These tests pin both.
"""

import importlib
import os
from unittest.mock import MagicMock

import dotenv
import pytest


@pytest.mark.medium
def test_importing_the_api_module_does_not_read_dotenv(monkeypatch):
    """FAILS ON OLD BEHAVIOUR: app.py's import-time `from dotenv import
    load_dotenv` + call would hit the spy once on reload."""
    import src.api.app as app_module

    spy = MagicMock(return_value=False)
    monkeypatch.setattr(dotenv, "load_dotenv", spy)
    monkeypatch.setattr("dotenv.main.load_dotenv", spy)
    before = dict(os.environ)

    importlib.reload(app_module)

    assert spy.call_count == 0, "src.api.app read .env at import"
    assert dict(os.environ) == before, "importing src.api.app changed the environment"


@pytest.mark.medium
def test_dotenv_cannot_reinject_secrets_during_a_test(tmp_path):
    """FAILS ON OLD BEHAVIOUR: the real loader would set ADMIN_TOKEN here."""
    env_file = tmp_path / ".env"
    env_file.write_text("ADMIN_TOKEN=leaked-from-dotenv\n", encoding="utf-8")

    loaded = dotenv.load_dotenv(env_file, override=True)

    assert loaded is False
    assert os.environ.get("ADMIN_TOKEN") is None


@pytest.mark.small
def test_the_ambient_variables_start_every_test_unset():
    for name in ("ADMIN_TOKEN", "SPREADSHEET_ID", "GOOGLE_CREDENTIALS"):
        assert os.environ.get(name) is None, f"{name} leaked into the test process"
