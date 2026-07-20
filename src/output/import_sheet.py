"""Seed/refresh the local PolicyStore from the Google Sheets Staging worksheet.

Makes the Staging sheet the canonical cross-machine dataset: a fresh
deployment runs this once and data/policies.json (and therefore the map/list
UI) is populated without re-scanning every domain.

Usage:
    python -m src.output.import_sheet             # import into data/policies.json
    python -m src.output.import_sheet --dry-run    # map + summarize, write nothing
    python -m src.output.import_sheet --data-dir /srv/policypulse/data

Requires the same GOOGLE_CREDENTIALS / SPREADSHEET_ID configuration as the
writer (see README "Google Sheets Setup").
"""

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from ..core.config import ConfigLoader
from ..core.models import Policy
from ..core.policy_schema import from_staging_row
from ..storage.store import PolicyStore

logger = logging.getLogger(__name__)


@dataclass
class ImportSummary:
    rows_read: int = 0
    imported: int = 0
    duplicates: int = 0
    invalid: int = 0
    invalid_rows: list[int] = field(default_factory=list)


def map_row_to_policy(row: dict, row_number: int) -> Policy:
    """Build a Policy from one Staging row, or raise ValueError with context.

    row_number is the 1-based spreadsheet row (header is row 1) so a curator
    can find the offending row without re-deriving the offset.
    """
    kwargs = from_staging_row(row)
    if not kwargs["url"]:
        raise ValueError(f"row {row_number}: missing URL (Link column)")
    # The URL becomes a clickable link for every visitor; the sheet is
    # curator-edited, so reject non-web schemes (javascript:, file:, ...)
    # at this boundary rather than trusting every cell.
    if not kwargs["url"].startswith(("http://", "https://")):
        raise ValueError(f"row {row_number}: URL must start with http:// or https://")
    if not kwargs["policy_name"]:
        raise ValueError(f"row {row_number}: missing Name")
    try:
        return Policy(**kwargs)
    except ValidationError as e:
        raise ValueError(f"row {row_number}: {e}") from e


def import_from_sheet(
    config_dir: str = "config",
    data_dir: Optional[str] = None,
    sheet_name: Optional[str] = None,
    dry_run: bool = False,
) -> ImportSummary:
    """Read the Staging sheet and merge valid rows into the PolicyStore.

    Idempotent: PolicyStore.add_policies dedupes by URL, so re-running after
    the sheet gains new rows only imports what's new. dry_run maps and
    previews counts without writing to disk.
    """
    config = ConfigLoader(config_dir=config_dir)
    output_cfg = config.settings.output
    if not (output_cfg.spreadsheet_id and output_cfg.google_credentials_b64):
        raise ValueError(
            "Google Sheets is not configured — set GOOGLE_CREDENTIALS and "
            "SPREADSHEET_ID (see README 'Google Sheets Setup')."
        )

    resolved_data_dir = data_dir or config.settings.data_dir
    resolved_sheet_name = sheet_name or output_cfg.staging_sheet_name

    from .sheets import SheetsClient

    client = SheetsClient(
        credentials_b64=output_cfg.google_credentials_b64,
        spreadsheet_id=output_cfg.spreadsheet_id,
    )
    client.connect()
    rows = client.read_staging_rows(resolved_sheet_name)

    policies: list[Policy] = []
    invalid_rows: list[int] = []
    for i, row in enumerate(rows):
        row_number = i + 2  # data rows start after the header row
        try:
            policies.append(map_row_to_policy(row, row_number))
        except ValueError as e:
            invalid_rows.append(row_number)
            logger.warning("Skipping invalid Staging row: %s", e)

    store = PolicyStore(data_dir=resolved_data_dir)
    if dry_run:
        existing_urls = {p["url"] for p in store.get_all()}
        seen: set[str] = set()
        imported = 0
        for p in policies:
            if p.url not in existing_urls and p.url not in seen:
                seen.add(p.url)
                imported += 1
    else:
        imported = store.add_policies(policies)

    return ImportSummary(
        rows_read=len(rows),
        imported=imported,
        duplicates=len(policies) - imported,
        invalid=len(invalid_rows),
        invalid_rows=invalid_rows,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed/refresh the local PolicyStore from the Google Sheets "
        "Staging worksheet."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="map and summarize without writing to the store",
    )
    parser.add_argument(
        "--data-dir", default=None,
        help="override the policies.json directory "
        "(default: $OCP_DATA_DIR or 'data')",
    )
    parser.add_argument(
        "--config-dir", default=os.environ.get("OCP_CONFIG_DIR", "config"),
        help="config directory for settings.yaml (default: config)",
    )
    parser.add_argument(
        "--sheet-name", default=None,
        help="Staging worksheet name override "
        "(default: config's output.staging_sheet_name)",
    )
    args = parser.parse_args(argv)

    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

    data_dir = args.data_dir or os.environ.get("OCP_DATA_DIR", "data")

    try:
        summary = import_from_sheet(
            config_dir=args.config_dir,
            data_dir=data_dir,
            sheet_name=args.sheet_name,
            dry_run=args.dry_run,
        )
    except ValueError as e:
        print(str(e))
        return 1

    print(f"Rows read from Staging: {summary.rows_read}")
    print(f"Imported new: {summary.imported}")
    print(f"Duplicates skipped: {summary.duplicates}")
    print(f"Invalid skipped: {summary.invalid}")
    if summary.invalid_rows:
        print(f"Invalid row numbers: {', '.join(str(n) for n in summary.invalid_rows)}")
    if args.dry_run:
        print("(dry run — no changes written to the store)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
