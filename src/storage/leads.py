"""Lead queue: candidate policy pointers awaiting a chase.

News signals and community submissions produce leads, not policies.
A lead holds a URL and enough context to decide whether to "chase" it
(run the full analysis pipeline against it) or dismiss it. This keeps
expensive model spend human-gated and capped.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

LEAD_STATUSES = ("new", "chased", "dismissed")


class Lead(BaseModel):
    lead_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str
    source_url: str
    snippet: str = ""
    jurisdiction_guess: str = ""
    origin: str = "news"  # news | community | curated
    found_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    status: str = "new"
    policy_url: Optional[str] = None  # set when a chase produced a policy


class LeadStore:
    """Atomic JSON persistence for leads, deduplicated by source_url."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.leads_file = self.data_dir / "leads.json"
        self._leads: dict[str, Lead] = {}
        self._load()

    def _load(self) -> None:
        if not self.leads_file.exists():
            return
        try:
            raw = json.loads(self.leads_file.read_text(encoding="utf-8"))
            for item in raw:
                lead = Lead(**item)
                self._leads[lead.lead_id] = lead
        except Exception as e:
            backup = self.leads_file.with_suffix(".json.corrupt")
            logger.error("Failed to load leads (%s); backing up to %s", e, backup)
            try:
                self.leads_file.replace(backup)
            except OSError:
                pass

    def save(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.leads_file.with_suffix(".json.tmp")
        payload = [lead.model_dump(mode="json") for lead in self._leads.values()]
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.leads_file)

    def add_leads(self, leads: list[Lead]) -> int:
        """Add leads, skipping source URLs already present. Returns added count."""
        existing_urls = {lead.source_url for lead in self._leads.values()}
        added = 0
        for lead in leads:
            if lead.source_url in existing_urls:
                continue
            self._leads[lead.lead_id] = lead
            existing_urls.add(lead.source_url)
            added += 1
        if added:
            self.save()
        return added

    def get(self, lead_id: str) -> Optional[Lead]:
        return self._leads.get(lead_id)

    def list(self, status: Optional[str] = None) -> list[Lead]:
        leads = sorted(
            self._leads.values(), key=lambda lead: lead.found_at, reverse=True,
        )
        if status:
            leads = [lead for lead in leads if lead.status == status]
        return leads

    def update_status(
        self, lead_id: str, status: str, policy_url: Optional[str] = None,
    ) -> Optional[Lead]:
        if status not in LEAD_STATUSES:
            raise ValueError(f"Invalid lead status '{status}'")
        lead = self._leads.get(lead_id)
        if lead is None:
            return None
        lead.status = status
        if policy_url:
            lead.policy_url = policy_url
        self.save()
        return lead
