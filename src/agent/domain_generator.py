"""Generate domain YAML configuration from URLs.

Pure functions for generating domain IDs, detecting regions, suggesting
output files, and producing YAML entries.  No I/O — all functions are
fully testable without network access.
"""

import re
from datetime import date

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
    if hostname.startswith("www."):
        return hostname[4:]
    return hostname


def _match_tld(hostname: str) -> str | None:
    lower = hostname.lower()
    for suffix in _TLD_SUFFIXES_SORTED:
        if lower.endswith(suffix) or lower == suffix.lstrip("."):
            return suffix
    return None


def _us_state_from_hostname(hostname: str) -> str | None:
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

    if tld == ".gov":
        if len(parts) >= 3:
            state = parts[-2]
            agency = parts[0] if len(parts) == 3 else "_".join(parts[:-2])
            abbrev = US_STATE_ABBREVS.get(state, state[:2])
            return f"{abbrev}_{agency}"[:30]
        elif len(parts) == 2:
            return f"us_{parts[0]}"[:30]

    if tld == ".gov.uk":
        bare = tld.lstrip(".")
        if clean == bare:
            prefix = "gov"
        else:
            prefix = clean[: -len(tld)].replace(".", "_").strip("_")
            if not prefix:
                prefix = "gov"
        return f"uk_{prefix}"[:30]

    if tld and tld != ".gov":
        prefix = clean[: -len(tld)].replace(".", "_").replace("-", "_")
        if not prefix:
            prefix = tld.replace(".", "").replace("-", "_")
        return re.sub(r"_+", "_", prefix).strip("_")[:30]

    domain_id = clean.replace(".", "_").replace("-", "_")
    domain_id = re.sub(r"_+", "_", domain_id).strip("_")
    return domain_id[:30]


def detect_region(hostname: str) -> list[str]:
    """Detect geographic region(s) from hostname TLD."""
    clean = _strip_www(hostname).lower()
    tld = _match_tld(clean)

    if tld is None:
        return []

    if tld == ".gov":
        state = _us_state_from_hostname(clean)
        if state:
            return ["us", "us_states"]
        return ["us"]

    entry = TLD_REGION_MAP.get(tld)
    if entry is not None:
        return list(entry[0])
    return []


def suggest_output_file(hostname: str) -> str:
    """Suggest which config/domains/ file to place this domain in."""
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


# ---------------------------------------------------------------------------
# Custom YAML formatter
# ---------------------------------------------------------------------------

_FIELD_ORDER = [
    "name", "id", "enabled", "region", "base_url", "start_paths",
    "max_depth", "language", "requires_playwright", "rate_limit_seconds",
    "category", "tags", "policy_types", "verified_by", "verified_date", "notes",
]

_QUOTED_FIELDS = {"name", "id", "base_url", "verified_by", "verified_date", "category"}
_QUOTED_LIST_FIELDS = {"region", "start_paths", "tags", "policy_types"}


def _yaml_scalar(key: str, value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.1f}" if value == int(value) else str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        if key in _QUOTED_FIELDS:
            return f'"{value}"'
        return value
    return str(value)


def _format_entry_yaml(entry: dict, indent: str = "    ") -> str:
    lines: list[str] = []
    first = True

    for key in _FIELD_ORDER:
        if key not in entry:
            continue
        value = entry[key]

        if isinstance(value, list) and not value:
            continue
        if isinstance(value, str) and not value:
            continue

        prefix = "  - " if first else indent
        first = False

        if isinstance(value, list):
            lines.append(f"{prefix}{key}:")
            quote = key in _QUOTED_LIST_FIELDS
            for item in value:
                item_str = f'"{item}"' if quote else str(item)
                lines.append(f"{indent}  - {item_str}")
        elif key == "notes" and isinstance(value, str) and "\n" in value:
            lines.append(f"{prefix}{key}: |")
            for note_line in value.rstrip("\n").split("\n"):
                lines.append(f"{indent}  {note_line}")
        else:
            lines.append(f"{prefix}{key}: {_yaml_scalar(key, value)}")

    for key in entry:
        if key not in _FIELD_ORDER:
            value = entry[key]
            if isinstance(value, list) and not value:
                continue
            if isinstance(value, str) and not value:
                continue
            lines.append(f"{indent}{key}: {_yaml_scalar(key, value)}")

    return "\n".join(lines) + "\n"


def format_domain_yaml(entry: dict, *, standalone: bool = True) -> str:
    """Format a domain entry dict as YAML matching hand-crafted file style."""
    body = _format_entry_yaml(entry)
    if standalone:
        return "domains:\n" + body
    return body
