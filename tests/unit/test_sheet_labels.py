"""Tests for turning the reviewer's free-text column into golden labels.

`parse_verdict` and `find_review_header` are pinned against her real
strings (see `tests/fixtures/review_column_2026-09-02.csv`) rather than
invented ones, because the whole point of this module is to survive her
actual vocabulary, not a tidier one.
"""

import csv
import json
from pathlib import Path

import pytest

from src.core.policy_schema import STAGING_HEADERS
from src.core.urls import normalize_url
from src.eval import golden as golden_module
from src.eval.golden import REJECTION_REASONS, GoldenSetError, load_golden
from src.eval.score import evaluate
from src.eval.sheet_labels import (
    CATEGORIES,
    REVIEW_HEADER_TEXT,
    ParsedVerdict,
    _CATEGORY_TO_REJECTION_REASON,
    find_review_header,
    labels_to_golden,
    parse_verdict,
    read_review_labels,
    staging_rows_from_csv_export,
)

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "review_column_2026-09-02.csv"


def _fixture_labels():
    with FIXTURE_PATH.open(newline="", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    return read_review_labels(staging_rows_from_csv_export(csv_rows))


class TestParseVerdict:
    """Twelve-plus of her real strings, verbatim from the fixture."""

    @pytest.mark.small
    @pytest.mark.parametrize(
        "text, verdict, reason_text, categories",
        [
            ("Keep", "keep", "", ()),
            (
                "Keep - implementation of EU's Energy Efficiency Directive",
                "keep", "implementation of EU's Energy Efficiency Directive", (),
            ),
            (
                "Remove - not a policy, also the link does not work",
                "remove", "not a policy, also the link does not work",
                ("not_a_policy_article", "bad_link"),
            ),
            ("Remove - TENs policy", "remove", "TENs policy", ("no_data_centre",)),
            (
                "Remove - no reference to heat reuse",
                "remove", "no reference to heat reuse", ("no_heat_reuse",),
            ),
            (
                "Remove - no reference to data centers",
                "remove", "no reference to data centers", ("no_data_centre",),
            ),
            (
                "Remove - repeat from above",
                "remove", "repeat from above", ("duplicate",),
            ),
            (
                "Remove - news article about a policy already included",
                "remove", "news article about a policy already included",
                ("not_a_policy_article", "duplicate"),
            ),
            (
                "Remove - private sector initiative",
                "remove", "private sector initiative", ("private_initiative",),
            ),
            (
                "Remove - link is an error page",
                "remove", "link is an error page", ("bad_link",),
            ),
            ("Remove", "remove", "", ("unexplained",)),
            ("TBD - only in Dutch", "tbd", "only in Dutch", ("language",)),
            (
                "TBD - requires reporting of waste heat amounts",
                "tbd", "requires reporting of waste heat amounts", ("judgement",),
            ),
            (
                "Not able to access the article",
                "unreachable", "Not able to access the article", (),
            ),
            ("", "blank", "", ()),
        ],
    )
    def test_parse_verdict_table(self, text, verdict, reason_text, categories):
        parsed = parse_verdict(text)
        assert parsed == ParsedVerdict(verdict, reason_text, categories)

    @pytest.mark.small
    def test_case_insensitive_prefix(self):
        assert parse_verdict("keep").verdict == "keep"
        assert parse_verdict("REMOVE - x").verdict == "remove"
        assert parse_verdict("tbd - x").verdict == "tbd"

    @pytest.mark.small
    def test_an_unrecognised_prefix_is_refused(self):
        with pytest.raises(GoldenSetError, match="unrecognised"):
            parse_verdict("Maybe - who knows")

    @pytest.mark.small
    def test_every_category_produced_is_from_the_fixed_list(self):
        """`_categorize_remove` builds its list from a fixed pattern table,
        but the table is hand-edited; a typo there should fail loudly."""
        for label in _fixture_labels():
            assert set(label.categories) <= set(CATEGORIES), label


class TestFindReviewHeader:
    @pytest.mark.small
    def test_finds_the_ac_header_among_the_real_29_headers(self):
        headers = STAGING_HEADERS + [REVIEW_HEADER_TEXT]
        assert len(headers) == 29
        assert find_review_header(headers) == REVIEW_HEADER_TEXT

    @pytest.mark.small
    def test_raises_with_the_header_list_when_absent(self):
        with pytest.raises(GoldenSetError, match="Geographical Area"):
            find_review_header(STAGING_HEADERS)


class TestReadReviewLabels:
    @pytest.mark.small
    def test_url_normalisation_matches_scheme_slash_and_case_variants(self):
        """A label's URL goes through the same normaliser `missing_protected`
        uses on the other side, so a scheme, trailing-slash or case
        difference from the sheet is not a false non-match."""
        canonical = "https://lis.virginia.gov/bill-details/20261/HB323"
        variant = "HTTP://LIS.VIRGINIA.GOV/bill-details/20261/HB323/"
        rows = [{"Link": variant, REVIEW_HEADER_TEXT: "Keep"}]
        labels = read_review_labels(rows)
        assert len(labels) == 1
        assert labels[0].url == normalize_url(canonical)

    @pytest.mark.small
    def test_a_row_with_no_url_is_skipped(self):
        rows = [{"Link": "", REVIEW_HEADER_TEXT: "Keep"}]
        assert read_review_labels(rows) == []

    @pytest.mark.small
    def test_empty_input_is_empty_output(self):
        assert read_review_labels([]) == []

    @pytest.mark.small
    def test_row_numbers_count_from_two(self):
        rows = [
            {"Link": "https://a.gov/1", REVIEW_HEADER_TEXT: "Keep"},
            {"Link": "https://a.gov/2", REVIEW_HEADER_TEXT: "Remove"},
        ]
        labels = read_review_labels(rows)
        assert [label.row_number for label in labels] == [2, 3]


class TestLabelsToGoldenCategoryMapping:
    @pytest.mark.small
    def test_every_rejection_category_maps_to_a_valid_golden_reason(self):
        """WP-1's whole point for REJECTION_REASONS: every category a
        `remove` label can carry must be loadable by `golden.load_golden`,
        or building the set would fail at the last step instead of never."""
        for category, reason in _CATEGORY_TO_REJECTION_REASON.items():
            assert reason in REJECTION_REASONS, f"{category} -> {reason!r}"

    @pytest.mark.small
    def test_a_keep_needs_no_reason(self):
        from src.eval.sheet_labels import ReviewLabel

        labels = [ReviewLabel(url="https://x.gov/a", verdict="keep",
                               categories=(), reason_text="", row_number=2)]
        rows = labels_to_golden(labels, reviewer="r", read_on="2026-09-02")
        assert rows == [{"url": "https://x.gov/a", "keep": True, "reason": "",
                          "labelled_by": "r", "labelled_on": "2026-09-02"}]

    @pytest.mark.small
    def test_tbd_blank_and_unreachable_produce_no_golden_row(self):
        from src.eval.sheet_labels import ReviewLabel

        labels = [
            ReviewLabel(url="https://x.gov/a", verdict="tbd",
                        categories=("judgement",), reason_text="hmm", row_number=2),
            ReviewLabel(url="https://x.gov/b", verdict="blank",
                        categories=(), reason_text="", row_number=3),
            ReviewLabel(url="https://x.gov/c", verdict="unreachable",
                        categories=(), reason_text="Not able to access the article",
                        row_number=4),
        ]
        assert labels_to_golden(labels, reviewer="r", read_on="2026-09-02") == []

    @pytest.mark.small
    def test_sorted_by_row_number_regardless_of_input_order(self):
        from src.eval.sheet_labels import ReviewLabel

        labels = [
            ReviewLabel(url="https://x.gov/b", verdict="keep", categories=(),
                        reason_text="", row_number=9),
            ReviewLabel(url="https://x.gov/a", verdict="keep", categories=(),
                        reason_text="", row_number=2),
        ]
        rows = labels_to_golden(labels, reviewer="r", read_on="2026-09-02")
        assert [row["url"] for row in rows] == ["https://x.gov/a", "https://x.gov/b"]


class TestFixtureIntegration:
    """Fixture CSV -> labels -> golden rows -> load_golden -> evaluate()."""

    @pytest.mark.medium
    def test_full_pipeline_against_the_fixture(self, tmp_path):
        labels = _fixture_labels()
        assert len(labels) == 143  # every row in the fixture carries a Link

        golden_rows = labels_to_golden(labels, reviewer="test reviewer",
                                        read_on="2026-09-02")
        assert len(golden_rows) == 120  # 32 keep + 88 remove; tbd/blank/unreachable excluded

        golden_path = tmp_path / "v1.jsonl"
        golden_path.write_text(
            "\n".join(json.dumps(row) for row in golden_rows) + "\n", encoding="utf-8")
        loaded = load_golden("v1", golden_dir=tmp_path)
        assert len(loaded) == 120

        keep_urls = {item.url for item in loaded if item.keep}
        assert len(keep_urls) == 32
        scores_keeps_only = evaluate(keep_urls, loaded)
        assert scores_keeps_only.precision == pytest.approx(1.0)
        assert scores_keeps_only.recall == pytest.approx(1.0)

        all_decided_urls = {item.url for item in loaded}
        scores_everything = evaluate(all_decided_urls, loaded)
        assert scores_everything.precision == pytest.approx(32 / 120)


class TestCli:
    @pytest.mark.medium
    def test_building_twice_from_csv_is_byte_identical(self, tmp_path):
        out_a = tmp_path / "a.jsonl"
        out_b = tmp_path / "b.jsonl"
        common = [
            "--from-csv", str(FIXTURE_PATH),
            "--reviewer", "workstream reviewer, Staging column AC",
            "--read-on", "2026-09-02",
        ]
        assert golden_module.main([*common, "--out", str(out_a)]) == 0
        assert golden_module.main([*common, "--out", str(out_b)]) == 0
        assert out_a.read_bytes() == out_b.read_bytes()

    @pytest.mark.medium
    def test_dry_run_writes_no_file(self, tmp_path):
        out = tmp_path / "would_not_exist.jsonl"
        rc = golden_module.main(
            ["--from-csv", str(FIXTURE_PATH), "--out", str(out), "--dry-run"])
        assert rc == 0
        assert not out.exists()
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.medium
    def test_out_is_required_without_dry_run(self, tmp_path, capsys):
        rc = golden_module.main(["--from-csv", str(FIXTURE_PATH)])
        assert rc == 1
        assert "--out is required" in capsys.readouterr().err

    @pytest.mark.medium
    def test_from_sheet_parses_arguments_and_reaches_the_credentials_boundary(self):
        """Untested beyond argument parsing, as specified: this only proves
        --from-sheet/--spreadsheet-id are accepted and dispatch correctly.
        No real network call is made - SheetsClient.connect() raises on the
        missing GOOGLE_CREDENTIALS (stripped by tests/conftest.py) before
        anything would be sent. Marked medium rather than small: importing
        the gspread/google-auth stack this path pulls in touches a socket
        object internally (caught, harmless) which small's hard socket
        block would otherwise flag."""
        with pytest.raises(ValueError, match="GOOGLE_CREDENTIALS"):
            golden_module.main(
                ["--from-sheet", "--spreadsheet-id", "abc123", "--dry-run"])

    @pytest.mark.small
    def test_from_csv_and_from_sheet_are_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            golden_module.main(
                ["--from-csv", str(FIXTURE_PATH), "--from-sheet", "--dry-run"])


@pytest.mark.small
def test_a_category_outside_the_closed_vocabulary_is_refused_not_mapped_to_other():
    """CATEGORIES is the closed vocabulary; a label carrying anything else
    means the pattern table and the vocabulary have drifted, which must be
    loud rather than quietly written as "other"."""
    from src.eval.golden import GoldenSetError
    from src.eval.sheet_labels import ReviewLabel, labels_to_golden

    label = ReviewLabel(
        url="https://example.gov/x", verdict="remove", categories=("made_up",),
        reason_text="made up", row_number=2,
    )
    with pytest.raises(GoldenSetError, match="made_up"):
        labels_to_golden([label], reviewer="r", read_on="2026-09-02")

