# Continuity Document

## Current State

### Version: 0.3.3

### Just Completed: Content-Area Link Extraction (Backlog Item 2)

**What was done:**
- Modified `_extract_links()` in `async_crawler.py` to strip `<nav>`, `<header>`, `<footer>` tags and `role="navigation"` elements before extracting links
- This prevents global navigation menus (common on SPAs) from adding dozens of irrelevant links to the crawl queue
- Added `_NAV_TAGS_FOR_LINK_EXTRACTION` module-level constant
- Only structural nav tags are removed -- `<aside>`, `<section>`, `<article>`, `<main>` are preserved (sidebars may contain related bill links)
- Operates on BeautifulSoup's parsed tree (a copy), so it doesn't affect content extraction which uses `result.content`
- 6 new unit tests in `TestContentAreaLinkExtraction` class
- 603 tests pass

**Files changed:**
1. `src/crawler/async_crawler.py` - Added nav stripping in `_extract_links()`, `_NAV_TAGS_FOR_LINK_EXTRACTION` constant
2. `tests/unit/test_link_extractor.py` - 6 new tests in `TestContentAreaLinkExtraction`
3. `CHANGELOG.md` - Documented feature
4. `CONTINUITY.md` - This file

**Backlog status:** Items 1-2 DONE. See `docs/Backlog_20260204.md` for remaining items (3-9).

### Previously Completed: Global Crawl-Time Blocked Patterns (DRY improvement to Backlog Item 1)

**What was done:**
- Added `crawl_blocked_patterns` section to `config/url_filters.yaml` with ~30 common junk path patterns (auth flows, developer docs, admin areas, search/feeds, social/sharing, careers, media galleries)
- These global patterns apply to ALL domains at crawl time — domains no longer need to repeat common patterns like `/login`, `/developers/*`, `/admin/*`
- Domain-specific `blocked_path_patterns` merge additively: `blocked = global + domain-specific`
- Added `crawl_blocked_patterns` field to `URLFilterConfig` dataclass in `url_filter.py`
- Added `crawl_blocked_patterns` parameter to `AsyncCrawler.__init__()`
- Updated `main.py` to pass global patterns from URL filter config to crawler
- Cleaned up Virginia configs: removed patterns now covered globally, kept only site-specific patterns
- 5 new unit tests in `TestGlobalBlockedPatterns` class
- 597 tests pass

**Files changed:**
1. `config/url_filters.yaml` - Added `crawl_blocked_patterns` section (~30 patterns)
2. `src/analysis/url_filter.py` - Added `crawl_blocked_patterns` field to `URLFilterConfig`, load in `load_url_filters()`
3. `src/crawler/async_crawler.py` - Added `crawl_blocked_patterns` constructor param, merge in `_extract_links()`
4. `src/main.py` - Pass global patterns to `AsyncCrawler`
5. `config/domains/us/virginia.yaml` - Removed globally-covered patterns, kept site-specific only
6. `tests/unit/test_link_extractor.py` - 5 new tests in `TestGlobalBlockedPatterns`
7. `CHANGELOG.md` - Documented feature
8. `CONTINUITY.md` - This file

**Backlog status:** See `docs/Backlog_20260204.md` for remaining items (2-9).

### Previously Completed: Crawl-Time Path Pattern Filtering (Backlog Item 1)

**What was done:**
- Implemented `allowed_path_patterns` and `blocked_path_patterns` enforcement in `_extract_links()` in `async_crawler.py`
- These fields were already documented in `_template.yaml` and present on 128 of 275 domains, but the crawler never read them
- Uses `fnmatch` (glob-style) matching against lowercased URL paths
- Blocked patterns checked first (reject known-bad before allow-list check)
- Empty `allowed_path_patterns` = allow all (backward compatible)
- Start paths bypass filtering (added directly to queue by `crawl_domain()`)
- Added path patterns to Virginia domains: `va_legislature` and `us_va_hb323_2026`
- 10 new unit tests covering all filtering scenarios
- 592 tests pass

**Files changed:**
1. `src/crawler/async_crawler.py` - Added `fnmatch` import, path pattern filtering in `_extract_links()`
2. `config/domains/us/virginia.yaml` - Added `allowed_path_patterns` and `blocked_path_patterns` to `va_legislature` and `us_va_hb323_2026`
3. `tests/unit/test_link_extractor.py` - 10 new tests in `TestPathPatternFiltering` class
4. `CHANGELOG.md` - Documented feature
5. `CONTINUITY.md` - This file

### Previously Completed: `report` CLI Command

**What was done:**
- Created `src/reporting/` module with `run_report.py` (~420 lines) for parsing run logs and generating formatted terminal reports
- Parses JSON event stream from any run log, reconstructing per-domain stats via state machine (keyed on "Starting: {domain_id}" markers)
- Report sections: Header, Result Summary, Pipeline Funnel (visual bar chart), Domain Breakdown (blocked/error details), Filter Details (URL pre-filter + keyword reasons), Suggestions (heuristic rules), Configuration Summary
- Suggestion heuristics: zero policies bottleneck analysis, high block rate per domain, download errors, 404 stale URLs, timeout errors, captcha blocking
- Works with ALL existing log files (no new data needed); filter details only appear when `--verbose` was used during the run
- Added `report` subcommand in main.py with `--log` flag (same pattern as `last-run`)
- 31 unit tests covering parsing, formatting, suggestions, edge cases
- 582 tests pass

**Files changed:**
1. `src/reporting/__init__.py` - New package
2. `src/reporting/run_report.py` - Data model, event parser, report formatter, suggestions
3. `src/main.py` - Added `report` subcommand parser, `cmd_report()` handler, dispatch
4. `tests/unit/test_run_report.py` - 31 tests
5. `CHANGELOG.md` - Documented feature
6. `CONTINUITY.md` - This file

### Previously Completed: URL Filtering Fixes (CGI-bin, path-only check, config-driven extensions)

**What was done:**
- Fixed URL pre-filter `_check_extension()` in `url_filter.py` to exempt `/cgi-bin/` paths from `.exe` extension filtering — Virginia legislature CGI scripts (`legp604.exe?ses=251&typ=bil&val=hb116`) were incorrectly skipped as binary files
- Fixed link extractor `_extract_links()` in `async_crawler.py` to check `parsed.path.lower()` instead of `full_url.lower()` — query strings could interfere with extension matching
- Link extractor now uses `skip_extensions` from URL filter config (passed via `AsyncCrawler.__init__`) instead of a hard-coded 5-extension list, keeping crawl-time and analysis-time filtering consistent
- Added `_DEFAULT_SKIP_EXTENSIONS` fallback in `async_crawler.py` for when no config is provided
- Fixed `virginia.yaml` YAML indentation for `us_va_hb323_2026` domain entry
- Added `virginia` to `VALID_REGIONS` in `loader.py`
- 5 new tests in `test_url_filter.py` (CGI-bin exception), 9 new tests in `test_link_extractor.py`
- 551 tests pass

**Files changed:**
1. `src/analysis/url_filter.py` - CGI-bin exception in `_check_extension()`
2. `src/crawler/async_crawler.py` - Path-only extension check, config-driven extensions, `_DEFAULT_SKIP_EXTENSIONS`
3. `src/main.py` - Pass `skip_extensions` from URL filter config to `AsyncCrawler`
4. `config/domains/us/virginia.yaml` - Fixed YAML indentation
5. `src/config/loader.py` - Added `virginia` to `VALID_REGIONS`
6. `tests/unit/test_url_filter.py` - 5 new CGI-bin tests
7. `tests/unit/test_link_extractor.py` - 9 new tests (path-only, CGI-bin, config extensions)
8. `CHANGELOG.md` - Documented fixes
9. `CONTINUITY.md` - This file

### Previously Completed: Access Denied Diagnostic Logging

**What was done:**
- Added `_diagnose_response()` and `diagnose_denial_from_text()` in `http_fetcher.py` to analyze HTTP error responses (checks Server header for Cloudflare/Akamai, scans response body for 11 denial patterns)
- Fixed Playwright fetcher: HTTP 403/404/429 now correctly mapped to ACCESS_DENIED/NOT_FOUND/RATE_LIMITED (was all UNKNOWN_ERROR)
- Real-time log lines now include reason: `[WARN] access_denied: /path (HTTP 403 -- Cloudflare bot protection)`
- Verbose mode adds blocked-pages section: groups by status, shows per-page reasons, and provides actionable suggestions (e.g., "try requires_playwright: true")
- 9 new unit tests in `test_denial_diagnosis.py`
- 537 tests pass

**Files changed:**
1. `src/crawler/fetchers/http_fetcher.py` - Added `_diagnose_response()`, `diagnose_denial_from_text()`, `_DENIAL_PATTERNS`
2. `src/crawler/fetchers/playwright_fetcher.py` - Fixed status mapping, added diagnosis
3. `src/crawler/async_crawler.py` - Log line now includes error_message
4. `src/main.py` - Added blocked_details collection and verbose output block with suggestions
5. `tests/unit/test_denial_diagnosis.py` - 9 new tests
6. `CHANGELOG.md` - Added entries under [Unreleased]
7. `CONTINUITY.md` - This file

### Previously Completed: `--domains` Individual Domain ID Targeting

**What was done:**
- Added domain ID as a fallback in `get_enabled_domains()` resolution (step 5b, after file name match)
- `--domains us_va_hb323_2026` now scans just that single domain without needing a group
- Updated CLI help text, docstring, README resolution order, CHANGELOG
- 3 new unit tests: `test_domain_id_match`, `test_domain_id_skips_disabled`, `test_domain_id_fallback_order`
- 528 tests pass

### Previously Completed: DeepResearch Domain Integration (20260203_0818)

**What was done:**
- Integrated 17 domain entries from DeepResearch session with enriched metadata (verified tags, policy types, categories, detailed notes with regulatory specifics, `verified_by`/`verified_date` fields)
- Updated 11 YAML files: germany.yaml, eu.yaml, france.yaml, nordic.yaml, denmark.yaml, sweden.yaml, ireland.yaml, apac.yaml, switzerland.yaml, us/oregon.yaml, us/texas.yaml
- Expanded `VALID_REGIONS` in loader.py with 13 country/state-level regions: `europe`, `germany`, `france`, `netherlands`, `denmark`, `sweden`, `norway`, `ireland`, `switzerland`, `singapore`, `japan`, `oregon`, `texas`, `california`
- Expanded `VALID_CATEGORIES` with 10 new entries: `legislation`, `regulatory_authority`, `regulation`, `building_codes`, `guidance`, `policy`, `cantonal_authority`, `coordination_body`, `program`, `environment_ministry`
- Expanded `VALID_TAGS` with 60+ new entries covering regulatory specifics
- Expanded `VALID_POLICY_TYPES` with 10 new entries: `legislation`, `incentives`, `energy_efficiency`, `waste_heat_recovery`, `reporting_requirements`, `regulatory_authority`, `building_codes`, `grid_interconnection`, `district_heating`, `certification`
- Fixed 5 test groups in `groups.yaml` that referenced DeepResearch domain IDs instead of actual domain IDs
- Updated CHANGELOG.md, README.md

**Domains updated (17 across 11 files):**
- germany.yaml: `gesetze_enefg`, `bfee_dc_registry`
- eu.yaml: `rvo_nl`, `eurlex_eed_recommendation`
- france.yaml: `legifrance_dc`
- nordic.yaml: `lovdata_no`
- denmark.yaml: `ens_dk_heat`, `retsinformation_dk`
- sweden.yaml: `riksdagen_se_dc`
- ireland.yaml: `gov_ie_dc`, `cru_ie_dc`
- apac.yaml: `imda_sg`, `bca_sg_greenmark`, `enecho_jp`
- switzerland.yaml: `zh_dc_guidance`, `zh_energy_buildings`
- us/oregon.yaml: `or_building_codes`
- us/texas.yaml: `tx_legislature`

**Result:** 274 total domains. 525 tests pass.

**Files changed:**
1. `config/domains/germany.yaml` - Updated 2 domains
2. `config/domains/eu.yaml` - Updated 2 domains
3. `config/domains/france.yaml` - Updated 1 domain
4. `config/domains/nordic.yaml` - Updated 1 domain
5. `config/domains/denmark.yaml` - Updated 2 domains
6. `config/domains/sweden.yaml` - Updated 1 domain
7. `config/domains/ireland.yaml` - Updated 2 domains
8. `config/domains/apac.yaml` - Updated 3 domains
9. `config/domains/switzerland.yaml` - Updated 2 domains
10. `config/domains/us/oregon.yaml` - Updated 1 domain
11. `config/domains/us/texas.yaml` - Updated 1 domain
12. `src/config/loader.py` - Expanded VALID_REGIONS, VALID_CATEGORIES, VALID_TAGS, VALID_POLICY_TYPES
13. `config/groups.yaml` - Fixed 5 test groups
14. `CHANGELOG.md` - Added [Unreleased] section
15. `README.md` - Updated tables and counts

### Previously Completed: Verbose Pipeline Logging (`--verbose`)

**What was done:**
- Added detailed per-page diagnostic logging when `--verbose` flag is passed
- New `RunLogger.detail()` method for indented subordinate log lines without timestamps
- New `KeywordMatcher.get_failure_reason()` method returns the specific reason a page failed keyword filtering
- Modified `run_batch()` in `main.py` to collect verbose data during the page loop (collect-then-log pattern) and output organized blocks after the loop
- Near-miss reporting shows pages scoring >= 60% of keyword threshold, capped at 15 entries
- Zero overhead when `--verbose` is not passed

**Result:** 525 tests pass. Version bumped 0.2.4 → 0.3.0.

### Previously Completed: Deduplicate uk.yaml Domain Entries

**What was done:**
- Removed 3 duplicate entries from `config/domains/uk.yaml`:
  1. First `uk_legislation` entry (less complete) — kept second entry with more start_paths, `enabled: true`, allowed/blocked path patterns
  2. `nwf_uk` — empty stub duplicate of `uk_national_wealth_fund`
  3. `dfe_ni` — empty stub duplicate of `uk_ni_economy`
- Entries sharing a base_url but with different IDs and different crawl focus were kept (intentional separate crawl targets)

**Result:** UK domains: 77 → 74. Total enabled domains: 264. 521 tests pass.

**Files changed:**
1. `config/domains/uk.yaml` - Removed 3 duplicate entries
2. `CHANGELOG.md` - Documented fix
3. `CONTINUITY.md` - Updated current state

### Previously Completed: Fix California Domain YAML Structure

**What was done:**
- Restructured `config/domains/us/california.yaml`: 17 domain entries from Deep Research were bare YAML list items at root level (outside the `domains:` key) and missing `enabled: true`
- Moved all 17 entries under the `domains:` key with proper indentation
- Added `enabled: true` to each entry
- Normalized non-standard fields: `country` → removed, `confidence` → removed, `estimated_rate_limit` → `rate_limit_seconds`, `region: "US-California"` → `region: ["us", "us_states"]`
- Added standard schema fields: `category`, `tags`, `max_depth`, `verified_by`, `verified_date`
- Merged `justification` content into `notes` field
- Normalized `policy_types` to valid values (law, regulation, directive, incentive, guidance, standard, report)
- Removed dead 404 start path `/programs-and-topics/topics/data-centers` from `ca_energy`

**Result:** California domains went from 1 to 20. Total enabled domains: 266. 521 tests pass.

**Files changed:**
1. `config/domains/us/california.yaml` - Full restructure
2. `CHANGELOG.md` - Documented fix
3. `CONTINUITY.md` - Updated current state
4. `pyproject.toml` - Version bump 0.2.3 → 0.2.4

### Previously Completed: Fix Compound-Word Language Keyword Matching

**What was done:**
- Fixed `_compile_patterns()` in `src/analysis/keywords.py` to use substring matching (no `\b` word boundaries) for compound-word languages: German (de), Dutch (nl), Swedish (sv), Danish (da)
- English, French, Italian, and Spanish keywords retain `\b` word boundaries
- Added `COMPOUND_LANGUAGES` constant to `src/analysis/keywords.py`
- Added 14 unit tests for compound word matching across all four affected languages
- Added German policy text integration test using actual `config/keywords.yaml`

**Root cause:** `\b` word boundaries prevented keywords like "Abwärme" from matching inside compound words like "Rechenzentrumsabwärme", causing 0/383 pages to pass keyword filtering in German-language crawls.

**Files changed:**
1. `src/analysis/keywords.py` - Added `COMPOUND_LANGUAGES` constant, conditional pattern compilation
2. `tests/unit/test_keywords.py` - Added `TestCompoundLanguagesConstant`, `TestCompoundWordMatching`, `TestCompoundWordIntegration` classes
3. `CHANGELOG.md` - Documented fix under [Unreleased]
4. `CONTINUITY.md` - Updated current state
5. `pyproject.toml` - Version bump 0.2.1 -> 0.2.2

**Verification:** 521 tests pass.

### Also Completed: Disable Keyword Density Filter Default

**What was done:** Changed `config/keywords.yaml` density from `enabled: true, min_density: 1.0` to `enabled: false, min_density: 0`.

**Why:** The density gate (1.0 matches per 1000 chars) was too aggressive for real-world pages. HTML boilerplate (nav, header, footer) inflates character count, pushing density below threshold even for relevant pages. Evidence: 0/383 pages passed in Switzerland crawl, 0/83 in California crawl.

**Filtering now relies on:** keyword score + unique matches + required_combinations + Haiku screening + Sonnet analysis. Density can be re-enabled via `--min-density <value>` CLI flag.

### Previously: Split US Domains into Per-State Files

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

### COMPLETED: Merge Grid 6.x DeepResearch Entries into Per-State Files

**Goal:** Transfer all domain entries from 5 Grid 6.x DeepResearch files into the per-state YAML files under `config/domains/us/`. Also extract rejected-site entries into `config/rejected_sites/us.yaml` sorted by state.

**Result:** 117 entries merged across 8 states (IN:12, IA:11, MT:12, NV:12, SC:14, TN:15, UT:13, WI:9). 24 rejected entries written to `config/rejected_sites/us.yaml`. Total: 248 domains, 507 tests pass. Committed as `2297e5f`.

**Source files (all in `DeepResearch/`):**

| File | Format | Domain Entries | Rejected Entries | States |
|------|--------|---------------|-----------------|--------|
| Grid_6_1 (energy offices) | YAML | 15 | 5 | IA, IN, NV, UT, SC, TN, MT, WI |
| Grid_6_2 (legislative systems) | YAML | 19 | 8+ | IA, IN, NV, UT, SC, TN, MT, WI |
| Grid_6_3 (district heating) | Markdown tables | 47 | unknown | IA, IN, NV, UT, SC, TN, MT, WI |
| Grid_6_4 (grid operators) | Markdown tables | 23 | unknown | IA, IN, NV, UT, SC, TN, MT, WI |
| Grid_6_5 (economic dev) | YAML | 19 | 3 | IA, IN, NV, UT, SC, TN, MT, WI |
| **TOTAL** | | **123** | **16+** | **8 states** |

**CRITICAL: Duplicate ID handling**
Grid_6_2 and Grid_6_5 share duplicate domain IDs for legislative entries:
- `us_iowa_legislature` (Grid_6_2 vs Grid_6_5) - SAME base_url, different start_paths/focus
- `us_indiana_legislature` (Grid_6_5) vs `us_indiana_general_assembly` (Grid_6_2) - different IDs, OK
- `us_nevada_legislature` (Grid_6_2 vs Grid_6_5) - SAME base_url, different start_paths
- `us_utah_legislature` (Grid_6_2 vs Grid_6_5) - SAME base_url, different start_paths
- `us_south_carolina_legislature` (Grid_6_2) vs `us_sc_legislature` (Grid_6_5) - different IDs, OK
- `us_tennessee_general_assembly` (Grid_6_2) vs `us_tennessee_legislature` (Grid_6_5) - different IDs, OK
- `us_montana_legislature` (Grid_6_2) vs no equivalent in Grid_6_5
- `us_wisconsin_legislature` (Grid_6_2) vs `us_wisconsin_legislature` (Grid_6_5) - SAME ID!

**Resolution strategy for duplicates:**
- When same ID appears in both Grid_6_2 and Grid_6_5: MERGE start_paths from both, keep the more detailed notes (usually Grid_6_2), keep the more complete config
- When different IDs cover same site: Keep both as separate entries (different crawl focus)

**Entries per state (after dedup):**

**Iowa (IA):**
- Grid_6_1: us_ia_ieda_energy, us_ia_energy_plan
- Grid_6_2: us_iowa_legislature (MERGE with 6_5), us_iowa_admin_rules, us_iowa_admin_code_legis
- Grid_6_5: us_iowa_ieda, us_iowa_dor_datacenter, us_iowa_legislature (MERGE with 6_2)
- Grid_6_3: ~4 entries (need conversion from MD)
- Grid_6_4: ~2 entries (need conversion from MD)
- REJECTED from 6_1: Iowa Utilities Board

**Indiana (IN):**
- Grid_6_1: us_in_oed
- Grid_6_2: us_indiana_general_assembly, us_indiana_admin_code
- Grid_6_5: us_indiana_iedc, us_indiana_legislature
- Grid_6_3: ~6 entries (need conversion from MD)
- Grid_6_4: ~2 entries (need conversion from MD)
- REJECTED from 6_1: Indiana Utility Regulatory Commission

**Nevada (NV):**
- Grid_6_1: us_nv_goe, us_nv_leg_energy
- Grid_6_2: us_nevada_legislature (MERGE with 6_5), us_nevada_admin_code
- Grid_6_5: us_nevada_goed, us_nevada_legislature (MERGE with 6_2)
- Grid_6_3: ~5 entries (need conversion from MD)
- Grid_6_4: ~2 entries (need conversion from MD)

**Utah (UT):**
- Grid_6_1: us_ut_oed, us_ut_oed_efficiency
- Grid_6_2: us_utah_legislature (MERGE with 6_5), us_utah_admin_code
- Grid_6_5: us_utah_goeo, us_utah_legislature (MERGE with 6_2)
- Grid_6_3: ~9 entries (need conversion from MD)
- Grid_6_4: ~2 entries (need conversion from MD)

**South Carolina (SC):**
- Grid_6_1: us_sc_energy, us_sc_ors
- Grid_6_2: us_south_carolina_legislature, us_south_carolina_code
- Grid_6_5: us_sc_commerce, us_sc_dor, us_sc_legislature
- Grid_6_3: ~5 entries (need conversion from MD)
- Grid_6_4: ~4 entries (need conversion from MD)

**Tennessee (TN):**
- Grid_6_1: us_tn_tdec_oep, us_tn_tdec_financing
- Grid_6_2: us_tennessee_general_assembly, us_tennessee_bill_search
- Grid_6_5: us_tennessee_tnecd, us_tennessee_transparent, us_tennessee_legislature
- Grid_6_3: ~6 entries (need conversion from MD)
- Grid_6_4: ~2 entries (need conversion from MD)

**Montana (MT):**
- Grid_6_1: us_mt_deq_energy, us_mt_deq_resources
- Grid_6_2: us_montana_legislature, us_montana_bill_explorer, us_montana_code
- Grid_6_5: us_montana_commerce, us_montana_business
- Grid_6_3: ~8 entries (need conversion from MD)
- Grid_6_4: ~2 entries (need conversion from MD)
- REJECTED from 6_1: Montana PSC

**Wisconsin (WI):**
- Grid_6_1: us_wi_psc_oei, us_wi_leg_psc137
- Grid_6_2: us_wisconsin_legislature (MERGE with 6_5), us_wisconsin_legis_docs, us_wisconsin_admin_code
- Grid_6_5: us_wisconsin_wedc, us_wisconsin_legislature (MERGE with 6_2)
- Grid_6_3: ~4 entries (need conversion from MD)
- Grid_6_4: ~1 entry (need conversion from MD)

**Rejected sites for `config/rejected_sites/us.yaml` (sorted by state):**

From Grid_6_1 "EVALUATED BUT NOT RECOMMENDED":
- Iowa: Iowa Utilities Board (https://iub.iowa.gov)
- Indiana: Indiana Utility Regulatory Commission (https://www.in.gov/iurc)
- Montana: Montana Public Service Commission (https://psc.mt.gov)
- South Carolina: SC Public Service Commission (https://psc.sc.gov)
- Tennessee: Tennessee Regulatory Authority (https://www.tn.gov/tra)

From Grid_6_2 "SITES EVALUATED BUT NOT RECOMMENDED":
- All states: LegiScan (https://legiscan.com)
- All states: State Affairs Pro (https://pro.stateaffairs.com)
- All states: FastDemocracy (https://fastdemocracy.com)
- Utah: HEAL Utah Bill Tracker (https://www.healutah.org/billtracker/)
- Montana: MEIC Bill Tracker (https://meic.org/bill-tracker/)
- Montana: Montana Free Press Capitol Tracker
- Wisconsin: WI Green Fire (https://wigreenfire.org)
- Indiana: Citizens Action Coalition (https://www.citact.org)
- Utah: Utah League of Cities and Towns (https://www.ulct.utah.gov)
- Iowa: Iowa DD Council (https://www.iowaddcouncil.org)

From Grid_6_5 "EVALUATED - NOT RECOMMENDED":
- All states: Good Jobs First (https://goodjobsfirst.org)
- All states: BLS Strategies (https://www.blsstrategies.com)
- All states: Data Center Dynamics (https://www.datacenterdynamics.com)

**Execution plan:**
1. Write a Python script to:
   a. Parse Grid_6_1, 6_2, 6_5 YAML entries (they're bare lists, not wrapped in `domains:`)
   b. Group by state, deduplicate by ID (merge start_paths for duplicates)
   c. Append entries to existing per-state YAML files (after the existing entries or replacing the skeleton comment)
2. Read Grid_6_3 and Grid_6_4 markdown tables, convert to YAML entries, add to same state files
3. Extract all rejected-site entries, write to `config/rejected_sites/us.yaml` in proper schema
4. Validate: `load_settings()` loads all domains, no duplicate IDs, 507 tests pass
5. Commit and push

**Non-standard fields to normalize:**
- Grid_6_1/6_2/6_5 use `verified_by` and `verified_date` fields (not in template but harmless)
- Grid_6_1 uses `policy_types: ["grant_program"]` which isn't in VALID_POLICY_TYPES (should map to "incentive")
- Grid_6_5 uses tags like `property_tax`, `sales_tax`, `data_center` etc. not in VALID_TAGS (harmless, just non-standard)
- Grid_6_2 uses tags like `legislation`, `utilities`, `administrative` not in VALID_TAGS (harmless)

**After completion:** 8 states went from 0 entries to 9-15 entries each. Total domain count increased from 150 to 248.

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
