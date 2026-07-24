"""Serve the built React frontend from the same FastAPI process.

Production runs one process on one port: this module mounts the CRA
``build/`` directory (hashed assets under ``static/``, plus ``index.html``)
onto an already-fully-routed FastAPI app, with client-side (SPA) routes
falling back to ``index.html``. When the build directory does not exist —
every current dev/test setup — ``mount_frontend()`` is a no-op and leaves
the app exactly as it was.
"""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Path prefixes handled by the API itself — the SPA fallback must never
# swallow a genuine 404 under these into index.html.
_RESERVED_PREFIXES = ("api/", "health")


def mount_frontend(app: FastAPI, static_dir: str | os.PathLike) -> bool:
    """Mount a built frontend onto ``app``. Returns whether it mounted.

    Call this after every API route is registered. If ``static_dir`` is
    not a directory, this does nothing and returns False (today's
    behavior, byte-identical). Otherwise:

    - ``static_dir/static`` (CRA's hashed JS/CSS) is mounted at ``/static``.
    - the existing ``/`` route (the JSON service-info page) is removed and
      replaced, along with a catch-all, so any non-API path serves the
      matching file under ``static_dir`` if one exists, or ``index.html``
      otherwise (SPA client-side routing).
    - ``/api/*`` and ``/health`` are left untouched; unknown paths under
      those prefixes still 404 instead of falling back to the SPA shell.
    """
    build_dir = Path(static_dir)
    if not build_dir.is_dir():
        return False

    index_file = build_dir / "index.html"

    assets_dir = build_dir / "static"
    if assets_dir.is_dir():
        app.mount("/static", StaticFiles(directory=assets_dir), name="frontend-static")

    # Drop the JSON "/" info route — the SPA owns "/" once a build exists.
    app.router.routes = [
        route
        for route in app.router.routes
        if not (getattr(route, "path", None) == "/" and "GET" in getattr(route, "methods", set()))
    ]

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        if full_path.startswith(_RESERVED_PREFIXES) or full_path == "api":
            raise HTTPException(status_code=404)

        candidate = build_dir / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_file)

    return True
