# OCP Heat Reuse Policy Searcher

Automated discovery of global data center heat reuse policies for the [OCP Heat Reuse Subproject](https://www.opencompute.org/wiki/Heat_Reuse).

## Overview

This tool automatically:
- 🔍 Crawls government websites for heat reuse policies
- 🤖 Analyzes content using keyword matching and Claude AI
- 📊 Outputs results to Google Sheets for review
- ⏰ Runs monthly via GitHub Actions

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

### Command Line Options

```bash
python -m src.main [OPTIONS]
```

**Options:**
- `--domains GROUP` - Domain group to scan (see groups below)
- `--dry-run` - Don't write to Google Sheets (testing mode)
- `--skip-llm` - Use keyword matching only (no Claude API calls)
- `--verbose` - Enable verbose logging

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

### Examples

```bash
# Scan all EU domains
python -m src.main --domains eu

# Nordic countries (heat reuse leaders)
python -m src.main --domains nordic

# Asia-Pacific region
python -m src.main --domains apac --skip-llm

# Quick scan (2 domains only)
python -m src.main --domains quick --dry-run

# Countries with most advanced policies
python -m src.main --domains leaders
```

## Configuration

### Domains (`config/domains.yaml`)

Define target government websites:

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

**Coverage**: 29 domains across Europe, North America, and Asia-Pacific
**Domain groups**: See Command Line Options section for full list

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
├── config/              # Configuration files
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

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_keywords.py -v
```

### Adding a New Domain

1. Edit `config/domains.yaml`
2. Add domain configuration
3. Test with: `python -m src.main --domains test --dry-run`
4. Submit PR

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
