# Continuity Document - Cost Optimization & Efficiency Improvements

## Purpose
This document tracks the implementation progress of cost optimization features to ensure continuity across context window compactions. It contains all necessary context to resume work at any point.

---

## Project Overview

**Goal**: Reduce LLM API costs while maintaining policy detection accuracy through:
1. Two-stage LLM analysis (Haiku screening → Sonnet extraction)
2. URL pre-filtering (skip obviously irrelevant URLs)
3. Stricter keyword requirements (reduce false positives)
4. Content extraction (send less data to LLM)
5. Result caching (skip previously analyzed URLs)

**Current Problem** (from run_20260115_202004.log):
- 87 LLM API calls, only 3 relevant policies found
- $3.42 spent, 45 minutes runtime
- 84 validation errors (policy_type: null on irrelevant pages)
- 96% of API spend was on irrelevant pages

---

## Implementation Plan

### Phase 0: Fix Existing Bug (policy_type coercion)
- [x] Add policy_type coercion in `_coerce_types()` - null → "not_relevant"
- [x] Add tests for policy_type coercion (8 new tests)
- [x] Commit and push

### Phase 1: URL Pre-filtering (Free, Easy)
- [x] Create `config/url_filters.yaml` - User-configurable URL patterns
- [x] Create `src/analysis/url_filter.py` - URL filtering logic
- [x] Create `tests/unit/test_url_filter.py` - 46 unit tests
- [x] Update `src/main.py` - Integrate URL filtering

**URL filter config structure:**
```yaml
url_filters:
  # Paths to always skip (substring match)
  skip_paths:
    - /login
    - /contact
    - /cookies
    - /privacy
    - /account/
    - /registry/
    - /user/
    - /cart
    - /checkout

  # Path patterns to skip (regex)
  skip_patterns:
    - "^/[a-z]{2}/news/"  # News sections in any language
    - "/press-release"
    - "/event/"

  # File extensions to skip
  skip_extensions:
    - .pdf
    - .doc
    - .xls
    - .zip

  # Domain-specific overrides
  domain_overrides:
    energimyndigheten.se:
      skip_paths:
        - /emissions-trading/
        - /about-us/
```

### Phase 2: Stricter Keyword Requirements (Free)
**Files to create/modify:**
- `config/keywords.yaml` - Add required_combinations, min_density
- `src/analysis/keywords.py` - Enhanced matching logic
- `tests/unit/test_keywords.py` - Additional tests

**Enhanced keyword config structure:**
```yaml
# Existing structure preserved
keywords:
  primary: [...]
  secondary: [...]

# New additions
keyword_requirements:
  # Minimum keyword density (matches per 1000 chars)
  min_density: 2.0

  # Required combinations - at least one must match
  required_combinations:
    - primary: ["data center", "datacenter", "data centre"]
      secondary: ["heat", "waste heat", "thermal", "reuse", "recovery"]
    - primary: ["server farm", "computing facility"]
      secondary: ["heat", "energy efficiency", "thermal"]

  # Boost score if these appear
  boost_keywords:
    - "heat reuse"
    - "waste heat recovery"
    - "district heating"
    - "thermal energy"

  # Reduce score if these appear (generic energy pages)
  penalty_keywords:
    - "cookie policy"
    - "terms of service"
    - "privacy policy"
```

### Phase 3: Content Extraction (Moderate Effort)
**Files to create/modify:**
- `src/analysis/content_extractor.py` - Main content extraction
- `src/crawler/async_crawler.py` - Integrate extraction
- `tests/unit/test_content_extractor.py` - Unit tests

**Features:**
- Strip navigation, headers, footers, sidebars
- Extract main content area
- Remove boilerplate (cookie notices, etc.)
- Optionally use readability algorithm

### Phase 4: Two-Stage LLM Analysis (Biggest Impact)
**Files to create/modify:**
- `src/analysis/llm/screener.py` - Haiku-based quick screening
- `src/analysis/llm/client.py` - Add model selection
- `src/analysis/llm/prompts.py` - Screening prompt
- `config/settings.yaml` - Model configuration
- `src/main.py` - Two-stage pipeline

**Screening prompt (for Haiku):**
```
Quick relevance check: Does this page describe government policy about:
- Data center waste heat reuse
- Data center energy efficiency requirements
- Heat recovery from computing facilities

Answer ONLY with JSON: {"relevant": true/false, "confidence": 1-10}
```

**Cost comparison:**
- Current: All pages → Sonnet ($3/MTok input)
- New: All pages → Haiku ($0.25/MTok) → Relevant only → Sonnet
- If 10% relevant: ~75% cost reduction

### Phase 5: Result Caching (Good for Repeated Runs)
**Files to create/modify:**
- `src/cache/url_cache.py` - URL result caching
- `data/url_cache.json` - Cache storage
- `src/main.py` - Cache integration
- CLI: `--no-cache`, `--clear-cache` flags

**Cache structure:**
```json
{
  "https://example.gov/policy": {
    "is_relevant": false,
    "relevance_score": 2,
    "analyzed_date": "2026-01-15",
    "content_hash": "abc123",
    "expires": "2026-02-15"
  }
}
```

---

## Current Status

**Phase**: 1 (Completed)
**Last Action**: Implemented URL pre-filtering with user config
**Next Action**: Ask user before proceeding to Phase 2
**Blockers**: None

---

## File Inventory

### New Files to Create
- [ ] `docs/CONTINUITY.md` (this file)
- [ ] `docs/ACCOMPLISHMENTS.md`
- [ ] `config/url_filters.yaml`
- [ ] `src/analysis/url_filter.py`
- [ ] `src/analysis/content_extractor.py`
- [ ] `src/analysis/llm/screener.py`
- [ ] `src/cache/url_cache.py`
- [ ] `tests/unit/test_url_filter.py`
- [ ] `tests/unit/test_content_extractor.py`
- [ ] `tests/unit/test_screener.py`
- [ ] `tests/unit/test_url_cache.py`

### Files to Modify
- [ ] `src/analysis/llm/client.py` - policy_type coercion
- [ ] `src/analysis/llm/prompts.py` - screening prompt
- [ ] `src/analysis/keywords.py` - enhanced matching
- [ ] `src/config/loader.py` - load new configs
- [ ] `src/main.py` - integrate all features
- [ ] `config/keywords.yaml` - new structure
- [ ] `config/settings.yaml` - model config
- [ ] `README.md` - documentation
- [ ] `tests/unit/test_llm_client.py` - policy_type tests
- [ ] `tests/unit/test_keywords.py` - enhanced tests

---

## Testing Checklist

### Unit Tests Required
- [ ] policy_type coercion (null → "not_relevant")
- [ ] URL filter path matching
- [ ] URL filter pattern matching
- [ ] URL filter domain overrides
- [ ] Keyword density calculation
- [ ] Keyword combination matching
- [ ] Content extraction accuracy
- [ ] Haiku screening prompt parsing
- [ ] Cache read/write
- [ ] Cache expiration

### Integration Tests
- [ ] Full pipeline with URL filtering
- [ ] Full pipeline with two-stage LLM
- [ ] Cache hit/miss behavior

---

## Configuration Summary

After implementation, users can customize:

1. **URL Filters** (`config/url_filters.yaml`)
   - Skip paths, patterns, extensions
   - Domain-specific overrides

2. **Keywords** (`config/keywords.yaml`)
   - Required combinations
   - Minimum density
   - Boost/penalty keywords

3. **LLM Settings** (`config/settings.yaml`)
   - Screening model (default: haiku)
   - Analysis model (default: sonnet)
   - Enable/disable two-stage

4. **Cache Settings** (`config/settings.yaml`)
   - Enable/disable cache
   - Cache expiration days
   - Cache location

---

## Git Commit Plan

1. `Fix policy_type coercion for non-relevant pages`
2. `Add URL pre-filtering with user config`
3. `Add stricter keyword requirements`
4. `Add content extraction for cleaner LLM input`
5. `Add two-stage Haiku/Sonnet analysis`
6. `Add URL result caching`

---

## Notes & Decisions

- Use "not_relevant" (not "unknown") for coerced policy_type
- URL filters use substring match by default (faster than regex)
- Keyword density = matches / (content_length / 1000)
- Cache expires after 30 days by default
- Haiku screening uses minimal prompt for speed

---

## Resume Instructions

If context is lost, read this file and:
1. Check "Current Status" section
2. Look at "Next Action"
3. Review relevant file inventory items
4. Continue from where we left off
