"""Tests for comma-separated scan target resolution in ConfigLoader."""

import pytest

from src.core.config import ConfigLoader, ConfigurationError


@pytest.fixture
def config_dir(tmp_path):
    config = tmp_path / "config"
    domains_dir = config / "domains"
    domains_dir.mkdir(parents=True)

    (config / "settings.yaml").write_text(
        "crawl:\n  max_depth: 2\n", encoding="utf-8",
    )
    (domains_dir / "test.yaml").write_text(
        "domains:\n"
        "  - id: ca_leg\n"
        "    name: California Legislature\n"
        "    base_url: https://leginfo.legislature.ca.gov\n"
        "    region: [california, us_states, us]\n"
        "  - id: ct_deep\n"
        "    name: Connecticut DEEP\n"
        "    base_url: https://portal.ct.gov\n"
        "    region: [connecticut, us_states, us]\n"
        "  - id: legiscan_api\n"
        "    name: LegiScan\n"
        "    base_url: https://api.legiscan.com\n"
        "    region: [us, us_states]\n"
        "    source_type: legiscan\n",
        encoding="utf-8",
    )
    (config / "groups.yaml").write_text(
        "groups:\n"
        "  quick:\n"
        "    description: Quick\n"
        "    domains: [ca_leg]\n",
        encoding="utf-8",
    )
    (config / "keywords.yaml").write_text(
        "categories:\n"
        "  heat:\n"
        "    weight: 3.0\n"
        "    terms:\n"
        "      en: [waste heat]\n"
        "thresholds:\n  min_score: 3.0\n  min_matches: 1\n",
        encoding="utf-8",
    )
    (config / "url_filters.yaml").write_text(
        "url_filters:\n  skip_paths: []\n", encoding="utf-8",
    )
    return config


@pytest.fixture
def loader(config_dir):
    return ConfigLoader(config_dir=str(config_dir))


class TestCommaSeparatedTargets:
    def test_union_of_region_and_domain_id(self, loader):
        ids = {d["id"] for d in loader.get_enabled_domains("california,legiscan_api")}
        assert ids == {"ca_leg", "legiscan_api"}

    def test_overlap_deduplicated(self, loader):
        # ca_leg appears via both the region and the quick group.
        domains = loader.get_enabled_domains("california,quick")
        assert [d["id"] for d in domains] == ["ca_leg"]

    def test_whitespace_tolerated(self, loader):
        ids = {d["id"] for d in loader.get_enabled_domains(" california , legiscan_api ")}
        assert ids == {"ca_leg", "legiscan_api"}

    def test_unknown_part_raises(self, loader):
        with pytest.raises(ConfigurationError):
            loader.get_enabled_domains("california,atlantis")

    def test_single_target_unchanged(self, loader):
        ids = {d["id"] for d in loader.get_enabled_domains("us_states")}
        assert ids == {"ca_leg", "ct_deep", "legiscan_api"}

    def test_empty_parts_ignored(self, loader):
        ids = {d["id"] for d in loader.get_enabled_domains("california,,")}
        assert ids == {"ca_leg"}
