"""Tests for FastAPI API routes."""

from unittest.mock import MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.core.models import Policy, PolicyType, ScanJob, ScanStatus, ScanProgress


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.domains_config = {
        "domains": [
            {
                "id": "test_gov",
                "name": "Test Gov",
                "base_url": "https://test.gov",
                "enabled": True,
                "region": ["us"],
                "category": "government",
                "tags": ["energy"],
            },
        ],
    }
    config.list_domains.return_value = config.domains_config["domains"]
    config.get_enabled_domains.return_value = config.domains_config["domains"]
    config.list_groups.return_value = {"groups": {"quick": ["test_gov"]}}
    config.list_regions.return_value = ["us"]
    config.list_categories.return_value = ["government"]
    config.list_tags.return_value = ["energy"]
    return config


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.get_all.return_value = []
    store.search.return_value = []
    store.get_stats.return_value = {
        "total": 0,
        "by_jurisdiction": {},
        "by_type": {},
        "by_score_range": {"1-3": 0, "4-6": 0, "7-8": 0, "9-10": 0},
        "flagged_count": 0,
    }
    return store


@pytest.fixture
def mock_manager():
    manager = MagicMock()
    manager.jobs = {}
    manager.get_all_policies.return_value = []
    manager.get_policies.return_value = []
    return manager


@pytest.fixture
def mock_broadcaster():
    return MagicMock()


@pytest.fixture
def client(mock_config, mock_store, mock_manager, mock_broadcaster):
    from src.api.app import app
    from src.api import deps

    app.dependency_overrides[deps.get_config] = lambda: mock_config
    app.dependency_overrides[deps.get_policy_store] = lambda: mock_store
    app.dependency_overrides[deps.get_scan_manager] = lambda: mock_manager
    app.dependency_overrides[deps.get_broadcaster] = lambda: mock_broadcaster

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


# --- Root & Health ---

class TestRootAndHealth:
    def test_root(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "OCP CE HR Policy Searcher"
        assert "endpoints" in data

    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


# --- Domains ---

class TestDomainRoutes:
    def test_list_domains(self, client):
        response = client.get("/api/domains")
        assert response.status_code == 200
        data = response.json()
        assert "domains" in data
        assert data["count"] == 1
        assert data["domains"][0]["id"] == "test_gov"

    def test_list_domains_with_group_filter(self, client, mock_config):
        response = client.get("/api/domains?group=quick")
        assert response.status_code == 200
        mock_config.get_enabled_domains.assert_called_with("quick")

    def test_list_domains_with_category_filter(self, client, mock_config):
        response = client.get("/api/domains?category=government")
        assert response.status_code == 200

    def test_list_groups(self, client):
        response = client.get("/api/groups")
        assert response.status_code == 200

    def test_list_regions(self, client):
        response = client.get("/api/regions")
        assert response.status_code == 200

    def test_list_categories(self, client):
        response = client.get("/api/categories")
        assert response.status_code == 200

    def test_list_tags(self, client):
        response = client.get("/api/tags")
        assert response.status_code == 200

    def test_get_domain_not_found(self, client):
        response = client.get("/api/domains/nonexistent_domain")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "nonexistent_domain" in data["detail"]

    def test_list_domains_invalid_group(self, client, mock_config):
        from src.core.config import ConfigurationError
        mock_config.get_enabled_domains.side_effect = ConfigurationError(
            "Unknown group/region/domain: 'bogus'"
        )
        response = client.get("/api/domains?group=bogus")
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "bogus" in data["detail"]


# --- Policies ---

class TestPolicyRoutes:
    def test_list_policies_empty(self, client):
        response = client.get("/api/policies")
        assert response.status_code == 200
        data = response.json()
        assert data["policies"] == []
        assert data["count"] == 0

    def test_list_policies_with_store_data(self, client, mock_store):
        mock_store.search.return_value = [
            {"url": "https://a.gov/p1", "policy_name": "P1", "jurisdiction": "US"},
        ]
        response = client.get("/api/policies")
        data = response.json()
        assert data["count"] == 1

    def test_list_policies_merges_in_memory(self, client, mock_manager):
        mock_manager.get_all_policies.return_value = [
            Policy(
                url="https://b.gov/p2",
                policy_name="P2",
                jurisdiction="DE",
                policy_type=PolicyType.LAW,
                summary="Test",
                relevance_score=7,
            )
        ]
        response = client.get("/api/policies")
        data = response.json()
        assert data["count"] == 1

    def test_list_policies_deduplicates(self, client, mock_store, mock_manager):
        mock_store.search.return_value = [
            {"url": "https://a.gov/p1", "policy_name": "P1"},
        ]
        mock_manager.get_all_policies.return_value = [
            Policy(
                url="https://a.gov/p1",
                policy_name="P1",
                jurisdiction="US",
                policy_type=PolicyType.LAW,
                summary="Test",
                relevance_score=7,
            )
        ]
        response = client.get("/api/policies")
        data = response.json()
        assert data["count"] == 1  # deduplicated

    def test_list_policies_filters(self, client):
        response = client.get("/api/policies?jurisdiction=US&min_score=5")
        assert response.status_code == 200

    def test_policy_stats(self, client):
        response = client.get("/api/policies/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data


# --- Scans ---

class TestScanRoutes:
    def test_list_scans_empty(self, client):
        response = client.get("/api/scans")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_scans_with_job(self, client, mock_manager):
        job = ScanJob(scan_id="s1", status=ScanStatus.COMPLETED, domain_count=2, policy_count=1)
        mock_manager.jobs = {"s1": job}
        response = client.get("/api/scans")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["scan_id"] == "s1"

    def test_get_scan_not_found(self, client):
        response = client.get("/api/scans/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_get_scan_detail(self, client, mock_manager):
        job = ScanJob(
            scan_id="s1",
            status=ScanStatus.COMPLETED,
            domain_count=2,
            policy_count=1,
            progress=ScanProgress(total_domains=2, completed_domains=2),
        )
        mock_manager.jobs = {"s1": job}
        mock_manager.get_policies.return_value = []
        response = client.get("/api/scans/s1")
        assert response.status_code == 200
        data = response.json()
        assert data["scan_id"] == "s1"
        assert data["progress"]["total"] == 2

    def test_cancel_scan_not_found(self, client, mock_manager):
        mock_manager.stop_scan = AsyncMock(return_value=False)
        response = client.delete("/api/scans/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
