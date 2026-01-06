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

    Scans config/domains/ for .yaml files (excluding _template.yaml)
    and merges all domains into a single list.
    """
    all_domains = []

    if not domains_dir.exists():
        return all_domains

    for yaml_file in sorted(domains_dir.glob("*.yaml")):
        # Skip template file
        if yaml_file.name.startswith("_"):
            continue

        try:
            content = _load_yaml(yaml_file)
            domains = content.get("domains", [])
            all_domains.extend(domains)
        except Exception as e:
            raise ConfigurationError(f"Error loading {yaml_file}: {e}")

    return all_domains


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
    """Get domains for a group.

    Args:
        domains_config: Configuration dict with 'domains' and 'groups' keys
        group: Group name (default "all" returns all enabled domains)

    Returns:
        List of domain dicts matching the group

    Raises:
        ConfigurationError: If group doesn't exist
    """
    all_domains = {d["id"]: d for d in domains_config.get("domains", [])}

    if group == "all":
        return [d for d in all_domains.values() if d.get("enabled", True)]

    groups = domains_config.get("groups", {})
    if group not in groups:
        available = ", ".join(sorted(groups.keys()))
        raise ConfigurationError(
            f"Unknown group: '{group}'. Available groups: {available}"
        )

    group_ids = groups[group].get("domains", [])

    # Validate all domain IDs exist
    missing = [id for id in group_ids if id not in all_domains]
    if missing:
        raise ConfigurationError(
            f"Group '{group}' references unknown domains: {missing}"
        )

    return [all_domains[id] for id in group_ids if all_domains[id].get("enabled", True)]


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
        }
        for d in domains_config.get("domains", [])
    ]
