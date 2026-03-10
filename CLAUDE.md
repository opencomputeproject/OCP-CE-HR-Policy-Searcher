# CLAUDE.md

## Project
OCP CE HR Policy Searcher — automated discovery of government data center waste heat reuse policies.
Built for the Open Compute Project (OCP) Heat Reuse subproject.

## Repos
- OCP org: `opencomputeproject/OCP-CE-HR-Policy-Searcher` (primary)
- Personal: `ahliana/OCP-CE-HR-Policy-Searcher` (mirror)
- `git push origin main` pushes to BOTH via dual push URLs
- Branch: `main` (not master)

## Commands
- `python -m src.agent` — run CLI agent (interactive mode)
- `python -m src.agent "message"` — single command mode
- `pytest` — run all tests (514+, must all pass before commits)
- `ruff check src/ tests/` — lint (must pass before commits)
- `python -m src.api` — run FastAPI server

## Architecture
```
src/
├── agent/        # CLI entry point (__main__.py), orchestrator (AI agent loop), tools
├── core/         # Business logic: crawler, keywords, llm, scanner, config, models, log_setup
├── orchestration/ # Parallel scan_manager, events, auditor
├── api/          # FastAPI REST API + WebSocket (routes/ subpackage)
├── output/       # Google Sheets export (gspread + tenacity retry)
├── mcp/          # MCP server (11 tools)
└── storage/      # JSON persistence (PolicyStore with atomic writes)
```
Config: `config/` — YAML files for domains, keywords, groups, settings.
Data: `data/` — runtime output (policies.json, logs/, gitignored).

## Key Patterns
- Python 3.11+, async/await throughout, Pydantic models for all data structures
- `structlog` over stdlib logging — JSON file logs + human console output
- `log_audit_event()` for crash-safe audit trail (fsync to `data/logs/audit.jsonl`)
- `SESSION_ID` per-process for log correlation across concurrent agents
- Rate limit retry with exponential backoff at 3 layers: agent loop, scanner analysis, scanner screening
- Per-domain persistence: save after each domain completes, not just at scan end
- Incremental Google Sheets export: write per-domain, reconcile at end
- `PolicyAgent.__new__(PolicyAgent)` pattern to test agent without API key
- `anthropic.RateLimitError.__new__()` with mock response to create catchable test exceptions

## Testing
- Unit tests: `tests/unit/` — mock everything, no network/API calls
- Integration tests: `tests/integration/` — full pipeline, agent loop, discovery
- Use `pytest.fixture`, `@pytest.mark.asyncio`, `unittest.mock.AsyncMock`
- Test file naming: `test_{module}.py` matching `src/{package}/{module}.py`

## Gotchas
- Windows: can't rename directories while processes have open handles — close sessions first
- `MagicMock` used as filesystem path creates junk directories (e.g., `MagicMock/`) — clean up after tests
- `MagicMock(spec=Exception)` can't be raised/caught — use `ExceptionClass.__new__(ExceptionClass)` instead
- `log_audit_event()` does NOT auto-include `session_id` — only includes explicitly passed `**fields`
- `ruff check` before commit — line length 100 chars (`pyproject.toml`)
- The project was renamed from `ocp-policy-hub` in March 2026 — no old-name references should exist
- License: MIT (matches OCP org standard)
