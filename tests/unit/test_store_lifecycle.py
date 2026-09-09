"""Every store owns its connection and closes it (lesson PL-012).

Until 2026-09-08 no store had a close(); a store built for one call left
its sqlite3 connection to the garbage collector, which emitted 3,139
ResourceWarnings per suite run and closed the app's connections whenever it
got around to it.
"""

import gc
import sqlite3
import warnings

import pytest

from src.storage.domain_overrides import DomainOverridesStore
from src.storage.keyword_overrides import KeywordOverridesStore
from src.storage.leads import LeadStore
from src.storage.notifications import NotificationStateStore, NotificationSubscriptionsStore
from src.storage.public_visibility import PublicVisibilityStore
from src.storage.scan_history import ScanHistoryStore
from src.storage.schedules import SchedulesStore
from src.storage.signals_status import SignalsStatusStore
from src.storage.store import PolicyStore

STORES = [
    PolicyStore, LeadStore, ScanHistoryStore, SchedulesStore, PublicVisibilityStore,
    SignalsStatusStore, NotificationSubscriptionsStore, NotificationStateStore,
    DomainOverridesStore, KeywordOverridesStore,
]


class TestEveryStoreOwnsItsConnection:
    @pytest.mark.medium
    @pytest.mark.parametrize("cls", STORES, ids=lambda c: c.__name__)
    def test_close_closes_and_a_closed_store_says_so(self, cls, tmp_path):
        store = cls(data_dir=str(tmp_path))
        assert not store.closed
        store.close()
        assert store.closed
        with pytest.raises(sqlite3.ProgrammingError):
            store._conn.execute("SELECT 1")
        store.close()  # idempotent

    @pytest.mark.medium
    @pytest.mark.parametrize("cls", STORES, ids=lambda c: c.__name__)
    def test_a_store_used_as_a_context_manager_leaves_nothing_for_the_collector(
        self, cls, tmp_path,
    ):
        """FAILS ON OLD BEHAVIOUR: with no close(), dropping the store makes
        the collector close the connection and warn."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with cls(data_dir=str(tmp_path)) as store:
                assert store is not None
            del store
            gc.collect()
        leaks = [w for w in caught if issubclass(w.category, ResourceWarning)]
        assert leaks == [], [str(w.message) for w in leaks]


class TestTheLongLivedOwnersClose:
    @pytest.mark.medium
    def test_the_scan_manager_builds_one_policy_store_and_closes_it(self, tmp_path):
        from unittest.mock import MagicMock

        from src.orchestration.scan_manager import ScanManager

        manager = ScanManager(config=MagicMock(), broadcaster=MagicMock(), data_dir=str(tmp_path))
        assert manager._own_policy_store is None  # lazy: constructing a manager opens nothing
        first = manager.policy_store()
        assert manager.policy_store() is first
        history = manager.history_store()
        manager.close()
        assert first.closed and history.closed
        assert manager.policy_store() is not first  # a fresh one after close

    @pytest.mark.medium
    def test_deps_close_stores_closes_every_cached_store(self, tmp_path, monkeypatch):
        from src.api import deps

        monkeypatch.setenv("OCP_DATA_DIR", str(tmp_path))
        deps.close_stores()  # start clean, whatever earlier tests cached
        opened = [getter() for getter in deps._STORE_GETTERS if getter is not deps.get_mailer]
        assert all(not s.closed for s in opened)
        deps.close_stores()
        assert all(s.closed for s in opened)
        assert deps.get_policy_store() is not opened[0]

    @pytest.mark.medium
    def test_the_digest_tick_closes_the_stores_it_builds(self, tmp_path, monkeypatch):
        from src.notifications import digest

        seen = {}

        def fake_tick(subscriptions, state, mailer, policies, signals, history, now=None):
            seen.update(subscriptions=subscriptions, state=state, mailer=mailer,
                        policies=policies, signals=signals, history=history)
            assert not any(s.closed for s in (subscriptions, state, policies, signals, history))

        monkeypatch.setattr(digest, "run_digest_tick", fake_tick)
        digest.run_digest_tick_for_data_dir(data_dir=str(tmp_path))
        assert seen, "the tick did not run"
        for name in ("subscriptions", "state", "policies", "signals", "history"):
            assert seen[name].closed, name
        assert seen["mailer"]._state.closed
