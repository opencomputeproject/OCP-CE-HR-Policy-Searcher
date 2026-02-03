# OCP Heat Reuse Policy Searcher

Automated discovery of global data center heat reuse policies for the [OCP Heat Reuse Subproject](https://www.opencompute.org/wiki/Heat_Reuse).

## Overview

This tool automatically:
- 🔍 Crawls government websites for heat reuse policies
- 🤖 Analyzes content using keyword matching and Claude AI
- 📊 Outputs results to Google Sheets for review
- ⏰ Runs monthly via GitHub Actions

## How It Works

The tool follows a step-by-step process to find and analyze policies:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            PROCESSING PIPELINE                              │
└─────────────────────────────────────────────────────────────────────────────┘

  Step 1: CRAWL                     Step 2: EXTRACT
  ─────────────────                 ───────────────
  Visit government      ──────►    Read the page text,
  websites and follow              remove menus/headers,
  links to find pages              keep main content

           │                                │
           ▼                                ▼

  Step 3: KEYWORD SCAN              Step 4: AI ANALYSIS
  ────────────────────              ───────────────────
  Search text for                   Claude AI reads the
  heat reuse terms in   ──────►    page and extracts:
  8 languages                       • Policy name
                                    • Summary
  Score too low?                    • Requirements
  → Skip this page                  • Relevance score (1-10)

           │                                │
           ▼                                ▼

  Step 5: FILTER                    Step 6: OUTPUT
  ──────────────                    ──────────────
  Only keep policies    ──────►    Add new policies to
  with relevance                    Google Sheets for
  score 5 or higher                 team review
```

### What happens at each step

1. **Crawl** — The tool visits each government website in its list, starting from known energy policy pages. It follows links up to 3 levels deep, respecting rate limits to avoid overloading servers.

2. **Extract** — For each page, it strips away navigation menus, footers, and other clutter to get just the main content. It also detects the page language.

3. **Keyword Scan** — The text is searched for relevant terms like "waste heat," "data center energy," and "heat recovery" in 8 languages. Each match adds to a score. Pages scoring below the threshold are skipped (saving AI costs).

4. **AI Analysis** — Pages that pass the keyword filter are sent to Claude AI, which reads the content and determines if it's actually a policy. If so, it extracts key details and assigns a relevance score from 1-10.

5. **Filter** — Only policies scoring 5 or higher are kept. This ensures the final results are genuinely relevant to data center heat reuse.

6. **Output** — New policies are added to Google Sheets. The tool checks for duplicates first, so running it multiple times won't create repeat entries.

### What gets detected but flagged for human review

Some pages can't be fully processed automatically:
- **Paywalls** — Content behind a subscription
- **CAPTCHAs** — "Are you human?" challenges
- **Login required** — Member-only content
- **JavaScript-heavy sites** — Some pages need a real browser (the tool will retry with one)

These are logged and marked for manual review.

---

## Features

- **Smart crawling**: HTTP-first with Playwright fallback for JavaScript sites
- **Multi-language support**: Detects policies in English, German, French, Dutch, Swedish, Danish
- **Paywall/CAPTCHA detection**: Flags pages requiring human review
- **Keyword scoring**: Weighted keyword matching with configurable thresholds
- **LLM analysis**: Claude API for intelligent policy extraction and summarization
- **Deduplication**: Avoids re-adding existing policies to Google Sheets
- **Comprehensive logging**: Human-readable logs + structured JSON for analysis

## Quick Start

### Prerequisites

- Python 3.11+ (3.13 recommended)
- Anthropic API key ([get one here](https://console.anthropic.com/))
- Google Cloud service account with Sheets API access

### Installation

```bash
# Clone repository
git clone https://github.com/opencomputeproject/heat-reuse-policy-searcher.git
cd heat-reuse-policy-searcher

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Install Playwright browser
playwright install chromium

# Copy and configure environment
cp config/example.env .env
# Edit .env with your API keys
```

### Run a Test Scan

```bash
# Dry run with test domain (no API keys needed for keyword-only mode)
python -m src.main --domains test --dry-run --skip-llm

# Full test with Claude API
python -m src.main --domains test --dry-run
```

## Usage

### Before Running Any Commands

> **Important:** You must activate the virtual environment before running any Python commands.
> All dependencies are installed in the `venv` folder, not your system Python.

**On Windows:**
```bash
.\venv\Scripts\activate
```

**On macOS/Linux:**
```bash
source venv/bin/activate
```

You should see `(venv)` at the beginning of your command prompt when activated.

---

### Command Line Options

```bash
python -m src.main [OPTIONS]
```

**Options:**
- `--domains GROUP` - Domain group or file name to scan (see below)
- `--dry-run` - Don't write to Google Sheets (testing mode)
- `--skip-llm` - Use keyword matching only (no Claude API calls)
- `--verbose` - Enable verbose logging
- `--verbose-summary` - Show all settings used in the run summary
- `--chunk-size N` - Auto-chunk: process N domains at a time (see Chunking below)
- `--chunk N/M` - Manual chunk: run only chunk N of M total
- `--chunk-delay SEC` - Seconds to pause between chunks (default: 30)

**Keyword Tuning Options** (override config for this run):
- `--min-keyword-score N` - Minimum keyword score to pass to LLM (default: from keywords.yaml)
- `--require-combinations true|false` - Enable/disable required keyword combinations
- `--min-density N` - Minimum keyword density (matches per 1000 chars)

**Available Domain Groups:**

Regional:
- `all` - All 29 enabled domains
- `eu` - European Union (17 domains)
- `us` - United States federal and state (6 domains)
- `apac` - Asia-Pacific region (6 domains)
- `nordic` - Nordic countries - leaders in heat reuse (7 domains)
- `eu_central` - Germany, Switzerland, Austria, France (5 domains)
- `eu_west` - Netherlands, Belgium, Ireland (3 domains)
- `us_states` - US state governments only (4 domains)

Thematic:
- `federal` - Federal/EU/National level only (8 domains)
- `leaders` - Countries with most advanced policies (9 domains)
- `emerging` - Countries with emerging regulations (7 domains)

Testing:
- `test` - Single domain for testing
- `quick` - Fast scan - 2 diverse domains
- `sample_nordic` - Sample Nordic countries (3 domains)
- `sample_apac` - Sample APAC countries (2 domains)

**Domain Files (no group entry needed):**

You can also use the name of any domain file in `config/domains/` directly. This is useful when you add a new file and want to scan just those domains without editing `groups.yaml`:

```bash
# Scan all domains from config/domains/germany.yaml
python -m src.main --domains germany

# Scan all domains from config/domains/denmark.yaml
python -m src.main --domains denmark
```

When a name matches both a group and a file (e.g., `eu`), the group takes priority. Use `list-groups` to see all available groups and domain files.

### Examples

```bash
# Scan all EU domains
python -m src.main --domains eu

# Nordic countries (heat reuse leaders)
python -m src.main --domains nordic

# Scan domains from a specific file (no group needed)
python -m src.main --domains germany --dry-run

# Asia-Pacific region
python -m src.main --domains apac --skip-llm

# Quick scan (2 domains only)
python -m src.main --domains quick --dry-run

# Countries with most advanced policies
python -m src.main --domains leaders
```

### Chunking (For Large Scans)

When scanning many domains, you can split the work into smaller **chunks** to:
- Avoid long-running processes that might timeout
- Respect API rate limits with pauses between batches
- Make it easier to retry if something fails
- Stay within GitHub Actions time limits

#### Auto-Chunking (Recommended)

Let the tool automatically split domains into batches:

```bash
# Scan all 29 domains in batches of 5
# Pauses 30 seconds between each batch
python -m src.main --domains all --chunk-size 5

# Scan EU domains in batches of 3, with 60-second pauses
python -m src.main --domains eu --chunk-size 3 --chunk-delay 60
```

**What happens:**
```
============================================================
  BATCH 1/6
  Domains: bmwk_de, energy_gov, ec_europa, energistyrelsen_dk, minenv_fi
============================================================

  [10:30:15] Crawling bmwk_de...
  [10:31:45] Crawling energy_gov...
  ...

Batch 1/6 complete. Pausing 30s before next batch...

============================================================
  BATCH 2/6
  Domains: rvo_nl, energimyndigheten_se, enova_no...
============================================================
  ...
```

#### Manual Chunking (For Retries or CI/CD)

Run a specific chunk manually - useful for retrying failed batches or parallel CI jobs:

```bash
# Run only chunk 2 of 4
python -m src.main --domains all --chunk 2/4

# Retry just the third batch
python -m src.main --domains eu --chunk 3/5
```

**How chunks are split:**
| Domains | Chunk | What runs |
|---------|-------|-----------|
| 29 total | `--chunk 1/4` | Domains 1-8 |
| 29 total | `--chunk 2/4` | Domains 9-16 |
| 29 total | `--chunk 3/4` | Domains 17-22 |
| 29 total | `--chunk 4/4` | Domains 23-29 |

#### GitHub Actions Example

Run chunks in parallel for faster monthly scans:

```yaml
jobs:
  scan:
    strategy:
      matrix:
        chunk: ["1/4", "2/4", "3/4", "4/4"]
      fail-fast: false  # Continue others if one fails
    steps:
      - run: python -m src.main --domains all --chunk ${{ matrix.chunk }}
```

### Category & Tag Filtering

Beyond regional groups, you can filter domains by **category**, **tags**, and **policy types** for more targeted scans.

#### Filter Options

| Option | Description |
|--------|-------------|
| `--category NAME` | Filter by primary category |
| `--tag NAME` | Filter by tag (can use multiple times) |
| `--policy-type NAME` | Filter by policy type (can use multiple times) |
| `--match-all-tags` | Require ALL tags instead of ANY |

#### Available Categories

```bash
# See all categories
python -m src.main list-categories
```

| Category | Description |
|----------|-------------|
| `energy_ministry` | National/state energy departments |
| `environmental_agency` | EPA equivalents, climate agencies |
| `legislative` | Bill trackers, law databases, parliaments |
| `district_heating` | Heat network authorities |
| `grid_operator` | RTOs, ISOs, grid planners |
| `economic_dev` | Business incentives, tax programs |
| `regulatory` | Utility commissions, permit authorities |
| `standards` | Building codes, efficiency standards |

#### Available Tags

```bash
# See all tags
python -m src.main list-tags
```

| Tag | Description |
|-----|-------------|
| `incentives` | Grants, tax breaks, subsidies |
| `mandates` | Required regulations |
| `reporting` | Disclosure requirements |
| `carbon` | Carbon pricing, credits, emissions |
| `efficiency` | PUE, energy efficiency programs |
| `planning` | Zoning, permits, infrastructure |
| `research` | Studies, reports, data |

#### Available Policy Types

```bash
# See all policy types
python -m src.main list-policy-types
```

| Policy Type | Description |
|-------------|-------------|
| `law` | Enacted legislation |
| `regulation` | Agency rules |
| `directive` | EU directives, guidance with force |
| `incentive` | Grant programs, tax credits |
| `guidance` | Best practices, recommendations |
| `standard` | Technical standards, building codes |
| `report` | Research, data, analysis |

#### Filtering Examples

```bash
# Scan only energy ministry domains
python -m src.main --category energy_ministry

# Find domains with efficiency programs
python -m src.main --tag efficiency

# Find domains with grant programs
python -m src.main --tag incentives

# Find legislative sources with mandates
python -m src.main --category legislative --tag mandates

# Find domains that publish laws
python -m src.main --policy-type law

# Combine with regional group: EU energy ministries only
python -m src.main --domains eu --category energy_ministry

# Multiple tags (matches ANY)
python -m src.main --tag efficiency --tag incentives

# Multiple tags (matches ALL - must have both)
python -m src.main --tag efficiency --tag mandates --match-all-tags

# Grid operators focused on planning
python -m src.main --category grid_operator --tag planning
```

#### View Domain Statistics

```bash
# See how domains are categorized
python -m src.main domain-stats
```

**Output:**
```
============================================================
  DOMAIN CATEGORIZATION STATS
============================================================

  Total domains:    48
  Enabled domains:  42

  By Category:
  ----------------------------------------
    energy_ministry           18
    regulatory                 8
    legislative                5
    economic_dev               4
    environmental_agency       3
    grid_operator              2
    standards                  1
    (uncategorized)            1

  By Tag:
  ----------------------------------------
    efficiency                35
    mandates                  18
    incentives                15
    carbon                     8
    planning                   7
    research                   6
    reporting                  4

  By Policy Type:
  ----------------------------------------
    regulation                28
    guidance                  22
    law                       15
    incentive                 12
    report                     8
    standard                   5
    directive                  4

============================================================
```

#### Adding Categories to New Domains

When adding a new domain, include these optional fields:

```yaml
- name: "Example Ministry"
  id: "example_ministry"
  base_url: "https://example.gov"
  # ... other fields ...

  # Categorization
  category: "energy_ministry"    # Pick ONE primary category
  tags:                          # Pick any relevant tags
    - "efficiency"
    - "mandates"
  policy_types:                  # What kinds of policies this site has
    - "regulation"
    - "guidance"
```

### Run Summary

When a scan completes, you'll see a formatted summary showing exactly what happened:

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                              RUN COMPLETE                                     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Duration: 2m 34s                                                            ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  CRAWL STATS                                                                 ║
║  ───────────────────────────────────────────────────────────────────────     ║
║  Domains scanned:     7                                                      ║
║  Pages crawled:      45                                                      ║
║  ├─ Success:         38 (84%)                                                ║
║  ├─ Blocked:          4                                                      ║
║  └─ Errors:           3                                                      ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  POLICY STATS                                                                ║
║  ───────────────────────────────────────────────────────────────────────     ║
║  Keywords matched:   12                                                      ║
║  Policies found:      5                                                      ║
║  ├─ New:              3  ← added to Sheets                                   ║
║  └─ Duplicates:       2  ← already existed                                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  LLM STATS                                                                   ║
║  ───────────────────────────────────────────────────────────────────────     ║
║  API calls:          12                                                      ║
║  Tokens (in/out):    45,230 / 3,456                                          ║
║  Estimated cost:     $0.19                                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

**What the stats mean:**

| Stat | Description |
|------|-------------|
| **Domains scanned** | Number of government websites visited |
| **Pages crawled** | Total pages processed |
| **Success** | Pages successfully read and analyzed |
| **Blocked** | Pages with paywalls, CAPTCHAs, or login requirements |
| **Errors** | Pages that failed (timeout, server error, etc.) |
| **Keywords matched** | Pages that passed keyword filtering |
| **Policies found** | Pages identified as relevant policies |
| **New** | Policies added to Google Sheets (not duplicates) |
| **Duplicates** | Policies already in Sheets from previous runs |
| **API calls** | Number of Claude API requests made |
| **Tokens** | Input/output tokens used (for billing reference) |
| **Estimated cost** | Approximate cost based on Claude Sonnet pricing |

#### Verbose Summary

Want to see exactly what settings were used for a run? Add `--verbose-summary`:

```bash
python -m src.main --domains nordic --verbose-summary
```

This appends a detailed configuration section (with cost breakdown) after the run summary:

```
┌────────────────────────────────────────────────────────────────────┐
│                       RUN CONFIGURATION                            │
├────────────────────────────────────────────────────────────────────┤
│  Domain group:       nordic                                        │
│  Domains selected:   7                                             │
├────────────────────────────────────────────────────────────────────┤
│  min_keyword_score:  5.0                                           │
│  min_keyword_matches:2                                             │
│  require_combinations:enabled                                      │
│  min_density:        1.0 (enabled)                                 │
│  boost/penalty:      enabled / enabled                             │
├────────────────────────────────────────────────────────────────────┤
│  LLM mode:           two-stage (Haiku -> Sonnet)                   │
│  Screening model:    claude-haiku-4-20250514                       │
│  screening_min_conf: 5                                             │
│  Analysis model:     claude-sonnet-4-20250514                      │
│  min_relevance_score:5                                             │
├────────────────────────────────────────────────────────────────────┤
│  Cache:              enabled                                       │
│  Dry run:            false                                         │
├────────────────────────────────────────────────────────────────────┤
│                         COST BREAKDOWN                             │
├────────────────────────────────────────────────────────────────────┤
│  Screening (Haiku):  15 calls, 45,000 in / 4,500 out              │
│    Cost:             $0.0169                                       │
│  Analysis (Sonnet):  5 calls, 25,000 in / 2,500 out               │
│    Cost:             $0.1125                                       │
├────────────────────────────────────────────────────────────────────┤
│  TOTAL COST:         $0.1294                                       │
└────────────────────────────────────────────────────────────────────┘
```

This helps you understand exactly what settings were active and how much each LLM model cost, useful when debugging runs or optimizing costs.

#### View Run Summary

After running scans, you can view summaries of any run:

```bash
# Show most recent run (default)
python -m src.main last-run

# Show a specific run by number (1=most recent, 2=previous, etc.)
python -m src.main last-run --log 2

# Show run by date
python -m src.main last-run --log 20260115

# Show run by full ID
python -m src.main last-run --log run_20260115_143022

# Show only configuration (not stats)
python -m src.main last-run --config-only

# Show only summary stats (not configuration)
python -m src.main last-run --summary-only
```

#### List Available Runs

See all available run logs:

```bash
# Show last 10 runs
python -m src.main list-runs

# Show all runs
python -m src.main list-runs --all
```

**Example output:**

```
==============================================================================
  AVAILABLE RUN LOGS
==============================================================================

  #   Run ID                   Date         Domains  Policies  Cost
  ------------------------------------------------------------------------
  1   run_20260116_143022      2026-01-16   7        3         $0.1294
  2   run_20260115_120000      2026-01-15   5        1         $0.0856
  3   run_20260114_090000      2026-01-14   29       8         $0.4521

  Usage: python -m src.main last-run --log <#>
  Example: python -m src.main last-run --log 2
```

#### Run Summary Output

**Example `last-run` output:**

```
┌────────────────────────────────────────────────────────────────────┐
│                        LAST RUN SUMMARY                            │
├────────────────────────────────────────────────────────────────────┤
│  Run ID:            run_20260115_143022                            │
│  Completed:         2026-01-15 14:35:56 UTC                        │
├────────────────────────────────────────────────────────────────────┤
│  Domains scanned:    7                                             │
│  Pages crawled:      156                                           │
│  Pages successful:   142                                           │
│  Pages blocked:      12                                            │
│  Pages with errors:  2                                             │
│  Success rate:       91.0%                                         │
├────────────────────────────────────────────────────────────────────┤
│  Policies found:     5                                             │
│  New policies:       3                                             │
│  Duplicates skipped: 2                                             │
├────────────────────────────────────────────────────────────────────┤
│  Screening (Haiku):  15 calls, 45,000 in / 4,500 out               │
│    Cost:             $0.0169                                       │
│  Analysis (Sonnet):  5 calls, 25,000 in / 2,500 out                │
│    Cost:             $0.1125                                       │
│  TOTAL COST:         $0.1294                                       │
├────────────────────────────────────────────────────────────────────┤
│  Duration:           5m 56s                                        │
└────────────────────────────────────────────────────────────────────┘
```

#### Tuning Keyword Settings

You can override keyword filtering settings for a single run without editing config files:

```bash
# Lower keyword score threshold (find more potential matches)
python -m src.main --domains nordic --min-keyword-score 3.0

# Disable required keyword combinations (more permissive)
python -m src.main --domains nordic --require-combinations false

# Adjust minimum keyword density
python -m src.main --domains nordic --min-density 0.5

# Combine multiple overrides
python -m src.main --domains nordic --min-keyword-score 3.0 --require-combinations false --verbose-summary
```

These are useful for experimentation:
- If a scan finds **zero policies**, try lowering `--min-keyword-score` or disabling `--require-combinations`
- If a scan finds **too many false positives**, try raising `--min-keyword-score` or enabling stricter density checks

### Cost Monitoring

The tool tracks Claude API costs across all runs, helping you monitor usage and stay within budget.

#### View Cost History

```bash
# Show cumulative cost history
python -m src.main cost-history
```

**Output:**
```
╔══════════════════════════════════════════════════════════════════════════════╗
║                              COST HISTORY                                     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Total runs:           12                                                     ║
║  Total API calls:     156                                                     ║
║  Total tokens:        2,340,500 in / 198,450 out                             ║
║  Total cost:          $10.04                                                  ║
║  30-day cost:         $8.25                                                   ║
║  7-day cost:          $2.15                                                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  RECENT RUNS                                                                  ║
║  ───────────────────────────────────────────────────────────────────────     ║
║  2026-01-05 14:30  run_20260105_143022  $1.25  (nordic, 5 policies)          ║
║  2026-01-04 09:15  run_20260104_091533  $0.90  (eu_central, 3 policies)      ║
║  2026-01-03 16:45  run_20260103_164512  $0.45  (quick, 1 policy)             ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

#### Estimate Costs Before Running

Plan your scans by estimating costs beforehand:

```bash
# Estimate cost for scanning all domains
python -m src.main estimate-cost --domains all

# Estimate with custom parameters
python -m src.main estimate-cost --domains eu --pages-per-domain 100
```

**Output:**
```
╔══════════════════════════════════════════════════════════════════════════════╗
║                              COST ESTIMATE                                    ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Domains:              29                                                     ║
║  Est. pages:          1,450                                                   ║
║  Est. analyzed:         145  (10% pass keyword filter)                       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Est. input tokens:   580,000                                                 ║
║  Est. output tokens:   72,500                                                 ║
║  Est. cost:           $2.83                                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

#### Budget Warnings

The tool automatically warns you when approaching or exceeding your monthly budget:

- **Warning at 80%**: "Budget warning: $40.50 of $50 used (81%)"
- **Alert at 100%**: "BUDGET EXCEEDED: $52.30 of $50 used (105%)"

Budget is configured in `config/settings.yaml`:

```yaml
costs:
  monthly_budget_usd: 50.0    # Set to null to disable warnings
  warn_threshold: 0.8         # Warn at 80% of budget
```

#### Model Pricing

Costs are calculated based on current Claude API pricing:

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| Claude Sonnet 4 | $3.00 | $15.00 |
| Claude Haiku 3.5 | $0.80 | $4.00 |
| Claude Opus 3 | $15.00 | $75.00 |

The default model (Claude Sonnet) provides the best balance of cost and accuracy for policy analysis.

#### Cost History Storage

Cost history is stored in `logs/cost_history.json` and persists across runs. Each run record includes:
- Timestamp and run ID
- Model used
- Token counts (input/output)
- Total cost
- Domains scanned and policies found

### Email Notifications & Alerts

Stay informed about your scans with comprehensive email notifications and intelligent alerting.

#### Why Notifications Matter

Running automated scans means you need to know when:
- A scan completes successfully (with results summary)
- Something goes wrong (errors, failures, stuck processes)
- Costs are getting high (budget warnings)
- Performance degrades (high error rates, connection issues)

The notification system handles all of this automatically, so you can run scans with confidence.

#### Setting Up Email Notifications

1. **Edit the configuration file:**
```bash
# Open config/notifications.yaml in your editor
```

2. **Configure SMTP settings (Gmail example):**
```yaml
email:
  enabled: true
  smtp_host: "smtp.gmail.com"
  smtp_port: 587
  smtp_use_tls: true
  smtp_username: "your.email@gmail.com"
  smtp_password: "your-app-password"  # NOT your regular password!
  from_email: "your.email@gmail.com"
  to_emails:
    - "alerts@yourteam.com"
    - "you@example.com"
```

> **Gmail Users:** You need an "App Password", not your regular password.
> Go to https://myaccount.google.com/apppasswords to generate one.

3. **Test your configuration:**
```bash
python -m src.main test-notifications
```

**Output:**
```
============================================================
  NOTIFICATION TEST
============================================================

  Email Configuration:
    SMTP Host:     smtp.gmail.com:587
    From:          your.email@gmail.com
    To:            alerts@yourteam.com
    TLS:           Yes

  Sending test email...
  [OK] Test email sent to alerts@yourteam.com

============================================================
```

#### What Triggers Notifications

| Event | Priority | When It's Sent |
|-------|----------|----------------|
| **Scan Complete** | Low | Every successful scan (optional) |
| **Scan Failed** | High | Any unrecoverable error |
| **Budget Warning** | Medium | When 80% of monthly budget is used |
| **Budget Exceeded** | Critical | When budget is exceeded |
| **High Error Rate** | High | When >30% of pages fail |
| **Cost Spike** | Medium | When run costs 2x+ the average |
| **No Policies Found** | Medium | When a scan finds nothing |
| **Connection Errors** | High | When multiple domains fail |

#### Customizing Alert Thresholds

Fine-tune when alerts trigger in `config/notifications.yaml`:

```yaml
thresholds:
  # Error rate thresholds
  error_rate_warning: 0.2      # Alert at 20% error rate
  error_rate_critical: 0.4     # Critical at 40% error rate

  # Budget thresholds
  budget_warning_percent: 0.8  # Warn at 80% of budget
  budget_critical_percent: 1.0 # Critical at 100%

  # Cost spike detection
  cost_spike_multiplier: 2.0   # Alert if cost > 2x average

  # Stuck process detection
  stuck_timeout_minutes: 30    # Alert if no progress for 30min
```

#### Filtering Notifications

Don't want every notification? Configure what you receive:

```yaml
preferences:
  notify_on_success: true   # Get notified on successful scans
  notify_on_error: true     # Get notified on failures
  notify_on_warning: true   # Get notified on warnings

  # Minimum priority to send (low, medium, high, critical)
  min_priority: "medium"    # Only medium+ priority notifications
```

**Priority Levels:**
- **Low**: Informational (scan complete)
- **Medium**: Warnings (budget approaching, cost spike)
- **High**: Errors (high error rate, failures)
- **Critical**: System failures (budget exceeded, stuck process)

#### Viewing Alert History

```bash
python -m src.main alerts
```

**Output:**
```
============================================================
  ALERT SUMMARY
============================================================

  Active Alerts: 2

  By Severity:
    WARNING: 1
    ERROR: 1

  By Type:
    high_error_rate: 1
    budget_warning: 1

============================================================

  Recent Alerts (last 10):
  ----------------------------------------------------------
  [WARNING ] 2026-01-06T10:30:00 - budget_warning
  [ERROR   ] 2026-01-06T09:15:00 - high_error_rate
  [INFO    ] 2026-01-05T14:00:00 - run_complete
```

#### Email Examples

**Success Notification:**
```
Subject: OCP Policy Searcher: Scan Completed Successfully

Your policy scan has completed successfully!

Scanned 10 domains and found 5 relevant policies (3 new).

The scan took 2m 34s and cost approximately $0.1875.

Details:
  Domains Scanned: 10
  Policies Found: 5
  New Policies: 3
  Duration: 2m 34s
  Estimated Cost: $0.1875
```

**Error Notification:**
```
Subject: [ERROR] OCP Policy Searcher: High Error Rate Detected

Your scan is experiencing a high error rate.

Error Rate: 35% (35/100 pages)
Threshold: 30%

This could indicate:
- Network connectivity issues
- Target sites blocking requests
- Rate limiting being applied
```

## Configuration

### File Structure

```
config/
├── settings.yaml          # Runtime settings (crawl speed, thresholds)
├── keywords.yaml          # Search terms in 8 languages
├── groups.yaml            # Domain groups (you can edit this!)
├── notifications.yaml     # Email & alert configuration
├── domains/               # Domain definitions (supports subdirectories)
│   ├── _template.yaml     # Template for adding new domains
│   ├── eu.yaml            # European Union
│   ├── nordic.yaml        # Nordic countries
│   ├── us_federal.yaml    # US federal agencies
│   ├── us_states.yaml     # US state governments
│   ├── apac.yaml          # Asia-Pacific
│   └── uk/                # Subdirectories are supported
│       └── government.yaml
└── rejected_sites/        # Sites evaluated but not useful
    ├── _template.yaml     # Template for rejected sites
    ├── general.yaml       # General rejected sites
    └── uk/                # Subdirectories work here too
        └── research.yaml
```

### Domains (`config/domains/*.yaml`)

Domains are organized by region. Each file contains government websites to crawl:

```yaml
domains:
  - name: "German Federal Ministry"
    id: "bmwk_de"
    base_url: "https://www.bmwk.de"
    start_paths:
      - "/Redaktion/EN/Artikel/Energy/"
    max_depth: 3
    language: "de"
```

**To add a new domain:** Copy from `_template.yaml`, fill in the fields, and add to the appropriate regional file.

### Groups (`config/groups.yaml`)

Groups let you run scans on specific sets of domains. **You can edit this file** to create your own custom groups!

```yaml
groups:
  # Create your own group:
  my_research:
    description: "Domains I'm currently researching"
    domains:
      - bmwk_de
      - energy_gov
      - imda_sg
```

Then run: `python -m src.main --domains my_research`

### Rejected Sites (`config/rejected_sites/`)

Track sites you've evaluated but decided not to include. Organize files however you like:

```
config/rejected_sites/
├── _template.yaml     # Template (ignored by loader)
├── general.yaml       # Default file for CLI
├── eu.yaml            # EU-specific rejections
├── uk/                # Subdirectories work too
│   ├── government.yaml
│   └── research.yaml
└── 2026-01-research.yaml  # By date/session
```

Each YAML file contains:

```yaml
rejected_sites:
  - url: "https://example.gov/department"
    evaluated_date: "2026-01-05"
    reason: "No policy content - only press releases"
    evaluated_by: "Your Name"           # optional
    reconsider_if: "They add a policy section"  # optional
    replaced_by: "other_domain_id"      # optional
```

**CLI Commands:**

```bash
# Add a rejected site (goes to general.yaml by default)
python -m src.main reject-site --url "https://example.gov" --reason "No policy content"

# Add to a specific file
python -m src.main reject-site --url "https://uk.gov/page" --reason "Duplicate" --file uk.yaml

# Add to a subdirectory file
python -m src.main reject-site --url "https://scotland.gov" --reason "Out of scope" --file uk/scotland.yaml

# List all rejected sites
python -m src.main list-rejected

# List with full details
python -m src.main list-rejected -v
```

**Workflow tip:** When evaluating a batch of domains, you can:
1. Copy a domains file to `rejected_sites/` (e.g., `uk_candidates.yaml`)
2. Keep the good ones in `domains/`, move rejected ones to `rejected_sites/`
3. The loader handles both directories independently

### Keywords (`config/keywords.yaml`)

Define search terms with weights:

```yaml
keywords:
  subject:
    weight: 3.0  # Highest weight
    terms:
      en: ["data center waste heat", "heat reuse"]
      de: ["Abwärme", "Wärmerückgewinnung"]

  policy_type:
    weight: 2.0
    terms:
      en: ["regulation", "law", "directive"]
```

### Settings (`config/settings.yaml`)

Runtime configuration:

```yaml
crawl:
  max_depth: 3
  max_pages_per_domain: 100
  delay_seconds: 3.0

analysis:
  min_keyword_score: 3.0
  min_relevance_score: 5
  llm_model: "claude-sonnet-4-20250514"
```

## Environment Variables

Create `.env` file (see `config/example.env`):

```bash
# Required for LLM analysis
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here

# Required for Google Sheets output
GOOGLE_CREDENTIALS=base64-encoded-service-account-json
SPREADSHEET_ID=your-spreadsheet-id

# Optional overrides
POLICYSEARCH__CRAWL__DELAY_SECONDS=5.0
POLICYSEARCH__ANALYSIS__ENABLE_LLM_ANALYSIS=false
```

## GitHub Actions

### Monthly Automated Scan

Runs on the 15th of each month at 9:00 AM UTC:

```yaml
# .github/workflows/monthly_scan.yml
schedule:
  - cron: '0 9 15 * *'
```

**Manual trigger**: Go to Actions → Monthly Policy Scan → Run workflow

### CI/CD

Runs on every push/PR:
- Linting (ruff)
- Type checking (mypy)
- Tests (pytest)

## Project Structure

```
OCP-Heat-Reuse-Policy-Searcher/
├── src/
│   ├── config/          # Configuration loading
│   ├── models/          # Data models (Policy, CrawlResult)
│   ├── crawler/         # Web crawling
│   │   ├── fetchers/    # HTTP & Playwright
│   │   ├── extractors/  # HTML extraction
│   │   └── detection/   # Paywall/CAPTCHA detection
│   ├── analysis/        # Keyword matching & LLM
│   ├── output/          # Google Sheets integration
│   ├── logging/         # Run logging
│   └── main.py          # Entry point
├── config/
│   ├── domains/         # Domain files by region (supports subdirectories)
│   ├── rejected_sites/  # Rejected sites (supports subdirectories)
│   ├── groups.yaml      # Domain groups (user-editable)
│   ├── settings.yaml    # Runtime configuration
│   └── keywords.yaml    # Search terms
├── tests/               # Unit & integration tests
├── logs/                # Run logs
└── snapshots/           # Page snapshots
```

## Output Format

Results are written to Google Sheets with these columns:

| Column | Description |
|--------|-------------|
| URL | Policy page URL |
| Policy Name | Extracted policy title |
| Jurisdiction | Country/region |
| Policy Type | law, regulation, directive, incentive, etc. |
| Summary | 2-3 sentence summary |
| Relevance Score | 1-10 (Claude's assessment) |
| Source Language | Detected language |
| Effective Date | When policy takes effect |
| Bill Number | Legislative reference |
| Key Requirements | Main policy requirements |
| Discovered At | Timestamp of discovery |
| Crawl Status | success, paywall, captcha, etc. |
| Review Status | new, reviewed, rejected |

## Logs

Each run produces:
- `logs/run_YYYYMMDD_HHMMSS.log` - Human-readable log
- `logs/run_YYYYMMDD_HHMMSS.json` - Structured JSON events

## Development

### Running Tests

The project includes comprehensive unit tests covering configuration loading and keyword matching.

```bash
# Run all tests
pytest

# Run with verbose output (recommended)
pytest -v

# Run with coverage report
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_keywords.py -v

# Run a specific test class
pytest tests/unit/test_config_loader.py::TestGetEnabledDomains -v
```

### Test Structure

```
tests/
├── unit/
│   ├── test_alerts.py           # 38 tests - Error alerting
│   ├── test_chunking.py         # 31 tests - Domain chunking
│   ├── test_config_loader.py    # 20 tests - Configuration loading
│   ├── test_costs.py            # 26 tests - Cost tracking
│   ├── test_domain_filtering.py # 46 tests - Category/tag filtering
│   ├── test_keywords.py         # 16 tests - Keyword matching
│   ├── test_last_run.py         # 46 tests - Last run summary/config/costs
│   ├── test_notifications.py    # 24 tests - Email notifications
│   └── test_url_cache.py        # 29 tests - URL result caching
└── integration/                  # (future integration tests)
```

### Test Coverage

**Chunking Tests** (`test_chunking.py`):
- `TestParseChunkSpec` — Parsing "N/M" format, error handling
- `TestSplitIntoChunks` — Even/uneven splits, edge cases
- `TestGetChunkBySpec` — Domain distribution, order preservation
- `TestCalculateChunks` — Auto vs manual chunking logic
- `TestChunkInfo` — Dataclass properties and formatting

**Configuration Loader Tests** (`test_config_loader.py`):
- `TestLoadYaml` — Loading YAML files, handling missing/empty files
- `TestLoadDomainsDirectory` — Merging multiple domain files, skipping templates
- `TestGetEnabledDomains` — Filtering by group, handling disabled domains
- `TestListGroups` — Group listing with descriptions
- `TestListDomains` — Domain listing with enabled status
- `TestLoadSettingsIntegration` — Full integration with actual config files

**Keyword Matcher Tests** (`test_keywords.py`):
- `TestKeywordMatcher` — Pattern compilation, single/multiple matches, case insensitivity
- `TestKeywordMatchResult` — Result dataclass behavior
- `TestIsRelevant` — Threshold checking for score and match count
- `TestIntegrationWithActualConfig` — Integration with real keywords.yaml

**Cost Tracking Tests** (`test_costs.py`):
- `TestModelPricing` — Pricing constants for different Claude models
- `TestCostBreakdown` — Cost calculation, formatting, unknown model fallback
- `TestCostHistory` — Run aggregation, date filtering, summary generation
- `TestCostTracker` — Persistence, budget warnings, file loading
- `TestEstimateRunCost` — Cost estimation with different parameters
- `TestIntegration` — Full workflow with multiple runs

**Alert Tests** (`test_alerts.py`):
- `TestAlertType` — Alert type enumeration and all expected types
- `TestAlertSeverity` — Severity levels from INFO to CRITICAL
- `TestAlert` — Alert creation, JSON serialization/deserialization
- `TestAlertThresholds` — Threshold configuration and custom values
- `TestRunHealthMetrics` — Health tracking, success/error recording, error rates
- `TestAlertManager` — Error rate checks, budget checks, cost spikes, stuck processes
- `TestAlertManagerCustomThresholds` — Custom threshold configuration
- `TestAlertPersistence` — Alert loading/saving to files

**Notification Tests** (`test_notifications.py`):
- `TestNotificationType` — Notification type enumeration
- `TestNotificationPriority` — Priority level comparison
- `TestNotificationConfig` — Configuration loading, defaults, validation
- `TestNotification` — Notification creation and formatting
- `TestEmailNotifier` — SMTP connection, email formatting, TLS support
- `TestNotificationManager` — Priority filtering, notification dispatch

**Domain Filtering Tests** (`test_domain_filtering.py`):
- `TestValidConstants` — Valid categories, tags, and policy types
- `TestFilterDomainsByCategory` — Category filtering, disabled domain exclusion
- `TestFilterDomainsByTag` — Tag filtering with single and multiple tags
- `TestFilterDomainsByPolicyType` — Policy type filtering
- `TestFilterDomains` — Combined filtering with category + tags + policy types
- `TestListFunctions` — list_categories, list_tags, list_policy_types
- `TestGetDomainStats` — Statistics generation by category/tag/policy type
- `TestIntegrationWithActualConfig` — Integration with actual config files

**Last Run Tests** (`test_last_run.py`):
- `TestGetLastRunLog` — Finding most recent log file, handling edge cases
- `TestLoadRunLog` — Loading and parsing run log JSON files
- `TestFormatLastRunSummary` — Summary formatting with stats and LLM costs
- `TestFormatLastRunConfig` — Configuration formatting with all settings
- `TestRunConfigDataclass` — RunConfig defaults and format_verbose method
- `TestIntegration` — Full workflow of saving and loading run data
- `TestFindRunLog` — Finding logs by index, date, or run ID pattern
- `TestListRunLogs` — Listing available runs with summary info

**URL Cache Tests** (`test_url_cache.py`):
- `TestCacheEntry` — Expiry checks, content hash matching
- `TestCacheStats` — Hit rate calculation, session reset
- `TestURLCache` — Set/get/remove operations, expired entry handling
- `TestComputeContentHash` — Content hashing and truncation
- `TestLoadSaveCache` — Cache persistence and error handling
- `TestCacheIntegration` — Typical usage workflows

### Running Tests Before Commits

Always run tests before committing:

```bash
# Quick check
pytest -v

# Full check with linting
ruff check src/ && pytest -v
```

### Adding a New Domain

1. Open the appropriate regional file in `config/domains/` (e.g., `us_states.yaml`)
2. Copy the template from `config/domains/_template.yaml`
3. Fill in the domain details
4. Test with: `python -m src.main --domains test --dry-run`
5. Add the domain ID to a group in `config/groups.yaml` if needed
6. Submit PR

### Code Quality

```bash
# Lint
ruff check src/

# Format
ruff format src/

# Type check
mypy src/
```

## Troubleshooting

### "PYTHONPATH error" on Windows

Remove the `PYTHONPATH` environment variable from Windows system settings.

### "No policies found"

- Check keyword configuration matches policy content
- Lower `min_keyword_score` in settings.yaml
- Review logs for blocked pages (paywalls, CAPTCHAs)

### "Timeout errors"

- Increase `timeout_seconds` in settings.yaml
- Enable Playwright for specific domains

### "Google Sheets authentication failed"

- Verify service account has edit access to spreadsheet
- Check GOOGLE_CREDENTIALS is base64-encoded correctly
- Ensure Sheets API is enabled in Google Cloud Console

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure CI passes
5. Submit a pull request

## License

MIT License - See [LICENSE](LICENSE) for details

## Acknowledgments

Built for the [Open Compute Project Heat Reuse Subproject](https://www.opencompute.org/wiki/Heat_Reuse).

## Support

- Issues: [GitHub Issues](https://github.com/opencomputeproject/heat-reuse-policy-searcher/issues)
- Discussions: [OCP Heat Reuse Forum](https://www.opencompute.org/wiki/Heat_Reuse)
