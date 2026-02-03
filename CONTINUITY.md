# Continuity Document

## Current State

### Just Completed: Split US Domains into Per-State Files

**What was done:**
- Split `config/domains/us_states.yaml` (19 entries, 16 states) into 50 individual per-state YAML files under `config/domains/us/`
- Moved `config/domains/us_federal.yaml` into `config/domains/us/` subdirectory
- Migrated all existing domain entries preserving exact YAML formatting
- Created empty skeleton templates for 34 states without entries (ready for DeepResearch)
- Fixed `_load_domains_directory()` in `loader.py:49` to handle `None` domains value (`content.get("domains") or []`)
- Fixed Windows console `UnicodeEncodeError` in `notifications.py`
- Enabled `context` keyword category in `keywords.yaml`

**Files changed:**
1. `config/domains/us/*.yaml` - 50 new per-state files + us_federal.yaml (moved)
2. `config/domains/us_states.yaml` - DELETED (migrated)
3. `config/domains/us_federal.yaml` - DELETED (moved to us/)
4. `src/config/loader.py` - Fixed None domains handling
5. `src/utils/notifications.py` - Fixed UnicodeEncodeError
6. `config/keywords.yaml` - Enabled context category
7. `CHANGELOG.md` - Updated [Unreleased]
8. `README.md` - Updated directory tree and domain file references

**Verification:** 150 domains load correctly, 507 tests pass.

### Previously Completed: Add `region` Field to Domain Configuration (v0.2.0)

**What was built:**
- Added `region` field (list of strings) to every domain in all YAML files
- Modified `get_enabled_domains()` to merge group + region results (union, deduplicated)
- Added `VALID_REGIONS` dict with 7 geographic regions: `eu`, `nordic`, `eu_central`, `eu_west`, `us`, `us_states`, `apac`
- Added `list-regions` CLI command
- Updated `list-groups` to show region-contributed domains
- Added startup warnings for enabled domains missing `region` field
- Added region counts to `domain-stats` output
- Updated `_template.yaml` with region documentation
- Fixed several country files (france, switzerland, austria, belgium, ireland) that were missing `domains:` YAML wrapper

**Resolution order for `--domains eu`:**
1. `"all"` -> all enabled domains (unchanged)
2. Check groups.yaml for group name -> get listed domain IDs
3. Check `region` field on all domains -> any domain with the name in its region list
4. **Merge steps 2 and 3** -- union of both, deduplicated by domain ID
5. If nothing matched from groups or region, fall back to file name match (existing)
6. If still nothing, error with helpful message

**Region assignments:**
- EU institution domains -> `["eu"]`
- German domains -> `["eu", "eu_central"]`
- Nordic EU members (SE, DK, FI) -> `["eu", "nordic"]`
- Norway, Iceland -> `["nordic"]` (not EU members)
- France -> `["eu", "eu_central"]`
- Switzerland -> `["eu_central"]` (not EU, but geographically central European)
- Austria -> `["eu", "eu_central"]`
- Netherlands, Belgium, Ireland -> `["eu", "eu_west"]`
- US federal -> `["us"]`
- US states -> `["us", "us_states"]`
- APAC -> `["apac"]`

**Files changed:**
1. `src/config/loader.py` - VALID_REGIONS, modified get_enabled_domains(), warn_missing_regions(), list_regions(), updated list_domains(), get_domain_stats()
2. `src/main.py` - list-regions command, updated list-groups, cmd_list_regions(), region warnings at startup, cmd_domain_stats region display
3. `config/domains/*.yaml` - All 14 domain files updated with region field
4. `config/domains/_template.yaml` - Added region field with documentation
5. `tests/unit/test_config_loader.py` - 15 new tests for region resolution, warnings, integration
6. `README.md` - Documented region field, resolution order, updated domain config guide
7. `CHANGELOG.md` - Added under [Unreleased]
8. `pyproject.toml` - Version bumped to 0.2.0

### Git state
- Branch: master
- Remote: origin (https://github.com/ahliana/OCP-Heat-Reuse-Policy-Searcher.git)
- Pending commit for region feature (v0.2.0)

---

## Recently Completed

### Commit dbbaf5d -- Suppress XMLParsedAsHTMLWarning (v0.1.1)
- Added `warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)` to:
  - `src/crawler/extractors/html_extractor.py`
  - `src/crawler/async_crawler.py`
- Updated CHANGELOG.md under [Unreleased] > Fixed
- Bumped version 0.1.0 -> 0.1.1
- Pushed to origin/master

### Commit eb01d72 -- Add initial CHANGELOG.md (v0.1.0)
- Created comprehensive CHANGELOG.md with all 0.1.0 features
- Set pyproject.toml version to 0.1.0
- Pushed to origin/master

### Commit 702b123 -- File-based domain targeting
- `--domains germany` now works without groups.yaml entry
- Added `_source_file` tagging, file-name fallback, `get_available_domain_files()` helper
- 11 new tests, README updated
- Pushed to origin/master

### User preferences
- Uses the ImplementationRequest_ClaudeCode.md template (in docs/)
- Wants TODO tracking with TodoWrite tool
- Wants CONTINUITY.md kept current
- Wants to see commit message before committing
- Wants to approve push separately
- Semantic versioning: minor bump for new features
