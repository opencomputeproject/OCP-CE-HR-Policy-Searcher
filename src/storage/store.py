"""JSON file store with atomic writes for policies and scan results."""

import json
import logging
from pathlib import Path
from typing import Optional

from ..core.models import Policy

logger = logging.getLogger(__name__)


class PolicyStore:
    """Persistent storage for discovered policies."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.policies_file = self.data_dir / "policies.json"
        self._policies: list[dict] = []
        self._load()

    def _load(self) -> None:
        if self.policies_file.exists():
            try:
                with open(self.policies_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, list):
                    logger.error(
                        "policies.json contains %s instead of a list — "
                        "backing up to policies.json.corrupt and starting fresh",
                        type(data).__name__,
                    )
                    self._backup_corrupt_file()
                    self._policies = []
                else:
                    self._policies = data
            except json.JSONDecodeError as e:
                logger.error(
                    "policies.json is corrupted (JSON parse error: %s) — "
                    "backing up to policies.json.corrupt so data is not lost",
                    e,
                )
                self._backup_corrupt_file()
                self._policies = []
            except Exception as e:
                logger.error(
                    "Failed to read policies.json: %s — "
                    "file preserved, starting with empty policy list",
                    e,
                )
                self._policies = []

    def _backup_corrupt_file(self) -> None:
        """Move corrupt policies.json to .corrupt so the user can recover data."""
        backup = self.policies_file.with_suffix(".json.corrupt")
        try:
            self.policies_file.rename(backup)
            logger.warning("Corrupt file backed up to %s", backup)
        except OSError as e:
            logger.error("Failed to backup corrupt file: %s", e)

    def save(self) -> bool:
        """Save policies to disk with atomic write."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            tmp = self.policies_file.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._policies, f, indent=2, default=str)
            tmp.replace(self.policies_file)
            return True
        except Exception as e:
            logger.error(f"Failed to save policies: {e}")
            return False

    def add_policies(self, policies: list[Policy]) -> int:
        """Add policies, deduplicating by URL. Returns count added."""
        existing_urls = {p["url"] for p in self._policies}
        added = 0
        for policy in policies:
            if policy.url not in existing_urls:
                self._policies.append(policy.model_dump(mode="json"))
                existing_urls.add(policy.url)
                added += 1
        if added:
            self.save()
        return added

    def get_all(self) -> list[dict]:
        return self._policies.copy()

    def search(
        self,
        jurisdiction: Optional[str] = None,
        policy_type: Optional[str] = None,
        min_score: Optional[int] = None,
        scan_id: Optional[str] = None,
    ) -> list[dict]:
        """Search policies with filters."""
        results = self._policies
        if jurisdiction:
            j_lower = jurisdiction.lower()
            results = [
                p for p in results
                if j_lower in (p.get("jurisdiction", "") or "").lower()
            ]
        if policy_type:
            results = [
                p for p in results
                if p.get("policy_type") == policy_type
            ]
        if min_score is not None:
            results = [
                p for p in results
                if (p.get("relevance_score", 0) or 0) >= min_score
            ]
        if scan_id:
            results = [
                p for p in results
                if p.get("scan_id") == scan_id
            ]
        return results

    def get_stats(self) -> dict:
        """Get aggregate policy statistics."""
        policies = self._policies
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
