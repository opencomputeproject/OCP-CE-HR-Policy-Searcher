"""Deterministic post-extraction verifier.

Catches hallucinations, duplicates, jurisdiction mismatches, and other
quality issues without any LLM calls.
"""

from datetime import date, timedelta
from typing import Optional
from urllib.parse import urlparse

from .models import Policy, VerificationFlag


# Generic policy names that indicate low-quality extraction
_GENERIC_NAMES = {
    "energy policy", "energy law", "energy regulation",
    "data center policy", "data center regulation",
    "heat policy", "heat regulation", "heat law",
    "energy efficiency", "policy", "regulation", "law",
    "directive", "act", "bill", "measure", "standard",
}

# Region → expected jurisdiction keywords
_REGION_JURISDICTIONS: dict[str, list[str]] = {
    "germany": ["germany", "german", "deutschland", "deutsch", "bundesrepublik"],
    "france": ["france", "french", "français", "république"],
    "netherlands": ["netherlands", "dutch", "nederland"],
    "denmark": ["denmark", "danish", "danmark"],
    "sweden": ["sweden", "swedish", "sverige"],
    "norway": ["norway", "norwegian", "norge"],
    "ireland": ["ireland", "irish", "éire"],
    "switzerland": ["switzerland", "swiss", "schweiz", "suisse"],
    "uk": ["united kingdom", "uk", "britain", "british", "england", "scotland", "wales"],
    "us": ["united states", "us", "usa", "america", "american", "federal"],
    "singapore": ["singapore"],
    "japan": ["japan", "japanese"],
    "eu": ["european union", "eu", "european"],
    "oregon": ["oregon"],
    "texas": ["texas"],
    "california": ["california"],
    "virginia": ["virginia"],
}


class Verifier:
    """Deterministic policy verification rules."""

    def __init__(self):
        self._seen_urls: set[str] = set()

    def verify(
        self,
        policy: Policy,
        domain_regions: Optional[list[str]] = None,
    ) -> list[VerificationFlag]:
        """Run all verification checks on a policy. Returns list of flags."""
        flags: list[VerificationFlag] = []

        # 1. Duplicate URL detection
        if policy.url in self._seen_urls:
            flags.append(VerificationFlag.DUPLICATE_URL)
        self._seen_urls.add(policy.url)

        # 2. Jurisdiction mismatch
        if domain_regions:
            if self._check_jurisdiction_mismatch(policy.jurisdiction, domain_regions):
                flags.append(VerificationFlag.JURISDICTION_MISMATCH)

        # 3. Future date check (>2 years from now)
        if policy.effective_date:
            max_future = date.today() + timedelta(days=730)
            if policy.effective_date > max_future:
                flags.append(VerificationFlag.FUTURE_DATE)

        # 4. Generic name with no bill number
        if self._is_generic_name(policy.policy_name) and not policy.bill_number:
            flags.append(VerificationFlag.GENERIC_NAME)

        # 5. Low confidence but high relevance score
        if policy.relevance_score >= 9:
            path = urlparse(policy.url).path.lower()
            if any(seg in path for seg in ["/about", "/contact", "/team", "/staff"]):
                flags.append(VerificationFlag.LOW_CONFIDENCE_HIGH_SCORE)

        return flags

    def _check_jurisdiction_mismatch(
        self, jurisdiction: str, domain_regions: list[str],
    ) -> bool:
        """Check if extracted jurisdiction matches domain's expected region."""
        if not jurisdiction or jurisdiction == "Unknown":
            return False

        jurisdiction_lower = jurisdiction.lower()

        for region in domain_regions:
            expected_keywords = _REGION_JURISDICTIONS.get(region, [])
            if any(kw in jurisdiction_lower for kw in expected_keywords):
                return False

        # If no region has expected keywords defined, skip the check
        has_any_expected = any(
            region in _REGION_JURISDICTIONS for region in domain_regions
        )
        return has_any_expected

    def _is_generic_name(self, name: str) -> bool:
        """Check if policy name is too generic to be real."""
        return name.lower().strip() in _GENERIC_NAMES

    def verify_batch(
        self,
        policies: list[Policy],
        domain_regions: Optional[list[str]] = None,
    ) -> dict[str, list[VerificationFlag]]:
        """Verify a batch of policies. Returns {url: [flags]}."""
        results = {}
        for policy in policies:
            flags = self.verify(policy, domain_regions)
            if flags:
                results[policy.url] = flags
                policy.verification_flags = flags
        return results

    def reset(self):
        """Reset state (clear seen URLs)."""
        self._seen_urls.clear()
