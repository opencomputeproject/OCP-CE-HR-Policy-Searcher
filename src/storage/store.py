"""SQLite-backed store for policies and scan results.

Schema, connection handling, and the JSON -> SQLite migration live in
``src/storage/db.py``. This module keeps the same public interface the
JSON-file version had (same constructor, same method signatures and
result shapes) so callers never notice the storage swap.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from . import db as storage_db
from ..core.models import Policy

logger = logging.getLogger(__name__)


class PolicyStore:
    """Persistent storage for discovered policies."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.policies_file = self.data_dir / "policies.json"
        self._presanitize_legacy_json()
        self._conn = storage_db.connect(self.data_dir)

    def _presanitize_legacy_json(self) -> None:
        """Back up a corrupt legacy policies.json before migration runs.

        Preserves the pre-SQLite behavior: a corrupt or wrong-shaped
        policies.json never blocks startup or loses data — it's renamed to
        ``.corrupt`` and migration proceeds as if it were never there.
        """
        db_path = self.data_dir / storage_db.DB_FILENAME
        if db_path.exists() or not self.policies_file.exists():
            return
        try:
            data = json.loads(self.policies_file.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                logger.error(
                    "policies.json contains %s instead of a list — "
                    "backing up to policies.json.corrupt and starting fresh",
                    type(data).__name__,
                )
                self._backup_corrupt_file()
        except json.JSONDecodeError as e:
            logger.error(
                "policies.json is corrupted (JSON parse error: %s) — "
                "backing up to policies.json.corrupt so data is not lost",
                e,
            )
            self._backup_corrupt_file()
        except Exception as e:
            logger.error(
                "Failed to read policies.json: %s — "
                "file preserved, starting with empty policy list",
                e,
            )

    def _backup_corrupt_file(self) -> None:
        """Move corrupt policies.json to .corrupt so the user can recover data."""
        backup = self.policies_file.with_suffix(".json.corrupt")
        try:
            self.policies_file.rename(backup)
            logger.warning("Corrupt file backed up to %s", backup)
        except OSError as e:
            logger.error("Failed to backup corrupt file: %s", e)

    def save(self) -> bool:
        """Commit pending writes. Kept for interface compatibility."""
        try:
            self._conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save policies: {e}")
            return False

    def add_policies(self, policies: list[Policy]) -> int:
        """Add policies, deduplicating by URL. Returns count added."""
        added = 0
        for policy in policies:
            record = policy.model_dump(mode="json")
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO policies (
                    url, policy_name, jurisdiction, policy_type, lifecycle_stage,
                    review_status, relevance_score, scan_id, domain_id,
                    source_language, raw
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.get("url"),
                    record.get("policy_name"),
                    record.get("jurisdiction"),
                    record.get("policy_type"),
                    record.get("lifecycle_stage"),
                    record.get("review_status"),
                    record.get("relevance_score"),
                    record.get("scan_id"),
                    record.get("domain_id"),
                    record.get("source_language"),
                    json.dumps(record, ensure_ascii=False, default=str),
                ),
            )
            if cur.rowcount:
                added += 1
        # Commit unconditionally: even a batch that turns out to be all
        # duplicates still ran INSERT OR IGNORE statements, which open an
        # implicit transaction that must be closed out — otherwise it's
        # left open on this connection and blocks the next writer.
        self._conn.commit()
        return added

    def get_all(self) -> list[dict]:
        rows = self._conn.execute("SELECT raw FROM policies ORDER BY rowid").fetchall()
        return [json.loads(row[0]) for row in rows]

    def update_review_status(self, url: str, review_status: str) -> bool:
        """Set a policy's review status by URL. Returns False if not found."""
        cur = self._conn.execute(
            "UPDATE policies SET review_status = ?, "
            "raw = json_set(raw, '$.review_status', ?) WHERE url = ?",
            (review_status, review_status, url),
        )
        # Commit unconditionally — the UPDATE opened a transaction whether
        # or not it matched a row, and an unmatched url must not leave it
        # open on this connection.
        self._conn.commit()
        return cur.rowcount > 0

    def search(
        self,
        jurisdiction: Optional[str] = None,
        policy_type: Optional[str] = None,
        min_score: Optional[int] = None,
        scan_id: Optional[str] = None,
        review_status: Optional[str] = None,
    ) -> list[dict]:
        """Search policies with filters.

        The jurisdiction filter is a case-insensitive substring match — the
        exact semantics of the JSON-backed store this replaced. FTS5 token
        matching answers mid-word fragments differently, so the FTS index is
        deliberately NOT used here; it exists for the upcoming free-text
        search feature, where new semantics belong.
        """
        conditions: list[str] = []
        params: list = []

        query = "SELECT raw, rowid FROM policies"
        if jurisdiction:
            conditions.append("LOWER(jurisdiction) LIKE ? ESCAPE '\\'")
            params.append(f"%{storage_db.escape_like(jurisdiction.lower())}%")

        if review_status:
            conditions.append("review_status = ?")
            params.append(review_status)
        if policy_type:
            conditions.append("policy_type = ?")
            params.append(policy_type)
        if min_score is not None:
            conditions.append("COALESCE(relevance_score, 0) >= ?")
            params.append(min_score)
        if scan_id:
            conditions.append("scan_id = ?")
            params.append(scan_id)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY rowid"

        rows = self._conn.execute(query, params).fetchall()
        return [json.loads(row[0]) for row in rows]

    def get_stats(self) -> dict:
        """Get aggregate policy statistics."""
        policies = self.get_all()
        by_jurisdiction: dict[str, int] = {}
        by_type: dict[str, int] = {}
        by_score: dict[str, int] = {"1-3": 0, "4-6": 0, "7-8": 0, "9-10": 0}
        flagged = 0

        for p in policies:
            j = p.get("jurisdiction", "Unknown") or "Unknown"
            by_jurisdiction[j] = by_jurisdiction.get(j, 0) + 1

            pt = p.get("policy_type", "unknown") or "unknown"
            by_type[pt] = by_type.get(pt, 0) + 1

            score = p.get("relevance_score", 0) or 0
            if score <= 3:
                by_score["1-3"] += 1
            elif score <= 6:
                by_score["4-6"] += 1
            elif score <= 8:
                by_score["7-8"] += 1
            else:
                by_score["9-10"] += 1

            if p.get("verification_flags"):
                flagged += 1

        return {
            "total": len(policies),
            "by_jurisdiction": by_jurisdiction,
            "by_type": by_type,
            "by_score_range": by_score,
            "flagged_count": flagged,
        }
