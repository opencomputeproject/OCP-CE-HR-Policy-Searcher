"""Lead queue: candidate policy pointers awaiting a chase.

News signals and community submissions produce leads, not policies.
A lead holds a URL and enough context to decide whether to "chase" it
(run the full analysis pipeline against it) or dismiss it. This keeps
expensive model spend human-gated and capped.

Persistence is SQLite-backed (see ``src/storage/db.py``); this module
keeps the same public interface the JSON-file version had.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from . import db as storage_db

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
    """SQLite-backed persistence for leads, deduplicated by source_url."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.leads_file = self.data_dir / "leads.json"
        self._presanitize_legacy_json()
        self._conn = storage_db.connect(self.data_dir)

    def _presanitize_legacy_json(self) -> None:
        """Back up a corrupt legacy leads.json before migration runs."""
        db_path = self.data_dir / storage_db.DB_FILENAME
        if db_path.exists() or not self.leads_file.exists():
            return
        try:
            data = json.loads(self.leads_file.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError(f"leads.json contains {type(data).__name__} instead of a list")
        except Exception as e:
            backup = self.leads_file.with_suffix(".json.corrupt")
            logger.error("Failed to load leads (%s); backing up to %s", e, backup)
            try:
                self.leads_file.replace(backup)
            except OSError:
                pass

    def save(self) -> None:
        """Commit pending writes. Kept for interface compatibility."""
        self._conn.commit()

    def add_leads(self, leads: list[Lead]) -> int:
        """Add leads, skipping source URLs already present. Returns added count."""
        added = 0
        for lead in leads:
            record = lead.model_dump(mode="json")
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO leads (lead_id, source_url, status, raw) "
                "VALUES (?, ?, ?, ?)",
                (
                    record["lead_id"],
                    record["source_url"],
                    record["status"],
                    json.dumps(record, ensure_ascii=False, default=str),
                ),
            )
            if cur.rowcount:
                added += 1
        # Commit unconditionally: even an all-duplicates batch ran INSERT OR
        # IGNORE statements, which open an implicit transaction that must be
        # closed out — otherwise it's left open on this connection and
        # blocks the next writer.
        self._conn.commit()
        return added

    def get(self, lead_id: str) -> Optional[Lead]:
        row = self._conn.execute(
            "SELECT raw FROM leads WHERE lead_id = ?", (lead_id,)
        ).fetchone()
        return Lead(**json.loads(row[0])) if row else None

    def list(self, status: Optional[str] = None) -> list[Lead]:
        query = "SELECT raw FROM leads"
        params: list = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        rows = self._conn.execute(query, params).fetchall()
        leads = [Lead(**json.loads(row[0])) for row in rows]
        leads.sort(key=lambda lead: lead.found_at, reverse=True)
        return leads

    def update_status(
        self, lead_id: str, status: str, policy_url: Optional[str] = None,
    ) -> Optional[Lead]:
        if status not in LEAD_STATUSES:
            raise ValueError(f"Invalid lead status '{status}'")
        row = self._conn.execute(
            "SELECT raw FROM leads WHERE lead_id = ?", (lead_id,)
        ).fetchone()
        if row is None:
            return None
        record = json.loads(row[0])
        record["status"] = status
        if policy_url:
            record["policy_url"] = policy_url
        self._conn.execute(
            "UPDATE leads SET status = ?, raw = ? WHERE lead_id = ?",
            (status, json.dumps(record, ensure_ascii=False, default=str), lead_id),
        )
        self._conn.commit()
        return Lead(**record)
