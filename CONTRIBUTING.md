# Contributing to OCP CE HR Policy Searcher

Thanks for your interest in contributing! This project helps the [Open Compute Project](https://www.opencompute.org/) track global data center heat reuse policies, and community contributions are welcome.

## Quick Start

```bash
git clone https://github.com/ahliana/OCP-CE-HR-Policy-Searcher.git
cd OCP-CE-HR-Policy-Searcher
.\setup.ps1 -Dev        # Linux/macOS: ./setup.sh --dev
```

This installs all dependencies including dev tools (pytest, ruff).

## Development Workflow

1. **Fork the repo** and clone your fork
2. **Create a branch**: `git checkout -b my-feature`
3. **Make your changes**
4. **Run tests and lint**:
   ```bash
   pytest                    # All 432 tests must pass
   ruff check src/ tests/    # No lint errors
   ```
5. **Commit** with a clear message (e.g., `feat: add Bulgarian keyword support`)
6. **Push and open a PR**

## What to Contribute

### Add a New Country or Region

This is the most impactful contribution. Follow these steps:

1. **Add keywords** in `config/keywords.yaml` — add terms in the country's language to all 7 categories (subject, policy_type, incentives, enabling, off_takers, context, energy)
2. **Create domain configs** in `config/domains/` — add 2-3 government websites (energy ministry + legislation database). Use `config/domains/germany.yaml` as a template
3. **If the language has compound words** (like German, Dutch, Hungarian), add its code to `COMPOUND_LANGUAGES` in `src/core/keywords.py`
4. **Add the region** to `VALID_REGIONS` in `src/core/config.py`
5. **Add TLD mappings** to `TLD_REGION_MAP` in `src/agent/domain_generator.py`
6. **Update groups** in `config/groups.yaml` with the new domain IDs
7. **Add tests** to `tests/unit/test_keywords.py` — see `TestEuropeanExpansionLanguages` for examples

### Improve Keyword Accuracy

Edit `config/keywords.yaml` to add terms, adjust weights, or add boost/penalty phrases. Test your changes:

```bash
python -m src.agent "Match keywords: 'your test text in any language'"
```

### Fix Bugs or Improve Code

All source code is in `src/`, organized as:

```
src/
├── agent/          # AI agent (CLI entry point, tool dispatch, domain generator)
├── core/           # Business logic (keywords, LLM, crawler, models, config)
├── orchestration/  # Parallel scan management, events, auditor
├── api/            # FastAPI REST API + WebSocket
├── output/         # Google Sheets export
├── mcp/            # MCP server (advanced)
└── storage/        # JSON persistence
```

See the [Architecture section](README.md#architecture) in the README for how the pipeline works.

## Code Style

- **Linter**: [ruff](https://docs.astral.sh/ruff/) — run `ruff check src/ tests/` before committing
- **Type hints**: Use Python type hints for function signatures
- **Docstrings**: Add docstrings to all public functions and classes
- **Models**: Use [Pydantic](https://docs.pydantic.dev/) BaseModel for data structures (see `src/core/models.py`)
- **Async**: Use `async/await` for I/O-bound operations (HTTP, API calls)
- **Config**: All tunable values go in YAML config files, not hardcoded in Python

## Testing

```bash
pytest                         # Run all tests
pytest tests/unit/             # Unit tests only (280+)
pytest tests/integration/      # Integration tests (109+)
pytest tests/unit/test_keywords.py -v  # Specific file, verbose
pytest --cov=src               # With coverage report
```

### Test Categories

| Category | Location | What it covers |
|----------|----------|----------------|
| Unit tests | `tests/unit/` | Keywords, models, API routes, agent tools, cache, crawler, verifier, sheets |
| Integration tests | `tests/integration/` | Full pipeline, agent loop, discovery workflow, onboarding |
| Edge case tests | across both | Missing files, invalid input, duplicates, error handling (~95 tests) |
| Onboarding tests | `test_full_pipeline.py` | Setup scripts, env files, banner, error messages (~51 tests) |

### Writing Tests

- Follow existing patterns in the test files
- Use `pytest.fixture` for shared setup
- Use `@pytest.mark.asyncio` for async tests
- Use `unittest.mock.AsyncMock` for mocking async methods
- Use `PolicyAgent.__new__(PolicyAgent)` pattern for testing the agent without a real API key (see `test_agent_loop.py`)

## Domain YAML Format

```yaml
domains:
  - id: "agency_cc"              # Unique ID: agency_countrycode
    name: "Government Agency Name"
    enabled: true
    base_url: "https://www.agency.gov.xx"
    region: ["eu", "eu_south", "country_name"]
    language: "xx"
    category: "energy_ministry"   # or: legislation_db, energy_regulator
    tags: ["energy_efficiency", "waste_heat"]
    policy_types: ["law", "regulation"]
    start_paths:
      - "/energy/policies/"
    allowed_path_patterns:
      - "/energy/*"
    blocked_path_patterns:
      - "/news/*"
      - "/press/*"
    max_depth: 3
    max_pages: 100
```

## PR Checklist

Before submitting a pull request, verify:

- [ ] `pytest` — all tests pass (no failures)
- [ ] `ruff check src/ tests/` — no lint errors
- [ ] New functions have docstrings
- [ ] New features have corresponding tests
- [ ] YAML files are valid (no syntax errors)
- [ ] Domain IDs follow the `agency_countrycode` convention
- [ ] If adding a language, it's added to all 7 keyword categories

## Questions?

Open an issue on GitHub or check the [README](README.md) for detailed documentation on every feature.
