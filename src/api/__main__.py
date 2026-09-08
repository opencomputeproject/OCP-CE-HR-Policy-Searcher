"""`python -m src.api` - the API server's entry point.

Loads the project `.env` (with `override=True`, so a stale or empty variable
in the shell loses to the file - `tests/unit/test_env_loading.py` pins why),
then starts uvicorn on `src.api.app:app`.

Importing `src.api.app` itself no longer touches `.env` (lesson PL-009). A
module that 90-odd test files and every tool import must not read the
developer's secrets as a side effect of being imported; loading the file is
this entry point's job, exactly as `src/agent/__main__.py` and
`src/mcp/server.py` do for theirs. The deployed container never used the
file at all: `.dockerignore` excludes it and compose supplies the variables
through `env_file`, so `uvicorn src.api.app:app` stays the right command
there.

    python -m src.api                                   # 127.0.0.1:8000
    python -m src.api --reload                          # development
    python -m src.api --host 0.0.0.0 --port 8000 --workers 4

Everything after `python -m src.api` is handed to uvicorn unchanged; host
and port default to 127.0.0.1 and 8000 when not given.
"""

import sys
from pathlib import Path

import uvicorn.main
from dotenv import load_dotenv

# Resolve .env from project root (2 levels up from src/api/__main__.py)
# so credentials load regardless of the process working directory.
_project_root = Path(__file__).resolve().parents[2]

APP = "src.api.app:app"
DEFAULTS = {"--host": "127.0.0.1", "--port": "8000"}


def uvicorn_args(argv: list[str]) -> list[str]:
    """The uvicorn command line: the app path, then the caller's arguments,
    then a default for any of host/port the caller did not set. Pure."""
    args = [APP, *argv]
    for flag, value in DEFAULTS.items():
        if not any(a == flag or a.startswith(flag + "=") for a in argv):
            args += [flag, value]
    return args


def main(argv: list[str] | None = None) -> int:
    load_dotenv(_project_root / ".env", override=True)
    args = uvicorn_args(sys.argv[1:] if argv is None else argv)
    # uvicorn's CLI is a click command; standalone_mode=False makes it return
    # instead of calling sys.exit, so this stays a plain function to test.
    result = uvicorn.main.main(args, standalone_mode=False)
    return int(result or 0)


if __name__ == "__main__":
    sys.exit(main())
