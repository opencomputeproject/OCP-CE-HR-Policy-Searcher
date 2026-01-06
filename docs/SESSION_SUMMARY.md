# OCP Heat Reuse Policy Searcher - Session Summary

**Date:** 2026-01-06
**Purpose:** Summary document for context continuity

---

## Project Overview

**What it is:** An automated tool that crawls government websites worldwide to discover data center heat reuse policies for the Open Compute Project (OCP) Heat Reuse Subproject.

**How it works:**
1. **Crawl** - Visit government websites, follow links up to 3 levels deep
2. **Extract** - Strip HTML to get clean text content
3. **Keyword Scan** - Score pages against 400+ multilingual terms (8 languages)
4. **AI Analysis** - Claude AI extracts policy details from high-scoring pages
5. **Filter** - Keep only policies with relevance score ≥5
6. **Output** - Write to Google Sheets, skip duplicates

**GitHub Repo:** https://github.com/ahliana/OCP-Heat-Reuse-Policy-Searcher (private)

---

## What Was Completed This Session

### 1. Repository Setup
- Initialized Git repository
- Created private GitHub repo under `ahliana` account
- Created `.gitignore` (excludes `.env`, `.keys/`, `venv/`, `logs/`, `snapshots/`)
- Pushed initial commit (42 files, 3,716 lines)

### 2. Multi-File Domain Configuration (MAJOR)
Restructured from single `domains.yaml` to scalable directory structure:

**Before:**
```
config/domains.yaml  (976 lines, all domains + groups in one file)
```

**After:**
```
config/
├── settings.yaml          # Runtime settings (unchanged)
├── keywords.yaml          # Search terms (unchanged)
├── groups.yaml            # NEW - Domain groups (user-editable!)
├── rejected_sites.yaml    # NEW - Track evaluated/rejected sites
└── domains/               # NEW - Domain files by region
    ├── _template.yaml     # Template for adding new domains
    ├── eu.yaml            # 10 EU domains
    ├── nordic.yaml        # 7 Nordic domains
    ├── us_federal.yaml    # 6 US federal domains
    ├── us_states.yaml     # 19 US state domains
    └── apac.yaml          # 6 APAC domains
```

**Total:** 48 domains across 5 regional files, 16 groups

### 3. Updated Config Loader (`src/config/loader.py`)
- Scans `config/domains/` directory for all `.yaml` files
- Merges domains from all files
- Loads groups from separate `config/groups.yaml`
- Backwards compatible (would still work with old single file)
- Added `list_groups()` and `list_domains()` helper functions

### 4. New CLI Commands (`src/main.py`)
Added subcommands:

```bash
# Reject a site (adds to rejected_sites.yaml)
python -m src.main reject-site --url "URL" --reason "Reason"
python -m src.main reject-site --url "URL" --reason "Reason" --evaluated-by "Name"

# List available groups
python -m src.main list-groups

# List all domains
python -m src.main list-domains
```

### 5. README Updates
- Added "How It Works" section with visual pipeline diagram
- Added "Before Running Any Commands" section (venv activation reminder)
- Updated Configuration section to document new file structure
- Updated "Adding a New Domain" instructions

### 6. Rejected Sites Tracking
Created `config/rejected_sites.yaml` to track:
- Sites evaluated but not useful
- Who evaluated them and when
- Reason for rejection
- Conditions to reconsider

---

## Current File Structure

```
OCP-Heat-Reuse-Policy-Searcher/
├── src/
│   ├── main.py              # Entry point + CLI commands
│   ├── config/
│   │   ├── loader.py        # Config loading (updated for multi-file)
│   │   └── settings.py      # Pydantic settings models
│   ├── crawler/
│   │   ├── async_crawler.py
│   │   ├── fetchers/        # http_fetcher.py, playwright_fetcher.py
│   │   ├── extractors/      # html_extractor.py
│   │   └── detection/       # paywall.py, captcha.py, js_required.py
│   ├── analysis/
│   │   ├── keywords.py      # Keyword matching
│   │   └── llm/             # client.py, prompts.py
│   ├── models/              # policy.py, crawl.py
│   ├── output/              # sheets.py
│   └── logging/             # run_logger.py
├── config/
│   ├── domains/             # Regional domain files
│   ├── groups.yaml          # User-editable groups
│   ├── rejected_sites.yaml  # Rejected sites tracking
│   ├── settings.yaml
│   └── keywords.yaml
├── tests/
├── .github/workflows/       # CI + monthly scan
├── README.md
└── pyproject.toml
```

---

## How to Run

```bash
# Activate virtual environment first!
.\venv\Scripts\activate      # Windows
source venv/bin/activate     # macOS/Linux

# Quick test (2 domains, no API calls)
python -m src.main --domains quick --dry-run --skip-llm

# Scan a region
python -m src.main --domains nordic --dry-run

# Full scan with LLM analysis
python -m src.main --domains eu
```

---

## Planned / Future Work

### Near-Term (discussed but not implemented)

1. **`--chunk` flag** - Run specific domain files (e.g., `--chunk us_states`)
2. **Run summaries** - Stats output (pages crawled, policies found, API costs)
3. **Unit tests** - For config loading, keyword matching
4. **Email notifications** - On completion/errors

### Medium-Term (from user requirements)

5. **Cost monitoring** - Track Claude API token usage
6. **Error alerting** - Detect stuck processes, rising costs
7. **GitHub Actions improvements** - Run regions in parallel, manual triggers
8. **Jupyter notebook** - For non-technical users (deferred pending team input)

### Long-Term (discussed)

9. **Web UI** - For non-technical users (Flask/Django admin or similar)
10. **Cloud hosting** - AWS Lambda / Google Cloud Run
11. **Database backend** - For run history, analytics

---

## Key Design Decisions

1. **Multi-file domains** - Scalability for 100+ domains, easier collaboration
2. **Separate groups.yaml** - Users can create custom groups without touching domain files
3. **Rejected sites tracking** - Prevents duplicate research, documents decisions
4. **Backwards compatible loader** - Old single-file structure would still work
5. **CLI subcommands** - `reject-site`, `list-groups`, `list-domains` for usability

---

## Environment Notes

- **Python:** 3.11+ required, 3.13 recommended
- **Virtual env:** `venv/` folder (must activate before running)
- **Platform:** Windows (user is on Windows)
- **GitHub CLI:** Authenticated as `ahliana`

---

## Files Modified This Session

1. `config/domains.yaml` - **DELETED** (replaced by directory structure)
2. `config/domains/*.yaml` - **CREATED** (5 regional files + template)
3. `config/groups.yaml` - **CREATED**
4. `config/rejected_sites.yaml` - **CREATED**
5. `src/config/loader.py` - **UPDATED** (multi-file loading)
6. `src/main.py` - **UPDATED** (added CLI subcommands)
7. `README.md` - **UPDATED** (How It Works, venv reminder, new structure docs)
8. `.gitignore` - **CREATED**

---

## Quick Reference: CLI Commands

```bash
# Scan commands
python -m src.main --domains GROUP [--dry-run] [--skip-llm] [--verbose]

# Utility commands
python -m src.main list-groups
python -m src.main list-domains
python -m src.main reject-site --url URL --reason "REASON" [--evaluated-by NAME]

# Available groups: all, eu, nordic, us, us_federal, us_states, apac,
#                   leaders, emerging, federal, test, quick, sample_nordic, sample_apac
```

---

## Contact / Context

- **Meeting:** Tomorrow at 10:00 (user mentioned)
- **User:** Working late (mentioned ~23:00 local time)
- **Goal:** Stabilize before meeting, potential continued work on session 2 items
