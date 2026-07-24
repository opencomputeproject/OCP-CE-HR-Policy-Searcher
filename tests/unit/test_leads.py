"""Tests for the lead queue store."""

import pytest

from src.storage.leads import Lead, LeadStore


@pytest.fixture
def store(tmp_path):
    return LeadStore(data_dir=str(tmp_path))


def _lead(url="https://news.example/article", title="Denmark heat mandate"):
    return Lead(title=title, source_url=url)


class TestLeadStore:
    def test_add_and_list(self, store):
        added = store.add_leads([_lead()])
        assert added == 1
        leads = store.list()
        assert len(leads) == 1
        assert leads[0].status == "new"

    def test_dedupes_by_source_url(self, store):
        store.add_leads([_lead()])
        added = store.add_leads([_lead(title="Same URL again")])
        assert added == 0
        assert len(store.list()) == 1

    def test_persistence_roundtrip(self, tmp_path):
        store = LeadStore(data_dir=str(tmp_path))
        store.add_leads([_lead()])
        reloaded = LeadStore(data_dir=str(tmp_path))
        assert len(reloaded.list()) == 1

    def test_update_status_and_filter(self, store):
        lead = _lead()
        store.add_leads([lead])
        store.update_status(lead.lead_id, "dismissed")
        assert store.list(status="new") == []
        assert len(store.list(status="dismissed")) == 1

    def test_chase_records_policy_url(self, store):
        lead = _lead()
        store.add_leads([lead])
        updated = store.update_status(
            lead.lead_id, "chased", policy_url="https://gov.example/law",
        )
        assert updated.policy_url == "https://gov.example/law"

    def test_invalid_status_rejected(self, store):
        lead = _lead()
        store.add_leads([lead])
        with pytest.raises(ValueError):
            store.update_status(lead.lead_id, "bogus")

    def test_unknown_lead_returns_none(self, store):
        assert store.update_status("nope", "dismissed") is None

    def test_corrupt_file_backed_up(self, tmp_path):
        (tmp_path / "leads.json").write_text("not json", encoding="utf-8")
        store = LeadStore(data_dir=str(tmp_path))
        assert store.list() == []
        assert (tmp_path / "leads.json.corrupt").exists()


class TestNoteOnlyLeadDedupe:
    """Note-only leads (no URL) must not collide on an empty source_url."""

    def _note_lead(self, title, snippet):
        return Lead(title=title, source_url="", snippet=snippet)

    def test_source_url_defaults_to_empty_string(self):
        lead = Lead(title="t")
        assert lead.source_url == ""

    def test_distinct_note_only_leads_both_added(self, store):
        added = store.add_leads([
            self._note_lead("Rumor A", "First rumor"),
            self._note_lead("Rumor B", "Second, unrelated rumor"),
        ])
        assert added == 2
        assert len(store.list()) == 2

    def test_identical_note_text_dedupes(self, store):
        store.add_leads([self._note_lead("Rumor", "Same text")])
        added = store.add_leads([self._note_lead("Rumor again", "Same text")])
        assert added == 0
        assert len(store.list()) == 1

    def test_note_only_lead_does_not_collide_with_url_lead(self, store):
        store.add_leads([_lead()])  # has a real source_url
        added = store.add_leads([self._note_lead("Rumor", "Some note")])
        assert added == 1
        assert len(store.list()) == 2
