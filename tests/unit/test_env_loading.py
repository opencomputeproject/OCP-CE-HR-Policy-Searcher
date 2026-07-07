"""Tests for .env loading with explicit project-root path resolution.

All three entry points (agent, MCP server, API) resolve the .env file
relative to their own ``__file__`` so that credentials load correctly
even when the process working directory is *not* the project root
(e.g. when started as a Claude Code MCP subprocess).
"""

import base64
import os
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Project-root resolution
# ---------------------------------------------------------------------------

class TestProjectRootResolution:
    """Each entry point must resolve .env from the project root, not CWD."""

    @pytest.fixture(autouse=True)
    def _project_root(self):
        self.project_root = Path(__file__).resolve().parents[2]

    def test_agent_resolves_project_root(self):
        """src/agent/__main__.py should resolve project root 2 levels up."""
        agent_file = self.project_root / "src" / "agent" / "__main__.py"
        assert agent_file.exists()
        resolved = agent_file.resolve().parents[2]
        assert (resolved / ".env").exists() or (resolved / "config").is_dir()

    def test_mcp_server_resolves_project_root(self):
        """src/mcp/server.py should resolve project root 2 levels up."""
        server_file = self.project_root / "src" / "mcp" / "server.py"
        assert server_file.exists()
        resolved = server_file.resolve().parents[2]
        assert (resolved / ".env").exists() or (resolved / "config").is_dir()

    def test_api_app_resolves_project_root(self):
        """src/api/app.py should resolve project root 2 levels up."""
        api_file = self.project_root / "src" / "api" / "app.py"
        assert api_file.exists()
        resolved = api_file.resolve().parents[2]
        assert (resolved / ".env").exists() or (resolved / "config").is_dir()


class TestLoadDotenvUsesExplicitPath:
    """Entry points must call load_dotenv with an explicit file path."""

    @pytest.fixture(autouse=True)
    def _project_root(self):
        self.project_root = Path(__file__).resolve().parents[2]

    def _read_source(self, relative_path: str) -> str:
        return (self.project_root / relative_path).read_text(encoding="utf-8")

    def test_agent_uses_explicit_env_path(self):
        source = self._read_source("src/agent/__main__.py")
        assert 'load_dotenv(_project_root / ".env"' in source

    def test_mcp_server_uses_explicit_env_path(self):
        source = self._read_source("src/mcp/server.py")
        assert 'load_dotenv(_project_root / ".env"' in source

    def test_api_uses_explicit_env_path(self):
        source = self._read_source("src/api/app.py")
        assert 'load_dotenv(_project_root / ".env"' in source

    def test_all_use_override_true(self):
        """override=True is required so .env wins over stale system vars."""
        for path in [
            "src/agent/__main__.py",
            "src/mcp/server.py",
            "src/api/app.py",
        ]:
            source = self._read_source(path)
            assert "override=True" in source, f"{path} missing override=True"


class TestDotenvOverrideBehavior:
    """load_dotenv(override=True) should replace stale env vars."""

    def test_override_replaces_empty_env_var(self, tmp_path):
        from dotenv import load_dotenv

        env_file = tmp_path / ".env"
        env_file.write_text("TEST_OVERRIDE_KEY=from_file\n")

        with patch.dict(os.environ, {"TEST_OVERRIDE_KEY": ""}, clear=False):
            assert os.environ["TEST_OVERRIDE_KEY"] == ""
            load_dotenv(env_file, override=True)
            assert os.environ["TEST_OVERRIDE_KEY"] == "from_file"

    def test_override_replaces_stale_value(self, tmp_path):
        from dotenv import load_dotenv

        env_file = tmp_path / ".env"
        env_file.write_text("TEST_STALE_KEY=new_value\n")

        with patch.dict(os.environ, {"TEST_STALE_KEY": "old_value"}, clear=False):
            load_dotenv(env_file, override=True)
            assert os.environ["TEST_STALE_KEY"] == "new_value"

    def test_no_override_keeps_empty_value(self, tmp_path):
        """Without override, empty env var is kept (the bug scenario)."""
        from dotenv import load_dotenv

        env_file = tmp_path / ".env"
        env_file.write_text("TEST_NOOVERRIDE=from_file\n")

        with patch.dict(os.environ, {"TEST_NOOVERRIDE": ""}, clear=False):
            load_dotenv(env_file, override=False)
            assert os.environ["TEST_NOOVERRIDE"] == ""


# ---------------------------------------------------------------------------
# Google Sheets credential validation
# ---------------------------------------------------------------------------

class TestSheetsClientCredentialValidation:
    """SheetsClient.connect() should reject clearly invalid credentials."""

    def test_rejects_none_credentials(self):
        from src.output.sheets import SheetsClient

        client = SheetsClient(credentials_b64=None, spreadsheet_id="test-id")
        with pytest.raises(ValueError, match="GOOGLE_CREDENTIALS looks invalid"):
            client.connect()

    def test_rejects_empty_credentials(self):
        from src.output.sheets import SheetsClient

        client = SheetsClient(credentials_b64="", spreadsheet_id="test-id")
        with pytest.raises(ValueError, match="GOOGLE_CREDENTIALS looks invalid"):
            client.connect()

    def test_rejects_short_credentials(self):
        from src.output.sheets import SheetsClient

        client = SheetsClient(credentials_b64="dG9vc2hvcnQ=", spreadsheet_id="x")
        with pytest.raises(ValueError, match="length="):
            client.connect()

    def test_rejects_bad_base64(self):
        from src.output.sheets import SheetsClient

        # 100 chars of non-base64
        bad = "!" * 100
        client = SheetsClient(credentials_b64=bad, spreadsheet_id="test-id")
        with pytest.raises(Exception):
            client.connect()

    def test_accepts_valid_base64_credentials(self):
        """Valid base64 should pass the length check (will fail at Google auth)."""
        from src.output.sheets import SheetsClient

        creds_dict = {"type": "service_account", "project_id": "test"}
        valid_b64 = base64.b64encode(
            __import__("json").dumps(creds_dict).encode()
        ).decode()

        client = SheetsClient(credentials_b64=valid_b64, spreadsheet_id="test-id")
        # Should pass validation but fail at Google auth (no real credentials)
        with pytest.raises(Exception) as exc_info:
            client.connect()
        # Should NOT be a ValueError about invalid credentials
        assert "GOOGLE_CREDENTIALS looks invalid" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# Config loader credential plumbing
# ---------------------------------------------------------------------------

class TestResolveGoogleCredentials:
    """_resolve_google_credentials() should auto-detect credential format."""

    PLACEHOLDERS = {
        "your-base64-encoded-credentials-here",
        "eyJ0eXBlIjoic2VydmljZV9hY2NvdW50Ii...",
    }
    SAMPLE_JSON = '{"type":"service_account","project_id":"test"}'

    def test_file_env_var_loads_and_encodes(self, tmp_path):
        from src.core.config import _resolve_google_credentials

        creds_file = tmp_path / "sa.json"
        creds_file.write_text(self.SAMPLE_JSON, encoding="utf-8")

        with patch.dict(os.environ, {"GOOGLE_CREDENTIALS_FILE": str(creds_file)}):
            result = _resolve_google_credentials(None, self.PLACEHOLDERS)

        expected = base64.b64encode(self.SAMPLE_JSON.encode("utf-8")).decode("ascii")
        assert result == expected

    def test_file_env_var_missing_file_falls_through(self):
        from src.core.config import _resolve_google_credentials

        with patch.dict(os.environ, {"GOOGLE_CREDENTIALS_FILE": "/no/such/file.json"}):
            result = _resolve_google_credentials(None, self.PLACEHOLDERS)
        assert result is None

    def test_file_env_var_takes_priority_over_raw(self, tmp_path):
        from src.core.config import _resolve_google_credentials

        creds_file = tmp_path / "sa.json"
        creds_file.write_text(self.SAMPLE_JSON, encoding="utf-8")

        with patch.dict(os.environ, {"GOOGLE_CREDENTIALS_FILE": str(creds_file)}):
            result = _resolve_google_credentials("some_b64_value", self.PLACEHOLDERS)

        # Should use the file, not the raw value
        expected = base64.b64encode(self.SAMPLE_JSON.encode("utf-8")).decode("ascii")
        assert result == expected

    def test_raw_json_auto_encoded(self):
        from src.core.config import _resolve_google_credentials

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_CREDENTIALS_FILE", None)
            result = _resolve_google_credentials(self.SAMPLE_JSON, self.PLACEHOLDERS)

        expected = base64.b64encode(self.SAMPLE_JSON.encode("utf-8")).decode("ascii")
        assert result == expected

    def test_json_file_path_in_value(self, tmp_path):
        from src.core.config import _resolve_google_credentials

        creds_file = tmp_path / "creds.json"
        creds_file.write_text(self.SAMPLE_JSON, encoding="utf-8")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_CREDENTIALS_FILE", None)
            result = _resolve_google_credentials(str(creds_file), self.PLACEHOLDERS)

        expected = base64.b64encode(self.SAMPLE_JSON.encode("utf-8")).decode("ascii")
        assert result == expected

    def test_base64_passthrough(self):
        from src.core.config import _resolve_google_credentials

        pre_encoded = base64.b64encode(self.SAMPLE_JSON.encode()).decode("ascii")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_CREDENTIALS_FILE", None)
            result = _resolve_google_credentials(pre_encoded, self.PLACEHOLDERS)

        assert result == pre_encoded

    def test_placeholder_returns_none(self):
        from src.core.config import _resolve_google_credentials

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_CREDENTIALS_FILE", None)
            for placeholder in self.PLACEHOLDERS:
                result = _resolve_google_credentials(placeholder, self.PLACEHOLDERS)
                assert result is None, f"Placeholder '{placeholder}' should return None"

    def test_empty_and_none_return_none(self):
        from src.core.config import _resolve_google_credentials

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_CREDENTIALS_FILE", None)
            assert _resolve_google_credentials(None, self.PLACEHOLDERS) is None
            assert _resolve_google_credentials("", self.PLACEHOLDERS) is None

    def test_nonexistent_json_path_returns_none(self):
        from src.core.config import _resolve_google_credentials

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_CREDENTIALS_FILE", None)
            result = _resolve_google_credentials("/no/such/creds.json", self.PLACEHOLDERS)
        # Path doesn't exist, so not treated as file path — passed through as base64
        assert result == "/no/such/creds.json"


class TestConfigLoaderCredentials:
    """ConfigLoader should pass env vars through to OutputSettings."""

    def test_google_credentials_from_env(self):
        with patch.dict(os.environ, {"GOOGLE_CREDENTIALS": "test_b64_value"}, clear=False):
            from src.core.config import ConfigLoader
            config = ConfigLoader(config_dir="config")
            config.load()
            assert config.settings.output.google_credentials_b64 == "test_b64_value"

    def test_spreadsheet_id_from_env(self):
        with patch.dict(os.environ, {"SPREADSHEET_ID": "sheet_123"}, clear=False):
            from src.core.config import ConfigLoader
            config = ConfigLoader(config_dir="config")
            config.load()
            assert config.settings.output.spreadsheet_id == "sheet_123"

    def test_placeholder_credentials_treated_as_none(self):
        """Placeholder values from example.env should be treated as absent."""
        placeholders = [
            "your-base64-encoded-credentials-here",
            "eyJ0eXBlIjoic2VydmljZV9hY2NvdW50Ii...",  # old example.env
        ]
        for placeholder in placeholders:
            with patch.dict(os.environ, {"GOOGLE_CREDENTIALS": placeholder}, clear=False):
                from src.core.config import ConfigLoader
                config = ConfigLoader(config_dir="config")
                config.load()
                assert config.settings.output.google_credentials_b64 is None, (
                    f"Placeholder '{placeholder}' should be treated as None"
                )

    def test_placeholder_spreadsheet_id_treated_as_none(self):
        """Placeholder spreadsheet IDs from example.env should be treated as absent."""
        placeholders = [
            "your-spreadsheet-id-here",
            "1aBcDeFgHiJkLmNoPqRsTuVwXyZ",  # old example.env
        ]
        for placeholder in placeholders:
            with patch.dict(os.environ, {"SPREADSHEET_ID": placeholder}, clear=False):
                from src.core.config import ConfigLoader
                config = ConfigLoader(config_dir="config")
                config.load()
                assert config.settings.output.spreadsheet_id is None, (
                    f"Placeholder '{placeholder}' should be treated as None"
                )

    def test_missing_credentials_default_to_none(self):
        with patch.dict(
            os.environ,
            {"GOOGLE_CREDENTIALS": "", "SPREADSHEET_ID": ""},
            clear=False,
        ):
            # Remove them entirely so they default
            env = os.environ.copy()
            env.pop("GOOGLE_CREDENTIALS", None)
            env.pop("SPREADSHEET_ID", None)
            with patch.dict(os.environ, env, clear=True):
                from src.core.config import ConfigLoader
                config = ConfigLoader(config_dir="config")
                config.load()
                assert config.settings.output.google_credentials_b64 is None


# ---------------------------------------------------------------------------
# Setup script credential detection logic
# ---------------------------------------------------------------------------
# The setup scripts (setup.sh / setup.ps1) check whether Google credentials
# are already configured to decide whether to show the onboarding prompt.
# These tests replicate that detection logic in Python and verify it works
# correctly against the actual example.env content.
#
# This caught a real bug: the PowerShell script used a regex that matched
# commented-out lines like "# GOOGLE_CREDENTIALS_FILE=..." and silently
# skipped the entire Google Sheets onboarding prompt.


def _has_uncommented_google_creds(env_content: str) -> bool:
    """Replicate the setup script logic: check for UNCOMMENTED credential lines.

    Returns True if the .env content has active (uncommented) Google
    credentials, meaning the setup prompt should be SKIPPED.
    Returns False if no active credentials exist (prompt should SHOW).

    This mirrors the logic in setup.ps1 lines 149-150 and setup.sh lines 147-148.
    """
    for line in env_content.splitlines():
        stripped = line.strip()
        # Skip comments and empty lines
        if stripped.startswith("#") or not stripped:
            continue
        if stripped.startswith("GOOGLE_CREDENTIALS_FILE="):
            return True
        if stripped.startswith("GOOGLE_CREDENTIALS=") and not stripped.startswith(
            "GOOGLE_CREDENTIALS=your-"
        ):
            return True
    return False


class TestSetupScriptCredentialDetection:
    """Verify the setup script logic correctly distinguishes commented vs active creds.

    The setup scripts (setup.sh, setup.ps1) must show the Google Sheets
    onboarding prompt when .env has only commented-out credential examples,
    and skip it when real credentials are already configured.
    """

    def test_example_env_shows_prompt(self):
        """The shipped example.env should trigger the Google prompt (no active creds)."""
        example_env = Path(__file__).resolve().parents[2] / "config" / "example.env"
        content = example_env.read_text(encoding="utf-8")
        assert not _has_uncommented_google_creds(content), (
            "example.env should NOT be detected as having active Google credentials. "
            "Commented-out lines like '# GOOGLE_CREDENTIALS_FILE=...' must be ignored."
        )

    def test_example_env_after_api_key_replacement_still_shows_prompt(self):
        """After the setup script replaces the API key, Google prompt should still show."""
        example_env = Path(__file__).resolve().parents[2] / "config" / "example.env"
        content = example_env.read_text(encoding="utf-8")
        # Simulate what the setup script does: replace the API key placeholder
        content = content.replace(
            "ANTHROPIC_API_KEY=sk-ant-api03-your-key-here",
            "ANTHROPIC_API_KEY=sk-ant-api03-realkey123",
        )
        assert not _has_uncommented_google_creds(content)

    def test_uncommented_creds_file_detected(self):
        """An uncommented GOOGLE_CREDENTIALS_FILE= line means creds are configured."""
        content = (
            "ANTHROPIC_API_KEY=sk-ant-real\n"
            "GOOGLE_CREDENTIALS_FILE=/path/to/sa.json\n"
        )
        assert _has_uncommented_google_creds(content)

    def test_uncommented_creds_value_detected(self):
        """An uncommented GOOGLE_CREDENTIALS=<real-value> line means configured."""
        content = (
            "ANTHROPIC_API_KEY=sk-ant-real\n"
            "GOOGLE_CREDENTIALS=eyJ0eXBlIjoic2VydmljZV9hY2NvdW50Ii...\n"
        )
        assert _has_uncommented_google_creds(content)

    def test_commented_creds_file_not_detected(self):
        """Commented lines must NOT count as configured."""
        content = (
            "ANTHROPIC_API_KEY=sk-ant-real\n"
            "# GOOGLE_CREDENTIALS_FILE=path/to/service-account.json\n"
            "# GOOGLE_CREDENTIALS={\"type\":\"service_account\"}\n"
        )
        assert not _has_uncommented_google_creds(content)

    def test_your_placeholder_not_detected(self):
        """GOOGLE_CREDENTIALS=your-* placeholders should not count as configured."""
        content = "GOOGLE_CREDENTIALS=your-base64-here\n"
        assert not _has_uncommented_google_creds(content)

    def test_mixed_comments_and_active(self):
        """Only uncommented lines count, even when comments exist too."""
        content = (
            "# GOOGLE_CREDENTIALS_FILE=path/to/old.json\n"
            "GOOGLE_CREDENTIALS_FILE=/real/path.json\n"
        )
        assert _has_uncommented_google_creds(content)

    def test_empty_env_shows_prompt(self):
        """An empty .env should trigger the prompt."""
        assert not _has_uncommented_google_creds("")

    def test_only_api_key_shows_prompt(self):
        """An .env with only the API key should trigger the prompt."""
        content = "ANTHROPIC_API_KEY=sk-ant-real\n"
        assert not _has_uncommented_google_creds(content)

    def test_indented_uncommented_line_detected(self):
        """Whitespace before key should still be detected."""
        content = "  GOOGLE_CREDENTIALS_FILE=/path/to/sa.json\n"
        assert _has_uncommented_google_creds(content)


class TestSetupScriptRegexConsistency:
    """The regex patterns in setup.sh and setup.ps1 must match our Python logic."""

    @pytest.fixture(autouse=True)
    def _project_root(self):
        self.project_root = Path(__file__).resolve().parents[2]

    def test_powershell_checks_for_uncommented_lines(self):
        """setup.ps1 must split into lines and check start-of-line, not full-content match."""
        source = (self.project_root / "setup.ps1").read_text(encoding="utf-8")
        # Must NOT use simple substring match (the original bug)
        assert '-notmatch "GOOGLE_CREDENTIALS_FILE="' not in source, (
            "setup.ps1 must not use simple -notmatch on full content — "
            "it matches commented lines. Use per-line matching instead."
        )
        # Must use line-by-line matching with start-of-line anchor
        assert "-split" in source and "GOOGLE_CREDENTIALS_FILE=" in source

    def test_bash_checks_for_uncommented_lines(self):
        """setup.sh must use ^ anchor to skip commented lines."""
        source = (self.project_root / "setup.sh").read_text(encoding="utf-8")
        assert '"^GOOGLE_CREDENTIALS_FILE="' in source, (
            "setup.sh must use ^ anchor to match only uncommented lines"
        )
        assert '"^GOOGLE_CREDENTIALS="' in source


# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------

class TestDotenvDependency:
    """python-dotenv must be listed as a project dependency."""

    def test_dotenv_in_pyproject(self):
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        if pyproject.exists():
            assert "python-dotenv" in pyproject.read_text()
        else:
            pytest.skip("No pyproject.toml found")

    def test_dotenv_importable(self):
        from dotenv import load_dotenv
        assert callable(load_dotenv)
