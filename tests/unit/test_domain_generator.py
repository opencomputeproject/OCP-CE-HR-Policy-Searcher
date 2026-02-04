"""Unit tests for domain YAML generator."""

import yaml

from src.tools.domain_generator import (
    generate_domain_id,
    detect_region,
    suggest_output_file,
    build_domain_entry,
    format_domain_yaml,
)


class TestGenerateDomainId:
    """Test domain ID generation from hostnames."""

    def test_us_state_gov(self):
        assert generate_domain_id("lis.virginia.gov") == "va_lis"

    def test_us_state_gov_energy(self):
        assert generate_domain_id("energy.virginia.gov") == "va_energy"

    def test_us_federal_gov(self):
        assert generate_domain_id("energy.gov") == "us_energy"

    def test_us_federal_epa(self):
        assert generate_domain_id("epa.gov") == "us_epa"

    def test_strips_www_federal(self):
        assert generate_domain_id("www.energy.gov") == "us_energy"

    def test_uk_gov(self):
        assert generate_domain_id("www.gov.uk") == "uk_gov"

    def test_uk_legislation(self):
        assert generate_domain_id("legislation.gov.uk") == "uk_legislation"

    def test_eu_domain(self):
        result = generate_domain_id("eur-lex.europa.eu")
        assert "eur" in result

    def test_french_gov(self):
        result = generate_domain_id("www.legifrance.gouv.fr")
        assert "legifrance" in result

    def test_swiss_admin(self):
        result = generate_domain_id("www.bfe.admin.ch")
        assert "bfe" in result

    def test_generic_hostname(self):
        assert generate_domain_id("www.example.com") == "example_com"

    def test_strips_www_generic(self):
        assert generate_domain_id("www.data-center-map.com") == "data_center_map_com"

    def test_truncates_long_id(self):
        result = generate_domain_id("very-long-subdomain.extremely-long-state-name.gov")
        assert len(result) <= 30

    def test_no_leading_trailing_underscores(self):
        result = generate_domain_id("example.com")
        assert not result.startswith("_")
        assert not result.endswith("_")


class TestDetectRegion:
    """Test geographic region detection from hostname TLD."""

    def test_us_state(self):
        assert detect_region("energy.virginia.gov") == ["us", "us_states"]

    def test_us_federal(self):
        assert detect_region("energy.gov") == ["us"]

    def test_uk(self):
        assert detect_region("www.gov.uk") == ["uk"]

    def test_uk_legislation(self):
        assert detect_region("legislation.gov.uk") == ["uk"]

    def test_eu(self):
        assert detect_region("eur-lex.europa.eu") == ["eu"]

    def test_france(self):
        assert detect_region("www.legifrance.gouv.fr") == ["eu", "france"]

    def test_austria(self):
        assert detect_region("www.ris.gv.at") == ["eu", "eu_central"]

    def test_switzerland(self):
        assert detect_region("www.bfe.admin.ch") == ["eu_central"]

    def test_sweden(self):
        assert detect_region("www.riksdagen.se") == ["eu", "nordic"]

    def test_denmark(self):
        assert detect_region("www.retsinformation.dk") == ["eu", "nordic"]

    def test_japan(self):
        assert detect_region("www.enecho.meti.go.jp") == ["apac"]

    def test_singapore(self):
        assert detect_region("www.imda.gov.sg") == ["apac"]

    def test_australia(self):
        assert detect_region("www.energy.gov.au") == ["apac"]

    def test_unknown(self):
        assert detect_region("example.com") == []

    def test_strips_www(self):
        assert detect_region("www.energy.gov") == ["us"]


class TestSuggestOutputFile:
    """Test output file suggestion from hostname."""

    def test_us_state(self):
        assert suggest_output_file("energy.virginia.gov") == "us/virginia.yaml"

    def test_us_state_california(self):
        assert suggest_output_file("www.energy.ca.gov") == "us/ca.yaml"

    def test_us_federal(self):
        assert suggest_output_file("energy.gov") == "us/us_federal.yaml"

    def test_uk(self):
        assert suggest_output_file("www.gov.uk") == "uk.yaml"

    def test_france(self):
        assert suggest_output_file("www.legifrance.gouv.fr") == "france.yaml"

    def test_switzerland(self):
        assert suggest_output_file("www.bfe.admin.ch") == "switzerland.yaml"

    def test_eu(self):
        assert suggest_output_file("eur-lex.europa.eu") == "eu.yaml"

    def test_generic(self):
        assert suggest_output_file("example.com") == "new_domains.yaml"


class TestBuildDomainEntry:
    """Test domain entry dict construction."""

    def test_required_fields_present(self):
        entry = build_domain_entry(
            name="Test Domain",
            domain_id="test_domain",
            base_url="https://example.com",
            start_paths=["/"],
        )
        assert entry["name"] == "Test Domain"
        assert entry["id"] == "test_domain"
        assert entry["base_url"] == "https://example.com"
        assert entry["start_paths"] == ["/"]
        assert entry["enabled"] is True

    def test_defaults(self):
        entry = build_domain_entry(
            name="Test", domain_id="test",
            base_url="https://example.com", start_paths=["/"],
        )
        assert entry["language"] == "en"
        assert entry["requires_playwright"] is False
        assert entry["max_depth"] == 2
        assert entry["rate_limit_seconds"] == 2.0
        assert entry["category"] == ""
        assert entry["tags"] == []
        assert entry["policy_types"] == []

    def test_custom_values(self):
        entry = build_domain_entry(
            name="German Law",
            domain_id="de_law",
            base_url="https://gesetze.de",
            start_paths=["/enefg/"],
            language="de",
            requires_playwright=True,
            region=["eu", "germany"],
        )
        assert entry["language"] == "de"
        assert entry["requires_playwright"] is True
        assert entry["region"] == ["eu", "germany"]

    def test_verified_by_auto_generated(self):
        entry = build_domain_entry(
            name="Test", domain_id="test",
            base_url="https://example.com", start_paths=["/"],
        )
        assert entry["verified_by"] == "auto-generated"
        assert entry["verified_date"]  # non-empty


class TestFormatDomainYaml:
    """Test YAML formatting of domain entries."""

    def test_standalone_valid_yaml(self):
        entry = build_domain_entry(
            name="Test", domain_id="test",
            base_url="https://example.com", start_paths=["/"],
        )
        output = format_domain_yaml(entry, standalone=True)
        parsed = yaml.safe_load(output)
        assert "domains" in parsed
        assert len(parsed["domains"]) == 1
        assert parsed["domains"][0]["id"] == "test"

    def test_appending_valid_yaml(self):
        entry = build_domain_entry(
            name="Test", domain_id="test",
            base_url="https://example.com", start_paths=["/"],
        )
        output = format_domain_yaml(entry, standalone=False)
        # Non-standalone output is a list item; prepend domains: key to parse
        full = "domains:\n" + output
        parsed = yaml.safe_load(full)
        assert "domains" in parsed
        assert parsed["domains"][0]["id"] == "test"

    def test_contains_all_fields(self):
        entry = build_domain_entry(
            name="Energy Policy",
            domain_id="us_energy",
            base_url="https://energy.gov",
            start_paths=["/programs"],
            language="en",
            region=["us"],
        )
        output = format_domain_yaml(entry)
        assert "name:" in output
        assert "id:" in output
        assert "base_url:" in output
        assert "start_paths:" in output
        assert "enabled:" in output
        assert "region:" in output

    def test_unicode_support(self):
        entry = build_domain_entry(
            name="Bundesamt f\u00fcr Energie",
            domain_id="bfe",
            base_url="https://www.bfe.admin.ch",
            start_paths=["/"],
            language="de",
        )
        output = format_domain_yaml(entry)
        assert "Bundesamt f\u00fcr Energie" in output


class TestFormatDomainYamlStyle:
    """Test that YAML formatting matches hand-crafted domain file style."""

    def test_name_is_quoted(self):
        entry = build_domain_entry(
            name="Texas Legislature", domain_id="tx_legislature",
            base_url="https://capitol.texas.gov", start_paths=["/"],
        )
        output = format_domain_yaml(entry)
        assert '"Texas Legislature"' in output

    def test_id_is_quoted(self):
        entry = build_domain_entry(
            name="Test", domain_id="tx_legislature",
            base_url="https://example.com", start_paths=["/"],
        )
        output = format_domain_yaml(entry)
        assert '"tx_legislature"' in output

    def test_base_url_is_quoted(self):
        entry = build_domain_entry(
            name="Test", domain_id="test",
            base_url="https://example.com", start_paths=["/"],
        )
        output = format_domain_yaml(entry)
        assert '"https://example.com"' in output

    def test_empty_lists_omitted(self):
        entry = build_domain_entry(
            name="Test", domain_id="test",
            base_url="https://example.com", start_paths=["/"],
        )
        output = format_domain_yaml(entry)
        assert "tags:" not in output
        assert "policy_types:" not in output

    def test_empty_category_omitted(self):
        entry = build_domain_entry(
            name="Test", domain_id="test",
            base_url="https://example.com", start_paths=["/"],
        )
        output = format_domain_yaml(entry)
        assert "category:" not in output

    def test_populated_lists_present(self):
        entry = build_domain_entry(
            name="Test", domain_id="test",
            base_url="https://example.com", start_paths=["/"],
            region=["us", "us_states"],
        )
        entry["tags"] = ["incentives", "efficiency"]
        output = format_domain_yaml(entry)
        assert "tags:" in output
        assert '- "incentives"' in output
        assert "region:" in output
        assert '- "us"' in output

    def test_notes_multiline_uses_literal_block(self):
        entry = build_domain_entry(
            name="Test", domain_id="test",
            base_url="https://example.com", start_paths=["/"],
        )
        entry["notes"] = "Line one.\nLine two.\nLine three."
        output = format_domain_yaml(entry)
        assert "notes: |" in output
        assert "Line one." in output
        assert "Line two." in output

    def test_notes_single_line_no_literal_block(self):
        entry = build_domain_entry(
            name="Test", domain_id="test",
            base_url="https://example.com", start_paths=["/"],
        )
        entry["notes"] = "Auto-generated from https://example.com"
        output = format_domain_yaml(entry)
        assert "notes: |" not in output
        assert "notes: Auto-generated" in output

    def test_region_items_quoted(self):
        entry = build_domain_entry(
            name="Test", domain_id="test",
            base_url="https://example.com", start_paths=["/"],
            region=["us", "us_states"],
        )
        output = format_domain_yaml(entry)
        assert '- "us"' in output
        assert '- "us_states"' in output

    def test_start_paths_quoted(self):
        entry = build_domain_entry(
            name="Test", domain_id="test",
            base_url="https://example.com",
            start_paths=["/programs", "/about"],
        )
        output = format_domain_yaml(entry)
        assert '- "/programs"' in output
        assert '- "/about"' in output

    def test_field_order_canonical(self):
        entry = build_domain_entry(
            name="Test", domain_id="test",
            base_url="https://example.com", start_paths=["/"],
            region=["us"],
        )
        output = format_domain_yaml(entry)
        name_pos = output.index("name:")
        id_pos = output.index("id:")
        enabled_pos = output.index("enabled:")
        region_pos = output.index("region:")
        base_url_pos = output.index("base_url:")
        start_paths_pos = output.index("start_paths:")
        assert name_pos < id_pos < enabled_pos < region_pos < base_url_pos < start_paths_pos

    def test_standalone_starts_with_domains(self):
        entry = build_domain_entry(
            name="Test", domain_id="test",
            base_url="https://example.com", start_paths=["/"],
        )
        output = format_domain_yaml(entry, standalone=True)
        assert output.startswith("domains:\n")

    def test_standalone_roundtrips(self):
        entry = build_domain_entry(
            name="Test Domain", domain_id="test_domain",
            base_url="https://example.com", start_paths=["/path"],
            region=["us"],
        )
        output = format_domain_yaml(entry, standalone=True)
        parsed = yaml.safe_load(output)
        assert parsed["domains"][0]["name"] == "Test Domain"
        assert parsed["domains"][0]["id"] == "test_domain"
        assert parsed["domains"][0]["base_url"] == "https://example.com"
        assert parsed["domains"][0]["start_paths"] == ["/path"]
        assert parsed["domains"][0]["region"] == ["us"]
        assert parsed["domains"][0]["enabled"] is True

    def test_booleans_lowercase(self):
        entry = build_domain_entry(
            name="Test", domain_id="test",
            base_url="https://example.com", start_paths=["/"],
        )
        output = format_domain_yaml(entry)
        assert "enabled: true" in output
        assert "requires_playwright: false" in output

    def test_rate_limit_one_decimal(self):
        entry = build_domain_entry(
            name="Test", domain_id="test",
            base_url="https://example.com", start_paths=["/"],
        )
        output = format_domain_yaml(entry)
        assert "rate_limit_seconds: 2.0" in output


class TestQueryStringPreservation:
    """Test that query strings are preserved in start_paths."""

    def test_query_string_included(self):
        from urllib.parse import urlparse
        url = "https://capitol.texas.gov/BillLookup/History.aspx?LegSess=89R&Bill=SB2888"
        parsed = urlparse(url)
        path = parsed.path or "/"
        start_path = f"{path}?{parsed.query}" if parsed.query else path
        assert start_path == "/BillLookup/History.aspx?LegSess=89R&Bill=SB2888"

    def test_no_query_string(self):
        from urllib.parse import urlparse
        url = "https://energy.gov/programs"
        parsed = urlparse(url)
        path = parsed.path or "/"
        start_path = f"{path}?{parsed.query}" if parsed.query else path
        assert start_path == "/programs"

    def test_query_string_in_yaml_output(self):
        entry = build_domain_entry(
            name="Test", domain_id="test",
            base_url="https://capitol.texas.gov",
            start_paths=["/BillLookup/History.aspx?LegSess=89R&Bill=SB2888"],
        )
        output = format_domain_yaml(entry)
        assert "LegSess=89R&Bill=SB2888" in output
