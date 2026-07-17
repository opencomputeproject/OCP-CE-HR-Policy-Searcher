"""Tests for Verifier — deterministic policy verification."""

from datetime import date, timedelta


from src.core.models import Policy, PolicyType, VerificationFlag
from src.core.verifier import Verifier


def _make_policy(**overrides) -> Policy:
    """Helper to create a Policy with defaults."""
    defaults = dict(
        url="https://example.gov/policy",
        policy_name="Energy Efficiency Act 2024",
        jurisdiction="Germany",
        policy_type=PolicyType.LAW,
        summary="A policy about energy",
        relevance_score=7,
    )
    defaults.update(overrides)
    return Policy(**defaults)


class TestDuplicateUrlDetection:
    def test_first_url_no_flag(self):
        v = Verifier()
        flags = v.verify(_make_policy(url="https://a.gov/p1"))
        assert VerificationFlag.DUPLICATE_URL not in flags

    def test_duplicate_url_flagged(self):
        v = Verifier()
        v.verify(_make_policy(url="https://a.gov/p1"))
        flags = v.verify(_make_policy(url="https://a.gov/p1"))
        assert VerificationFlag.DUPLICATE_URL in flags

    def test_different_urls_no_flag(self):
        v = Verifier()
        v.verify(_make_policy(url="https://a.gov/p1"))
        flags = v.verify(_make_policy(url="https://a.gov/p2"))
        assert VerificationFlag.DUPLICATE_URL not in flags


class TestJurisdictionMismatch:
    def test_matching_jurisdiction(self):
        v = Verifier()
        flags = v.verify(
            _make_policy(jurisdiction="Germany"),
            domain_regions=["germany"],
        )
        assert VerificationFlag.JURISDICTION_MISMATCH not in flags

    def test_mismatched_jurisdiction(self):
        v = Verifier()
        flags = v.verify(
            _make_policy(jurisdiction="France"),
            domain_regions=["germany"],
        )
        assert VerificationFlag.JURISDICTION_MISMATCH in flags

    def test_unknown_jurisdiction_skips_check(self):
        v = Verifier()
        flags = v.verify(
            _make_policy(jurisdiction="Unknown"),
            domain_regions=["germany"],
        )
        assert VerificationFlag.JURISDICTION_MISMATCH not in flags

    def test_no_domain_regions_skips_check(self):
        v = Verifier()
        flags = v.verify(
            _make_policy(jurisdiction="France"),
            domain_regions=None,
        )
        assert VerificationFlag.JURISDICTION_MISMATCH not in flags

    def test_eu_region_matches_european_union(self):
        v = Verifier()
        flags = v.verify(
            _make_policy(jurisdiction="European Union"),
            domain_regions=["eu"],
        )
        assert VerificationFlag.JURISDICTION_MISMATCH not in flags

    def test_undefined_region_skips(self):
        v = Verifier()
        flags = v.verify(
            _make_policy(jurisdiction="Mars"),
            domain_regions=["mars"],  # not in _REGION_JURISDICTIONS
        )
        assert VerificationFlag.JURISDICTION_MISMATCH not in flags

    def test_second_batch_source_countries_are_checked(self):
        """Every country with a structured source must be in the
        jurisdiction map, or the mismatch check silently skips for it.
        Regression for the 2026-07-17 batch (GR, EE, PL, ZA, BR)."""
        v = Verifier()
        for region, native in [
            ("greece", "Ελλάδα"),
            ("estonia", "Eesti"),
            ("poland", "Polska"),
            ("south_africa", "South Africa"),
            ("brazil", "Brasil"),
        ]:
            flags = v.verify(
                _make_policy(url=f"https://example.org/{region}", jurisdiction=native),
                domain_regions=[region],
            )
            assert VerificationFlag.JURISDICTION_MISMATCH not in flags, region
            flags = v.verify(
                _make_policy(url=f"https://example.org/{region}2", jurisdiction="France"),
                domain_regions=[region],
            )
            assert VerificationFlag.JURISDICTION_MISMATCH in flags, region


class TestFutureDate:
    def test_reasonable_future_date_ok(self):
        v = Verifier()
        future = date.today() + timedelta(days=365)
        flags = v.verify(_make_policy(effective_date=future))
        assert VerificationFlag.FUTURE_DATE not in flags

    def test_far_future_date_flagged(self):
        v = Verifier()
        far_future = date.today() + timedelta(days=800)
        flags = v.verify(_make_policy(effective_date=far_future))
        assert VerificationFlag.FUTURE_DATE in flags

    def test_past_date_ok(self):
        v = Verifier()
        past = date(2020, 1, 1)
        flags = v.verify(_make_policy(effective_date=past))
        assert VerificationFlag.FUTURE_DATE not in flags

    def test_no_date_ok(self):
        v = Verifier()
        flags = v.verify(_make_policy(effective_date=None))
        assert VerificationFlag.FUTURE_DATE not in flags


class TestGenericName:
    def test_generic_name_no_bill_flagged(self):
        v = Verifier()
        flags = v.verify(_make_policy(policy_name="Energy Policy", bill_number=None))
        assert VerificationFlag.GENERIC_NAME in flags

    def test_generic_name_with_bill_not_flagged(self):
        v = Verifier()
        flags = v.verify(_make_policy(policy_name="Energy Policy", bill_number="HB-123"))
        assert VerificationFlag.GENERIC_NAME not in flags

    def test_specific_name_not_flagged(self):
        v = Verifier()
        flags = v.verify(_make_policy(policy_name="EnEfG Section 18"))
        assert VerificationFlag.GENERIC_NAME not in flags


class TestLowConfidenceHighScore:
    def test_about_page_high_score_flagged(self):
        v = Verifier()
        flags = v.verify(_make_policy(
            url="https://example.gov/about",
            relevance_score=9,
        ))
        assert VerificationFlag.LOW_CONFIDENCE_HIGH_SCORE in flags

    def test_about_page_low_score_not_flagged(self):
        v = Verifier()
        flags = v.verify(_make_policy(
            url="https://example.gov/about",
            relevance_score=7,
        ))
        assert VerificationFlag.LOW_CONFIDENCE_HIGH_SCORE not in flags

    def test_policy_page_high_score_not_flagged(self):
        v = Verifier()
        flags = v.verify(_make_policy(
            url="https://example.gov/policy/heat-reuse",
            relevance_score=10,
        ))
        assert VerificationFlag.LOW_CONFIDENCE_HIGH_SCORE not in flags


class TestVerifyBatch:
    def test_batch_verify_sets_flags(self):
        v = Verifier()
        policies = [
            _make_policy(url="https://a.gov/p1", policy_name="Energy Policy"),
            _make_policy(url="https://a.gov/p1", policy_name="Good Name Act"),
        ]
        results = v.verify_batch(policies, domain_regions=None)
        # Second should have DUPLICATE_URL, first should have GENERIC_NAME
        assert "https://a.gov/p1" in results

    def test_batch_verify_assigns_flags_to_policy(self):
        v = Verifier()
        policy = _make_policy(url="https://a.gov/p1", policy_name="Energy Policy")
        v.verify_batch([policy])
        assert VerificationFlag.GENERIC_NAME in policy.verification_flags


class TestReset:
    def test_reset_clears_seen_urls(self):
        v = Verifier()
        v.verify(_make_policy(url="https://a.gov/p1"))
        v.reset()
        flags = v.verify(_make_policy(url="https://a.gov/p1"))
        assert VerificationFlag.DUPLICATE_URL not in flags
