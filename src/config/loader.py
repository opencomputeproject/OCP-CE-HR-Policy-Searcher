"""Configuration loader.

Loads configuration from:
- config/settings.yaml     - Runtime settings
- config/domains/*.yaml    - Domain definitions (multiple files)
- config/groups.yaml       - Domain groups
- config/keywords.yaml     - Search keywords
"""

from pathlib import Path
from typing import Optional
import yaml

from .settings import Settings


class ConfigurationError(Exception):
    """Configuration error."""
    pass


def _load_yaml(path: Path) -> dict:
    """Load a YAML file, returning empty dict if file doesn't exist."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_domains_directory(domains_dir: Path) -> list[dict]:
    """Load all domain files from the domains directory.

    Scans config/domains/ and subdirectories for .yaml files
    (excluding files starting with _) and merges all domains into a single list.
    """
    all_domains = []

    if not domains_dir.exists():
        return all_domains

    # Use rglob for recursive search through subdirectories
    for yaml_file in sorted(domains_dir.rglob("*.yaml")):
        # Skip template files (files starting with _)
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


def _load_rejected_sites_directory(rejected_dir: Path) -> list[dict]:
    """Load all rejected site files from the rejected_sites directory.

    Scans config/rejected_sites/ and subdirectories for .yaml files
    (excluding files starting with _) and merges all rejected sites into a single list.
    """
    all_rejected = []

    if not rejected_dir.exists():
        return all_rejected

    # Use rglob for recursive search through subdirectories
    for yaml_file in sorted(rejected_dir.rglob("*.yaml")):
        # Skip template files (files starting with _)
        if yaml_file.name.startswith("_"):
            continue

        try:
            content = _load_yaml(yaml_file)
            # Support both "rejected_sites" key and flat list
            sites = content.get("rejected_sites", [])
            if sites:
                # Add source file info to each entry
                for site in sites:
                    if site:  # Skip None entries
                        site["_source_file"] = str(yaml_file.relative_to(rejected_dir))
                        all_rejected.append(site)
        except Exception as e:
            raise ConfigurationError(f"Error loading {yaml_file}: {e}")

    return all_rejected


def load_rejected_sites(rejected_dir: Optional[Path] = None) -> list[dict]:
    """Load all rejected sites from the rejected_sites directory.

    Supports both:
    - New structure: config/rejected_sites/*.yaml (and subdirectories)
    - Legacy structure: config/rejected_sites.yaml (single file)

    Returns:
        List of rejected site dicts, each with url, reason, etc.
    """
    config_dir = Path("config")
    rejected_sites_dir = rejected_dir or config_dir / "rejected_sites"
    legacy_file = config_dir / "rejected_sites.yaml"

    all_rejected = []

    # Load from directory (new structure)
    if rejected_sites_dir.exists():
        all_rejected.extend(_load_rejected_sites_directory(rejected_sites_dir))

    # Also check legacy single file for backwards compatibility
    if legacy_file.exists():
        try:
            content = _load_yaml(legacy_file)
            sites = content.get("rejected_sites", [])
            for site in sites:
                if site:
                    site["_source_file"] = "rejected_sites.yaml (legacy)"
                    all_rejected.append(site)
        except Exception as e:
            raise ConfigurationError(f"Error loading {legacy_file}: {e}")

    return all_rejected


def list_rejected_sites(rejected_sites: Optional[list[dict]] = None) -> list[dict]:
    """List all rejected sites with their info.

    Args:
        rejected_sites: Optional pre-loaded list. If None, loads from config.

    Returns:
        List of dicts with url, reason, source_file, etc.
    """
    if rejected_sites is None:
        rejected_sites = load_rejected_sites()

    return [
        {
            "url": site.get("url", ""),
            "reason": site.get("reason", ""),
            "evaluated_date": site.get("evaluated_date", ""),
            "evaluated_by": site.get("evaluated_by", ""),
            "reconsider_if": site.get("reconsider_if", ""),
            "replaced_by": site.get("replaced_by", ""),
            "source_file": site.get("_source_file", ""),
        }
        for site in rejected_sites
        if site
    ]


def is_url_rejected(url: str, rejected_sites: Optional[list[dict]] = None) -> bool:
    """Check if a URL is in the rejected sites list.

    Args:
        url: URL to check
        rejected_sites: Optional pre-loaded list. If None, loads from config.

    Returns:
        True if URL is rejected, False otherwise
    """
    if rejected_sites is None:
        rejected_sites = load_rejected_sites()

    rejected_urls = {site.get("url") for site in rejected_sites if site}
    return url in rejected_urls


def load_settings(
    settings_path: Optional[Path] = None,
    domains_path: Optional[Path] = None,
    keywords_path: Optional[Path] = None,
) -> tuple[Settings, dict, dict]:
    """Load all configuration files.

    Returns:
        tuple: (Settings, domains_config, keywords_config)

    The domains_config dict contains:
        - domains: list of all domains from config/domains/*.yaml
        - groups: dict of groups from config/groups.yaml
        - defaults: default settings for domains
    """
    config_dir = Path("config")

    # Load settings.yaml
    settings_file = settings_path or config_dir / "settings.yaml"
    settings_dict = _load_yaml(settings_file)
    settings = Settings(**settings_dict)

    # Load domains from directory (new structure)
    domains_dir = config_dir / "domains"

    # Check for old single-file structure (backwards compatibility)
    old_domains_file = domains_path or config_dir / "domains.yaml"

    if domains_dir.exists() and any(domains_dir.glob("*.yaml")):
        # New structure: load from domains/ directory
        all_domains = _load_domains_directory(domains_dir)

        # Load groups from separate file
        groups_file = config_dir / "groups.yaml"
        groups_config = _load_yaml(groups_file)
        groups = groups_config.get("groups", {})

        domains_config = {
            "domains": all_domains,
            "groups": groups,
            "defaults": {
                "max_depth": 3,
                "rate_limit_seconds": 3.0,
                "requires_playwright": False,
                "enabled": True,
            }
        }
    elif old_domains_file.exists():
        # Old structure: single domains.yaml file (backwards compatible)
        with open(old_domains_file, encoding="utf-8") as f:
            domains_config = yaml.safe_load(f)
    else:
        raise ConfigurationError(
            "No domain configuration found. "
            "Expected config/domains/*.yaml or config/domains.yaml"
        )

    # Load keywords.yaml
    keywords_file = keywords_path or config_dir / "keywords.yaml"
    if not keywords_file.exists():
        raise ConfigurationError(f"Missing: {keywords_file}")
    with open(keywords_file, encoding="utf-8") as f:
        keywords_config = yaml.safe_load(f)

    return settings, domains_config, keywords_config


def get_enabled_domains(domains_config: dict, group: str = "all") -> list[dict]:
    """Get domains for a group, region, domain file, or individual domain ID.

    Resolution order:
    1. "all" -> all enabled domains
    2. Check groups.yaml for group name -> listed domain IDs
    3. Check region field on all domains -> any domain with name in its region list
    4. Merge steps 2 and 3 (union, deduplicated by domain ID)
    5. If nothing matched, fall back to file name match
    5b. If still nothing, fall back to individual domain ID match
    6. If still nothing, error with helpful message

    Args:
        domains_config: Configuration dict with 'domains' and 'groups' keys
        group: Group name, region name, domain file name, domain ID, or "all" (default)

    Returns:
        List of domain dicts matching the group/region/file

    Raises:
        ConfigurationError: If group/region/file doesn't exist
    """
    all_domains = {d["id"]: d for d in domains_config.get("domains", [])}

    if group == "all":
        return [d for d in all_domains.values() if d.get("enabled", True)]

    groups = domains_config.get("groups", {})
    matched_ids: set[str] = set()

    # Step 2: Check groups.yaml
    group_exists = group in groups
    if group_exists:
        group_ids = groups[group].get("domains", [])
        # Validate all domain IDs exist
        missing = [id for id in group_ids if id not in all_domains]
        if missing:
            raise ConfigurationError(
                f"Group '{group}' references unknown domains: {missing}"
            )
        matched_ids.update(group_ids)

    # Step 3: Check region field on all domains
    region_ids = {
        d["id"] for d in all_domains.values()
        if group in d.get("region", [])
    }
    matched_ids.update(region_ids)

    # Step 4: If group or region matched, return the merged union
    if matched_ids:
        return [
            all_domains[id] for id in matched_ids
            if all_domains[id].get("enabled", True)
        ]

    # Step 5: Fall back to file name match
    file_domains = [
        d for d in all_domains.values()
        if d.get("_source_file") == group and d.get("enabled", True)
    ]
    if file_domains:
        return file_domains

    # Step 5b: Fall back to individual domain ID match
    if group in all_domains:
        domain = all_domains[group]
        if domain.get("enabled", True):
            return [domain]

    # Step 6: Nothing matched — error with helpful message
    available_groups = ", ".join(sorted(groups.keys()))
    available_regions = ", ".join(sorted(VALID_REGIONS.keys()))
    available_files = sorted(
        {d["_source_file"] for d in all_domains.values() if "_source_file" in d}
        - set(groups.keys())
    )
    msg = f"Unknown group, region, or file: '{group}'."
    msg += f"\n  Available groups: {available_groups}"
    msg += f"\n  Available regions: {available_regions}"
    if available_files:
        msg += f"\n  Available domain files: {', '.join(available_files)}"
    raise ConfigurationError(msg)


def warn_missing_regions(domains_config: dict) -> list[str]:
    """Check for enabled domains without a region field.

    Returns:
        List of warning messages for domains missing region.
    """
    warnings = []
    for d in domains_config.get("domains", []):
        if d.get("enabled", True) and not d.get("region"):
            warnings.append(
                f"Domain '{d['id']}' has no region assigned "
                f"(source: {d.get('_source_file', 'unknown')})"
            )
    return warnings


def list_regions() -> dict[str, str]:
    """List all valid regions with descriptions.

    Returns:
        Dict mapping region name to description
    """
    return VALID_REGIONS.copy()


def list_groups(domains_config: dict) -> dict[str, str]:
    """List all available groups with descriptions.

    Returns:
        Dict mapping group name to description
    """
    groups = domains_config.get("groups", {})
    return {
        name: config.get("description", "No description")
        for name, config in groups.items()
    }


def get_available_domain_files(domains_config: dict) -> dict[str, int]:
    """List available domain file names with enabled domain counts.

    Returns:
        Dict mapping file stem to count of enabled domains in that file.
    """
    file_counts: dict[str, int] = {}
    for d in domains_config.get("domains", []):
        source = d.get("_source_file")
        if source and d.get("enabled", True):
            file_counts[source] = file_counts.get(source, 0) + 1
    return dict(sorted(file_counts.items()))


def list_domains(domains_config: dict) -> list[dict]:
    """List all domains with basic info.

    Returns:
        List of dicts with id, name, enabled, and source file
    """
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
        for d in domains_config.get("domains", [])
    ]


# =============================================================================
# VALID CATEGORIES, TAGS, AND POLICY TYPES
# =============================================================================

VALID_REGIONS = {
    # Broad regions
    "eu": "European Union institutions and member states",
    "europe": "European countries (including non-EU)",
    "nordic": "Nordic countries (Sweden, Denmark, Finland, Norway, Iceland)",
    "eu_central": "Germany, Switzerland, Austria, France",
    "eu_west": "Netherlands, Belgium, Ireland",
    "uk": "United Kingdom (England, Scotland, Wales, Northern Ireland)",
    "us": "United States (federal and state)",
    "us_states": "US state governments",
    "apac": "Asia-Pacific region",
    # Country-level regions
    "germany": "Germany",
    "france": "France",
    "netherlands": "Netherlands",
    "denmark": "Denmark",
    "sweden": "Sweden",
    "norway": "Norway",
    "ireland": "Ireland",
    "switzerland": "Switzerland",
    "singapore": "Singapore",
    "japan": "Japan",
    # US state-level regions
    "oregon": "Oregon",
    "texas": "Texas",
    "california": "California",
}


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
    "building_codes": "Building energy codes and construction standards",
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
    "pue_target": "PUE benchmark targets",
    "pue_measurement": "PUE measurement methodology",
    "renewable_energy": "Renewable energy requirements",
    "data_center_specific": "Data center specific regulations",
    "registry": "Registry and registration requirements",
    "deadlines": "Compliance deadlines",
    "article_26": "EU EED Article 26 related",
    "cost_benefit_analysis": "Cost-benefit analysis requirements",
    "interpretation": "Legal interpretation guidance",
    "payback_period": "Payback period requirements",
    "recognized_measures": "Recognized efficiency measures",
    "nve_approval": "NVE (Norwegian) approval required",
    "consultation": "Consultation requirements",
    "waste_heat_pricing": "Waste heat pricing frameworks",
    "price_ceiling": "Price ceiling regulations",
    "tax_exemption": "Tax exemption provisions",
    "pricing": "Pricing frameworks",
    "simplified_rules": "Simplified regulatory rules",
    "waste_heat_data": "Waste heat data reporting",
    "energimyndigheten": "Swedish Energy Agency related",
    "eu_database": "EU database reporting",
    "sustainability": "Sustainability requirements",
    "grid_connection": "Grid connection requirements",
    "dispatchable_generation": "Dispatchable generation requirements",
    "certification": "Certification schemes",
    "wue": "Water Usage Effectiveness",
    "green_mark": "Green Mark certification",
    "dc_cfa": "Data Centre Call for Application",
    "cooling_efficiency": "Cooling system efficiency",
    "district_cooling": "District cooling systems",
    "benchmark": "Benchmark targets",
    "technical_guidance": "Technical guidance documents",
    "energy_planning": "Energy planning requirements",
    "cooling": "Cooling requirements",
    "cantonal": "Swiss cantonal requirements",
    "large_consumers": "Large energy consumer requirements",
    "ashrae_90_4": "ASHRAE Standard 90.4",
    "hvac": "HVAC efficiency requirements",
    "power_distribution": "Power distribution efficiency",
    "ercot": "ERCOT grid requirements",
    "backup_generation": "Backup generation requirements",
    "curtailment": "Demand curtailment provisions",
    "large_load": "Large load interconnection",
    "best_practices": "Best practices guidelines",
    "eu_eed": "EU Energy Efficiency Directive",
    "framework": "Framework legislation",
    "cantonal_authority": "Cantonal authority requirements",
    "model_regulation": "Model regulations",
    "buildings": "Building requirements",
    "thermal_storage": "Thermal energy storage",
    "strategy": "Strategic plans",
    "net_zero": "Net zero targets",
    "co2_levy": "CO2 levy related",
    "data_centers": "Data center specific",
    "industry": "Industrial requirements",
    "heat_networks": "Heat network requirements",
    "zoning": "Zoning regulations",
    "authorisation": "Authorization requirements",
    "guidance": "Guidance documents",
    "may_deadline": "May deadline for reporting",
}

VALID_POLICY_TYPES = {
    "law": "Enacted legislation",
    "legislation": "Primary legislation and enacted laws",
    "regulation": "Agency rules",
    "directive": "EU directives, guidance with force",
    "incentive": "Grant programs, tax credits",
    "incentives": "Incentive programs and frameworks",
    "guidance": "Best practices, recommendations",
    "standard": "Technical standards, building codes",
    "report": "Research, data, analysis",
    "energy_efficiency": "Energy efficiency requirements",
    "waste_heat_recovery": "Waste heat recovery requirements",
    "reporting_requirements": "Reporting and disclosure requirements",
    "regulatory_authority": "Regulatory authority frameworks",
    "building_codes": "Building energy codes",
    "grid_interconnection": "Grid interconnection requirements",
    "district_heating": "District heating regulations",
    "strategy": "Strategic plans and frameworks",
    "program": "Government programs",
    "certification": "Certification schemes",
}


# =============================================================================
# FILTERING FUNCTIONS
# =============================================================================

def filter_domains_by_category(
    domains_config: dict,
    category: str,
) -> list[dict]:
    """Get domains matching a specific category.

    Args:
        domains_config: Configuration dict with 'domains' key
        category: Category to filter by

    Returns:
        List of enabled domain dicts matching the category

    Raises:
        ConfigurationError: If category is not valid
    """
    if category not in VALID_CATEGORIES:
        available = ", ".join(sorted(VALID_CATEGORIES.keys()))
        raise ConfigurationError(
            f"Unknown category: '{category}'. Valid categories: {available}"
        )

    return [
        d for d in domains_config.get("domains", [])
        if d.get("enabled", True) and d.get("category") == category
    ]


def filter_domains_by_tag(
    domains_config: dict,
    tag: str,
) -> list[dict]:
    """Get domains that have a specific tag.

    Args:
        domains_config: Configuration dict with 'domains' key
        tag: Tag to filter by

    Returns:
        List of enabled domain dicts that have the tag

    Raises:
        ConfigurationError: If tag is not valid
    """
    if tag not in VALID_TAGS:
        available = ", ".join(sorted(VALID_TAGS.keys()))
        raise ConfigurationError(
            f"Unknown tag: '{tag}'. Valid tags: {available}"
        )

    return [
        d for d in domains_config.get("domains", [])
        if d.get("enabled", True) and tag in d.get("tags", [])
    ]


def filter_domains_by_policy_type(
    domains_config: dict,
    policy_type: str,
) -> list[dict]:
    """Get domains that publish a specific policy type.

    Args:
        domains_config: Configuration dict with 'domains' key
        policy_type: Policy type to filter by

    Returns:
        List of enabled domain dicts that have the policy type

    Raises:
        ConfigurationError: If policy_type is not valid
    """
    if policy_type not in VALID_POLICY_TYPES:
        available = ", ".join(sorted(VALID_POLICY_TYPES.keys()))
        raise ConfigurationError(
            f"Unknown policy type: '{policy_type}'. Valid types: {available}"
        )

    return [
        d for d in domains_config.get("domains", [])
        if d.get("enabled", True) and policy_type in d.get("policy_types", [])
    ]


def filter_domains(
    domains_config: dict,
    category: str | None = None,
    tags: list[str] | None = None,
    policy_types: list[str] | None = None,
    match_all_tags: bool = False,
    match_all_policy_types: bool = False,
) -> list[dict]:
    """Filter domains by multiple criteria.

    Args:
        domains_config: Configuration dict with 'domains' key
        category: Optional category to filter by
        tags: Optional list of tags to filter by
        policy_types: Optional list of policy types to filter by
        match_all_tags: If True, domain must have ALL tags; if False, ANY tag
        match_all_policy_types: If True, domain must have ALL policy types

    Returns:
        List of enabled domain dicts matching all specified criteria

    Raises:
        ConfigurationError: If any filter value is invalid
    """
    # Start with all enabled domains
    result = [
        d for d in domains_config.get("domains", [])
        if d.get("enabled", True)
    ]

    # Filter by category
    if category:
        if category not in VALID_CATEGORIES:
            available = ", ".join(sorted(VALID_CATEGORIES.keys()))
            raise ConfigurationError(
                f"Unknown category: '{category}'. Valid categories: {available}"
            )
        result = [d for d in result if d.get("category") == category]

    # Filter by tags
    if tags:
        for tag in tags:
            if tag not in VALID_TAGS:
                available = ", ".join(sorted(VALID_TAGS.keys()))
                raise ConfigurationError(
                    f"Unknown tag: '{tag}'. Valid tags: {available}"
                )

        if match_all_tags:
            # Domain must have ALL specified tags
            result = [
                d for d in result
                if all(tag in d.get("tags", []) for tag in tags)
            ]
        else:
            # Domain must have ANY of the specified tags
            result = [
                d for d in result
                if any(tag in d.get("tags", []) for tag in tags)
            ]

    # Filter by policy types
    if policy_types:
        for pt in policy_types:
            if pt not in VALID_POLICY_TYPES:
                available = ", ".join(sorted(VALID_POLICY_TYPES.keys()))
                raise ConfigurationError(
                    f"Unknown policy type: '{pt}'. Valid types: {available}"
                )

        if match_all_policy_types:
            # Domain must have ALL specified policy types
            result = [
                d for d in result
                if all(pt in d.get("policy_types", []) for pt in policy_types)
            ]
        else:
            # Domain must have ANY of the specified policy types
            result = [
                d for d in result
                if any(pt in d.get("policy_types", []) for pt in policy_types)
            ]

    return result


def list_categories() -> dict[str, str]:
    """List all valid categories with descriptions.

    Returns:
        Dict mapping category name to description
    """
    return VALID_CATEGORIES.copy()


def list_tags() -> dict[str, str]:
    """List all valid tags with descriptions.

    Returns:
        Dict mapping tag name to description
    """
    return VALID_TAGS.copy()


def list_policy_types() -> dict[str, str]:
    """List all valid policy types with descriptions.

    Returns:
        Dict mapping policy type name to description
    """
    return VALID_POLICY_TYPES.copy()


def get_domain_stats(domains_config: dict) -> dict:
    """Get statistics about domain categorization.

    Returns:
        Dict with counts by category, tag, and policy_type
    """
    domains = domains_config.get("domains", [])
    enabled = [d for d in domains if d.get("enabled", True)]

    # Count by category
    category_counts = {}
    for cat in VALID_CATEGORIES:
        count = len([d for d in enabled if d.get("category") == cat])
        if count > 0:
            category_counts[cat] = count

    # Count uncategorized
    uncategorized = len([d for d in enabled if not d.get("category")])
    if uncategorized > 0:
        category_counts["(uncategorized)"] = uncategorized

    # Count by region
    region_counts = {}
    for region in VALID_REGIONS:
        count = len([d for d in enabled if region in d.get("region", [])])
        if count > 0:
            region_counts[region] = count

    # Count without region
    no_region = len([d for d in enabled if not d.get("region")])
    if no_region > 0:
        region_counts["(no region)"] = no_region

    # Count by tag
    tag_counts = {}
    for tag in VALID_TAGS:
        count = len([d for d in enabled if tag in d.get("tags", [])])
        if count > 0:
            tag_counts[tag] = count

    # Count by policy type
    policy_type_counts = {}
    for pt in VALID_POLICY_TYPES:
        count = len([d for d in enabled if pt in d.get("policy_types", [])])
        if count > 0:
            policy_type_counts[pt] = count

    return {
        "total_domains": len(domains),
        "enabled_domains": len(enabled),
        "by_region": region_counts,
        "by_category": category_counts,
        "by_tag": tag_counts,
        "by_policy_type": policy_type_counts,
    }
