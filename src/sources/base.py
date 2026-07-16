"""PolicySource: the query-side alternative to crawling.

A source talks to a structured system (legislation API, transposition
register, news index) and returns documents as CrawlResult objects so the
existing pipeline (keywords -> screening -> analysis -> verify -> store)
processes them unchanged. Sources replace only the crawl stage.

Contract rules:
- Every returned CrawlResult.url MUST be the official/primary document URL
  (never an aggregator URL) — it becomes the citation of record.
- Set lifecycle_stage when the source knows it (bill status, consultation);
  it overrides whatever the analysis model infers.
- Respect per-source caps from the domain config; never raise for a normal
  empty result. Raise SourceError for hard failures so the domain is marked
  failed with a clear message.
"""

from abc import ABC, abstractmethod

from ..core.models import CrawlResult


class SourceError(Exception):
    """Hard failure talking to a structured source."""


class PolicySource(ABC):
    """Base class for structured policy sources."""

    #: Registry key; also the value of `source_type` in domain YAML.
    id: str = ""

    #: Name of the environment variable holding this source's API key, or
    #: None for keyless sources. Lets the diagnostic report readiness
    #: without each client leaking its own key-loading details.
    api_key_env: str | None = None

    @abstractmethod
    async def fetch(self, domain: dict) -> list[CrawlResult]:
        """Fetch candidate documents for a domain config.

        Args:
            domain: The domain dict from config (id, source_params, caps).

        Returns:
            CrawlResults with content populated; may be empty.
        """
