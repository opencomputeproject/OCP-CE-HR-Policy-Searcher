"""Tests for scripts/build_explorer.py — static read-only policy explorer."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from build_explorer import build_explorer_html, main  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample_policies.json"


@pytest.fixture
def sample_policies():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestBuildExplorerHtml:
    def test_contains_all_policy_names(self, sample_policies):
        html = build_explorer_html(sample_policies)
        # Names are embedded in the JSON data island; every policy must be present
        for p in sample_policies:
            assert json.dumps(p["policy_name"])[1:-1] in html

    def test_output_is_self_contained(self, sample_policies):
        html = build_explorer_html(sample_policies)
        lowered = html.lower()
        assert "<script src=" not in lowered
        assert "https://cdn" not in lowered
        assert 'rel="stylesheet" href="http' not in lowered

    def test_data_island_parses_back_to_input(self, sample_policies):
        html = build_explorer_html(sample_policies)
        start = html.index('<script type="application/json" id="policy-data">')
        start = html.index(">", start) + 1
        end = html.index("</script>", start)
        parsed = json.loads(html[start:end])
        assert parsed == sample_policies

    def test_script_tag_in_policy_data_cannot_break_out(self):
        hostile = [{
            "url": "https://evil.example/x",
            "policy_name": "</script><script>alert(1)</script>",
            "jurisdiction": "Nowhere",
            "policy_type": "law",
            "summary": "hostile summary",
            "relevance_score": 1,
        }]
        html = build_explorer_html(hostile)
        start = html.index('<script type="application/json" id="policy-data">')
        end = html.index("</script>", start)
        island = html[start:end]
        # The raw close tag must not appear inside the data island
        assert "</script>" not in island

    def test_empty_policy_list(self):
        html = build_explorer_html([])
        assert "policy-data" in html
        assert json.loads(
            html.split('id="policy-data">')[1].split("</script>")[0]
        ) == []

    def test_generated_timestamp_present(self, sample_policies):
        html = build_explorer_html(sample_policies, generated_at="2026-07-07T06:00:00Z")
        assert "2026-07-07T06:00:00Z" in html


class TestMain:
    def test_main_writes_output_file(self, tmp_path, sample_policies):
        out = tmp_path / "explorer.html"
        main([str(FIXTURE), str(out)])
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "policy-data" in content
        assert sample_policies[0]["jurisdiction"] in content

    def test_main_rejects_missing_input(self, tmp_path):
        with pytest.raises(SystemExit):
            main([str(tmp_path / "nope.json"), str(tmp_path / "out.html")])
