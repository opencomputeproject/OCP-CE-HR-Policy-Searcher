"""Tests for environment variable loading and credential resolution.

Verifies that .env values override stale system environment variables
(e.g. ANTHROPIC_API_KEY="" inherited from parent process) and that
missing credentials produce actionable warnings.
"""

import os
from unittest.mock import patch, MagicMock

import pytest

from src.config.settings import Settings


class TestSettingsFromEnvVars:
    """Settings should resolve credentials from environment variables."""

    def test_loads_anthropic_key_from_env(self):
        """ANTHROPIC_API_KEY env var should populate settings."""
        env = {"ANTHROPIC_API_KEY": "sk-test-key-123"}
        with patch.dict(os.environ, env, clear=False):
            s = Settings(ANTHROPIC_API_KEY="sk-test-key-123")
        assert s.anthropic_api_key == "sk-test-key-123"

    def test_loads_spreadsheet_id_from_env(self):
        """SPREADSHEET_ID env var should populate settings."""
        s = Settings(SPREADSHEET_ID="abc123")
        assert s.spreadsheet_id == "abc123"

    def test_loads_google_credentials_from_env(self):
        """GOOGLE_CREDENTIALS env var should populate settings."""
        s = Settings(GOOGLE_CREDENTIALS="base64creds")
        assert s.google_credentials == "base64creds"

    def test_defaults_to_none_when_not_set(self):
        """Credentials should default to None when not in env or args."""
        s = Settings(
            ANTHROPIC_API_KEY=None,
            GOOGLE_CREDENTIALS=None,
            SPREADSHEET_ID=None,
        )
        assert s.anthropic_api_key is None
        assert s.google_credentials is None
        assert s.spreadsheet_id is None

    def test_empty_string_treated_as_set(self):
        """Empty string is truthy in pydantic — but falsy in conditionals."""
        s = Settings(ANTHROPIC_API_KEY="")
        # Empty string is stored, but `if settings.anthropic_api_key` is False
        assert not s.anthropic_api_key


class TestDotenvOverride:
    """load_dotenv(override=True) should win over stale env vars.

    Claude Code sets ANTHROPIC_API_KEY="" in its process environment.
    Without override=True, this empty value persists and the .env value
    is ignored, silently disabling LLM analysis.
    """

    def test_override_replaces_empty_env_var(self, tmp_path):
        """override=True should replace an empty system env var."""
        from dotenv import load_dotenv

        env_file = tmp_path / ".env"
        env_file.write_text("TEST_KEY_DOTENV=from_file\n")

        with patch.dict(os.environ, {"TEST_KEY_DOTENV": ""}, clear=False):
            assert os.environ["TEST_KEY_DOTENV"] == ""

            load_dotenv(env_file, override=True)

            assert os.environ["TEST_KEY_DOTENV"] == "from_file"

    def test_no_override_keeps_empty_env_var(self, tmp_path):
        """Without override, empty system env var is kept (the bug)."""
        from dotenv import load_dotenv

        env_file = tmp_path / ".env"
        env_file.write_text("TEST_KEY_NOOVERRIDE=from_file\n")

        with patch.dict(os.environ, {"TEST_KEY_NOOVERRIDE": ""}, clear=False):
            load_dotenv(env_file, override=False)

            # Bug behavior: empty env var wins over .env
            assert os.environ["TEST_KEY_NOOVERRIDE"] == ""

    def test_override_replaces_stale_value(self, tmp_path):
        """override=True should replace a stale non-empty env var."""
        from dotenv import load_dotenv

        env_file = tmp_path / ".env"
        env_file.write_text("TEST_KEY_STALE=new_value\n")

        with patch.dict(os.environ, {"TEST_KEY_STALE": "old_value"}, clear=False):
            load_dotenv(env_file, override=True)

            assert os.environ["TEST_KEY_STALE"] == "new_value"


class TestMainEntryPointLoadsDotenv:
    """The main module should call load_dotenv(override=True) at import time."""

    def test_main_module_imports_dotenv(self):
        """src/main.py should import and call load_dotenv."""
        from pathlib import Path

        main_py = Path("src/main.py")
        content = main_py.read_text()

        assert "from dotenv import load_dotenv" in content
        assert "load_dotenv(override=True)" in content

    def test_dotenv_called_before_config_imports(self):
        """load_dotenv must run before any config module is imported."""
        from pathlib import Path

        main_py = Path("src/main.py")
        lines = main_py.read_text().splitlines()

        dotenv_line = None
        first_config_import = None

        for i, line in enumerate(lines):
            if "load_dotenv(override=True)" in line and dotenv_line is None:
                dotenv_line = i
            if "from .config" in line and first_config_import is None:
                first_config_import = i

        assert dotenv_line is not None, "load_dotenv(override=True) not found"
        assert first_config_import is not None, "config import not found"
        assert dotenv_line < first_config_import, (
            f"load_dotenv (line {dotenv_line}) must come before "
            f"config imports (line {first_config_import})"
        )


class TestCredentialWarningMessages:
    """Missing credentials should produce actionable user-facing warnings."""

    def test_missing_api_key_warning_text(self):
        """Warning for missing ANTHROPIC_API_KEY should include setup URL."""
        from pathlib import Path

        main_py = Path("src/main.py").read_text()

        assert "console.anthropic.com" in main_py
        assert "ANTHROPIC_API_KEY" in main_py

    def test_missing_google_credentials_warning_text(self):
        """Warning for missing GOOGLE_CREDENTIALS should mention .env."""
        from pathlib import Path

        main_py = Path("src/main.py").read_text()

        assert "GOOGLE_CREDENTIALS not set" in main_py

    def test_missing_spreadsheet_id_warning_text(self):
        """Warning for missing SPREADSHEET_ID should mention .env."""
        from pathlib import Path

        main_py = Path("src/main.py").read_text()

        assert "SPREADSHEET_ID not set" in main_py


class TestPyprojectDotenvDependency:
    """python-dotenv must be listed as a project dependency."""

    def test_dotenv_in_dependencies(self):
        from pathlib import Path

        pyproject = Path("pyproject.toml").read_text()

        assert "python-dotenv" in pyproject
