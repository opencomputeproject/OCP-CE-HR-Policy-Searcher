# Continuity Document

## Latest Change: Suppress XMLParsedAsHTMLWarning

### What was done
Suppressed BeautifulSoup's `XMLParsedAsHTMLWarning` in the two files where `BeautifulSoup(html, "lxml")` is called. Government sites (e.g., gesetze-im-internet.de) serve XHTML/XML content that triggers this warning. The `lxml` HTML parser handles this content correctly — the warning is informational only.

### Files modified
1. **`src/crawler/extractors/html_extractor.py`** — Added `import warnings`, imported `XMLParsedAsHTMLWarning` from `bs4`, added `warnings.filterwarnings("ignore", ...)` at module level
2. **`src/crawler/async_crawler.py`** — Same 3-line addition
3. **`CHANGELOG.md`** — Added entry under [Unreleased] > Fixed
4. **`pyproject.toml`** — Bumped version 0.1.0 -> 0.1.1

### Options considered
1. **Suppress warning (chosen)** — Zero behavior change, BS4-recommended approach
2. **Detect XML and switch parser** — Risk of subtle parsing differences (case sensitivity, namespaces)
3. **Skip XML pages entirely** — Too aggressive, XHTML pages can contain policy content
4. **Switch to html.parser** — Slower, less tolerant of malformed HTML

### Testing status
- [x] 489/489 tests pass
- [x] Ruff clean on changed files
- [ ] Commit pending user approval

---

## Previous Change: File-Based Domain Targeting

### What was done
Added the ability to use `--domains <filename>` to target all enabled domains from a specific YAML file in `config/domains/`, without requiring an entry in `groups.yaml`.

### Files modified
1. **`src/config/loader.py`** — `_source_file` tagging, file-name fallback in `get_enabled_domains()`, `get_available_domain_files()` helper
2. **`src/main.py`** — Import, help text, `cmd_list_groups()` display
3. **`tests/unit/test_config_loader.py`** — 11 new tests
4. **`README.md`** — Domain Files subsection, examples

### Design decisions
- Groups take priority over file names when names conflict (backward compatible)
- `_source_file` follows existing pattern from rejected sites loader
- Error message shows only file names not already covered by group names
