"""Generate domain YAML configuration from URLs.

Pure functions for generating domain IDs, detecting regions, suggesting
output files, and producing YAML entries.  No I/O — all functions are
fully testable without network access.
"""

import re
from datetime import date
from urllib.parse import urlparse

import yaml


# ---------------------------------------------------------------------------
# US state name -> two-letter abbreviation
# ---------------------------------------------------------------------------
US_STATE_ABBREVS: dict[str, str] = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar",
    "california": "ca", "colorado": "co", "connecticut": "ct", "delaware": "de",
    "florida": "fl", "georgia": "ga", "hawaii": "hi", "idaho": "id",
    "illinois": "il", "indiana": "in", "iowa": "ia", "kansas": "ks",
    "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
    "massachusetts": "ma", "michigan": "mi", "minnesota": "mn", "mississippi": "ms",
    "missouri": "mo", "montana": "mt", "nebraska": "ne", "nevada": "nv",
    "new-hampshire": "nh", "new-jersey": "nj", "new-mexico": "nm", "new-york": "ny",
    "north-carolina": "nc", "north-dakota": "nd", "ohio": "oh", "oklahoma": "ok",
    "oregon": "or", "pennsylvania": "pa", "rhode-island": "ri",
    "south-carolina": "sc", "south-dakota": "sd", "tennessee": "tn", "texas": "tx",
    "utah": "ut", "vermont": "vt", "virginia": "va", "washington": "wa",
    "west-virginia": "wv", "wisconsin": "wi", "wyoming": "wy",
    "district-of-columbia": "dc",
}

# ---------------------------------------------------------------------------
# TLD -> (regions, suggested_file_name)
# Ordered longest-suffix-first so .gov.uk matches before .gov
# ---------------------------------------------------------------------------
TLD_REGION_MAP: dict[str, tuple[list[str], str] | None] = {
    ".gov.uk": (["uk"], "uk"),
    ".gov.au": (["apac"], "australia"),
    ".gov.sg": (["apac"], "apac"),
    ".gouv.fr": (["eu", "france"], "france"),
    ".gv.at": (["eu", "eu_central"], "austria"),
    ".admin.ch": (["eu_central"], "switzerland"),
    ".europa.eu": (["eu"], "eu"),
    ".riksdagen.se": (["eu", "nordic"], "sweden"),
    ".retsinformation.dk": (["eu", "nordic"], "denmark"),
    ".go.jp": (["apac"], "apac"),
    ".go.kr": (["apac"], "apac"),
    ".gov": None,  # US — handled specially in each function
}

# Sorted by suffix length descending so longest match wins
_TLD_SUFFIXES_SORTED = sorted(TLD_REGION_MAP.keys(), key=len, reverse=True)


def _strip_www(hostname: str) -> str:
    """Remove leading www. from hostname."""
    if hostname.startswith("www."):
        return hostname[4:]
    return hostname


def _match_tld(hostname: str) -> str | None:
    """Return the matching TLD suffix for *hostname*, or None.

    Handles both ``sub.gov.uk`` (endswith) and bare ``gov.uk`` (exact match
    with the suffix minus its leading dot).
    """
    lower = hostname.lower()
    for suffix in _TLD_SUFFIXES_SORTED:
        if lower.endswith(suffix) or lower == suffix.lstrip("."):
            return suffix
    return None


def _us_state_from_hostname(hostname: str) -> str | None:
    """Extract state name from a US state .gov hostname (e.g. lis.virginia.gov -> virginia)."""
    parts = _strip_www(hostname).lower().split(".")
    if len(parts) >= 3 and parts[-1] == "gov":
        return parts[-2]
    return None


def generate_domain_id(hostname: str) -> str:
    """Generate a domain ID from hostname.

    Examples:
        lis.virginia.gov   -> va_lis
        energy.gov         -> us_energy
        www.gov.uk         -> uk_gov
        www.example.com    -> example_com
    """
    clean = _strip_www(hostname).lower()
    parts = clean.split(".")

    tld = _match_tld(clean)

    # US .gov (must check before generic)
    if tld == ".gov":
        if len(parts) >= 3:
            # State: agency.state.gov -> {abbrev}_{agency}
            state = parts[-2]
            agency = parts[0] if len(parts) == 3 else "_".join(parts[:-2])
            abbrev = US_STATE_ABBREVS.get(state, state[:2])
            return f"{abbrev}_{agency}"[:30]
        elif len(parts) == 2:
            # Federal: energy.gov -> us_energy
            return f"us_{parts[0]}"[:30]

    # .gov.uk -> uk_{subdomain}
    if tld == ".gov.uk":
        # e.g. gov.uk -> uk_gov, legislation.gov.uk -> uk_legislation
        bare = tld.lstrip(".")  # "gov.uk"
        if clean == bare:
            prefix = "gov"
        else:
            prefix = clean[: -len(tld)].replace(".", "_").strip("_")
            if not prefix:
                prefix = "gov"
        return f"uk_{prefix}"[:30]

    # International TLDs
    if tld and tld != ".gov":
        # Strip the TLD suffix and use what's left
        prefix = clean[: -len(tld)].replace(".", "_").replace("-", "_")
        if not prefix:
            prefix = tld.replace(".", "").replace("-", "_")
        return re.sub(r"_+", "_", prefix).strip("_")[:30]

    # Generic: replace dots and dashes with underscores
    domain_id = clean.replace(".", "_").replace("-", "_")
    domain_id = re.sub(r"_+", "_", domain_id).strip("_")
    return domain_id[:30]


def detect_region(hostname: str) -> list[str]:
    """Detect geographic region(s) from hostname TLD.

    Returns:
        List of region strings (e.g. ["us", "us_states"]), or [] if unknown.
    """
    clean = _strip_www(hostname).lower()
    tld = _match_tld(clean)

    if tld is None:
        return []

    if tld == ".gov":
        # US: federal vs state
        state = _us_state_from_hostname(clean)
        if state:
            return ["us", "us_states"]
        return ["us"]

    entry = TLD_REGION_MAP.get(tld)
    if entry is not None:
        return list(entry[0])
    return []


def suggest_output_file(hostname: str) -> str:
    """Suggest which config/domains/ file to place this domain in.

    Returns:
        Relative path from config/domains/ (e.g. "us/virginia.yaml").
    """
    clean = _strip_www(hostname).lower()
    tld = _match_tld(clean)

    if tld == ".gov":
        state = _us_state_from_hostname(clean)
        if state:
            return f"us/{state}.yaml"
        return "us/us_federal.yaml"

    if tld and tld != ".gov":
        entry = TLD_REGION_MAP.get(tld)
        if entry is not None:
            return f"{entry[1]}.yaml"

    return "new_domains.yaml"


def build_domain_entry(
    *,
    name: str,
    domain_id: str,
    base_url: str,
    start_paths: list[str],
    language: str = "en",
    requires_playwright: bool = False,
    region: list[str] | None = None,
) -> dict:
    """Build a domain entry dict with sensible defaults."""
    return {
        "name": name,
        "id": domain_id,
        "enabled": True,
        "base_url": base_url,
        "start_paths": start_paths,
        "max_depth": 2,
        "language": language,
        "region": region or [],
        "requires_playwright": requires_playwright,
        "rate_limit_seconds": 2.0,
        "category": "",
        "tags": [],
        "policy_types": [],
        "verified_by": "auto-generated",
        "verified_date": date.today().isoformat(),
        "notes": f"Auto-generated from {base_url}",
    }


def format_domain_yaml(entry: dict, *, standalone: bool = True) -> str:
    """Format a domain entry dict as YAML.

    Args:
        entry: Domain entry dict from build_domain_entry().
        standalone: If True, wrap in ``domains:`` key for a new file.
                    If False, format as a list item for appending.
    """
    if standalone:
        data = {"domains": [entry]}
    else:
        data = [entry]
    return yaml.dump(
        data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
