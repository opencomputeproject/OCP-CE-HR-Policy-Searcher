"""`python -m src.api`: load .env first, then hand the command line to uvicorn.

The entry point exists so that src/api/app.py can stop reading .env at import
(lesson PL-009). These tests pin the two halves of its job.
"""

import pytest

from src.api import __main__ as runner


class TestUvicornArgs:
    @pytest.mark.small
    def test_defaults_fill_in_host_and_port(self):
        assert runner.uvicorn_args([]) == [
            runner.APP, "--host", "127.0.0.1", "--port", "8000",
        ]

    @pytest.mark.small
    def test_the_callers_flags_win_and_everything_passes_through(self):
        assert runner.uvicorn_args(["--port", "9000", "--reload"]) == [
            runner.APP, "--port", "9000", "--reload", "--host", "127.0.0.1",
        ]
        assert runner.uvicorn_args(["--host=0.0.0.0", "--workers", "4"]) == [
            runner.APP, "--host=0.0.0.0", "--workers", "4", "--port", "8000",
        ]


class TestMain:
    @pytest.mark.small
    def test_loads_dotenv_from_the_project_root_then_starts_uvicorn(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            runner, "load_dotenv",
            lambda path, override: calls.append(("dotenv", path, override)),
        )
        monkeypatch.setattr(
            runner.uvicorn.main, "main",
            lambda args, standalone_mode: calls.append(("uvicorn", args, standalone_mode)) or 0,
        )

        rc = runner.main(["--reload"])

        assert rc == 0
        assert calls[0] == ("dotenv", runner._project_root / ".env", True)
        assert calls[1] == (
            "uvicorn",
            [runner.APP, "--reload", "--host", "127.0.0.1", "--port", "8000"],
            False,
        )
