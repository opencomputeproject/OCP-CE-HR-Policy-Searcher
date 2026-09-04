"""One-way import of the reviewer's verdicts into the PolicyStore (WP-2).

ADR-0005 (proposed, not yet accepted): her column on the Staging sheet is
the review record, but nothing reads it. This module is the one-way import
that does: it reads her column (via ``src.eval.sheet_labels``, the same
parser the golden set uses) and updates each matching policy's review
status - ``keep`` becomes ``output.review_keep_status`` ("reviewed" by
default), ``remove`` becomes ``rejected`` with her reason stored as the
review note, and ``tbd``/blank/unreachable rows are left untouched, since
none of those is yet a decision.

The app never writes into her column - this is read-only against the
sheet, write-only against the store. Idempotent: re-running against an
unchanged column and an already-updated store changes nothing (see
``plan_import``).

Usage::

    python -m src.output.import_reviews --dry-run              # preview
    python -m src.output.import_reviews                        # apply
    python -m src.output.import_reviews --from-csv PATH         # no network
    python -m src.output.import_reviews --keep-as promoted
    python -m src.output.import_reviews --add-reason-column     # one-shot

Shaped after ``src.output.import_sheet`` (the existing sheet-to-store
import): same env handling (``.env`` loaded in ``main``, ``OCP_DATA_DIR``/
``OCP_CONFIG_DIR`` overrides), same "not configured" error text.
"""

import argparse
import csv
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..core.config import ConfigLoader
from ..core.log_setup import log_audit_event
from ..core.urls import normalize_url
from ..eval.sheet_labels import ReviewLabel, read_review_labels, staging_rows_from_csv_export
from ..storage.store import PolicyStore

logger = logging.getLogger(__name__)

# Recorded on every review_imported audit line so a status change that came
# from her column is never confused with one a person made in the app. She
# is not named in source (see docs/HOW_IT_WORKS.md's "the reviewer" voice);
# `source` says the mechanism, `reviewer` says the role.
REVIEWER = "reviewer"
SOURCE = "sheet column AC"

# A `remove` with no reason (her "No reason given" rows, see
# docs/HOW_IT_WORKS.md "The reviewer's vocabulary") still needs a note - it
# is what tells the row apart from an app-set rejection carrying none.
NO_REASON_GIVEN = "reviewer: no reason given"

# Statuses a `keep` verdict may map to (output.review_keep_status).
_DEFAULT_KEEP_STATUS = "reviewed"


@dataclass(frozen=True)
class Change:
    """One row's review status moving from what the store has to what her
    column says it should be. ``note`` is None for a ``keep`` (any stale
    rejection note is cleared); a ``remove`` always carries one - her
    reason, or ``NO_REASON_GIVEN``."""

    url: str
    from_status: str
    to_status: str
    note: Optional[str]


@dataclass
class ImportSummary:
    changed: int = 0
    unchanged: int = 0
    unmatched: int = 0
    tbd: int = 0
    blank: int = 0
    unreachable: int = 0
    changes: list = field(default_factory=list)  # up to 10 Changes, for display


def plan_import(
    labels: list[ReviewLabel],
    existing_policies: list[dict],
    keep_status: str = _DEFAULT_KEEP_STATUS,
) -> list[Change]:
    """What would change if ``labels`` were applied to ``existing_policies``.

    Pure: no store, no network, so both ``import_reviews`` and a test can
    reason about it directly. Only ``keep``/``remove`` labels that match a
    stored URL ever produce a ``Change`` - a ``tbd``/blank/unreachable
    verdict, a URL not in ``existing_policies``, or a row already at its
    target status with the same note, all produce none. ``promoted`` is
    never downgraded to ``keep_status``: a row a person already promoted
    stays promoted whatever a later ``keep`` verdict maps to.

    Matching is by ``normalize_url`` (the same normalisation
    ``read_review_labels`` already applied to ``label.url``), so a trailing
    slash or scheme difference between the sheet and the store is not a
    false miss - but the ``Change`` carries the URL exactly as stored, so
    ``PolicyStore.update_review_status``'s exact match still hits it.
    """
    by_normalized_url = {
        normalize_url(policy.get("url") or ""): policy for policy in existing_policies
    }
    changes: list[Change] = []
    for label in labels:
        if label.verdict not in ("keep", "remove"):
            continue
        policy = by_normalized_url.get(label.url)
        if policy is None:
            continue

        current_status = policy.get("review_status") or "new"
        current_note = policy.get("review_note") or None

        if label.verdict == "keep":
            target_status = "promoted" if current_status == "promoted" else keep_status
            target_note = None
        else:
            target_status = "rejected"
            target_note = label.reason_text or NO_REASON_GIVEN

        if current_status == target_status and current_note == target_note:
            continue

        changes.append(Change(
            url=policy.get("url") or "",
            from_status=current_status,
            to_status=target_status,
            note=target_note,
        ))
    return changes


def apply_import(
    store: PolicyStore, changes: list[Change], data_dir: str, reviewer: str = REVIEWER,
) -> int:
    """Write every change to ``store`` and leave one ``review_imported``
    audit line per change - the app's own record that a status change
    reflects her column, not a person acting in the app. Returns the count
    written (== ``len(changes)``)."""
    for change in changes:
        store.update_review_status(change.url, change.to_status, change.note)
        log_audit_event(
            data_dir=data_dir, event="review_imported",
            url=change.url, from_status=change.from_status, to_status=change.to_status,
            reviewer=reviewer, source=SOURCE,
        )
    return len(changes)


def _rows_from_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    return staging_rows_from_csv_export(csv_rows)


def import_reviews(
    config: ConfigLoader,
    store: PolicyStore,
    *,
    dry_run: bool,
    from_csv: Optional[str] = None,
    spreadsheet_id: Optional[str] = None,
    keep_status: Optional[str] = None,
) -> ImportSummary:
    """Read the reviewer's column and bring ``store``'s review status in
    line with it (ADR-0005). Sheet path (when ``from_csv`` is not given):
    ``SheetsClient(credentials, review_spreadsheet_id or spreadsheet_id)
    .read_staging_rows()``, then ``read_review_labels``.

    ``dry_run`` reports the same counts a real run would, previewing up to
    ten changes, and writes nothing - not to the store, not to the audit
    log. Raises ``ValueError`` if neither ``from_csv`` nor a configured
    sheet (credentials + a resolved spreadsheet id) is available.
    """
    output_cfg = config.settings.output
    resolved_keep_status = keep_status or output_cfg.review_keep_status

    if from_csv:
        rows = _rows_from_csv(from_csv)
    else:
        sheet_id = (
            spreadsheet_id or output_cfg.review_spreadsheet_id or output_cfg.spreadsheet_id
        )
        if not (sheet_id and output_cfg.google_credentials_b64):
            raise ValueError(
                "Google Sheets is not configured - set GOOGLE_CREDENTIALS and "
                "SPREADSHEET_ID (see README 'Google Sheets Setup'), or pass --from-csv."
            )
        from .sheets import SheetsClient

        client = SheetsClient(
            credentials_b64=output_cfg.google_credentials_b64, spreadsheet_id=sheet_id,
        )
        client.connect()
        rows = client.read_staging_rows(output_cfg.staging_sheet_name)

    labels = read_review_labels(rows)
    existing_policies = store.get_all()
    by_normalized_url = {
        normalize_url(policy.get("url") or ""): policy for policy in existing_policies
    }

    tbd = sum(1 for label in labels if label.verdict == "tbd")
    blank = sum(1 for label in labels if label.verdict == "blank")
    unreachable = sum(1 for label in labels if label.verdict == "unreachable")
    decidable = [label for label in labels if label.verdict in ("keep", "remove")]
    unmatched = sum(1 for label in decidable if label.url not in by_normalized_url)

    changes = plan_import(labels, existing_policies, resolved_keep_status)

    if not dry_run:
        apply_import(store, changes, data_dir=str(store.data_dir))

    return ImportSummary(
        changed=len(changes),
        unchanged=len(decidable) - unmatched - len(changes),
        unmatched=unmatched,
        tbd=tbd,
        blank=blank,
        unreachable=unreachable,
        changes=changes[:10],
    )


def _run_add_reason_column(config: ConfigLoader, spreadsheet_id: Optional[str]) -> int:
    """``--add-reason-column``: append the fixed-dropdown Reason column to
    Staging and exit. Never called from the schedule - explicit, one-shot,
    admin-run only."""
    output_cfg = config.settings.output
    sheet_id = spreadsheet_id or output_cfg.review_spreadsheet_id or output_cfg.spreadsheet_id
    if not (sheet_id and output_cfg.google_credentials_b64):
        print(
            "Google Sheets is not configured - set GOOGLE_CREDENTIALS and "
            "SPREADSHEET_ID (see README 'Google Sheets Setup')."
        )
        return 1

    from .sheets import SheetsClient

    client = SheetsClient(credentials_b64=output_cfg.google_credentials_b64, spreadsheet_id=sheet_id)
    client.connect()
    added = client.add_reason_column(sheet_name=output_cfg.staging_sheet_name)
    if added:
        print(f"Added the Reason column to {output_cfg.staging_sheet_name!r}.")
    else:
        print(
            f"The Reason column already exists on {output_cfg.staging_sheet_name!r}; "
            "nothing changed."
        )
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import the reviewer's verdicts (Staging sheet column AC) "
        "into the PolicyStore's review status (ADR-0005, proposed)."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report what would change without writing to the store or the audit log",
    )
    parser.add_argument(
        "--from-csv", default=None,
        help="read her column from a CSV export instead of the live sheet "
        "(row,country,name,link,discovered_at,review_status,anna_review)",
    )
    parser.add_argument(
        "--spreadsheet-id", default=None,
        help="override the sheet id (default: output.review_spreadsheet_id, "
        "falling back to output.spreadsheet_id)",
    )
    parser.add_argument(
        "--keep-as", choices=["reviewed", "promoted"], default=None,
        help="status a 'keep' verdict maps to (default: output.review_keep_status)",
    )
    parser.add_argument(
        "--data-dir", default=None,
        help="override the policies/policypulse.db directory "
        "(default: $OCP_DATA_DIR or 'data')",
    )
    parser.add_argument(
        "--config-dir", default=os.environ.get("OCP_CONFIG_DIR", "config"),
        help="config directory for settings.yaml (default: config)",
    )
    parser.add_argument(
        "--add-reason-column", action="store_true",
        help="one-shot: append the fixed-dropdown Reason column to Staging and exit "
        "(never run automatically)",
    )
    args = parser.parse_args(argv)

    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

    config = ConfigLoader(config_dir=args.config_dir)

    if args.add_reason_column:
        return _run_add_reason_column(config, spreadsheet_id=args.spreadsheet_id)

    data_dir = args.data_dir or os.environ.get("OCP_DATA_DIR", "data")
    store = PolicyStore(data_dir=data_dir)

    try:
        summary = import_reviews(
            config, store, dry_run=args.dry_run, from_csv=args.from_csv,
            spreadsheet_id=args.spreadsheet_id, keep_status=args.keep_as,
        )
    except ValueError as e:
        print(str(e))
        return 1

    verb = "would change" if args.dry_run else "changed"
    print(f"{verb} {summary.changed} rows")
    print(f"unchanged: {summary.unchanged}")
    print(f"unmatched: {summary.unmatched}")
    print(f"tbd: {summary.tbd}")
    print(f"blank: {summary.blank}")
    print(f"unreachable: {summary.unreachable}")
    for change in summary.changes[:10]:
        print(f"  {change.url}: {change.from_status} -> {change.to_status} ({change.note or ''})")
    if args.dry_run:
        print("(dry run - no changes written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
