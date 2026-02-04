"""Smoke test for the help CLI command."""

from unittest.mock import MagicMock

from src.main import cmd_help


class TestHelpCommand:
    """Test the pretty help command."""

    def test_cmd_help_returns_zero(self):
        """cmd_help() should return 0 (success)."""
        args = MagicMock()
        assert cmd_help(args) == 0

    def test_cmd_help_prints_output(self, capsys):
        """cmd_help() should print formatted help text."""
        args = MagicMock()
        cmd_help(args)
        captured = capsys.readouterr()
        assert "OCP Heat Reuse Policy Searcher" in captured.out
        assert "SCANNING" in captured.out
        assert "FILTERING" in captured.out
        assert "VIEWING RESULTS" in captured.out
        assert "DOMAIN MANAGEMENT" in captured.out
        assert "COST & NOTIFICATIONS" in captured.out
