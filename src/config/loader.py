"""Configuration loader."""

from pathlib import Path
from typing import Optional
import yaml

from .settings import Settings


class ConfigurationError(Exception):
    """Configuration error."""
    pass


def load_settings(
    settings_path: Optional[Path] = None,
    domains_path: Optional[Path] = None,
    keywords_path: Optional[Path] = None,
) -> tuple[Settings, dict, dict]:
    """Load all configuration files."""
    config_dir = Path("config")

    # Load settings.yaml
    settings_file = settings_path or config_dir / "settings.yaml"
    settings_dict = {}
    if settings_file.exists():
        with open(settings_file) as f:
            settings_dict = yaml.safe_load(f) or {}

    settings = Settings(**settings_dict)

    # Load domains.yaml
    domains_file = domains_path or config_dir / "domains.yaml"
    if not domains_file.exists():
        raise ConfigurationError(f"Missing: {domains_file}")
    with open(domains_file) as f:
        domains_config = yaml.safe_load(f)

    # Load keywords.yaml
    keywords_file = keywords_path or config_dir / "keywords.yaml"
    if not keywords_file.exists():
        raise ConfigurationError(f"Missing: {keywords_file}")
    with open(keywords_file) as f:
        keywords_config = yaml.safe_load(f)

    return settings, domains_config, keywords_config


def get_enabled_domains(domains_config: dict, group: str = "all") -> list[dict]:
    """Get domains for a group."""
    all_domains = {d["id"]: d for d in domains_config.get("domains", [])}

    if group == "all":
        return [d for d in all_domains.values() if d.get("enabled", True)]

    groups = domains_config.get("groups", {})
    if group not in groups:
        raise ConfigurationError(f"Unknown group: {group}")

    group_ids = groups[group].get("domains", [])
    return [all_domains[id] for id in group_ids if id in all_domains]
