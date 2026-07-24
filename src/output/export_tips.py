"""Export the tip queue to the Google Sheets "Tips" worksheet.

Usage:
    python -m src.output.export_tips
    python -m src.output.export_tips --data-dir /srv/policypulse/data
    python -m src.output.export_tips --sheet-name TipsStaging

One-way, batch/ops-triggered export (consistent with how policies export
during a scan — see ScanManager), never wired to tip submission itself.
Requires the same GOOGLE_CREDENTIALS / SPREADSHEET_ID configuration as the
policies writer (see README "Google Sheets Setup").
"""

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..core.config import ConfigLoader
from ..storage.leads import LeadStore

logger = logging.getLogger(__name__)

DEFAULT_TIPS_SHEET_NAME = "Tips"


@dataclass
class ExportSummary:
    total_tips: int = 0
    exported: int = 0


def export_tips_to_sheet(
    config_dir: str = "config",
    data_dir: Optional[str] = None,
    sheet_name: Optional[str] = None,
) -> ExportSummary:
    """Read every tip in the queue and rewrite the Tips worksheet from it."""
    config = ConfigLoader(config_dir=config_dir)
    output_cfg = config.settings.output
    if not (output_cfg.spreadsheet_id and output_cfg.google_credentials_b64):
        raise ValueError(
            "Google Sheets is not configured — set GOOGLE_CREDENTIALS and "
            "SPREADSHEET_ID (see README 'Google Sheets Setup')."
        )

    resolved_data_dir = data_dir or config.settings.data_dir
    resolved_sheet_name = sheet_name or DEFAULT_TIPS_SHEET_NAME

    from .sheets import SheetsClient

    client = SheetsClient(
        credentials_b64=output_cfg.google_credentials_b64,
        spreadsheet_id=output_cfg.spreadsheet_id,
    )
    client.connect()

    store = LeadStore(data_dir=resolved_data_dir)
    leads = store.list()
    exported = client.export_tips(leads, resolved_sheet_name)

    return ExportSummary(total_tips=len(leads), exported=exported)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export the tip queue to the Google Sheets Tips worksheet."
    )
    parser.add_argument(
        "--data-dir", default=None,
        help="override the tip queue's data directory "
        "(default: $OCP_DATA_DIR or 'data')",
    )
    parser.add_argument(
        "--config-dir", default=os.environ.get("OCP_CONFIG_DIR", "config"),
        help="config directory for settings.yaml (default: config)",
    )
    parser.add_argument(
        "--sheet-name", default=None,
        help=f"Tips worksheet name override (default: '{DEFAULT_TIPS_SHEET_NAME}')",
    )
    args = parser.parse_args(argv)

    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

    data_dir = args.data_dir or os.environ.get("OCP_DATA_DIR", "data")

    try:
        summary = export_tips_to_sheet(
            config_dir=args.config_dir, data_dir=data_dir, sheet_name=args.sheet_name,
        )
    except ValueError as e:
        print(str(e))
        return 1

    print(f"Tips in queue: {summary.total_tips}")
    print(f"Exported to sheet: {summary.exported}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
