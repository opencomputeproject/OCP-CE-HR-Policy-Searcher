"""Tests for src.orchestration.funnel (WP-6a) - pure counter-to-sentence
formatting for a scan's per-stage funnel.
"""

import pytest

from src.orchestration.funnel import funnel_sentences


@pytest.mark.small
class TestFunnelSentences:
    def test_empty_totals_gives_empty_list(self):
        assert funnel_sentences({}) == []

    def test_all_zero_totals_gives_empty_list(self):
        totals = {"pages_crawled": 0, "filtered_out_of_scope": 0, "policies_found": 0}
        assert funnel_sentences(totals) == []

    def test_zero_stages_are_skipped_not_shown_as_zero(self):
        totals = {
            "pages_crawled": 100,
            "filtered_short_content": 0,
            "filtered_out_of_scope": 40,
            "policies_found": 5,
        }
        sentences = funnel_sentences(totals)
        assert not any(s.startswith("0 ") for s in sentences)
        assert len(sentences) == 3

    def test_sentences_come_back_in_pipeline_order(self):
        # Deliberately inserted out of pipeline order - the output must
        # still follow the pipeline, not dict insertion order.
        totals = {
            "policies_found": 71,
            "pages_crawled": 35402,
            "analysis_calls": 445,
            "filtered_out_of_scope": 7909,
            "screening_calls": 636,
        }
        sentences = funnel_sentences(totals)
        assert sentences == [
            "35,402 pages fetched",
            "7,909 dropped for no data-centre mention, free",
            "636 screened by the cheap model",
            "445 analysed by the strong model",
            "71 policies found",
        ]

    def test_thousands_separators_on_large_numbers(self):
        sentences = funnel_sentences({"pages_crawled": 1234567})
        assert sentences == ["1,234,567 pages fetched"]

    def test_small_numbers_have_no_separator_and_read_naturally(self):
        sentences = funnel_sentences({"policies_found": 7})
        assert sentences == ["7 policies found"]

    def test_unrecognized_keys_are_ignored(self):
        sentences = funnel_sentences({"not_a_real_stage": 999, "policies_found": 2})
        assert sentences == ["2 policies found"]

    def test_missing_key_behaves_like_zero(self):
        # A totals dict that simply never mentions a stage is exactly as
        # valid as one that mentions it at 0 - both are skipped.
        assert funnel_sentences({"pages_crawled": 10}) == ["10 pages fetched"]

    def test_the_new_wp6a_counters_have_sentences(self):
        totals = {
            "filtered_doc_type": 3,
            "filtered_link": 4,
            "screened_kind": 5,
            "filtered_duplicate": 6,
        }
        sentences = funnel_sentences(totals)
        assert len(sentences) == 4
        assert all(str(n) in " ".join(sentences) for n in (3, 4, 5, 6))
