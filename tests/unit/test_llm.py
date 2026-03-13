"""Tests for LLM helpers and ClaudeClient.to_policy()."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import anthropic
import pytest

from src.core.llm import (
    _extract_json, _coerce_types, ClaudeClient,
    SCREENING_PROMPT, ANALYSIS_PROMPT,
)
from src.core.models import PolicyAnalysis, PolicyType, CostInfo


# --- _extract_json ---

class TestExtractJson:
    def test_raw_json(self):
        text = '{"relevant": true, "confidence": 8}'
        result = _extract_json(text)
        assert '"relevant": true' in result

    def test_json_in_code_block(self):
        text = 'Here is the result:\n```json\n{"relevant": true}\n```'
        result = _extract_json(text)
        assert result == '{"relevant": true}'

    def test_json_in_generic_code_block(self):
        text = '```\n{"relevant": false}\n```'
        result = _extract_json(text)
        assert result == '{"relevant": false}'

    def test_json_with_surrounding_text(self):
        text = 'The analysis shows: {"is_relevant": true, "score": 9} end.'
        result = _extract_json(text)
        assert '"is_relevant": true' in result

    def test_nested_braces(self):
        text = '{"outer": {"inner": 1}}'
        result = _extract_json(text)
        assert result == '{"outer": {"inner": 1}}'


# --- _coerce_types ---

class TestCoerceTypes:
    def test_string_true_to_bool(self):
        result = _coerce_types({"is_relevant": "true"})
        assert result["is_relevant"] is True

    def test_string_yes_to_bool(self):
        result = _coerce_types({"is_relevant": "yes"})
        assert result["is_relevant"] is True

    def test_string_ja_to_bool(self):
        result = _coerce_types({"is_relevant": "ja"})
        assert result["is_relevant"] is True

    def test_string_false_to_bool(self):
        result = _coerce_types({"is_relevant": "false"})
        assert result["is_relevant"] is False

    def test_int_to_bool(self):
        result = _coerce_types({"is_relevant": 1})
        assert result["is_relevant"] is True

    def test_float_score_to_int(self):
        result = _coerce_types({"relevance_score": 7.5})
        assert result["relevance_score"] == 7

    def test_string_score_to_int(self):
        result = _coerce_types({"relevance_score": "8/10"})
        assert result["relevance_score"] == 8

    def test_score_clamped_to_10(self):
        result = _coerce_types({"relevance_score": 15})
        assert result["relevance_score"] == 10

    def test_score_clamped_to_0(self):
        result = _coerce_types({"relevance_score": -5})
        assert result["relevance_score"] == 0

    def test_unparseable_score_defaults_to_zero(self):
        """Completely unparseable score string should default to 0."""
        result = _coerce_types({"relevance_score": "very high"})
        assert result["relevance_score"] == 0

    def test_unparseable_score_logs_warning(self, caplog):
        """Unparseable score should produce a warning log."""
        import logging
        with caplog.at_level(logging.WARNING, logger="src.core.llm"):
            _coerce_types({"relevance_score": "not a number"})
        assert any("unparseable" in r.message.lower() for r in caplog.records)

    def test_null_values_normalized(self):
        result = _coerce_types({
            "policy_name": "null",
            "jurisdiction": "N/A",
            "summary": "None",
            "effective_date": "n/a",
            "key_requirements": "unknown",
            "bill_number": "None",
        })
        # Required str fields → "" (not None), so Pydantic won't crash
        assert result["policy_name"] == ""
        assert result["jurisdiction"] == ""
        assert result["summary"] == ""
        assert result["key_requirements"] == ""
        # Optional fields → None
        assert result["effective_date"] is None
        assert result["bill_number"] is None

    def test_missing_relevance_explanation(self):
        result = _coerce_types({})
        assert result["relevance_explanation"] == "No explanation provided"

    def test_policy_type_default_when_not_relevant(self):
        result = _coerce_types({"is_relevant": False, "policy_type": None})
        assert result["policy_type"] == "not_relevant"

    def test_policy_type_default_when_relevant(self):
        result = _coerce_types({"is_relevant": True, "policy_type": "null"})
        assert result["policy_type"] == "unknown"

    def test_coerce_referenced_policies_from_null(self):
        """Null referenced_policies should become empty list."""
        result = _coerce_types({"referenced_policies": None, "referenced_urls": "null"})
        assert result["referenced_policies"] == []
        assert result["referenced_urls"] == []

    def test_coerce_referenced_policies_from_string(self):
        """Single string referenced_policies should become one-element list."""
        result = _coerce_types({"referenced_policies": "EU EED", "referenced_urls": ""})
        assert result["referenced_policies"] == ["EU EED"]
        assert result["referenced_urls"] == []

    def test_coerce_referenced_policies_filters_nulls(self):
        """List with null-like values should have them filtered out."""
        result = _coerce_types({
            "referenced_policies": ["EU EED", "N/A", "", None],
            "referenced_urls": ["https://x.com", "null"],
        })
        assert result["referenced_policies"] == ["EU EED"]
        assert result["referenced_urls"] == ["https://x.com"]

    def test_coerce_referenced_policies_missing_key(self):
        """Missing referenced_policies key should be added as empty list."""
        result = _coerce_types({})
        assert result.get("referenced_policies", []) == []
        assert result.get("referenced_urls", []) == []


# --- ClaudeClient.to_policy ---

class TestToPolicy:
    @pytest.fixture
    def client(self):
        # Create without actual API key — we only test to_policy
        client = ClaudeClient.__new__(ClaudeClient)
        client.cost = CostInfo()
        return client

    def test_converts_analysis_to_policy(self, client):
        analysis = PolicyAnalysis(
            is_relevant=True,
            relevance_score=8,
            policy_type="law",
            policy_name="Energy Act",
            jurisdiction="Germany",
            summary="A law about energy",
            effective_date="2024-06-01",
            key_requirements="Must recover heat",
        )
        policy = client.to_policy(analysis, "https://a.gov/p1", "en", "dom1", "scan1")
        assert policy is not None
        assert policy.url == "https://a.gov/p1"
        assert policy.policy_name == "Energy Act"
        assert policy.jurisdiction == "Germany"
        assert policy.policy_type == PolicyType.LAW
        assert policy.effective_date == date(2024, 6, 1)
        assert policy.domain_id == "dom1"
        assert policy.scan_id == "scan1"

    def test_returns_none_when_not_relevant(self, client):
        analysis = PolicyAnalysis(
            is_relevant=False,
            policy_name="Something",
        )
        assert client.to_policy(analysis, "https://a.gov", "en") is None

    def test_returns_none_when_no_name(self, client):
        analysis = PolicyAnalysis(
            is_relevant=True,
            policy_name="",
        )
        assert client.to_policy(analysis, "https://a.gov", "en") is None

    def test_invalid_policy_type_becomes_unknown(self, client):
        analysis = PolicyAnalysis(
            is_relevant=True,
            policy_name="Test",
            policy_type="not_a_real_type",
        )
        policy = client.to_policy(analysis, "https://a.gov", "en")
        assert policy.policy_type == PolicyType.UNKNOWN

    def test_invalid_date_ignored(self, client):
        analysis = PolicyAnalysis(
            is_relevant=True,
            policy_name="Test",
            effective_date="not-a-date",
        )
        policy = client.to_policy(analysis, "https://a.gov", "en")
        assert policy.effective_date is None

    def test_missing_jurisdiction_defaults_to_unknown(self, client):
        analysis = PolicyAnalysis(
            is_relevant=True,
            policy_name="Test",
            jurisdiction="",
        )
        policy = client.to_policy(analysis, "https://a.gov", "en")
        assert policy.jurisdiction == "Unknown"

    def test_to_policy_preserves_referenced_policies(self, client):
        """referenced_policies and referenced_urls should flow through to Policy."""
        analysis = PolicyAnalysis(
            is_relevant=True,
            relevance_score=8,
            policy_type="law",
            policy_name="Energy Efficiency Act",
            jurisdiction="Germany",
            summary="A law about heat reuse",
            key_requirements="Must reuse waste heat",
            referenced_policies=["EU EED Article 26", "EnEfG §12"],
            referenced_urls=["https://eur-lex.europa.eu/eli/dir/2023/1791"],
        )

        policy = client.to_policy(analysis, "https://example.gov", "de")

        assert policy is not None
        assert policy.referenced_policies == ["EU EED Article 26", "EnEfG §12"]
        assert policy.referenced_urls == ["https://eur-lex.europa.eu/eli/dir/2023/1791"]

        # Verify end-to-end sheet serialization
        row = policy.to_sheet_row()
        assert row[17] == "EU EED Article 26; EnEfG §12"
        assert row[18] == "https://eur-lex.europa.eu/eli/dir/2023/1791"

    def test_to_policy_empty_references_default(self, client):
        """Policy with no references should have empty lists."""
        analysis = PolicyAnalysis(
            is_relevant=True,
            policy_name="Basic Act",
            jurisdiction="US",
            summary="No references",
        )
        policy = client.to_policy(analysis, "https://a.gov", "en")
        assert policy.referenced_policies == []
        assert policy.referenced_urls == []


# --- ClaudeClient.update_cost_estimate ---

class TestUpdateCostEstimate:
    def test_cost_with_both_models(self):
        client = ClaudeClient.__new__(ClaudeClient)
        client.cost = CostInfo(
            input_tokens=100_000,
            output_tokens=10_000,
            screening_calls=50,
            analysis_calls=10,
        )
        client.update_cost_estimate()
        assert client.cost.total_usd > 0

    def test_cost_with_only_analysis(self):
        client = ClaudeClient.__new__(ClaudeClient)
        client.cost = CostInfo(
            input_tokens=50_000,
            output_tokens=5_000,
            screening_calls=0,
            analysis_calls=5,
        )
        client.update_cost_estimate()
        assert client.cost.total_usd > 0

    def test_cost_zero_tokens(self):
        client = ClaudeClient.__new__(ClaudeClient)
        client.cost = CostInfo()
        client.update_cost_estimate()
        assert client.cost.total_usd == 0


# --- Prompt content tests ---

class TestPromptContent:
    """Verify expanded prompts cover broader policy types."""

    def test_screening_mentions_reporting(self):
        assert "reporting" in SCREENING_PROMPT.lower()

    def test_screening_mentions_cost_benefit(self):
        assert "cost-benefit" in SCREENING_PROMPT.lower()

    def test_screening_mentions_tax_incentives(self):
        assert "tax incentiv" in SCREENING_PROMPT.lower()

    def test_screening_mentions_multi_language(self):
        assert "NO" in SCREENING_PROMPT or "any language" in SCREENING_PROMPT.lower()

    def test_analysis_mentions_reporting(self):
        assert "reporting" in ANALYSIS_PROMPT.lower()

    def test_analysis_mentions_cost_benefit(self):
        assert "cost-benefit" in ANALYSIS_PROMPT.lower()

    def test_analysis_mentions_tax_incentives(self):
        assert "tax incentiv" in ANALYSIS_PROMPT.lower()

    def test_analysis_mentions_eed(self):
        assert "EED" in ANALYSIS_PROMPT


# --- Scanner delay constants ---

class TestScannerDelayConstants:
    """Verify scanner delay constants are generous enough for Anthropic rate limits."""

    def test_base_delay_is_generous(self):
        """BASE_DELAY should be >= 10s since Anthropic rate limits are 60-120s."""
        assert ClaudeClient.BASE_DELAY >= 10.0

    def test_max_delay_matches_api_retry_after(self):
        """MAX_DELAY should be >= 120s to match typical retry-after headers."""
        assert ClaudeClient.MAX_DELAY >= 120.0

    def test_max_retries_at_least_3(self):
        """At least 3 retries to survive transient rate limits."""
        assert ClaudeClient.MAX_RETRIES >= 3


# --- Screening rate limit retry ---

def _make_screening_response(relevant: bool = True, confidence: int = 7):
    """Create a mock API response for screening."""
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 10
    content_block = MagicMock()
    content_block.text = f'{{"relevant": {str(relevant).lower()}, "confidence": {confidence}}}'
    response = MagicMock()
    response.content = [content_block]
    response.usage = usage
    return response


class TestScreeningRateLimitRetry:
    """Verify that screen_relevance retries on 429 instead of failing open."""

    def _build_client(self):
        """Create a ClaudeClient with mocked async client."""
        client = ClaudeClient.__new__(ClaudeClient)
        client.screening_model = "claude-haiku-4-5-20251001"
        client.analysis_model = "claude-sonnet-4-20250514"
        client.cost = CostInfo()
        client.client = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_screening_retries_on_rate_limit(self):
        """Should retry on 429 and succeed on second attempt."""
        client = self._build_client()

        rate_error = anthropic.RateLimitError.__new__(anthropic.RateLimitError)
        rate_error.response = None

        success = _make_screening_response(relevant=False, confidence=2)

        client.client.messages.create = AsyncMock(
            side_effect=[rate_error, success]
        )

        result = await client.screen_relevance("test content", "https://test.gov/page")

        # Should have retried and gotten the actual result (not relevant)
        assert result.relevant is False
        assert result.confidence == 2
        assert client.client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_screening_uses_retry_after_header(self):
        """Should respect retry-after header from API response."""
        client = self._build_client()

        # Create a real exception instance with a mock response bearing retry-after
        rate_error = anthropic.RateLimitError.__new__(anthropic.RateLimitError)
        rate_error.response = MagicMock()
        rate_error.response.headers = {"retry-after": "0.01"}

        success = _make_screening_response(relevant=True, confidence=8)

        client.client.messages.create = AsyncMock(
            side_effect=[rate_error, success]
        )

        result = await client.screen_relevance("test content", "https://test.gov/page")

        assert result.relevant is True
        assert client.client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_screening_fails_open_after_exhausting_retries(self):
        """After MAX_RETRIES rate limits, should fail open (assume relevant)."""
        client = self._build_client()

        rate_error = anthropic.RateLimitError.__new__(anthropic.RateLimitError)
        rate_error.response = None

        client.client.messages.create = AsyncMock(
            side_effect=[rate_error] * ClaudeClient.MAX_RETRIES
        )

        result = await client.screen_relevance("test content", "https://test.gov/page")

        # Should fail open after exhausting retries
        assert result.relevant is True
        assert result.confidence == 5
        assert client.client.messages.create.call_count == ClaudeClient.MAX_RETRIES

    @pytest.mark.asyncio
    async def test_screening_auth_error_not_retried(self):
        """Authentication errors should raise immediately, not retry."""
        client = self._build_client()

        from src.core.llm import LLMAuthError

        auth_error = anthropic.AuthenticationError.__new__(
            anthropic.AuthenticationError
        )

        client.client.messages.create = AsyncMock(side_effect=auth_error)

        with pytest.raises(LLMAuthError):
            await client.screen_relevance("test content", "https://test.gov/page")

        # Should NOT retry
        assert client.client.messages.create.call_count == 1

    @pytest.mark.asyncio
    async def test_screening_connection_error_fails_open(self):
        """Non-retryable errors should fail open (assume relevant)."""
        client = self._build_client()

        client.client.messages.create = AsyncMock(
            side_effect=ConnectionError("Network down")
        )

        result = await client.screen_relevance("test content", "https://test.gov/page")

        # Should fail open
        assert result.relevant is True
        assert result.confidence == 5
