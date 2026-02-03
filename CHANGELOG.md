# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Geographic `region` field on all domain YAML entries (list of strings: `eu`, `nordic`, `eu_central`, `eu_west`, `uk`, `us`, `us_states`, `apac`)
- `--domains` now merges group and region matches: `--domains eu` returns the union of the `eu` group from `groups.yaml` AND any domain with `region: ["eu"]`
- `list-regions` CLI command to show available geographic regions with domain counts
- `list-groups` output now shows how many extra domains each group gains via region tags
- Startup warning for any enabled domain missing the `region` field
- `VALID_REGIONS` constant and `list_regions()`, `warn_missing_regions()` functions in loader
- Region counts in `domain-stats` output
- Updated `_template.yaml` with region field and documentation

### Changed
- Split `us_states.yaml` into 50 individual per-state YAML files under `config/domains/us/` (e.g., `texas.yaml`, `virginia.yaml`, `alabama.yaml`) to support incremental per-state research
- Moved `us_federal.yaml` into `config/domains/us/` subdirectory alongside state files
- Enabled `context` keyword category in `config/keywords.yaml` (data center terms now required in combination matching)

### Fixed
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
