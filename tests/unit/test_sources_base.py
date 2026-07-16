"""Tests for the PolicySource abstraction and registry."""

import pytest

from src.core.models import CrawlResult, PageStatus
from src.sources import get_source, register_source, SOURCE_REGISTRY
from src.sources.base import PolicySource


class _FakeSource(PolicySource):
    id = "fake_test_source"

    async def fetch(self, domain: dict) -> list[CrawlResult]:
        return [CrawlResult(
            url="https://official.gov/law/1",
            status=PageStatus.SUCCESS,
            content="A law about waste heat.",
            content_type="text/html",
        )]


class TestRegistry:
    def test_register_and_get(self):
        register_source(_FakeSource)
        try:
            source = get_source("fake_test_source")
            assert isinstance(source, _FakeSource)
        finally:
            SOURCE_REGISTRY.pop("fake_test_source", None)

    def test_unknown_source_raises(self):
        with pytest.raises(KeyError):
            get_source("does_not_exist")


class TestLifecycleStageModel:
    def test_policy_has_lifecycle_stage_default_unknown(self):
        from src.core.models import Policy, PolicyType
        p = Policy(
            url="https://a.gov", policy_name="X", jurisdiction="SE",
            policy_type=PolicyType.LAW, summary="s", relevance_score=5,
        )
        assert p.lifecycle_stage == "unknown"

    def test_crawl_result_lifecycle_optional(self):
        r = CrawlResult(url="https://a.gov", status=PageStatus.SUCCESS)
        assert r.lifecycle_stage is None

    def test_valid_stages(self):
        from src.core.models import LIFECYCLE_STAGES
        assert {"proposed", "consultation", "in_committee", "passed",
                "enacted", "transposition_notified", "amended",
                "unknown"} <= set(LIFECYCLE_STAGES)
