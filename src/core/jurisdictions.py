"""Canonical jurisdiction registry: the single source of truth for what a
region slug or a free-text jurisdiction string actually *is* — its ISO code
and what it rolls up to.

Backed by ``config/jurisdictions.yaml`` (one row per jurisdiction). Replaces
knowledge that was smeared across ``VALID_REGIONS`` (config.py),
``_REGION_JURISDICTIONS`` (verifier.py), and ``_jurisdiction_aliases``
(tools.py).

Hard requirement: the runtime lookup paths NEVER raise on unknown input. New
wave sources routinely introduce slugs before anyone updates the registry, so
``get`` / ``resolve_text`` / ``country_of`` / ``members_of`` all return
``None``/``[]`` and record the miss instead of crashing.
"""

import re
from pathlib import Path
from typing import Optional

import structlog
import yaml
from pydantic import BaseModel, Field

log = structlog.get_logger(__name__)

_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config" / "jurisdictions.yaml"


class Jurisdiction(BaseModel):
    """One canonical jurisdiction row."""

    slug: str
    name: str
    kind: str  # country | us_state | subnational | supranational | group
    iso3: Optional[str] = None
    iso_numeric: Optional[str] = None
    code: Optional[str] = None  # ISO 3166-2 for us_state / subnational
    parent: Optional[str] = None
    members: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)


# --- Module-level caches (populated on first use) ---
_by_slug: Optional[dict[str, Jurisdiction]] = None
_alias_index: Optional[dict[str, str]] = None  # normalized string -> slug
_alias_by_len: Optional[list[tuple[str, str]]] = None  # (alias, slug), longest first
_unresolved: dict[str, int] = {}


def _normalize(text: str) -> str:
    """Lowercase, strip, collapse internal whitespace."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _load(path: Path = _REGISTRY_PATH) -> dict[str, Jurisdiction]:
    """Load and cache the registry. Tolerates a missing file (returns {})."""
    global _by_slug, _alias_index, _alias_by_len
    if _by_slug is not None:
        return _by_slug

    if not path.exists():
        log.warning("jurisdictions_registry_missing", path=str(path))
        _by_slug, _alias_index, _alias_by_len = {}, {}, []
        return _by_slug

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    by_slug: dict[str, Jurisdiction] = {}
    for row in raw.get("jurisdictions", []):
        j = Jurisdiction(**row)
        by_slug[j.slug] = j

    # Alias index: slug, name, and every alias resolve to the slug. On a
    # collision, keep the first and log — the registry should have none.
    alias_index: dict[str, str] = {}

    def _index(key: str, slug: str) -> None:
        key = _normalize(key)
        if not key:
            return
        existing = alias_index.get(key)
        if existing and existing != slug:
            log.warning(
                "jurisdiction_alias_collision", alias=key,
                kept=existing, dropped=slug,
            )
            return
        alias_index[key] = slug

    for j in by_slug.values():
        _index(j.slug, j.slug)
        _index(j.name, j.slug)
        for alias in j.aliases:
            _index(alias, j.slug)

    _by_slug = by_slug
    _alias_index = alias_index
    _alias_by_len = sorted(alias_index.items(), key=lambda kv: -len(kv[0]))
    return _by_slug


def _strip_parentheticals(text: str) -> str:
    """Drop ``(...)`` groups: 'Germany (Federal)' -> 'Germany'."""
    return _normalize(re.sub(r"\([^)]*\)", " ", text))


def _by_alias(text: str) -> Optional[Jurisdiction]:
    """Exact alias/name/slug lookup on already-normalized text."""
    _load()
    slug = _alias_index.get(text) if _alias_index else None
    return _by_slug.get(slug) if slug else None


def _substring_match(text: str) -> Optional[Jurisdiction]:
    """Whole-word alias match anywhere in the text, longest alias first.

    Word-boundary anchored so 'US' never matches inside 'Belarus'.
    """
    _load()
    for alias, slug in (_alias_by_len or []):
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return _by_slug.get(slug)
    return None


def _record_miss(original: str) -> None:
    first_time = original not in _unresolved
    _unresolved[original] = _unresolved.get(original, 0) + 1
    if first_time:
        log.warning("jurisdiction_unresolved", input=original)


# --- Public API ---

def get(slug: Optional[str]) -> Optional[Jurisdiction]:
    """Look up a jurisdiction by exact slug. Returns None if unknown."""
    if not slug:
        return None
    return _load().get(slug)


def resolve_text(jurisdiction_string: Optional[str]) -> Optional[Jurisdiction]:
    """Resolve LLM free text to a canonical jurisdiction. Never raises.

    Handles the real mess in ``data/policies.json`` — parenthetical
    annotations ('Sweden (EU)'), 'Region, Country' forms ('Minnesota, USA'),
    and alternate-language / abbreviation aliases. Unknown input returns None,
    logs one warning, and is counted in :func:`unresolved_report`.
    """
    if jurisdiction_string is None:
        return None
    raw = jurisdiction_string.strip()
    if not raw:
        return None

    _load()
    norm = _normalize(raw)

    # 1. Exact alias/name/slug (pins the seeded messy strings).
    hit = _by_alias(norm)
    if hit:
        return hit

    # 2. Strip parentheticals, retry exact. Must precede comma handling so a
    #    comma *inside* parens ('Germany (Peine, Lower Saxony)') is removed
    #    before we split.
    cleaned = _strip_parentheticals(norm)
    if cleaned and cleaned != norm:
        hit = _by_alias(cleaned)
        if hit:
            return hit
    else:
        cleaned = norm

    # 3. 'Region, Country' — resolve the country context, then place the
    #    region under it. Disambiguates 'Georgia, United States' (US state)
    #    from any same-named country, and falls back to the country when the
    #    region part is not itself a known slug ('Wallonia, Belgium').
    if "," in cleaned:
        left, right = (p.strip() for p in cleaned.split(",", 1))
        ctx = _by_alias(right) or _substring_match(right)
        child = _by_alias(left) or _substring_match(left)
        if child and ctx:
            child_country = country_of(child)
            if child_country and child_country.slug == ctx.slug:
                return child
        if ctx:
            return ctx
        if child:
            return child

    # 4. Whole-word substring fallback ('England (United Kingdom)' -> uk after
    #    the paren strip left 'england').
    hit = _substring_match(cleaned)
    if hit:
        return hit

    _record_miss(raw)
    return None


def country_of(slug_or_jur) -> Optional[Jurisdiction]:
    """Walk ``parent`` up to the country level. Never raises.

    Accepts a slug, a free-text string, or a Jurisdiction. Returns the country
    jurisdiction, or None if it does not roll up to a country (e.g. a group).
    """
    if isinstance(slug_or_jur, Jurisdiction):
        j = slug_or_jur
    else:
        j = get(slug_or_jur) or resolve_text(slug_or_jur)

    seen: set[str] = set()
    while j and j.kind != "country":
        if not j.parent or j.parent in seen:
            return None
        seen.add(j.slug)
        j = get(j.parent)
    return j


def members_of(slug: str) -> list[Jurisdiction]:
    """Expand a group/supranational to its leaf members, recursively.

    Returns [] for unknown slugs or non-group jurisdictions.
    """
    root = get(slug)
    if not root:
        return []

    out: list[Jurisdiction] = []
    seen: set[str] = set()

    def _expand(s: str) -> None:
        j = get(s)
        if not j or s in seen:
            return
        seen.add(s)
        if j.members:
            for m in j.members:
                _expand(m)
        else:
            out.append(j)

    for m in root.members:
        _expand(m)
    return out


def unresolved_report() -> dict[str, int]:
    """Inputs that :func:`resolve_text` could not resolve, with hit counts."""
    return dict(_unresolved)
