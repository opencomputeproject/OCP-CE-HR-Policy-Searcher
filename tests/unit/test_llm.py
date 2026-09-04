"""Tests for LLM helpers and ClaudeClient.to_policy()."""

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import anthropic
import pytest

from src.core.llm import (
    _extract_json, _coerce_types, _resolve_model, ClaudeClient,
    SCREENING_PROMPT, CLASSIFY_PROMPT, ANALYSIS_PROMPT,
    parse_screening_response, parse_screening_json, MAX_QUOTE_CHARS,
)
from src.core.models import (
    PolicyAnalysis, PolicyType, CostInfo,
    DEFAULT_ANALYSIS_MODEL, DEFAULT_SCREENING_MODEL,
)
from src.core.policy_schema import to_staging_row
from src.core.pricing import PricingLoader


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

    @pytest.mark.small
    def test_policy_name_en_null_normalized_to_none(self):
        result = _coerce_types({"policy_name_en": "null"})
        assert result["policy_name_en"] is None

    @pytest.mark.small
    def test_policy_name_en_empty_string_normalized_to_none(self):
        result = _coerce_types({"policy_name_en": ""})
        assert result["policy_name_en"] is None

    @pytest.mark.small
    def test_policy_name_en_missing_key_left_absent(self):
        """No key added when the model omits it - PolicyAnalysis's own
        default (None) applies, same as any old fixture predating this field."""
        result = _coerce_types({})
        assert "policy_name_en" not in result

    @pytest.mark.small
    def test_policy_name_en_real_value_passes_through(self):
        result = _coerce_types({"policy_name_en": "Energy Transition Act"})
        assert result["policy_name_en"] == "Energy Transition Act"


# --- parse_screening_response / parse_screening_json (WP-5) ---

class TestParseScreeningResponse:
    """The screener now asks for kind/dc_quote/heat_quote/confidence
    instead of a single relevant/confidence judgment.

    FAILS TODAY: ScreeningResult has no `kind` field yet, so
    parse_screening_response does not exist and this is red before the
    implementation lands.
    """

    @pytest.mark.small
    def test_kind_is_parsed(self):
        result = parse_screening_response(
            {"kind": "report", "dc_quote": None, "heat_quote": None, "confidence": 8},
        )
        assert result.kind == "report"

    @pytest.mark.small
    @pytest.mark.parametrize("dc,heat,expected", [
        ("A sentence naming a data centre.", "A sentence about reusing heat.", True),
        ("A sentence naming a data centre.", None, False),
        (None, "A sentence about reusing heat.", False),
        (None, None, False),
    ])
    def test_relevant_is_derived_from_both_quotes(self, dc, heat, expected):
        result = parse_screening_response(
            {"kind": "bill", "dc_quote": dc, "heat_quote": heat, "confidence": 7},
        )
        assert result.relevant is expected

    @pytest.mark.small
    def test_unknown_kind_becomes_other(self):
        result = parse_screening_response(
            {"kind": "memo", "dc_quote": None, "heat_quote": None, "confidence": 5},
        )
        assert result.kind == "other"

    @pytest.mark.small
    def test_missing_kind_becomes_other_not_none(self):
        """A successfully parsed response always gets a real kind - `other`
        at worst. `kind=None` is reserved for the outer parse-failure
        fallback, so screening_decision can trust it as "not a real
        verdict, always proceed" without a well-formed-but-vague answer
        sneaking through the same door."""
        result = parse_screening_response({"confidence": 5})
        assert result.kind == "other"

    @pytest.mark.small
    def test_long_quote_is_truncated(self):
        long_quote = "D" * 500
        result = parse_screening_response(
            {"kind": "bill", "dc_quote": long_quote, "heat_quote": None, "confidence": 5},
        )
        assert len(result.dc_quote) == MAX_QUOTE_CHARS
        assert result.dc_quote == long_quote[:MAX_QUOTE_CHARS]

    @pytest.mark.small
    def test_quote_not_found_in_excerpt_is_flagged_not_dropped(self):
        result = parse_screening_response(
            {"kind": "bill", "dc_quote": "This sentence is not in the excerpt.",
             "heat_quote": None, "confidence": 6},
            excerpt="Completely different page content altogether.",
        )
        assert result.dc_quote == "This sentence is not in the excerpt."
        assert result.quote_verified is False

    @pytest.mark.small
    def test_quote_found_in_excerpt_is_verified(self):
        excerpt = "Some page text. The facility is a data centre. More text."
        result = parse_screening_response(
            {"kind": "bill", "dc_quote": "The facility is a data centre.",
             "heat_quote": None, "confidence": 6},
            excerpt=excerpt,
        )
        assert result.quote_verified is True

    @pytest.mark.small
    def test_quote_verified_ignores_whitespace_differences(self):
        """A quote copied across a line break or extra spaces is still the
        same sentence."""
        excerpt = "The   facility\nis a data centre."
        result = parse_screening_response(
            {"kind": "bill", "dc_quote": "The facility is a data centre.",
             "heat_quote": None, "confidence": 6},
            excerpt=excerpt,
        )
        assert result.quote_verified is True

    @pytest.mark.small
    def test_no_quotes_claimed_is_verified(self):
        """Nothing claimed, nothing to verify - null/null must not be
        flagged as an unverified quote."""
        result = parse_screening_response(
            {"kind": "report", "dc_quote": None, "heat_quote": None, "confidence": 8},
            excerpt="",
        )
        assert result.quote_verified is True

    @pytest.mark.small
    def test_null_string_quote_treated_as_none(self):
        """Some models answer the string "null" instead of JSON null."""
        result = parse_screening_response(
            {"kind": "bill", "dc_quote": "null", "heat_quote": "None", "confidence": 5},
        )
        assert result.dc_quote is None
        assert result.heat_quote is None
        assert result.relevant is False


class TestParseScreeningJson:
    @pytest.mark.small
    def test_malformed_json_falls_open_with_kind_none(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="src.core.llm"):
            result = parse_screening_json("not json at all")
        assert result.relevant is True
        assert result.confidence == 5
        assert result.kind is None
        assert any("screening" in r.message.lower() for r in caplog.records)

    @pytest.mark.small
    def test_malformed_json_warning_includes_first_200_chars(self, caplog):
        import logging
        junk = "x" * 500
        with caplog.at_level(logging.WARNING, logger="src.core.llm"):
            parse_screening_json(junk)
        messages = " ".join(r.message for r in caplog.records)
        assert "x" * 200 in messages
        assert "x" * 500 not in messages

    @pytest.mark.small
    def test_well_formed_json_parses_through(self):
        raw = '{"kind": "act", "dc_quote": "A data centre.", ' \
              '"heat_quote": "Reuse the heat.", "confidence": 9}'
        result = parse_screening_json(raw, excerpt="A data centre. Reuse the heat.")
        assert result.kind == "act"
        assert result.relevant is True

    @pytest.mark.small
    def test_json_in_code_block_parses_through(self):
        raw = '```json\n{"kind": "act", "dc_quote": null, "heat_quote": null, ' \
              '"confidence": 4}\n```'
        result = parse_screening_json(raw)
        assert result.kind == "act"


# --- ClaudeClient.to_policy ---

class TestToPolicy:
    @pytest.fixture
    def client(self):
        # Create without actual API key - we only test to_policy
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

    def test_unnamed_relevant_policy_gets_synthesized_name(self, client):
        """A relevant policy without a crisp title must not be dropped."""
        analysis = PolicyAnalysis(
            is_relevant=True,
            policy_name="",
            policy_type="regulation",
            jurisdiction="Netherlands",
            relevance_score=7,
            summary="Waste heat feed-in rules",
        )
        policy = client.to_policy(analysis, "https://a.gov/x", "nl")
        assert policy is not None
        assert policy.policy_name  # synthesized, never empty
        assert "Netherlands" in policy.policy_name

    def test_to_policies_extracts_all_policies_on_page(self, client):
        """Index pages listing several laws must yield several records."""
        analysis = PolicyAnalysis(
            is_relevant=True,
            relevance_score=8,
            policy_type="law",
            policy_name="Heat Act",
            jurisdiction="Denmark",
            summary="Primary law",
            additional_policies=[
                PolicyAnalysis(
                    is_relevant=True, relevance_score=7, policy_type="regulation",
                    policy_name="Heat Supply Order", jurisdiction="Denmark",
                    summary="Order under the act",
                ),
                PolicyAnalysis(
                    is_relevant=True, relevance_score=6, policy_type="incentive",
                    policy_name="Waste Heat Tax Relief", jurisdiction="Denmark",
                    summary="Tax measure",
                ),
            ],
        )
        policies = client.to_policies(analysis, "https://a.gov/laws", "da", "dom1", "s1")
        assert len(policies) == 3
        names = {p.policy_name for p in policies}
        assert names == {"Heat Act", "Heat Supply Order", "Waste Heat Tax Relief"}
        assert all(p.url == "https://a.gov/laws" for p in policies)

    def test_to_policies_skips_irrelevant_additionals(self, client):
        analysis = PolicyAnalysis(
            is_relevant=True, relevance_score=8, policy_type="law",
            policy_name="Heat Act", jurisdiction="DK", summary="x",
            additional_policies=[
                PolicyAnalysis(is_relevant=False, policy_name="Noise"),
            ],
        )
        policies = client.to_policies(analysis, "https://a.gov", "en")
        assert len(policies) == 1

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

        # Verify end-to-end sheet serialization (Referenced Policies/URLs
        # are extra columns after the 13 master-database columns).
        from src.core.policy_schema import STAGING_HEADERS
        row = to_staging_row(policy)
        assert row[STAGING_HEADERS.index("Referenced Policies")] == \
            "EU EED Article 26; EnEfG §12"
        assert row[STAGING_HEADERS.index("Referenced URLs")] == \
            "https://eur-lex.europa.eu/eli/dir/2023/1791"

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

    @pytest.mark.small
    def test_policy_name_en_propagates_to_policy(self, client):
        analysis = PolicyAnalysis(
            is_relevant=True,
            policy_name="Energiewendegesetz",
            policy_name_en="Energy Transition Act",
            jurisdiction="Germany",
            summary="x",
        )
        policy = client.to_policy(analysis, "https://a.gov", "de")
        assert policy is not None
        assert policy.policy_name == "Energiewendegesetz"
        assert policy.policy_name_en == "Energy Transition Act"

    @pytest.mark.small
    def test_policy_name_en_repeated_when_already_english(self, client):
        analysis = PolicyAnalysis(
            is_relevant=True,
            policy_name="Data Center Efficiency Act",
            policy_name_en="Data Center Efficiency Act",
            jurisdiction="US",
            summary="x",
        )
        policy = client.to_policy(analysis, "https://a.gov", "en")
        assert policy.policy_name_en == policy.policy_name

    @pytest.mark.small
    def test_policy_name_en_defaults_to_none_when_omitted(self, client):
        """Old fixtures / LLM responses without policy_name_en must keep
        parsing and producing a Policy (WP-35 backward compatibility)."""
        analysis = PolicyAnalysis(
            is_relevant=True,
            policy_name="Test",
            jurisdiction="US",
            summary="x",
        )
        policy = client.to_policy(analysis, "https://a.gov", "en")
        assert policy is not None
        assert policy.policy_name_en is None


# --- ClaudeClient.update_cost_estimate ---

class TestUpdateCostEstimate:
    """WP-22: exact per-stage pricing, no call-count-fraction blend."""

    def _client(self, **cost_kwargs):
        client = ClaudeClient.__new__(ClaudeClient)
        client.screening_model = DEFAULT_SCREENING_MODEL
        client.analysis_model = DEFAULT_ANALYSIS_MODEL
        client.cost = CostInfo(**cost_kwargs)
        from src.core.pricing import PricingLoader
        client._pricing = PricingLoader()
        return client

    @pytest.mark.small
    def test_cost_with_both_stages(self):
        client = self._client(
            screening_calls=50,
            analysis_calls=10,
            screening_input_tokens=100_000,
            screening_output_tokens=2_500,
            analysis_input_tokens=200_000,
            analysis_output_tokens=10_000,
        )
        client.update_cost_estimate()
        assert client.cost.total_usd > 0

    @pytest.mark.small
    def test_cost_with_only_analysis(self):
        client = self._client(
            analysis_calls=5,
            analysis_input_tokens=50_000,
            analysis_output_tokens=5_000,
        )
        client.update_cost_estimate()
        assert client.cost.total_usd > 0

    @pytest.mark.small
    def test_cost_zero_tokens(self):
        client = self._client()
        client.update_cost_estimate()
        assert client.cost.total_usd == 0

    @pytest.mark.small
    def test_cost_is_exact_not_a_call_count_blend(self):
        """Regression: the old formula blended input_tokens/output_tokens
        (the combined pool) by screening_calls/analysis_calls fraction. A
        scenario with few calls carrying huge screening token counts and
        many calls carrying tiny analysis token counts makes the old blend
        (call-count-weighted) diverge sharply from the exact per-stage
        price - assert the exact answer, not the blend's."""
        pricing = PricingLoader()
        haiku = pricing.pricing_for(DEFAULT_SCREENING_MODEL)
        sonnet = pricing.pricing_for(DEFAULT_ANALYSIS_MODEL)

        screening_input, screening_output = 1_000_000, 50_000
        analysis_input, analysis_output = 1_000, 100

        client = self._client(
            screening_calls=1,
            analysis_calls=99,
            screening_input_tokens=screening_input,
            screening_output_tokens=screening_output,
            analysis_input_tokens=analysis_input,
            analysis_output_tokens=analysis_output,
        )
        client.update_cost_estimate()

        exact = round(
            haiku.cost_usd(screening_input, screening_output)
            + sonnet.cost_usd(analysis_input, analysis_output),
            4,
        )

        # The old blend priced ALL tokens (screening + analysis combined)
        # at haiku_frac/sonnet_frac of the call counts (1/100 haiku,
        # 99/100 sonnet) - wildly different from pricing each stage's own
        # tokens at its own model.
        total_input = screening_input + analysis_input
        total_output = screening_output + analysis_output
        haiku_frac = 1 / 100
        sonnet_frac = 99 / 100
        old_blend = round(
            total_input * (haiku_frac * haiku.input_per_mtok
                           + sonnet_frac * sonnet.input_per_mtok) / 1_000_000
            + total_output * (haiku_frac * haiku.output_per_mtok
                              + sonnet_frac * sonnet.output_per_mtok) / 1_000_000,
            4,
        )

        assert client.cost.total_usd == exact
        assert client.cost.total_usd != old_blend

    @pytest.mark.small
    def test_screening_priced_at_screening_model_analysis_at_analysis_model(self):
        pricing = PricingLoader()
        haiku = pricing.pricing_for(DEFAULT_SCREENING_MODEL)
        sonnet = pricing.pricing_for(DEFAULT_ANALYSIS_MODEL)

        client = self._client(
            screening_input_tokens=10_000, screening_output_tokens=200,
            analysis_input_tokens=20_000, analysis_output_tokens=1_000,
        )
        client.update_cost_estimate()

        expected = round(
            haiku.cost_usd(10_000, 200) + sonnet.cost_usd(20_000, 1_000), 4,
        )
        assert client.cost.total_usd == expected

    @pytest.mark.medium
    def test_reacts_to_monkeypatched_pricing_table(self, tmp_path):
        """Both stages must actually consult the pricing table, not a
        constant baked into the function."""
        (tmp_path / "pricing.yaml").write_text(
            "models:\n"
            f"  {DEFAULT_SCREENING_MODEL}:\n"
            "    input_per_mtok: 1000.0\n"
            "    output_per_mtok: 1000.0\n"
            f"  {DEFAULT_ANALYSIS_MODEL}:\n"
            "    input_per_mtok: 1000.0\n"
            "    output_per_mtok: 1000.0\n"
            "estimator: {}\n",
            encoding="utf-8",
        )
        client = self._client(
            screening_input_tokens=1_000, screening_output_tokens=0,
            analysis_input_tokens=1_000, analysis_output_tokens=0,
        )
        from src.core.pricing import PricingLoader as _PL
        client._pricing = _PL(config_dir=str(tmp_path))

        client.update_cost_estimate()

        # 1000 tokens * $1000/Mtok = $1 per stage, two stages = $2
        assert client.cost.total_usd == pytest.approx(2.0)


# --- Prompt content tests ---

class TestPromptContent:
    """Verify expanded prompts cover broader policy types."""

    def test_screening_mentions_multi_language(self):
        assert "NO" in SCREENING_PROMPT or "any language" in SCREENING_PROMPT.lower()

    def test_analysis_mentions_reporting(self):
        assert "reporting" in ANALYSIS_PROMPT.lower()

    def test_analysis_mentions_cost_benefit(self):
        assert "cost-benefit" in ANALYSIS_PROMPT.lower()

    def test_analysis_mentions_tax_incentives(self):
        assert "tax incentiv" in ANALYSIS_PROMPT.lower()

    @pytest.mark.small
    def test_the_data_centre_rule_is_not_hardcoded_in_the_prompt(self):
        """FAILS ON OLD BEHAVIOR. The prompt used to assert in capitals
        that heat network policy counts whether or not data centres are
        named, while the reviewer was rejecting exactly those pages. The
        rule now comes from the scope setting, so the two cannot disagree.
        """
        from src.core.scope import OFF, REQUIRED, screening_scope_line

        assert "{scope_line}" in SCREENING_PROMPT
        assert "whether or not" not in SCREENING_PROMPT.lower()

        required = SCREENING_PROMPT.format(
            url="u", content="c", scope_line=screening_scope_line(REQUIRED))
        permissive = SCREENING_PROMPT.format(
            url="u", content="c", scope_line=screening_scope_line(OFF))
        assert "must concern data centres" in required.lower()
        assert "whether or not" in permissive.lower()

    # --- WP-5: the screener asks three narrow questions ---

    @pytest.mark.small
    def test_screening_asks_for_document_kind(self):
        lowered = CLASSIFY_PROMPT.lower()
        for kind in (
            "act", "bill", "regulation", "consultation", "grant", "plan",
            "index", "report", "article", "speech", "question", "other",
        ):
            assert kind in lowered, f"kind {kind!r} missing from CLASSIFY_PROMPT"

    @pytest.mark.small
    def test_screening_defines_the_six_named_kinds(self):
        """The kinds a reviewer's removal reasons actually turn on need a
        one-line definition each, so a Kleine Anfrage lands as `question`
        and a Diet transcript as `speech`, not `report` or `other`."""
        lowered = CLASSIFY_PROMPT.lower()
        assert "kleine anfrage" in lowered  # question
        assert "transcript" in lowered  # speech
        assert "proposing future" in lowered or "roadmap" in lowered  # plan
        assert "news item" in lowered  # article
        assert "audit" in lowered and "evaluation" in lowered  # report
        assert "listing" in lowered or "directory" in lowered  # index

    @pytest.mark.small
    def test_screening_asks_for_a_verbatim_data_centre_quote(self):
        lowered = CLASSIFY_PROMPT.lower()
        assert "dc_quote" in lowered
        assert "names a data centre" in lowered or "names a data center" in lowered

    @pytest.mark.small
    def test_screening_asks_for_a_verbatim_heat_reuse_quote(self):
        lowered = CLASSIFY_PROMPT.lower()
        assert "heat_quote" in lowered
        assert "reusing or recovering heat" in lowered

    @pytest.mark.small
    def test_screening_says_quotes_must_be_copied_never_invented(self):
        lowered = CLASSIFY_PROMPT.lower()
        assert "verbatim" in lowered
        assert "never invent" in lowered or "never be invented" in lowered

    @pytest.mark.small
    def test_screening_says_null_is_correct_when_no_sentence_exists(self):
        lowered = CLASSIFY_PROMPT.lower()
        assert "null" in lowered
        assert "no such sentence exists" in lowered

    @pytest.mark.small
    def test_the_classifier_schema_has_the_three_fields_and_no_relevance_question(self):
        """The classifier never asks the yes/no: folding it into one call changed
        the model's relevance answers in replay and lost reviewer keeps."""
        assert '"kind"' in CLASSIFY_PROMPT
        assert '"dc_quote"' in CLASSIFY_PROMPT
        assert '"heat_quote"' in CLASSIFY_PROMPT
        assert '"confidence"' in CLASSIFY_PROMPT
        assert '"relevant"' not in CLASSIFY_PROMPT

    @pytest.mark.small
    def test_the_gate_prompt_is_the_original_recall_first_one(self):
        """ADR-0011: every stored row passed this prompt; it stays verbatim."""
        assert SCREENING_PROMPT.startswith("You are a RECALL-FIRST relevance screener.")
        assert '{{"relevant": true/false, "confidence": 1-10}}' in SCREENING_PROMPT
        assert "kind" not in SCREENING_PROMPT.split("RESPOND WITH JSON ONLY")[1]

    def test_analysis_asks_for_every_policy_on_page(self):
        lowered = ANALYSIS_PROMPT.lower()
        assert "additional_policies" in lowered
        assert "every" in lowered or "each" in lowered or "all distinct" in lowered

    def test_analysis_forbids_empty_name_for_relevant(self):
        lowered = ANALYSIS_PROMPT.lower()
        assert "descriptive label" in lowered or "never leave" in lowered

    @pytest.mark.small
    def test_analysis_mentions_policy_name_en(self):
        assert "policy_name_en" in ANALYSIS_PROMPT

    @pytest.mark.small
    def test_analysis_pins_summary_language_to_english(self):
        lowered = ANALYSIS_PROMPT.lower()
        assert "write the summary in english" in lowered

    @pytest.mark.small
    def test_analysis_policy_name_en_repeats_when_already_english(self):
        lowered = ANALYSIS_PROMPT.lower()
        assert "already english" in lowered


class TestScreeningExcerpt:
    """Long documents must not be screened on their head alone."""

    def test_short_content_passes_through(self):
        from src.core.llm import screening_excerpt
        text = "short policy text"
        assert screening_excerpt(text, ["policy"]) == text

    def test_head_kept_for_long_content(self):
        from src.core.llm import screening_excerpt
        text = "H" * 20000
        excerpt = screening_excerpt(text, [])
        assert excerpt.startswith("H" * 100)
        assert len(excerpt) <= 13000

    def test_anchor_beyond_head_included(self):
        from src.core.llm import screening_excerpt
        text = ("x" * 10000) + " Fernwärme Abwärmenutzung mandate " + ("y" * 5000)
        excerpt = screening_excerpt(text, ["Fernwärme"])
        assert "Fernwärme" in excerpt
        assert "Abwärmenutzung" in excerpt  # window around the anchor, not just the term

    def test_anchor_match_is_case_insensitive(self):
        from src.core.llm import screening_excerpt
        text = ("x" * 10000) + " FERNWÄRME statute " + ("y" * 5000)
        excerpt = screening_excerpt(text, ["fernwärme"])
        assert "FERNWÄRME" in excerpt

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

def _make_screening_response(
    kind: str = "act",
    dc_quote: str | None = "A sentence naming a data centre.",
    heat_quote: str | None = "A sentence about reusing heat.",
    confidence: int = 7,
):
    """Create a mock API response for screening (WP-5 kind/dc_quote/
    heat_quote/confidence schema). Pass dc_quote=None and/or heat_quote=None
    to simulate the model finding no such sentence - relevant is then
    derived as False by the parser, the same as a real "not relevant"
    verdict."""
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 10
    content_block = MagicMock()

    def _json_str(value: str | None) -> str:
        return "null" if value is None else f'"{value}"'

    content_block.text = (
        f'{{"kind": "{kind}", "dc_quote": {_json_str(dc_quote)}, '
        f'"heat_quote": {_json_str(heat_quote)}, "confidence": {confidence}}}'
    )
    response = MagicMock()
    response.content = [content_block]
    response.usage = usage
    return response


def _make_gate_response(relevant: bool, confidence: int):
    """The gate's answer shape (SCREENING_PROMPT): {"relevant", "confidence"}."""
    response = MagicMock()
    response.content = [MagicMock(text=json.dumps({"relevant": relevant, "confidence": confidence}))]
    response.usage = MagicMock(input_tokens=100, output_tokens=10)
    return response


@pytest.mark.large  # real-sleep backoff timing: ~40s for the class
class TestScreeningRateLimitRetry:
    """Verify that screen_relevance retries on 429 instead of failing open."""

    def _build_client(self):
        """Create a ClaudeClient with mocked async client (skips validation)."""
        client = ClaudeClient.__new__(ClaudeClient)
        client.screening_model = DEFAULT_SCREENING_MODEL
        client.analysis_model = DEFAULT_ANALYSIS_MODEL
        client.cost = CostInfo()
        client.client = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_screening_retries_on_rate_limit(self):
        """Should retry on 429 and succeed on second attempt."""
        client = self._build_client()

        rate_error = anthropic.RateLimitError.__new__(anthropic.RateLimitError)
        rate_error.response = None

        success = _make_gate_response(relevant=False, confidence=2)

        client.client.messages.create = AsyncMock(
            side_effect=[rate_error, success]
        )

        result = await client.screen_relevance("test content", "https://test.gov/page")

        # Should have retried and gotten the gate's actual answer
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

        success = _make_screening_response(confidence=8)  # default: both quotes present

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


# ---------------------------------------------------------------------------
# Model validation (_resolve_model)
# ---------------------------------------------------------------------------

class TestResolveModel:
    """_resolve_model() should validate and auto-fallback stale models."""

    def _mock_client(self):
        return MagicMock(spec=anthropic.Anthropic)

    def test_valid_model_passes_through(self):
        client = self._mock_client()
        client.models.retrieve.return_value = MagicMock(id="claude-haiku-4-5-20251001")

        result = _resolve_model(client, "claude-haiku-4-5-20251001", "screening", "haiku")
        assert result == "claude-haiku-4-5-20251001"
        client.models.retrieve.assert_called_once_with(model_id="claude-haiku-4-5-20251001")

    def test_stale_model_auto_resolves(self):
        client = self._mock_client()
        client.models.retrieve.side_effect = anthropic.NotFoundError(
            message="not found",
            response=MagicMock(status_code=404),
            body={"error": {"message": "not found"}},
        )
        # models.list returns newer haiku
        newer_model = MagicMock(id="claude-haiku-5-20260101", created_at="2026-01-01T00:00:00Z")
        client.models.list.return_value = [newer_model]

        result = _resolve_model(client, "claude-haiku-4-5-20251001", "screening", "haiku")
        assert result == "claude-haiku-5-20260101"

    def test_stale_model_no_alternatives_returns_original(self):
        client = self._mock_client()
        client.models.retrieve.side_effect = anthropic.NotFoundError(
            message="not found",
            response=MagicMock(status_code=404),
            body={"error": {"message": "not found"}},
        )
        # models.list returns only sonnet models (no haiku)
        client.models.list.return_value = [
            MagicMock(id="claude-sonnet-4-6", created_at="2025-06-01T00:00:00Z"),
        ]

        result = _resolve_model(client, "claude-haiku-4-5-20251001", "screening", "haiku")
        assert result == "claude-haiku-4-5-20251001"  # returns original

    def test_network_error_skips_validation(self):
        client = self._mock_client()
        client.models.retrieve.side_effect = ConnectionError("Network down")

        result = _resolve_model(client, "claude-haiku-4-5-20251001", "screening", "haiku")
        assert result == "claude-haiku-4-5-20251001"

    def test_auth_error_skips_validation(self):
        client = self._mock_client()
        client.models.retrieve.side_effect = anthropic.AuthenticationError(
            message="invalid key",
            response=MagicMock(status_code=401),
            body={"error": {"message": "invalid key"}},
        )

        result = _resolve_model(client, "claude-sonnet-4-6", "analysis", "sonnet")
        assert result == "claude-sonnet-4-6"

    def test_picks_newest_alternative(self):
        client = self._mock_client()
        client.models.retrieve.side_effect = anthropic.NotFoundError(
            message="not found",
            response=MagicMock(status_code=404),
            body={"error": {"message": "not found"}},
        )
        old_model = MagicMock(id="claude-haiku-4-5-20251001", created_at="2025-10-01T00:00:00Z")
        new_model = MagicMock(id="claude-haiku-5-20260301", created_at="2026-03-01T00:00:00Z")
        client.models.list.return_value = [old_model, new_model]

        result = _resolve_model(client, "claude-haiku-3-old", "screening", "haiku")
        assert result == "claude-haiku-5-20260301"  # newest by created_at
