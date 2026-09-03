"""Replay the WP-5 screening gate against real recorded pages and real
model answers.

The integrator records these fixtures once the final prompt is settled -
see the work package plan, piece 6. Until then, the two real replay tests
below must FAIL LOUDLY, never skip: a safety net that quietly shows green
while empty is worse than one that is visibly absent. The meta-tests at the
bottom pin that failure behavior in isolation, independent of whether the
real fixtures happen to exist yet.

Fixture shape (confirmed with the integrator):

- ``tests/fixtures/screening/index.json``: a list of row dicts - ``slug``,
  ``row``, ``url``, ``verdict`` (``"keep"``/``"remove"``), ``reason`` (a
  short category slug, e.g. ``"not_a_policy_article"``, not free text),
  ``reason_text``, ``chars``, ``fetch``, ``fetched_at``, ``usable`` (bool),
  and ``why_unusable`` (present only when ``usable`` is false).
- ``tests/fixtures/screening/responses.json``: ``{"recorded_at", "model",
  "prompt_sha256_12", "scope_setting", "responses": {slug: raw model
  text}}``. ``prompt_sha256_12`` pins the recording to the exact
  CLASSIFY_PROMPT it was made against - see _check_prompt_hash below.

Only rows with ``usable`` true AND a recorded response are decidable; a
row that failed to fetch, or that the recording run could not get an
answer for, carries no evidence either way and is excluded from both bars.
"""

import hashlib
import json
from pathlib import Path

import pytest

from src.core.llm import CLASSIFY_PROMPT, parse_screening_json
from src.core.models import DEFAULT_SCREENER_REJECT_KINDS, DEFAULT_SCREENER_SOFT_REJECT_KINDS
from src.core.scanner import screening_decision
from src.core.scope import REQUIRED

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "screening"

NOT_RECORDED = (
    "Screening replay fixtures not found at {dir}. The integrator has not "
    "recorded them yet (see the WP-5 plan, piece 6: tests/fixtures/screening/"
    "index.json and responses.json, real pages and real model answers). This "
    "is a missing safety net, not something to skip past."
)

STALE_PROMPT = (
    "tests/fixtures/screening/responses.json was recorded against a "
    "different CLASSIFY_PROMPT (recorded {recorded!r}, current {current!r}). "
    "Re-run scripts/record_screening_responses.py."
)

# Matches config/settings.yaml's analysis.screener_reject_kinds default and
# the AnalysisSettings.screening_min_confidence default (5) - the replay
# runs the gate exactly as production would with an unmodified config.
REJECT_KINDS = list(DEFAULT_SCREENER_REJECT_KINDS)
SOFT_REJECT_KINDS = list(DEFAULT_SCREENER_SOFT_REJECT_KINDS)
MIN_CONFIDENCE = 5

# The reason category the "not a policy: report, article, opinion, private
# initiative" reviewer removals are recorded under (docs/HOW_IT_WORKS.md,
# "The reviewer's vocabulary").
NOT_A_POLICY_ARTICLE = "not_a_policy_article"


def _load_fixtures() -> tuple[list[dict], dict]:
    """index.json and the full parsed responses.json object from
    FIXTURES_DIR.

    Raises AssertionError - never skips - when either file is missing. A
    plain assert makes this catchable with pytest.raises for the meta-tests
    below, using the exact same function the real replay tests call.
    """
    index_path = FIXTURES_DIR / "index.json"
    responses_path = FIXTURES_DIR / "responses.json"
    if not index_path.exists() or not responses_path.exists():
        raise AssertionError(NOT_RECORDED.format(dir=FIXTURES_DIR))
    index = json.loads(index_path.read_text(encoding="utf-8"))
    responses = json.loads(responses_path.read_text(encoding="utf-8"))
    return index, responses


def _current_prompt_hash() -> str:
    return hashlib.sha256(CLASSIFY_PROMPT.encode("utf-8")).hexdigest()[:12]


def _check_prompt_hash(responses: dict) -> None:
    """The recording must have been made against the prompt now in force.

    A recording made before a later prompt edit would silently validate a
    gate that no longer matches what production actually asks the model,
    so this must fail loudly rather than pass on stale evidence.
    """
    recorded = responses.get("prompt_sha256_12")
    current = _current_prompt_hash()
    if recorded != current:
        raise AssertionError(STALE_PROMPT.format(recorded=recorded, current=current))


def _decidable_rows(index: list[dict], responses: dict) -> tuple[list[dict], dict]:
    """Usable rows with a recorded response - the only ones with evidence
    either way. answered is the slug -> raw model text map."""
    answered = responses.get("responses", {})
    decidable = [
        row for row in index
        if row.get("usable") and row.get("slug") in answered
    ]
    return decidable, answered


def _decide(answered: dict, slug: str, scope_setting: str) -> str:
    result = parse_screening_json(answered[slug])
    return screening_decision(result, REJECT_KINDS, SOFT_REJECT_KINDS)


@pytest.mark.small
class TestReplayAgainstRecordedFixtures:
    """FAILS TODAY, and until the integrator records the fixtures (see the
    module docstring) - this is expected, not a bug to chase."""

    def test_every_reviewer_keep_survives_the_gate(self):
        """Zero lost keeps: every usable, answered row she kept must reach
        analysis (proceed or escalate), never drop_kind or drop_no_dc."""
        index, responses = _load_fixtures()
        _check_prompt_hash(responses)
        decidable, answered = _decidable_rows(index, responses)
        scope_setting = responses.get("scope_setting", REQUIRED)

        keeps = [row for row in decidable if row["verdict"] == "keep"]
        assert keeps, "no usable, answered keep rows in the fixture index"

        lost = [
            (row["slug"], _decide(answered, row["slug"], scope_setting))
            for row in keeps
        ]
        lost = [(slug, decision) for slug, decision in lost
                if decision not in ("proceed", "escalate")]
        assert not lost, f"Reviewer keeps lost at screening: {lost}"

    def test_soft_kinds_drop_without_evidence_and_escalate_with_it(self):
        """Reports and articles she removed: without a quoted data-centre or
        heat-reuse sentence they drop at the screener; with one they go to
        the strong model, which is what protects the kept agency pages and
        press release that came back with the same labels."""
        index, responses = _load_fixtures()
        _check_prompt_hash(responses)
        decidable, answered = _decidable_rows(index, responses)
        scope_setting = responses.get("scope_setting", REQUIRED)

        dropped, escalated, wrong = [], [], []
        for row in decidable:
            if row["verdict"] != "remove":
                continue
            result = parse_screening_json(answered[row["slug"]])
            if result.kind not in SOFT_REJECT_KINDS:
                continue
            decision = _decide(answered, row["slug"], scope_setting)
            has_evidence = bool(result.dc_quote or result.heat_quote)
            expected = "escalate" if has_evidence else "drop_kind"
            (escalated if has_evidence else dropped).append(row["slug"])
            if decision != expected:
                wrong.append((row["slug"], result.kind, has_evidence, decision))
        assert dropped or escalated, "no removed report/article rows in the recording"
        assert not wrong, f"soft-kind rows decided against the rule: {wrong}"

    def test_matching_hash_does_not_raise(self):
        assert _check_prompt_hash({"prompt_sha256_12": _current_prompt_hash()}) is None

    def test_mismatched_hash_raises_with_the_rerun_instruction(self):
        with pytest.raises(AssertionError, match="record_screening_responses"):
            _check_prompt_hash({"prompt_sha256_12": "0" * 12})

    def test_missing_hash_key_raises(self):
        with pytest.raises(AssertionError, match="record_screening_responses"):
            _check_prompt_hash({})


@pytest.mark.small
class TestDecidableRowsFiltering:
    """Only usable, answered rows carry evidence either way."""

    def test_unusable_row_is_excluded_even_with_a_response(self):
        index = [{"slug": "a", "verdict": "keep", "usable": False}]
        responses = {"responses": {"a": '{"kind": "act"}'}}
        decidable, _ = _decidable_rows(index, responses)
        assert decidable == []

    def test_usable_row_with_no_recorded_response_is_excluded(self):
        index = [{"slug": "b", "verdict": "keep", "usable": True}]
        responses = {"responses": {}}
        decidable, _ = _decidable_rows(index, responses)
        assert decidable == []

    def test_usable_answered_row_is_included(self):
        index = [{"slug": "c", "verdict": "keep", "usable": True}]
        responses = {"responses": {"c": '{"kind": "act"}'}}
        decidable, answered = _decidable_rows(index, responses)
        assert decidable == index
        assert answered == {"c": '{"kind": "act"}'}


@pytest.mark.small
class TestFixtureAbsenceFailsLoudly:
    """Pins the "fail loudly, never skip" contract in isolation, using
    tmp_path and a monkeypatched FIXTURES_DIR rather than depending on
    whether the real fixtures directory happens to exist yet."""

    def test_both_files_missing_raises_with_the_not_recorded_message(
        self, tmp_path, monkeypatch,
    ):
        empty_dir = tmp_path / "screening"
        empty_dir.mkdir()
        monkeypatch.setattr(
            "tests.unit.test_screening_replay.FIXTURES_DIR", empty_dir,
        )
        with pytest.raises(AssertionError, match="not recorded"):
            _load_fixtures()

    def test_only_responses_file_missing_still_raises(self, tmp_path, monkeypatch):
        """Also proves this is a real failure (AssertionError), never a
        pytest.skip - a skip would let a hollowed-out safety net report
        the suite green."""
        partial_dir = tmp_path / "screening"
        partial_dir.mkdir()
        (partial_dir / "index.json").write_text("[]", encoding="utf-8")
        monkeypatch.setattr(
            "tests.unit.test_screening_replay.FIXTURES_DIR", partial_dir,
        )
        with pytest.raises(AssertionError, match="not recorded"):
            _load_fixtures()

    def test_both_files_present_does_not_raise(self, tmp_path, monkeypatch):
        present_dir = tmp_path / "screening"
        present_dir.mkdir()
        (present_dir / "index.json").write_text("[]", encoding="utf-8")
        (present_dir / "responses.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(
            "tests.unit.test_screening_replay.FIXTURES_DIR", present_dir,
        )
        index, responses = _load_fixtures()
        assert index == []
        assert responses == {}
