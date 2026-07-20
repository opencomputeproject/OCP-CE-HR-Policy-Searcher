"""FastAPI application — REST API + WebSocket for OCP CE HR Policy Searcher."""

import hmac
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..core.log_setup import setup_logging
from .routes import (
    domains, scans, policies, analysis, agent, ask, coverage, leads, logs,
    search, settings,
)

# Resolve .env from project root (2 levels up from src/api/app.py)
# so credentials load regardless of the process working directory.
_project_root = Path(__file__).resolve().parents[2]
load_dotenv(_project_root / ".env", override=True)

if not os.environ.get("OCP_DATA_DIR"):
    os.environ["OCP_DATA_DIR"] = str(_project_root / "data")

# Structured logging: JSON to file, JSON to console (API/production mode).
# Uses the same unified config as the CLI agent.
data_dir = os.environ["OCP_DATA_DIR"]
setup_logging(data_dir, json_console=True, console_level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    logging.getLogger("ocp").info("OCP CE HR Policy Searcher starting")
    # Apply the admin's saved cost level so scans started after a restart
    # (including cron-triggered ones) run on the chosen models.
    from .deps import get_config, get_cost_settings_store
    get_cost_settings_store().apply_to_config(get_config())
    yield
    logging.getLogger("ocp").info("OCP CE HR Policy Searcher shutting down")


app = FastAPI(
    title="OCP CE HR Policy Searcher",
    description=(
        "API for scanning government websites to discover data center "
        "heat reuse policies. Supports parallel domain scanning, "
        "real-time WebSocket progress, and LLM-powered policy extraction."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


def admin_token_configured() -> bool:
    return bool(os.environ.get("ADMIN_TOKEN"))


# Non-GET routes that stay open when admin mode is active:
# community lead submission and reader questions are the point of the
# reader-facing app. /api/ask has its own rate and daily spend limits.
_ADMIN_EXEMPT = {("POST", "/api/leads"), ("POST", "/api/ask")}

# Loopback addresses trusted when ADMIN_TOKEN is unset.
_LOOPBACK_HOSTS = {"127.0.0.1", "::1"}
# Starlette's TestClient has no real socket and reports its own host as the
# literal string "testclient" — nearly the whole unit test suite runs with
# ADMIN_TOKEN stripped (see tests/conftest.py) and exercises non-GET routes
# through it, so it must be trusted the same as a real loopback caller.
_TESTCLIENT_HOST = "testclient"


class AdminGateMiddleware(BaseHTTPMiddleware):
    """Shared-token gate for state-changing endpoints.

    When ADMIN_TOKEN is set, every non-GET /api request (except explicit
    exemptions) must carry a matching X-Admin-Token header. Reading stays
    open; scanning, chatting, settings, and review actions become
    admin-only — the access model agreed at the 2026-07-07 OCP call.

    When ADMIN_TOKEN is unset, the server is assumed to be a local,
    single-user deployment: non-GET /api requests are only accepted from
    loopback clients. A public deploy that forgot to set ADMIN_TOKEN would
    otherwise let any visitor start paid scans or replace the stored API
    key; a remote caller instead gets a 403 telling the operator to set
    ADMIN_TOKEN.
    """

    async def dispatch(self, request, call_next):
        if (
            request.url.path.startswith("/api")
            and request.method not in ("GET", "HEAD", "OPTIONS")
            and (request.method, request.url.path) not in _ADMIN_EXEMPT
        ):
            token = os.environ.get("ADMIN_TOKEN")
            if token:
                provided = request.headers.get("x-admin-token", "")
                if not hmac.compare_digest(provided, token):
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Administrator token required"},
                    )
            else:
                # A forwarded header means the request traversed a reverse
                # proxy (the deployment runs behind Caddy), so a loopback TCP
                # peer is the proxy itself, not the operator - treat it as
                # remote. Same reasoning as _client_ip in routes/ask.py.
                forwarded = request.headers.get("x-forwarded-for") or request.headers.get(
                    "x-real-ip"
                )
                host = request.client.host if request.client else ""
                if forwarded or (host not in _LOOPBACK_HOSTS and host != _TESTCLIENT_HOST):
                    return JSONResponse(
                        status_code=403,
                        content={
                            "detail": (
                                "This server has no ADMIN_TOKEN configured, so "
                                "admin actions are restricted to local requests. "
                                "Set the ADMIN_TOKEN environment variable to "
                                "allow this action remotely."
                            ),
                        },
                    )
        return await call_next(request)


app.add_middleware(AdminGateMiddleware)

# CORS — allow React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
app.include_router(domains.router)
app.include_router(scans.router)
app.include_router(policies.router)
app.include_router(analysis.router)
app.include_router(agent.router)
app.include_router(ask.router)
app.include_router(coverage.router)
app.include_router(leads.router)
app.include_router(logs.router)
app.include_router(search.router)
app.include_router(settings.router)


@app.get("/")
def root():
    return {
        "service": "OCP CE HR Policy Searcher",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "domains": "/api/domains",
            "scans": "/api/scans",
            "policies": "/api/policies",
            "analyze": "/api/analyze",
            "agent": "/api/agent",
            "leads": "/api/leads",
            "logs": "/api/logs",
        },
    }


@app.get("/health")
def health():
    return {"status": "ok", "admin_required": admin_token_configured()}
