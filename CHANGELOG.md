# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- MutationObserver-based DOM stabilization for Playwright fetcher: replaces `wait_until="networkidle"` with `domcontentloaded` + a MutationObserver that waits for the DOM to stop changing (500ms of no mutations, 10s max timeout). This correctly captures SPA-rendered content on React/Vue/Angular sites without timing out on analytics polling or WebSocket connections. Static pages resolve near-instantly via "already-stable". Falls back gracefully if JS evaluation fails
- Crawl-time path pattern filtering: `allowed_path_patterns` and `blocked_path_patterns` in domain YAML configs are now enforced during link extraction, preventing the crawler from following irrelevant links that waste the page budget (e.g., `/developers/*`, `/login` on SPA sites)
- Global `crawl_blocked_patterns` in `config/url_filters.yaml`: ~30 common junk path patterns (auth, developer docs, admin, search, careers, media) applied to ALL domains at crawl time, so individual domain configs only need site-specific patterns. Domain `blocked_path_patterns` merge additively with global patterns
- Content-area link extraction: `_extract_links()` now strips `<nav>`, `<header>`, `<footer>`, and `role="navigation"` elements before harvesting links, preventing global navigation menus from consuming the crawl budget on SPA sites
- Multi-signal keyword scoring with URL bonuses: pages on government domains (+1.0), with bill/legislation paths (+1.5), or containing bill numbers like HB323/SB192 in the URL (+1.0) get bonus points added to their keyword score. This fixes the HB323 discovery failure where terse legislative text scored 4.0 against a 5.0 threshold -- the URL bonus of +3.5 now pushes it to 7.5
- Configurable URL bonus patterns in `config/keywords.yaml`: government TLD patterns (`.gov`, `.gov.uk`, `.gouv.fr`, `.gv.at`, `.admin.ch`, `.go.jp`, `.gov.sg`, `.europa.eu`, etc.), legislation path patterns (`/gesetze/`, `/lois/`, `/celex/`, `/legal-content/`), and bill number patterns are now loaded from YAML config instead of hardcoded Python constants. Bonus values are also configurable. Previously only `.gov` and `.gov.uk` got the TLD bonus -- now 12 international government domain suffixes are supported out of the box
- Per-domain config overrides: `max_pages` and `min_keyword_score` fields in domain YAML configs override global `max_pages_per_domain` and `minimum_keyword_score` settings. Allows tight page budgets for focused single-bill domains and lower keyword thresholds for terse legislative text. `domain_id` is now set on each `CrawlResult` to enable per-domain config lookup during analysis
- Integrated 17 domain entries from DeepResearch session (20260203_0818) with enriched metadata across 11 YAML files: verified tags, policy types, categories, notes with specific regulatory details, `verified_by`/`verified_date` fields
- 13 country-level and state-level geographic regions: `europe`, `germany`, `france`, `netherlands`, `denmark`, `sweden`, `norway`, `ireland`, `switzerland`, `singapore`, `japan`, `oregon`, `texas`, `california`
- 10 new domain categories: `legislation`, `regulatory_authority`, `regulation`, `building_codes`, `guidance`, `policy`, `cantonal_authority`, `coordination_body`, `program`, `environment_ministry`
- 60+ new domain tags covering regulatory specifics: `mandatory`, `waste_heat`, `pue_limits`, `cost_benefit_analysis`, `district_heating`, `renewable_energy`, `ashrae_90_4`, `tax_exemption`, `grid_connection`, and more
- 10 new policy types: `legislation`, `incentives`, `energy_efficiency`, `waste_heat_recovery`, `reporting_requirements`, `regulatory_authority`, `building_codes`, `grid_interconnection`, `district_heating`, `certification`
- 5 test groups in `groups.yaml` for validating new domains: `test_new`, `test_new_zh`, `test_new_de`, `test_new_eu`, `test_new_us`
- `--domains` now accepts individual domain IDs (e.g., `--domains us_va_hb323_2026`) to scan a single domain without creating a group
- Access denied diagnostic logging: HTTP 403 and other blocked responses now include the reason (Cloudflare bot protection, Akamai WAF, Access Denied, rate limited, etc.) in both real-time log output and verbose summary
- Verbose mode blocked-pages section with per-page reasons and actionable suggestions (e.g., "try requires_playwright: true")
- `report` CLI command: generates a detailed formatted report from any run log with header, result summary, pipeline funnel (visual bar chart), per-domain breakdown with blocked/error details, URL filter and keyword filter analysis, actionable suggestions, and configuration summary. Accepts `--log` flag for selecting runs by index, date, or run ID

### Fixed
- URL pre-filter `.exe` extension check now exempts CGI-bin paths (`/cgi-bin/*.exe?...`), which are dynamic scripts returning HTML (e.g., Virginia legislature `legp604.exe`)
- Link extractor now checks file extension on URL path only, not full URL with query string — previously a query like `?val=hb116` could prevent extension matching
- Link extractor extension list now uses `skip_extensions` from `config/url_filters.yaml` instead of a hard-coded list, keeping crawl-time and analysis-time filtering consistent
- Fixed `virginia.yaml` YAML indentation for `us_va_hb323_2026` domain entry
- Playwright fetcher now correctly maps HTTP 403/404/429 to ACCESS_DENIED/NOT_FOUND/RATE_LIMITED (previously all were UNKNOWN_ERROR)

### Changed
- Domain YAML files now use country-level regions (e.g., `germany` instead of only `eu_central`, `singapore` instead of only `apac`) for finer-grained geographic filtering
- Domain categories aligned with DeepResearch taxonomy (e.g., `legislation` instead of `legislative`, `regulation` instead of `regulatory`)
- Domain notes enriched with specific regulatory thresholds, effective dates, article numbers, and compliance requirements from DeepResearch verification

### Fixed
- Fixed `groups.yaml` test groups referencing DeepResearch domain IDs instead of actual domain IDs (e.g., `us_ca_title24_computer_rooms` → `ca_energy`)

## [0.3.0] - 2026-02-03

### Added
- Verbose pipeline logging (`--verbose`): when enabled, logs per-page diagnostic details at every filtering stage (URL pre-filter, keyword matching, Haiku screening, Sonnet analysis) so users can understand exactly why pages were filtered out
- `RunLogger.detail()` method for indented subordinate log lines without timestamps
- `KeywordMatcher.get_failure_reason()` method that returns the specific reason a page failed keyword filtering
- Near-miss reporting in verbose mode: shows pages that scored >= 60% of the keyword threshold but still failed, capped at 15 entries
- Merged 117 domain entries from 5 Grid 6.x DeepResearch files into 8 per-state YAML files (IA, IN, NV, UT, SC, TN, MT, WI) covering energy offices, legislative systems, district heating/waste heat, grid operators/regulators, and economic development
- Created `config/rejected_sites/us.yaml` with 24 rejected site entries sorted by state from all Grid 6.x files
- Geographic `region` field on all domain YAML entries (list of strings: `eu`, `nordic`, `eu_central`, `eu_west`, `uk`, `us`, `us_states`, `apac`)
- `--domains` now merges group and region matches: `--domains eu` returns the union of the `eu` group from `groups.yaml` AND any domain with `region: ["eu"]`
- `list-regions` CLI command to show available geographic regions with domain counts
- `list-groups` output now shows how many extra domains each group gains via region tags
- Startup warning for any enabled domain missing the `region` field
- `VALID_REGIONS` constant and `list_regions()`, `warn_missing_regions()` functions in loader
- Region counts in `domain-stats` output
- Updated `_template.yaml` with region field and documentation

### Changed
- Disabled keyword density filter by default (`min_density: 0`) in `config/keywords.yaml`. The required_combinations check + two-stage LLM screening (Haiku → Sonnet) provide sufficient filtering. The density gate was too aggressive for real-world pages with HTML boilerplate, causing 0% pass rate. Can be re-enabled via `--min-density <value>`.
- Split `us_states.yaml` into 50 individual per-state YAML files under `config/domains/us/` (e.g., `texas.yaml`, `virginia.yaml`, `alabama.yaml`) to support incremental per-state research
- Moved `us_federal.yaml` into `config/domains/us/` subdirectory alongside state files
- Enabled `context` keyword category in `config/keywords.yaml` (data center terms now required in combination matching)

### Fixed
- Removed 3 duplicate entries from `config/domains/uk.yaml`: first `uk_legislation` (less complete, kept second with more start_paths), `nwf_uk` (empty stub of `uk_national_wealth_fund`), `dfe_ni` (empty stub of `uk_ni_economy`). UK domains: 77 → 74.
- Fixed `config/domains/us/california.yaml` structure: 17 domain entries from Deep Research were bare YAML list items at root level (outside the `domains:` key) and missing `enabled: true`. Restructured all entries under `domains:` with standard schema fields (`region`, `category`, `tags`, `rate_limit_seconds`). California domains went from 1 to 20 (total domains: 248 → 266).
- Fixed keyword matching for compound-word languages (German, Dutch, Swedish, Danish) by using substring matching instead of `\b` word boundaries for `de`, `nl`, `sv`, `da` patterns. Previously, keywords like "Abwärme" and "Rechenzentrum" failed to match inside compound words like "Rechenzentrumsabwärme", causing 0% keyword pass rate on German pages.
- Suppress BeautifulSoup `XMLParsedAsHTMLWarning` when crawling XHTML/XML pages (e.g., German law database)
- Fixed several country domain files (france, switzerland, austria, belgium, ireland) missing `domains:` YAML wrapper key
- Fixed `switzerland.yaml` duplicate `domains:` key causing only last block to load (17 domains now load correctly)
- Fixed `rejected_sites/uk.yaml` mixed format: merged bare list entries from DeepResearch output into proper `rejected_sites:` schema (27 entries)
- Fixed domain loader crash on empty YAML domain files where `domains:` key parses as `None` instead of `[]`
- Fixed Windows console `UnicodeEncodeError` in email notification error logging

## [0.1.0] - 2026-02-03

Initial release of the OCP Heat Reuse Policy Searcher.

### Added

#### Core Pipeline
- Automated multi-step policy discovery pipeline: crawl, extract, keyword scan, LLM analysis, filter, output
- Asynchronous HTTP crawling with configurable rate limiting, retries, and depth control
- Playwright browser fallback for JavaScript-heavy government sites
- Configurable content extraction via `config/content_extraction.yaml` with boilerplate removal (nav, ads, cookie banners, social widgets, newsletter signups, sidebars stripped)
- Content extraction options: custom remove tags, regex patterns for class/id matching, content indicator patterns, min/max content length
- Automatic language detection for crawled pages
- Paywall, CAPTCHA, login-wall, and JavaScript-requirement detection with human review flagging

#### Keyword Analysis
- Weighted multi-language keyword matching (English, German, French, Dutch, Swedish, Danish)
- Keyword density calculation (matches per 1000 characters)
- Category-based combination requirements (e.g., requires both "data center" AND "heat" terms)
- Boost keywords for high-value phrases and penalty keywords for generic content
- CLI overrides for keyword tuning: `--min-keyword-score`, `--require-combinations`, `--min-density`

#### LLM Analysis
- Two-stage LLM pipeline: Haiku screening then Sonnet deep analysis (up to 75% cost savings)
- Policy extraction: name, jurisdiction, type, summary, relevance score (1-10), effective date, bill number, key requirements
- 11 policy type classifications: law, regulation, directive, incentive, tax incentive, grant, plan, requirement, standard, guidance, matching platform
- Configurable screening confidence threshold
- Robust error handling: parse error recovery, rate limit handling, authentication error detection
- Automatic type coercion for common LLM response issues (null/missing policy_type defaults, string-to-boolean conversion)

#### URL Pre-Filtering
- Path-based and regex-based URL filtering before crawling
- File extension filtering (.pdf, .doc, .zip, etc.)
- 40+ predefined skip rules (login pages, support pages, legal boilerplate, e-commerce, media galleries)
- Domain-specific filter overrides
- Filter effectiveness statistics in run summaries

#### URL Result Caching
- Persistent JSON-based cache (`data/url_cache.json`) to skip re-analyzing unchanged pages
- Content hash-based change detection with configurable expiry (default: 30 days)
- Cache hit/miss tracking and statistics reporting
- `--no-cache` and `--clear-cache` CLI options

#### Domain Configuration
- Multi-file domain configuration in `config/domains/` with recursive subdirectory support
- Template file (`_template.yaml`) for adding new domains
- Per-domain settings: start paths, max depth, Playwright requirement, rate limiting, language
- Domain categorization with categories, tags, and policy types
- File-based domain targeting: `--domains germany` loads directly from `config/domains/germany.yaml` without needing a `groups.yaml` entry
- Automatic inclusion of all enabled domains in the `all` group

#### Domain Groups & Filtering
- 15 predefined domain groups: regional (eu, nordic, us, apac, eu_central, eu_west, us_states), thematic (federal, leaders, emerging), and testing (test, quick, sample_nordic, sample_apac)
- Custom group creation via `config/groups.yaml`
- Category filtering (`--category`) across 8 categories: energy_ministry, environmental_agency, legislative, district_heating, grid_operator, economic_dev, regulatory, standards
- Tag filtering (`--tag`, `--match-all-tags`) across 7 tags: incentives, mandates, reporting, carbon, efficiency, planning, research
- Policy type filtering (`--policy-type`) across 7 types: law, regulation, directive, incentive, guidance, standard, report

#### Google Sheets Output
- Automatic policy output to Google Sheets "Staging" worksheet
- Duplicate detection to prevent re-adding existing policies
- Automatic worksheet creation if missing
- `--dry-run` mode for testing without writing results
- 13-column output format: URL, Policy Name, Jurisdiction, Policy Type, Summary, Relevance Score, Source Language, Effective Date, Bill Number, Key Requirements, Discovered At, Crawl Status, Review Status

#### Chunking & Batch Processing
- Auto-chunking: `--chunk-size N` processes N domains at a time with configurable pause (`--chunk-delay`)
- Manual chunking: `--chunk N/M` for running specific chunks (useful for retries and parallel CI jobs)
- Batch statistics accumulation across chunks

#### Cost Tracking & Monitoring
- Per-run cost calculation with separate Haiku/Sonnet breakdowns
- Persistent cost history (`logs/cost_history.json`) across all runs
- Cost breakdown always visible in run summaries
- `estimate-cost` command for pre-scan cost predictions
- `cost-history` command for cumulative usage and trends
- Monthly budget warnings at configurable thresholds (default: warn at 80%, alert at 100%)

#### Run Logging & History
- JSON-formatted run logs with timestamped run IDs (`logs/run_YYYYMMDD_HHMMSS.json`)
- Formatted run summary at scan completion: crawl stats, policy stats, LLM stats, cost breakdown
- `--verbose-summary` for detailed configuration and cost breakdown in run logs
- `last-run` command to view any previous run's summary or configuration
- `list-runs` command to browse all available run logs

#### Email Notifications & Alerts
- SMTP email notifications (Gmail compatible) with TLS support
- 8 notification triggers: scan complete, scan failed, budget warning, budget exceeded, high error rate, cost spike, no policies found, connection errors
- Priority-based filtering (low, medium, high, critical)
- Configurable alert thresholds for error rates, budget, cost spikes, and stuck processes
- `test-notifications` command for configuration verification
- `alerts` command for viewing alert history
- Alert persistence in `logs/alert_history.json`

#### Rejected Sites Management
- Rejected sites tracking in `config/rejected_sites/` with subdirectory support
- `reject-site` command to add sites with reason, evaluator, and reconsider conditions
- `list-rejected` command to view all rejected sites (with `-v` for full details)
- Metadata fields: URL, reason, evaluated date, evaluated by, reconsider conditions, replaced-by reference

#### CLI Information Commands
- `list-groups` - Show available domain groups and domain files with descriptions
- `list-domains` - Display all configured domains with enabled status
- `list-categories` - Show domain categorization options
- `list-tags` - List available domain tags
- `list-policy-types` - Display policy type options
- `domain-stats` - Show domain categorization statistics

#### Configuration
- YAML-based configuration: `settings.yaml`, `keywords.yaml`, `groups.yaml`, `notifications.yaml`, `url_filters.yaml`, `content_extraction.yaml`
- Environment variable overrides with `POLICYSEARCH__` prefix pattern
- `.env` file support for API keys and credentials

#### Domain Files Included
- `eu.yaml` - European Union institutions and member states (15 domains)
- `nordic.yaml` - Nordic countries (7 domains)
- `us/us_federal.yaml` - US federal agencies (6 domains)
- `us/*.yaml` - 50 individual US state files (19 domains across 16 states; 34 states ready for research)
- `apac.yaml` - Asia-Pacific region (6 domains)
- `germany.yaml` - German federal law database and ministry FAQ (2 domains)
- `denmark.yaml` - Danish Energy Agency heat policy (1 domain)
- `sweden.yaml` - Swedish Energy Agency data center reporting (1 domain)

#### Documentation
- README with visual pipeline diagram explaining the 6-step discovery process
- Virtual environment activation instructions for Windows and macOS/Linux
- Run summary documentation with example output
- Comprehensive test documentation with per-file coverage details
- Domain configuration guide with template usage instructions
- Full CLI reference with examples for all commands and options

#### Testing & CI
- Comprehensive unit test suite (489 tests) covering configuration, keywords, chunking, costs, alerts, notifications, domain filtering, URL caching, last-run, URL filtering, and content extraction
- GitHub Actions CI/CD: linting (ruff), type checking (mypy), tests (pytest)
- GitHub Actions monthly automated scan workflow (15th of each month at 9:00 AM UTC)
