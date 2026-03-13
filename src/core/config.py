"""Configuration loader for domains, groups, keywords, settings, and URL filters."""

import logging
import os
import re
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

from .models import DomainConfig, CrawlSettings, AnalysisSettings, OutputSettings, AppSettings


class ConfigurationError(Exception):
    """Configuration loading or validation error."""
    pass


# Valid regions, categories, tags, policy types for filtering/validation
VALID_REGIONS = {
    # Broad geographic groups
    "eu": "European Union institutions and member states",
    "europe": "European countries (including non-EU)",
    "nordic": "Nordic countries",
    "eu_central": "Germany, Switzerland, Austria, France",
    "eu_west": "Netherlands, Belgium, Ireland",
    "eu_south": "Southern European countries",
    "eu_east": "Eastern European countries",
    "uk": "United Kingdom",
    "us": "United States (federal and state)",
    "us_states": "US state governments",
    "apac": "Asia-Pacific region",
    "north_america": "North America (US, Canada, Mexico)",
    "south_america": "South America",
    "middle_east": "Middle East",
    "africa": "Africa",
    # European countries
    "germany": "Germany", "france": "France", "netherlands": "Netherlands",
    "denmark": "Denmark", "sweden": "Sweden", "norway": "Norway",
    "ireland": "Ireland", "switzerland": "Switzerland",
    "austria": "Austria", "belgium": "Belgium",
    "spain": "Spain", "italy": "Italy", "poland": "Poland",
    "portugal": "Portugal", "czech_republic": "Czech Republic",
    "greece": "Greece", "hungary": "Hungary", "romania": "Romania",
    "finland": "Finland", "iceland": "Iceland",
    # UK devolved nations
    "scotland": "Scotland", "wales": "Wales", "northern_ireland": "Northern Ireland",
    # Swiss cantons
    "zurich": "Zurich",
    # German Länder
    "hessen": "Hesse", "bayern": "Bavaria",
    "nordrhein_westfalen": "North Rhine-Westphalia",
    "baden_wuerttemberg": "Baden-Württemberg",
    "berlin": "Berlin", "hamburg": "Hamburg",
    "niedersachsen": "Lower Saxony", "sachsen": "Saxony",
    # Asia-Pacific countries
    "singapore": "Singapore", "japan": "Japan", "south_korea": "South Korea",
    "australia": "Australia", "india": "India",
    # Australian states
    "new_south_wales": "New South Wales", "south_australia": "South Australia",
    # Indian states
    "karnataka": "Karnataka", "tamil_nadu": "Tamil Nadu",
    "telangana": "Telangana", "maharashtra": "Maharashtra",
    # Americas
    "canada": "Canada", "brazil": "Brazil", "mexico": "Mexico",
    # Canadian provinces
    "ontario": "Ontario", "british_columbia": "British Columbia",
    "quebec": "Quebec", "alberta": "Alberta",
    # Middle East
    "uae": "United Arab Emirates", "saudi_arabia": "Saudi Arabia",
    "abu_dhabi": "Abu Dhabi", "dubai": "Dubai",
    # Africa
    "south_africa": "South Africa",
}

# Auto-add all 50 US states from domain_generator
from src.agent.domain_generator import US_STATE_ABBREVS as _US_STATES_REG
VALID_REGIONS.update({
    s.replace("-", "_"): s.replace("-", " ").title()
    for s in _US_STATES_REG
})

VALID_CATEGORIES = {
    "energy_ministry": "National/state energy departments",
    "environmental_agency": "EPA equivalents, climate agencies",
    "legislative": "Bill trackers, law databases, parliaments",
    "legislation": "Primary legislation, enacted laws",
    "district_heating": "Heat network authorities",
    "grid_operator": "RTOs, ISOs, grid planners",
    "economic_dev": "Business incentives, tax programs",
    "regulatory": "Utility commissions, permit authorities",
    "regulatory_authority": "Regulatory bodies and enforcement agencies",
    "regulation": "Regulatory frameworks and rules",
    "standards": "Building codes, efficiency standards",
    "building_codes": "Building energy codes",
    "guidance": "Non-binding guidance and recommendations",
    "policy": "Government policy frameworks",
    "cantonal_authority": "Swiss cantonal government bodies",
    "coordination_body": "Multi-jurisdictional coordination bodies",
    "program": "Government efficiency programs",
    "environment_ministry": "Environmental protection agencies",
}

VALID_TAGS = {
    "incentives": "Grants, tax breaks, subsidies",
    "mandates": "Required regulations",
    "mandatory": "Mandatory/binding requirements",
    "enabling": "Enabling/voluntary frameworks",
    "reporting": "Disclosure requirements",
    "carbon": "Carbon pricing, credits, emissions",
    "efficiency": "PUE, energy efficiency programs",
    "energy_efficiency": "Energy efficiency requirements",
    "planning": "Zoning, permits, infrastructure",
    "research": "Studies, reports, data",
    "waste_heat": "Waste heat recovery and reuse",
    "heat_reuse": "Heat reuse requirements",
    "district_heating": "District heating networks",
    "pue_limits": "PUE limits and targets",
    "renewable_energy": "Renewable energy requirements",
    "data_center_specific": "Data center specific regulations",
    "registry": "Registry and registration requirements",
    "deadlines": "Compliance deadlines",
    "article_26": "EU EED Article 26 related",
    "eu_eed": "EU Energy Efficiency Directive",
    "framework": "Framework legislation",
    "strategy": "Strategic plans",
    "net_zero": "Net zero targets",
    "data_centers": "Data center specific",
}

VALID_POLICY_TYPES = {
    "law": "Enacted legislation",
    "legislation": "Primary legislation",
    "regulation": "Agency rules",
    "directive": "EU directives",
    "incentive": "Grant programs, tax credits",
    "guidance": "Best practices, recommendations",
    "standard": "Technical standards, building codes",
    "report": "Research, data, analysis",
    "strategy": "Strategic plans and frameworks",
    "program": "Government programs",
    "certification": "Certification schemes",
}


def _load_yaml(path: Path) -> dict:
    """Load a YAML file, returning empty dict if file doesn't exist."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_domains_directory(domains_dir: Path) -> list[dict]:
    """Load all domain YAML files from directory (recursive, skipping _ prefixed)."""
    all_domains = []
    if not domains_dir.exists():
        return all_domains

    for yaml_file in sorted(domains_dir.rglob("*.yaml")):
        if yaml_file.name.startswith("_"):
            continue
        try:
            content = _load_yaml(yaml_file)
            domains = content.get("domains") or []
            for domain in domains:
                domain["_source_file"] = yaml_file.stem
            all_domains.extend(domains)
        except Exception as e:
            raise ConfigurationError(f"Error loading {yaml_file}: {e}")

    return all_domains


class ConfigLoader:
    """Loads and provides access to all configuration."""

    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self._settings: Optional[AppSettings] = None
        self._domains_config: Optional[dict] = None
        self._keywords_config: Optional[dict] = None
        self._url_filters: Optional[dict] = None

    def load(self) -> None:
        """Load all configuration files."""
        self._load_settings()
        self._load_domains()
        self._load_keywords()
        self._load_url_filters()

        # Log validation warnings (non-blocking)
        for warning in self.validate_config():
            logger.warning("Config: %s", warning)

    def _load_settings(self) -> None:
        settings_file = self.config_dir / "settings.yaml"
        data = _load_yaml(settings_file)

        crawl_data = data.get("crawl", data)
        analysis_data = data.get("analysis", data)

        crawl = CrawlSettings(
            max_depth=crawl_data.get("max_depth", 3),
            max_pages_per_domain=crawl_data.get("max_pages_per_domain", 200),
            delay_seconds=crawl_data.get("delay_seconds", crawl_data.get("rate_limit_seconds", 3.0)),
            timeout_seconds=crawl_data.get("timeout_seconds", 30),
            max_concurrent=crawl_data.get("max_concurrent", 3),
            user_agent=crawl_data.get("user_agent", "OCP-PolicyHub/1.0"),
            respect_robots_txt=crawl_data.get("respect_robots_txt", True),
            max_retries=crawl_data.get("max_retries", 3),
            force_playwright=crawl_data.get("force_playwright", False),
        )
        analysis = AnalysisSettings(
            min_keyword_score=analysis_data.get("min_keyword_score", 3.0),
            min_relevance_score=analysis_data.get("min_relevance_score", 5),
            min_keyword_matches=analysis_data.get("min_keyword_matches", 2),
            enable_llm_analysis=analysis_data.get("enable_llm_analysis", True),
            analysis_model=analysis_data.get("analysis_model", "claude-sonnet-4-20250514"),
            screening_model=analysis_data.get("screening_model", "claude-haiku-4-5-20251001"),
            enable_two_stage=analysis_data.get("enable_two_stage", True),
            screening_min_confidence=analysis_data.get("screening_min_confidence", 5),
        )
        output_data = data.get("output", {})
        output = OutputSettings(
            spreadsheet_id=os.environ.get("SPREADSHEET_ID", output_data.get("spreadsheet_id")),
            staging_sheet_name=output_data.get("staging_sheet_name", "Staging"),
            google_credentials_b64=os.environ.get("GOOGLE_CREDENTIALS"),
        )
        self._settings = AppSettings(
            crawl=crawl,
            analysis=analysis,
            output=output,
            config_dir=str(self.config_dir),
            data_dir=data.get("data_dir", "data"),
        )

    def _load_domains(self) -> None:
        domains_dir = self.config_dir / "domains"

        if domains_dir.exists() and any(domains_dir.glob("*.yaml")):
            all_domains = _load_domains_directory(domains_dir)
            groups_file = self.config_dir / "groups.yaml"
            groups_config = _load_yaml(groups_file)
            groups = groups_config.get("groups", {})

            self._domains_config = {
                "domains": all_domains,
                "groups": groups,
                "defaults": {
                    "max_depth": 3,
                    "rate_limit_seconds": 3.0,
                    "requires_playwright": False,
                    "enabled": True,
                },
            }
        else:
            raise ConfigurationError(
                "No domain configuration found. Expected config/domains/*.yaml"
            )

    def _load_keywords(self) -> None:
        keywords_file = self.config_dir / "keywords.yaml"
        if not keywords_file.exists():
            raise ConfigurationError(f"Missing: {keywords_file}")
        with open(keywords_file, encoding="utf-8") as f:
            self._keywords_config = yaml.safe_load(f)

    def _load_url_filters(self) -> None:
        filters_file = self.config_dir / "url_filters.yaml"
        self._url_filters = _load_yaml(filters_file).get("url_filters", {})

    @property
    def settings(self) -> AppSettings:
        if not self._settings:
            self.load()
        return self._settings

    @property
    def domains_config(self) -> dict:
        if self._domains_config is None:
            self.load()
        return self._domains_config

    @property
    def keywords_config(self) -> dict:
        if self._keywords_config is None:
            self.load()
        return self._keywords_config

    @property
    def url_filters(self) -> dict:
        if self._url_filters is None:
            self.load()
        return self._url_filters

    # --- Domain resolution ---

    def get_enabled_domains(self, group: str = "all") -> list[dict]:
        """Resolve domains by group, region, file, or individual ID."""
        all_domains = {d["id"]: d for d in self.domains_config.get("domains", [])}

        if group == "all":
            return [d for d in all_domains.values() if d.get("enabled", True)]

        groups = self.domains_config.get("groups", {})
        matched_ids: set[str] = set()

        # Check groups.yaml
        if group in groups:
            group_ids = groups[group].get("domains", [])
            missing = [id for id in group_ids if id not in all_domains]
            if missing:
                raise ConfigurationError(
                    f"Group '{group}' references unknown domains: {missing}"
                )
            matched_ids.update(group_ids)

        # Check region field
        region_ids = {
            d["id"] for d in all_domains.values()
            if group in d.get("region", [])
        }
        matched_ids.update(region_ids)

        if matched_ids:
            return [
                all_domains[id] for id in matched_ids
                if all_domains[id].get("enabled", True)
            ]

        # Fall back to file name
        file_domains = [
            d for d in all_domains.values()
            if d.get("_source_file") == group and d.get("enabled", True)
        ]
        if file_domains:
            return file_domains

        # Fall back to individual domain ID
        if group in all_domains:
            domain = all_domains[group]
            if domain.get("enabled", True):
                return [domain]

        available_groups = ", ".join(sorted(groups.keys()))
        raise ConfigurationError(
            f"Unknown group/region/domain: '{group}'. Available groups: {available_groups}"
        )

    def to_domain_config(self, domain_dict: dict) -> DomainConfig:
        """Convert raw domain dict to DomainConfig model."""
        return DomainConfig(
            id=domain_dict["id"],
            name=domain_dict["name"],
            base_url=domain_dict["base_url"],
            enabled=domain_dict.get("enabled", True),
            region=domain_dict.get("region", []),
            category=domain_dict.get("category", ""),
            tags=domain_dict.get("tags", []),
            policy_types=domain_dict.get("policy_types", []),
            start_paths=domain_dict.get("start_paths", ["/"]),
            max_depth=domain_dict.get("max_depth"),
            max_pages=domain_dict.get("max_pages"),
            requires_playwright=domain_dict.get("requires_playwright", False),
            min_keyword_score=domain_dict.get("min_keyword_score"),
            allowed_path_patterns=domain_dict.get("allowed_path_patterns", []),
            blocked_path_patterns=domain_dict.get("blocked_path_patterns", []),
        )

    # --- Filtering ---

    def filter_domains(
        self,
        category: Optional[str] = None,
        tags: Optional[list[str]] = None,
        policy_type: Optional[str] = None,
    ) -> list[dict]:
        """Filter enabled domains by category, tags, or policy type."""
        result = [
            d for d in self.domains_config.get("domains", [])
            if d.get("enabled", True)
        ]

        if category:
            result = [d for d in result if d.get("category") == category]

        if tags:
            result = [
                d for d in result
                if any(tag in d.get("tags", []) for tag in tags)
            ]

        if policy_type:
            result = [
                d for d in result
                if policy_type in d.get("policy_types", [])
            ]

        return result

    # --- Listing helpers ---

    def list_domains(self) -> list[dict]:
        """List all domains with basic info."""
        return [
            {
                "id": d["id"],
                "name": d["name"],
                "enabled": d.get("enabled", True),
                "base_url": d["base_url"],
                "region": d.get("region", []),
                "category": d.get("category"),
                "tags": d.get("tags", []),
                "policy_types": d.get("policy_types", []),
            }
            for d in self.domains_config.get("domains", [])
        ]

    def list_groups(self) -> dict[str, str]:
        """List groups with descriptions."""
        groups = self.domains_config.get("groups", {})
        return {
            name: config.get("description", "No description")
            for name, config in groups.items()
        }

    def list_regions(self) -> dict[str, str]:
        return VALID_REGIONS.copy()

    def list_categories(self) -> dict[str, str]:
        return VALID_CATEGORIES.copy()

    def list_tags(self) -> dict[str, str]:
        return VALID_TAGS.copy()

    def get_url_skip_paths(self) -> list[str]:
        """Get URL paths to skip (post-fetch, pre-analysis)."""
        return self.url_filters.get("skip_paths", [])

    def get_url_skip_patterns(self) -> list[re.Pattern]:
        """Get compiled URL skip patterns."""
        return [
            re.compile(p, re.IGNORECASE)
            for p in self.url_filters.get("skip_patterns", [])
        ]

    def get_crawl_blocked_patterns(self) -> list[str]:
        """Get crawl-time blocked patterns (glob/fnmatch)."""
        return self.url_filters.get("crawl_blocked_patterns", [])

    def get_skip_extensions(self) -> list[str]:
        """Get file extensions to skip."""
        return self.url_filters.get("skip_extensions", [
            ".pdf", ".doc", ".docx", ".zip", ".jpg", ".png",
        ])

    def validate_config(self) -> list[str]:
        """Check for orphan domains and stale group references. Returns warnings."""
        warnings = []
        all_domains = {d["id"]: d for d in self.domains_config.get("domains", [])}
        groups = self.domains_config.get("groups", {})

        # Collect all explicitly grouped domain IDs
        grouped_ids: set[str] = set()
        for group_name, group_config in groups.items():
            if group_name == "all":
                continue
            for did in (group_config.get("domains") or []):
                grouped_ids.add(did)
                if did not in all_domains:
                    warnings.append(
                        f"Group '{group_name}' references unknown domain: {did}"
                    )

        # Check for orphan domains (not in any explicit group)
        orphan_ids = {
            did for did in all_domains
            if did not in grouped_ids and all_domains[did].get("enabled", True)
        }
        if orphan_ids:
            sample = sorted(list(orphan_ids))[:10]
            warnings.append(
                f"{len(orphan_ids)} domains not in any explicit group "
                f"(discoverable via region/state scan): {', '.join(sample)}"
                + ("..." if len(orphan_ids) > 10 else "")
            )

        # Check for duplicate domain IDs across files
        id_counts: dict[str, int] = {}
        for d in self.domains_config.get("domains", []):
            did = d["id"]
            id_counts[did] = id_counts.get(did, 0) + 1
        for did, count in id_counts.items():
            if count > 1:
                warnings.append(f"Duplicate domain ID: {did} (appears {count} times)")

        # Check for unrecognized region values
        for d in all_domains.values():
            for r in d.get("region", []):
                if r not in VALID_REGIONS:
                    warnings.append(
                        f"Domain '{d['id']}' has unrecognized region: {r}"
                    )

        return warnings
