"""Tests for the domain generator — ID generation, region detection, YAML formatting."""


from src.agent.domain_generator import (
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

    def test_us_federal_gov(self):
        assert generate_domain_id("energy.gov") == "us_energy"

    def test_uk_gov(self):
        assert generate_domain_id("legislation.gov.uk") == "uk_legislation"

    def test_uk_gov_bare(self):
        assert generate_domain_id("www.gov.uk") == "uk_gov"

    def test_french_gov(self):
        assert generate_domain_id("legifrance.gouv.fr") == "legifrance"

    def test_austrian_gov(self):
        assert generate_domain_id("www.bmk.gv.at") == "bmk"

    def test_swiss_gov(self):
        assert generate_domain_id("www.bfe.admin.ch") == "bfe"

    def test_generic_domain(self):
        assert generate_domain_id("www.example.com") == "example_com"

    def test_strips_www(self):
        assert generate_domain_id("www.energy.gov") == "us_energy"

    def test_max_length(self):
        result = generate_domain_id("verylongsubdomain.virginia.gov")
        assert len(result) <= 30


class TestDetectRegion:
    """Test region detection from hostnames."""

    def test_us_federal(self):
        assert detect_region("energy.gov") == ["us"]

    def test_us_state(self):
        assert detect_region("lis.virginia.gov") == ["us", "us_states", "virginia"]

    def test_uk(self):
        assert detect_region("legislation.gov.uk") == ["uk"]

    def test_france(self):
        assert detect_region("legifrance.gouv.fr") == ["eu", "france"]

    def test_austria(self):
        assert detect_region("www.bmk.gv.at") == ["eu", "eu_central"]

    def test_switzerland(self):
        assert detect_region("www.bfe.admin.ch") == ["eu_central"]

    def test_eu(self):
        assert detect_region("ec.europa.eu") == ["eu"]

    def test_unknown_tld(self):
        assert detect_region("example.com") == []


class TestSuggestOutputFile:
    """Test output file suggestions."""

    def test_us_state(self):
        assert suggest_output_file("lis.virginia.gov") == "us/virginia.yaml"

    def test_us_federal(self):
        assert suggest_output_file("energy.gov") == "us/us_federal.yaml"

    def test_uk(self):
        assert suggest_output_file("legislation.gov.uk") == "uk.yaml"

    def test_france(self):
        assert suggest_output_file("legifrance.gouv.fr") == "france.yaml"

    def test_unknown(self):
        assert suggest_output_file("example.com") == "new_domains.yaml"


class TestBuildDomainEntry:
    """Test domain entry dict construction."""

    def test_basic_entry(self):
        entry = build_domain_entry(
            name="Test Site",
            domain_id="test_site",
            base_url="https://test.gov",
            start_paths=["/"],
        )
        assert entry["name"] == "Test Site"
        assert entry["id"] == "test_site"
        assert entry["enabled"] is True
        assert entry["base_url"] == "https://test.gov"
        assert entry["start_paths"] == ["/"]
        assert entry["max_depth"] == 2
        assert entry["language"] == "en"
        assert entry["requires_playwright"] is False
        assert entry["region"] == []
        assert entry["category"] == ""
        assert entry["tags"] == []
        assert "verified_date" in entry

    def test_with_region(self):
        entry = build_domain_entry(
            name="UK Gov",
            domain_id="uk_gov",
            base_url="https://www.gov.uk",
            start_paths=["/energy"],
            region=["uk"],
        )
        assert entry["region"] == ["uk"]

    def test_with_playwright(self):
        entry = build_domain_entry(
            name="JS Site",
            domain_id="js_site",
            base_url="https://js-site.gov",
            start_paths=["/"],
            requires_playwright=True,
        )
        assert entry["requires_playwright"] is True


class TestFormatDomainYaml:
    """Test YAML formatting."""

    def test_standalone_format(self):
        entry = build_domain_entry(
            name="Test",
            domain_id="test",
            base_url="https://test.gov",
            start_paths=["/"],
            region=["us"],
        )
        yaml_str = format_domain_yaml(entry, standalone=True)
        assert yaml_str.startswith("domains:\n")
        assert "  - name:" in yaml_str

    def test_append_format(self):
        entry = build_domain_entry(
            name="Test",
            domain_id="test",
            base_url="https://test.gov",
            start_paths=["/"],
        )
        yaml_str = format_domain_yaml(entry, standalone=False)
        assert not yaml_str.startswith("domains:")
        assert yaml_str.startswith("  - name:")

    def test_canonical_field_order(self):
        entry = build_domain_entry(
            name="Test",
            domain_id="test",
            base_url="https://test.gov",
            start_paths=["/policy"],
            region=["eu"],
            language="de",
        )
        yaml_str = format_domain_yaml(entry, standalone=True)
        lines = yaml_str.split("\n")
        # Find positions of key fields
        field_positions = {}
        for i, line in enumerate(lines):
            for field in ["name:", "id:", "enabled:", "region:", "base_url:", "start_paths:"]:
                if field in line:
                    field_positions[field] = i
        # name should come before id, id before enabled, etc.
        assert field_positions.get("name:", 0) < field_positions.get("id:", 999)
        assert field_positions.get("id:", 0) < field_positions.get("enabled:", 999)

    def test_quoted_fields(self):
        entry = build_domain_entry(
            name="Test Ministry",
            domain_id="test_ministry",
            base_url="https://test.gov",
            start_paths=["/"],
        )
        yaml_str = format_domain_yaml(entry)
        assert '"Test Ministry"' in yaml_str
        assert '"test_ministry"' in yaml_str
        assert '"https://test.gov"' in yaml_str
