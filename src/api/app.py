"""FastAPI application — REST API + WebSocket for OCP CE HR Policy Searcher."""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..core.log_setup import setup_logging
from .routes import domains, scans, policies, analysis, agent, logs

load_dotenv(override=True)  # .env wins over stale system env vars

# Structured logging: JSON to file, JSON to console (API/production mode).
# Uses the same unified config as the CLI agent.
data_dir = os.environ.get("OCP_DATA_DIR", "data")
setup_logging(data_dir, json_console=True, console_level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    logging.getLogger("ocp").info("OCP CE HR Policy Searcher starting")
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
app.include_router(logs.router)


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
            "logs": "/api/logs",
        },
    }


@app.get("/health")
def health():
    return {"status": "ok"}
