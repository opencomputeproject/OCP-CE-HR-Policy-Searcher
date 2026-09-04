"""The project .env must never reach a test, even through an import made
during the test (lesson PL-009).

`src.api.app` calls `load_dotenv(override=True)` at import. Clearing the
variables before a test was not enough: the first test in a process to
import the app re-injected the developer's ADMIN_TOKEN after the clearing
fixture ran, so a non-GET route test failed with 401 when run alone and
passed inside the full file. The shared autouse fixture now neutralises the
loader itself; this test pins that.
"""

import os

import dotenv
import pytest


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
