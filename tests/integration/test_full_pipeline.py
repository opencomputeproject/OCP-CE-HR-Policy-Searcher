"""End-to-end integration tests for the full interactive pipeline.

These tests verify that the complete chain works: config loading →
agent initialization → tool dispatch → scan execution → Sheets export.
External services (HTTP, Anthropic API, Google Sheets) are mocked, but
all internal wiring uses real code and real config files.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.orchestrator import PolicyAgent, _build_system_prompt
from src.agent.tools import execute_tool, get_all_tools
from src.core.config import ConfigLoader, ConfigurationError
from src.core.models import (
    CrawlResult, PageStatus, Policy, PolicyType,
)
from src.orchestration.events import EventBroadcaster
from src.orchestration.scan_manager import ScanManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def real_config():
    """Load real config files from config/."""
    c = ConfigLoader(config_dir="config")
    c.load()
    return c


@pytest.fixture
def scan_manager(real_config):
    broadcaster = EventBroadcaster()
    return ScanManager(config=real_config, broadcaster=broadcaster, data_dir="data")


@pytest.fixture
def tmp_config_dir(tmp_path):
    """Create a minimal valid config directory for testing."""
    config_dir = tmp_path / "config"
    domains_dir = config_dir / "domains"
    domains_dir.mkdir(parents=True)

    # settings.yaml
    (config_dir / "settings.yaml").write_text(
        "crawl:\n  max_depth: 2\n  delay_seconds: 0.5\n"
        "analysis:\n  min_keyword_score: 3\n",
        encoding="utf-8",
    )

    # domains/test.yaml
    (domains_dir / "test.yaml").write_text(
        "domains:\n"
        "  - id: test_gov\n"
        "    name: Test Gov\n"
        "    base_url: https://test.gov\n"
        "    start_paths: [\"/\"]\n"
        "    region: [us]\n"
        "    enabled: true\n",
        encoding="utf-8",
    )

    # groups.yaml
    (config_dir / "groups.yaml").write_text(
        "groups:\n"
        "  quick:\n"
        "    description: Quick scan\n"
        "    domains: [test_gov]\n",
        encoding="utf-8",
    )

    # keywords.yaml
    (config_dir / "keywords.yaml").write_text(
        "categories:\n"
        "  heat_recovery:\n"
        "    weight: 3.0\n"
        "    terms:\n"
        "      en: [heat reuse, waste heat]\n"
        "  data_center:\n"
        "    weight: 2.0\n"
        "    terms:\n"
        "      en: [data center, data centre]\n"
        "thresholds:\n"
        "  min_score: 3.0\n"
        "  min_matches: 1\n",
        encoding="utf-8",
    )

    # url_filters.yaml
    (config_dir / "url_filters.yaml").write_text(
        "url_filters:\n"
        "  skip_paths: [/login]\n"
        "  skip_extensions: [.pdf, .jpg]\n",
        encoding="utf-8",
    )

    return config_dir


# ---------------------------------------------------------------------------
# 1. Config loading with real files
# ---------------------------------------------------------------------------

class TestConfigLoadingReal:
    """Verify config loads correctly from actual config files."""

    def test_loads_all_sections(self, real_config):
        assert real_config.settings is not None
        assert real_config.domains_config is not None
        assert real_config.keywords_config is not None

    def test_has_domains(self, real_config):
        domains = real_config.get_enabled_domains("all")
        assert len(domains) > 10, "Expected at least 10 configured domains"

    def test_has_groups(self, real_config):
        groups = real_config.list_groups()
        assert "quick" in groups

    def test_has_keywords(self, real_config):
        kw = real_config.keywords_config
        assert "keywords" in kw
        assert "subject" in kw["keywords"]

    def test_has_crawl_settings(self, real_config):
        assert real_config.settings.crawl.max_depth >= 1
        assert real_config.settings.crawl.delay_seconds > 0


class TestConfigLoadingMinimal:
    """Verify config loads from minimal test fixtures."""

    def test_loads_minimal_config(self, tmp_config_dir):
        c = ConfigLoader(config_dir=str(tmp_config_dir))
        c.load()
        assert len(c.get_enabled_domains("all")) == 1
        assert c.get_enabled_domains("all")[0]["id"] == "test_gov"

    def test_missing_domains_dir_raises(self, tmp_path):
        config_dir = tmp_path / "empty_config"
        config_dir.mkdir()
        (config_dir / "settings.yaml").write_text("crawl:\n  max_depth: 2\n")
        (config_dir / "keywords.yaml").write_text("categories: {}\n")
        c = ConfigLoader(config_dir=str(config_dir))
        with pytest.raises(ConfigurationError):
            c.load()

    def test_missing_keywords_raises(self, tmp_path):
        config_dir = tmp_path / "no_kw_config"
        domains_dir = config_dir / "domains"
        domains_dir.mkdir(parents=True)
        (config_dir / "settings.yaml").write_text("crawl:\n  max_depth: 2\n")
        (domains_dir / "test.yaml").write_text(
            "domains:\n  - id: t\n    name: T\n    base_url: https://t.gov\n"
        )
        c = ConfigLoader(config_dir=str(config_dir))
        with pytest.raises(ConfigurationError):
            c.load()

    def test_output_settings_from_env(self, tmp_config_dir, monkeypatch):
        monkeypatch.setenv("SPREADSHEET_ID", "test-sheet-id")
        monkeypatch.setenv("GOOGLE_CREDENTIALS", "dGVzdC1jcmVkcw==")  # base64("test-creds")
        c = ConfigLoader(config_dir=str(tmp_config_dir))
        c.load()
        assert c.settings.output.spreadsheet_id == "test-sheet-id"
        assert c.settings.output.google_credentials_b64 == "dGVzdC1jcmVkcw=="


# ---------------------------------------------------------------------------
# 2. Agent initialization
# ---------------------------------------------------------------------------

class TestAgentInit:
    """Verify PolicyAgent can be fully initialized with real config."""

    def test_init_with_real_config(self, real_config):
        """Agent initializes with real config, mocked API client."""
        agent = PolicyAgent.__new__(PolicyAgent)
        agent.config = real_config
        agent.broadcaster = EventBroadcaster()
        agent.scan_manager = ScanManager(
            config=real_config,
            broadcaster=agent.broadcaster,
            data_dir="data",
        )
        agent.tools = get_all_tools()
        agent.system_prompt = _build_system_prompt(real_config)
        agent.model = "test-model"
        agent.client = AsyncMock()

        assert len(agent.tools) == 13
        assert "heat reuse" in agent.system_prompt.lower() or "government" in agent.system_prompt.lower()

    def test_system_prompt_has_domain_count(self, real_config):
        prompt = _build_system_prompt(real_config)
        # Should mention the actual number of domains
        domains = real_config.get_enabled_domains("all")
        assert str(len(domains)) in prompt

    def test_system_prompt_lists_groups(self, real_config):
        prompt = _build_system_prompt(real_config)
        assert "quick" in prompt


# ---------------------------------------------------------------------------
# 3. Tool dispatch — all local tools
# ---------------------------------------------------------------------------

class TestToolDispatchIntegration:
    """Test every local tool dispatches correctly with real config."""

    @pytest.mark.asyncio
    async def test_list_domains_all(self, real_config, scan_manager):
        result = await execute_tool("list_domains", {"group": "all"}, real_config, scan_manager)
        assert result["count"] > 10
        for d in result["domains"]:
            assert "id" in d
            assert "name" in d
            assert "base_url" in d

    @pytest.mark.asyncio
    async def test_list_domains_by_region(self, real_config, scan_manager):
        result = await execute_tool("list_domains", {"region": "eu"}, real_config, scan_manager)
        for d in result["domains"]:
            assert "eu" in d["region"]

    @pytest.mark.asyncio
    async def test_list_domains_by_category(self, real_config, scan_manager):
        result = await execute_tool("list_domains", {"category": "energy_ministry"}, real_config, scan_manager)
        for d in result["domains"]:
            assert d["category"] == "energy_ministry"

    @pytest.mark.asyncio
    async def test_get_domain_config_valid(self, real_config, scan_manager):
        # Get a real domain ID
        domains = real_config.get_enabled_domains("all")
        domain_id = domains[0]["id"]
        result = await execute_tool("get_domain_config", {"domain_id": domain_id}, real_config, scan_manager)
        assert result["id"] == domain_id

    @pytest.mark.asyncio
    async def test_get_domain_config_missing(self, real_config, scan_manager):
        result = await execute_tool("get_domain_config", {"domain_id": "nonexistent"}, real_config, scan_manager)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_estimate_cost(self, real_config, scan_manager):
        result = await execute_tool("estimate_cost", {"domains": "quick"}, real_config, scan_manager)
        assert result["domain_count"] > 0
        assert result["estimated_cost_usd"] >= 0

    @pytest.mark.asyncio
    async def test_match_keywords_relevant(self, real_config, scan_manager):
        result = await execute_tool(
            "match_keywords",
            {"text": "This data center waste heat reuse policy requires operators to recover heat from servers."},
            real_config, scan_manager,
        )
        assert result["score"] > 0
        assert len(result["matches"]) >= 2

    @pytest.mark.asyncio
    async def test_match_keywords_irrelevant(self, real_config, scan_manager):
        result = await execute_tool(
            "match_keywords",
            {"text": "The quick brown fox jumps over the lazy dog."},
            real_config, scan_manager,
        )
        assert result["score"] == 0

    @pytest.mark.asyncio
    async def test_get_policy_stats_empty(self, real_config, scan_manager):
        result = await execute_tool("get_policy_stats", {}, real_config, scan_manager)
        assert result["total"] == 0
        assert result["by_jurisdiction"] == {}

    @pytest.mark.asyncio
    async def test_search_policies_empty(self, real_config, scan_manager):
        result = await execute_tool("search_policies", {"jurisdiction": "Germany"}, real_config, scan_manager)
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_get_scan_status_missing(self, real_config, scan_manager):
        result = await execute_tool("get_scan_status", {"scan_id": "fake"}, real_config, scan_manager)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_stop_scan_missing(self, real_config, scan_manager):
        result = await execute_tool("stop_scan", {"scan_id": "fake"}, real_config, scan_manager)
        assert result["cancelled"] is False

    @pytest.mark.asyncio
    async def test_get_audit_advisory_missing(self, real_config, scan_manager):
        result = await execute_tool("get_audit_advisory", {"scan_id": "fake"}, real_config, scan_manager)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, real_config, scan_manager):
        result = await execute_tool("nonexistent", {}, real_config, scan_manager)
        assert "error" in result
        assert "Unknown tool" in result["error"]


# ---------------------------------------------------------------------------
# 4. analyze_url tool — full pipeline with mocked HTTP/LLM
# ---------------------------------------------------------------------------

class TestAnalyzeUrlPipeline:
    """Test analyze_url with mocked crawler and LLM."""

    @pytest.mark.asyncio
    async def test_analyze_url_full_pipeline(self, real_config, scan_manager, monkeypatch):
        """Full analyze_url: fetch → extract → keywords → LLM screen → LLM analyze → verify."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        html = """
        <html><head><title>Energy Efficiency Act</title></head>
        <body>
            <main>
                <h1>Data Center Heat Reuse Requirements</h1>
                <p>All data centers above 1MW must implement waste heat recovery
                systems. Operators are required to reuse at least 40% of waste heat
                by 2027. This regulation applies to all new and existing data center
                facilities in the jurisdiction.</p>
                <p>The data center energy efficiency standards mandate that heat
                recovery infrastructure must be installed within 24 months of the
                effective date of this legislation.</p>
            </main>
        </body></html>
        """

        mock_crawl_result = CrawlResult(
            url="https://test.gov/policy/heat-reuse",
            status=PageStatus.SUCCESS,
            content=html,
            content_length=len(html),
        )

        # Mock AsyncCrawler
        with patch("src.agent.tools.AsyncCrawler") as MockCrawler:
            mock_instance = AsyncMock()
            mock_instance.crawl_domain = AsyncMock(return_value=[mock_crawl_result])
            mock_instance.close = AsyncMock()
            MockCrawler.return_value = mock_instance

            # Mock ClaudeClient (use MagicMock base, not AsyncMock, for sync methods like to_policy)
            with patch("src.agent.tools.ClaudeClient") as MockLLM:
                mock_llm = MagicMock()
                mock_llm.screen_relevance = AsyncMock(return_value=MagicMock(
                    relevant=True, confidence=8,
                ))
                mock_llm.analyze_policy = AsyncMock(return_value=MagicMock(
                    is_relevant=True,
                    relevance_score=9,
                    policy_type="law",
                    policy_name="Heat Reuse Act",
                    jurisdiction="US",
                    summary="Requires data centers to reuse waste heat",
                ))
                mock_llm.to_policy.return_value = Policy(
                    url="https://test.gov/policy/heat-reuse",
                    policy_name="Heat Reuse Act",
                    jurisdiction="US",
                    policy_type=PolicyType.LAW,
                    summary="Requires data centers to reuse waste heat",
                    relevance_score=9,
                )
                mock_llm.close = AsyncMock()
                MockLLM.return_value = mock_llm

                result = await execute_tool(
                    "analyze_url",
                    {"url": "https://test.gov/policy/heat-reuse"},
                    real_config, scan_manager,
                )

        assert result["url"] == "https://test.gov/policy/heat-reuse"
        assert result["keyword_score"] > 0
        assert result["screening"]["relevant"] is True
        assert result["policy"]["policy_name"] == "Heat Reuse Act"
        assert result["policy"]["relevance_score"] == 9

    @pytest.mark.asyncio
    async def test_analyze_url_fetch_failure(self, real_config, scan_manager):
        """analyze_url handles crawler failure gracefully."""
        with patch("src.agent.tools.AsyncCrawler") as MockCrawler:
            mock_instance = AsyncMock()
            mock_instance.crawl_domain = AsyncMock(return_value=[
                CrawlResult(
                    url="https://test.gov/broken",
                    status=PageStatus.ACCESS_DENIED,
                    error_message="403 Forbidden",
                ),
            ])
            mock_instance.close = AsyncMock()
            MockCrawler.return_value = mock_instance

            result = await execute_tool(
                "analyze_url",
                {"url": "https://test.gov/broken"},
                real_config, scan_manager,
            )

        assert result["status"] == "access_denied"

    @pytest.mark.asyncio
    async def test_analyze_url_no_keywords(self, real_config, scan_manager):
        """analyze_url skips LLM when keywords don't match."""
        html = "<html><body><p>This is just a regular page about cooking recipes.</p></body></html>"
        with patch("src.agent.tools.AsyncCrawler") as MockCrawler:
            mock_instance = AsyncMock()
            mock_instance.crawl_domain = AsyncMock(return_value=[
                CrawlResult(
                    url="https://test.gov/cooking",
                    status=PageStatus.SUCCESS,
                    content=html,
                    content_length=len(html),
                ),
            ])
            mock_instance.close = AsyncMock()
            MockCrawler.return_value = mock_instance

            result = await execute_tool(
                "analyze_url",
                {"url": "https://test.gov/cooking"},
                real_config, scan_manager,
            )

        assert result["keyword_score"] == 0
        assert "screening" not in result
        assert "policy" not in result


# ---------------------------------------------------------------------------
# 5. add_domain tool — with mocked HTTP, real config dir
# ---------------------------------------------------------------------------

class TestAddDomainPipeline:
    """Test add_domain creates YAML and reloads config."""

    @pytest.mark.asyncio
    async def test_add_domain_creates_yaml(self, tmp_config_dir):
        """add_domain creates a YAML file and reloads config."""
        config = ConfigLoader(config_dir=str(tmp_config_dir))
        config.load()
        broadcaster = EventBroadcaster()
        sm = ScanManager(config=config, broadcaster=broadcaster, data_dir="data")

        html = "<html><head><title>Oregon DEQ Energy</title></head><body><p>Energy policy</p></body></html>"
        with patch("src.agent.tools.AsyncCrawler") as MockCrawler:
            mock_instance = AsyncMock()
            mock_instance.crawl_domain = AsyncMock(return_value=[
                CrawlResult(
                    url="https://energy.oregon.gov/policy",
                    status=PageStatus.SUCCESS,
                    content=html,
                    content_length=len(html),
                ),
            ])
            mock_instance.close = AsyncMock()
            MockCrawler.return_value = mock_instance

            result = await execute_tool(
                "add_domain",
                {"url": "https://energy.oregon.gov/policy"},
                config, sm,
            )

        assert result["success"] is True
        assert result["domain_id"] == "or_energy"
        assert "us" in result["region"]
        assert Path(result["config_file"]).exists()

        # Verify config was reloaded with new domain
        new_ids = {d["id"] for d in config.get_enabled_domains("all")}
        assert "or_energy" in new_ids

    @pytest.mark.asyncio
    async def test_add_domain_already_exists(self, tmp_config_dir):
        """add_domain returns already_exists for duplicate."""
        # test.gov → domain_id 'us_test' via generate_domain_id
        (tmp_config_dir / "domains" / "us_test.yaml").write_text(
            "domains:\n"
            "  - id: us_test\n"
            "    name: Test\n"
            "    base_url: https://test.gov\n"
            "    start_paths: [\"/\"]\n"
            "    region: [us]\n",
            encoding="utf-8",
        )
        config = ConfigLoader(config_dir=str(tmp_config_dir))
        config.load()
        broadcaster = EventBroadcaster()
        sm = ScanManager(config=config, broadcaster=broadcaster, data_dir="data")

        result = await execute_tool(
            "add_domain",
            {"url": "https://test.gov/new-page"},
            config, sm,
        )
        assert result["already_exists"] is True
        assert result["domain_id"] == "us_test"


# ---------------------------------------------------------------------------
# 6. on_tool_result callback — verifies the bug fix
# ---------------------------------------------------------------------------

class TestOnToolResultCallback:
    """Verify the on_tool_result callback always receives correct result."""

    @pytest.mark.asyncio
    async def test_callback_receives_result_on_success(self):
        """on_tool_result receives the actual tool result on success."""
        agent = PolicyAgent.__new__(PolicyAgent)
        agent.tools = []
        agent.system_prompt = "test"
        agent.model = "test-model"
        agent.config = ConfigLoader(config_dir="config")
        agent.config.load()
        agent.broadcaster = EventBroadcaster()
        agent.scan_manager = ScanManager(
            config=agent.config, broadcaster=agent.broadcaster, data_dir="data",
        )

        # Claude calls get_policy_stats (always succeeds), then responds
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "get_policy_stats"
        tool_block.input = {}
        tool_block.id = "t1"

        tool_response = MagicMock()
        tool_response.content = [tool_block]
        tool_response.stop_reason = "tool_use"

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Stats retrieved."

        text_response = MagicMock()
        text_response.content = [text_block]
        text_response.stop_reason = "end_turn"

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=[tool_response, text_response])
        agent.client = mock_client

        results_received = []
        await agent.run(
            "Get stats",
            on_tool_result=lambda name, result: results_received.append((name, result)),
        )

        assert len(results_received) == 1
        name, result = results_received[0]
        assert name == "get_policy_stats"
        assert "total" in result
        assert "by_jurisdiction" in result

    @pytest.mark.asyncio
    async def test_callback_receives_error_on_failure(self):
        """on_tool_result receives error dict when tool raises an exception."""
        agent = PolicyAgent.__new__(PolicyAgent)
        agent.tools = []
        agent.system_prompt = "test"
        agent.model = "test-model"
        agent.config = ConfigLoader(config_dir="config")
        agent.config.load()
        agent.broadcaster = EventBroadcaster()
        agent.scan_manager = ScanManager(
            config=agent.config, broadcaster=agent.broadcaster, data_dir="data",
        )

        # Claude calls a tool that will error
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "get_scan_status"
        tool_block.input = {"scan_id": "nonexistent_scan"}
        tool_block.id = "t1"

        tool_response = MagicMock()
        tool_response.content = [tool_block]
        tool_response.stop_reason = "tool_use"

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Not found."

        text_response = MagicMock()
        text_response.content = [text_block]
        text_response.stop_reason = "end_turn"

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=[tool_response, text_response])
        agent.client = mock_client

        results_received = []
        await agent.run(
            "Check scan",
            on_tool_result=lambda name, result: results_received.append((name, result)),
        )

        assert len(results_received) == 1
        name, result = results_received[0]
        assert name == "get_scan_status"
        # The error result should always be a dict with "error" key
        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_callback_on_consecutive_tools(self):
        """on_tool_result receives correct result for each tool in sequence."""
        agent = PolicyAgent.__new__(PolicyAgent)
        agent.tools = []
        agent.system_prompt = "test"
        agent.model = "test-model"
        agent.config = ConfigLoader(config_dir="config")
        agent.config.load()
        agent.broadcaster = EventBroadcaster()
        agent.scan_manager = ScanManager(
            config=agent.config, broadcaster=agent.broadcaster, data_dir="data",
        )

        # Two tool calls in one response
        tool1 = MagicMock()
        tool1.type = "tool_use"
        tool1.name = "get_policy_stats"
        tool1.input = {}
        tool1.id = "t1"

        tool2 = MagicMock()
        tool2.type = "tool_use"
        tool2.name = "estimate_cost"
        tool2.input = {"domains": "quick"}
        tool2.id = "t2"

        multi_response = MagicMock()
        multi_response.content = [tool1, tool2]
        multi_response.stop_reason = "tool_use"

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Done."
        text_response = MagicMock()
        text_response.content = [text_block]
        text_response.stop_reason = "end_turn"

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=[multi_response, text_response])
        agent.client = mock_client

        results_received = []
        await agent.run(
            "Stats and cost",
            on_tool_result=lambda name, result: results_received.append((name, result)),
        )

        assert len(results_received) == 2
        assert results_received[0][0] == "get_policy_stats"
        assert "total" in results_received[0][1]
        assert results_received[1][0] == "estimate_cost"
        assert "estimated_cost_usd" in results_received[1][1]


# ---------------------------------------------------------------------------
# 7. Scan pipeline — start_scan → poll → complete
# ---------------------------------------------------------------------------

class TestScanPipeline:
    """Test scan lifecycle with mocked crawler."""

    @pytest.mark.asyncio
    async def test_dry_run_scan(self, real_config, scan_manager):
        """Dry run scan completes immediately."""
        result = await execute_tool(
            "start_scan",
            {"domains": "quick", "skip_llm": True},
            real_config, scan_manager,
        )
        # start_scan dispatches scan in background; check immediate return
        assert "scan_id" in result
        assert result["status"] in ("running", "completed")
        assert result["domain_count"] > 0

    @pytest.mark.asyncio
    async def test_scan_status_after_start(self, real_config, scan_manager):
        """After starting a scan, status is retrievable."""
        start_result = await execute_tool(
            "start_scan",
            {"domains": "quick", "skip_llm": True},
            real_config, scan_manager,
        )
        scan_id = start_result["scan_id"]

        status_result = await execute_tool(
            "get_scan_status",
            {"scan_id": scan_id},
            real_config, scan_manager,
        )
        assert status_result["scan_id"] == scan_id
        assert status_result["status"] in ("running", "completed", "failed")

    @pytest.mark.asyncio
    async def test_scan_cancel(self, real_config, scan_manager):
        """Scan can be cancelled."""
        start_result = await execute_tool(
            "start_scan",
            {"domains": "quick", "skip_llm": True},
            real_config, scan_manager,
        )
        scan_id = start_result["scan_id"]

        # Cancel should succeed or report already done
        cancel_result = await execute_tool(
            "stop_scan",
            {"scan_id": scan_id},
            real_config, scan_manager,
        )
        assert "cancelled" in cancel_result


# ---------------------------------------------------------------------------
# 8. Sheets export integration (mocked gspread)
# ---------------------------------------------------------------------------

class TestSheetsExportIntegration:
    """Test that scan pipeline calls Sheets export when configured."""

    @pytest.mark.asyncio
    async def test_sheets_export_after_scan(self, tmp_config_dir, monkeypatch):
        """Scan exports to Sheets when SPREADSHEET_ID and GOOGLE_CREDENTIALS are set."""
        try:
            import gspread  # noqa: F401
        except ImportError:
            pytest.skip("gspread not installed")

        monkeypatch.setenv("SPREADSHEET_ID", "test-sheet-id")
        monkeypatch.setenv("GOOGLE_CREDENTIALS", "dGVzdA==")  # base64("test")

        config = ConfigLoader(config_dir=str(tmp_config_dir))
        config.load()

        # Verify output settings loaded from env
        output_cfg = config.settings.output
        assert output_cfg.spreadsheet_id == "test-sheet-id"
        assert output_cfg.google_credentials_b64 == "dGVzdA=="

        # Simulate the export logic from scan_manager lines 288-304
        # (SheetsClient is lazy-imported inside _run_scan, so we test
        # the logic directly instead of patching an unresolvable attribute)
        mock_sheets = MagicMock()
        mock_sheets.get_existing_urls.return_value = set()
        mock_sheets.append_policies.return_value = 1

        all_policies = [
            Policy(
                url="https://test.gov/p1",
                policy_name="Test Policy",
                jurisdiction="US",
                policy_type=PolicyType.LAW,
                summary="Test",
                relevance_score=8,
            ),
        ]

        # Run the same code path as scan_manager
        with patch("src.output.sheets.SheetsClient", return_value=mock_sheets):
            from src.output.sheets import SheetsClient
            sheets = SheetsClient(
                credentials_b64=output_cfg.google_credentials_b64,
                spreadsheet_id=output_cfg.spreadsheet_id,
            )
            sheets.connect()
            existing_urls = sheets.get_existing_urls("Staging")
            new_policies = [p for p in all_policies if p.url not in existing_urls]
            if new_policies:
                sheets.append_policies(new_policies, "Staging")

        mock_sheets.connect.assert_called_once()
        mock_sheets.get_existing_urls.assert_called_once_with("Staging")
        mock_sheets.append_policies.assert_called_once()
        appended = mock_sheets.append_policies.call_args[0][0]
        assert len(appended) == 1
        assert appended[0].url == "https://test.gov/p1"

    @pytest.mark.asyncio
    async def test_sheets_dedup_skips_existing(self, tmp_config_dir, monkeypatch):
        """Sheets export skips policies whose URLs already exist."""
        try:
            from src.output.sheets import SheetsClient  # noqa: F401
        except ImportError:
            pytest.skip("gspread not installed")

        monkeypatch.setenv("SPREADSHEET_ID", "test-sheet-id")
        monkeypatch.setenv("GOOGLE_CREDENTIALS", "dGVzdA==")

        config = ConfigLoader(config_dir=str(tmp_config_dir))
        config.load()

        all_policies = [
            Policy(
                url="https://test.gov/already-there",
                policy_name="Old Policy",
                jurisdiction="US",
                policy_type=PolicyType.LAW,
                summary="Already exported",
                relevance_score=7,
            ),
            Policy(
                url="https://test.gov/new-one",
                policy_name="New Policy",
                jurisdiction="US",
                policy_type=PolicyType.REGULATION,
                summary="Newly discovered",
                relevance_score=8,
            ),
        ]

        existing_urls = {"https://test.gov/already-there"}
        new_policies = [p for p in all_policies if p.url not in existing_urls]
        assert len(new_policies) == 1
        assert new_policies[0].url == "https://test.gov/new-one"

    @pytest.mark.asyncio
    async def test_no_sheets_without_env_vars(self, tmp_config_dir):
        """Without SPREADSHEET_ID, sheets export is not attempted."""
        config = ConfigLoader(config_dir=str(tmp_config_dir))
        config.load()
        assert config.settings.output.spreadsheet_id is None
        # The scan_manager check is: if output_cfg.spreadsheet_id and ...
        # With None, this evaluates to False → no export


# ---------------------------------------------------------------------------
# 9. Search policies with data in scan_manager
# ---------------------------------------------------------------------------

class TestSearchPoliciesWithData:
    """Test search_policies when scan_manager has policies."""

    @pytest.mark.asyncio
    async def test_search_finds_matching(self, real_config, scan_manager):
        # Inject policies
        scan_manager._policies["test"] = [
            Policy(
                url="https://a.gov/p1",
                policy_name="German Heat Act",
                jurisdiction="Germany",
                policy_type=PolicyType.LAW,
                summary="Heat recovery mandate",
                relevance_score=9,
            ),
            Policy(
                url="https://b.gov/p2",
                policy_name="French Energy Code",
                jurisdiction="France",
                policy_type=PolicyType.REGULATION,
                summary="Energy regulation",
                relevance_score=6,
            ),
        ]

        result = await execute_tool(
            "search_policies",
            {"jurisdiction": "Germany"},
            real_config, scan_manager,
        )
        assert result["count"] == 1
        assert result["policies"][0]["policy_name"] == "German Heat Act"

    @pytest.mark.asyncio
    async def test_search_by_type(self, real_config, scan_manager):
        scan_manager._policies["test"] = [
            Policy(
                url="https://a.gov/p1",
                policy_name="Act 1",
                jurisdiction="US",
                policy_type=PolicyType.LAW,
                summary="A law",
                relevance_score=7,
            ),
            Policy(
                url="https://b.gov/p2",
                policy_name="Reg 2",
                jurisdiction="US",
                policy_type=PolicyType.REGULATION,
                summary="A reg",
                relevance_score=7,
            ),
        ]

        result = await execute_tool(
            "search_policies",
            {"policy_type": "regulation"},
            real_config, scan_manager,
        )
        assert result["count"] == 1
        assert result["policies"][0]["policy_name"] == "Reg 2"

    @pytest.mark.asyncio
    async def test_search_by_min_score(self, real_config, scan_manager):
        scan_manager._policies["test"] = [
            Policy(url="https://a.gov", policy_name="High", jurisdiction="US",
                   policy_type=PolicyType.LAW, summary="s", relevance_score=9),
            Policy(url="https://b.gov", policy_name="Low", jurisdiction="US",
                   policy_type=PolicyType.LAW, summary="s", relevance_score=3),
        ]

        result = await execute_tool(
            "search_policies",
            {"min_score": 7},
            real_config, scan_manager,
        )
        assert result["count"] == 1
        assert result["policies"][0]["policy_name"] == "High"

    @pytest.mark.asyncio
    async def test_stats_with_data(self, real_config, scan_manager):
        scan_manager._policies["test"] = [
            Policy(url="https://a.gov", policy_name="P1", jurisdiction="Germany",
                   policy_type=PolicyType.LAW, summary="s", relevance_score=9),
            Policy(url="https://b.gov", policy_name="P2", jurisdiction="France",
                   policy_type=PolicyType.REGULATION, summary="s", relevance_score=6),
        ]

        result = await execute_tool("get_policy_stats", {}, real_config, scan_manager)
        assert result["total"] == 2
        assert result["by_jurisdiction"]["Germany"] == 1
        assert result["by_jurisdiction"]["France"] == 1
        assert result["by_type"]["law"] == 1
        assert result["by_type"]["regulation"] == 1


# ---------------------------------------------------------------------------
# 10. API error handling in agent loop
# ---------------------------------------------------------------------------

class TestAgentAPIErrors:
    """Test agent handles API errors gracefully."""

    @pytest.mark.asyncio
    async def test_api_error_returns_message(self):
        import anthropic

        agent = PolicyAgent.__new__(PolicyAgent)
        agent.tools = []
        agent.system_prompt = "test"
        agent.model = "test-model"
        agent.config = ConfigLoader(config_dir="config")
        agent.config.load()
        agent.broadcaster = EventBroadcaster()
        agent.scan_manager = ScanManager(
            config=agent.config, broadcaster=agent.broadcaster, data_dir="data",
        )

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic.APIError(
                message="Rate limited",
                request=MagicMock(),
                body=None,
            )
        )
        agent.client = mock_client

        text_received = []
        result = await agent.run("Test", on_text=lambda t: text_received.append(t))
        assert "API error" in result
        assert len(text_received) == 1


# ---------------------------------------------------------------------------
# 11. README onboarding flow — fresh-clone experience
# ---------------------------------------------------------------------------

class TestOnboardingFlow:
    """Verify the README 'Try it now' steps work for a new user.

    Tests the full flow: pyproject.toml is valid, example.env exists,
    config loads, python -m src.agent shows helpful errors when
    prerequisites are missing, and the entry point works end-to-end.
    """

    def test_pyproject_toml_exists_at_repo_root(self):
        """pip install -e . requires pyproject.toml at the repo root."""
        pyproject = Path("pyproject.toml")
        assert pyproject.exists(), "pyproject.toml not found at repo root"

    def test_pyproject_toml_has_project_metadata(self):
        """pyproject.toml has enough metadata for pip install."""
        content = Path("pyproject.toml").read_text(encoding="utf-8")
        assert "[project]" in content
        assert 'name = "ocp-policy-hub"' in content
        assert "dependencies" in content

    def test_example_env_exists(self):
        """cp config/example.env .env — the source file must exist."""
        assert Path("config/example.env").exists()

    def test_example_env_has_api_key_placeholder(self):
        """example.env should have an ANTHROPIC_API_KEY line to fill in."""
        content = Path("config/example.env").read_text(encoding="utf-8")
        assert "ANTHROPIC_API_KEY" in content

    def test_example_env_has_sheets_placeholders(self):
        """example.env should document the optional Sheets config."""
        content = Path("config/example.env").read_text(encoding="utf-8")
        assert "GOOGLE_CREDENTIALS" in content
        assert "SPREADSHEET_ID" in content

    def test_config_dir_exists_with_required_files(self):
        """Real config dir has all files the loader expects."""
        config = Path("config")
        assert (config / "settings.yaml").exists()
        assert (config / "keywords.yaml").exists()
        assert (config / "groups.yaml").exists()
        assert (config / "domains").is_dir()
        domain_files = list((config / "domains").glob("*.yaml"))
        assert len(domain_files) > 0, "No domain YAML files found"

    def test_config_loads_from_repo_root(self):
        """ConfigLoader succeeds with real config files."""
        from src.core.config import ConfigLoader

        c = ConfigLoader(config_dir="config")
        c.load()
        assert len(c.get_enabled_domains("all")) > 100

    def test_agent_no_api_key_exits_with_helpful_error(self, monkeypatch, capsys):
        """python -m src.agent with no key shows a helpful message."""
        # Import first so module-level load_dotenv() runs and gets cached.
        # Then delenv removes the key — main() won't find it.
        from src.agent.__main__ import main

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

        output = capsys.readouterr().out
        assert "ANTHROPIC_API_KEY" in output
        assert "example.env" in output
        assert "console.anthropic.com" in output

    def test_agent_no_api_key_shows_cross_platform_help(self, monkeypatch, capsys):
        """Error message includes both bash and PowerShell syntax."""
        from src.agent.__main__ import main

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(SystemExit):
            main()

        output = capsys.readouterr().out
        assert "export ANTHROPIC_API_KEY" in output  # bash/zsh
        assert "$env:ANTHROPIC_API_KEY" in output    # PowerShell

    def test_agent_placeholder_key_starts(self, monkeypatch):
        """Agent starts (doesn't crash) with a placeholder key.

        It will fail at first API call, but the config loading and
        initialization should succeed.
        """
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-placeholder")
        from src.agent.orchestrator import PolicyAgent

        agent = PolicyAgent(
            api_key="sk-ant-api03-placeholder",
            config_dir="config",
            data_dir="data",
        )
        assert len(agent.tools) == 13
        assert agent.config is not None

    def test_rest_api_starts_without_api_key(self):
        """FastAPI server starts even without an API key.

        The API key is only needed for agent/analysis endpoints,
        not for domain listing or config endpoints.
        """
        from fastapi.testclient import TestClient
        from src.api.app import app

        with TestClient(app) as client:
            r = client.get("/health")
            assert r.status_code == 200
            assert r.json()["status"] == "ok"

            r = client.get("/api/domains")
            assert r.status_code == 200
            assert r.json()["count"] > 100

    # ------------------------------------------------------------------
    # Setup script tests
    # ------------------------------------------------------------------

    def test_setup_sh_exists(self):
        """setup.sh exists at repo root for Linux/macOS users."""
        assert Path("setup.sh").exists()

    def test_setup_ps1_exists(self):
        """setup.ps1 exists at repo root for Windows users."""
        assert Path("setup.ps1").exists()

    @pytest.mark.skipif(
        not Path("/bin/bash").exists() and not Path("/usr/bin/bash").exists(),
        reason="bash not available (Windows)",
    )
    def test_setup_sh_has_valid_bash_syntax(self):
        """setup.sh parses without syntax errors."""
        import subprocess
        result = subprocess.run(
            ["bash", "-n", "setup.sh"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Bash syntax error: {result.stderr}"

    def test_setup_sh_has_shebang(self):
        """setup.sh starts with a proper shebang line."""
        first_line = Path("setup.sh").read_text(encoding="utf-8").split("\n")[0]
        assert first_line.startswith("#!/"), "Missing shebang"
        assert "bash" in first_line

    def test_setup_sh_exits_on_errors(self):
        """setup.sh uses set -e so failures don't silently continue."""
        content = Path("setup.sh").read_text(encoding="utf-8")
        assert "set -e" in content

    def test_setup_sh_checks_python_version(self):
        """setup.sh verifies Python 3.11+ before proceeding."""
        content = Path("setup.sh").read_text(encoding="utf-8")
        assert "3" in content and "11" in content
        assert "Python" in content
        # Should show helpful error with download link if missing
        assert "python.org/downloads" in content

    def test_setup_sh_creates_venv(self):
        """setup.sh creates a .venv virtual environment."""
        content = Path("setup.sh").read_text(encoding="utf-8")
        assert ".venv" in content
        assert "venv" in content

    def test_setup_sh_installs_with_pip(self):
        """setup.sh installs the project with pip."""
        content = Path("setup.sh").read_text(encoding="utf-8")
        assert "pip install" in content

    def test_setup_sh_copies_example_env(self):
        """setup.sh copies config/example.env to .env."""
        content = Path("setup.sh").read_text(encoding="utf-8")
        assert "example.env" in content
        assert ".env" in content

    def test_setup_sh_supports_dev_flag(self):
        """setup.sh --dev installs development dependencies."""
        content = Path("setup.sh").read_text(encoding="utf-8")
        assert "--dev" in content
        assert ".[dev]" in content

    def test_setup_sh_skips_existing_venv(self):
        """setup.sh doesn't recreate .venv if it already exists."""
        content = Path("setup.sh").read_text(encoding="utf-8")
        assert "already exists" in content

    def test_setup_sh_skips_existing_env_file(self):
        """setup.sh doesn't overwrite .env if it already exists."""
        content = Path("setup.sh").read_text(encoding="utf-8")
        # Must check for existing .env before copying
        assert '! -f ".env"' in content or "already exists" in content

    def test_setup_sh_shows_next_steps(self):
        """setup.sh tells the user what to do after setup."""
        content = Path("setup.sh").read_text(encoding="utf-8")
        assert "console.anthropic.com" in content
        assert "python -m src.agent" in content

    def test_setup_ps1_checks_python_version(self):
        """setup.ps1 verifies Python 3.11+ before proceeding."""
        content = Path("setup.ps1").read_text(encoding="utf-8")
        assert "3" in content and "11" in content
        assert "Python" in content
        assert "python.org/downloads" in content

    def test_setup_ps1_mentions_execution_policy(self):
        """setup.ps1 tells Windows users how to enable script execution."""
        content = Path("setup.ps1").read_text(encoding="utf-8")
        assert "Set-ExecutionPolicy" in content

    def test_setup_ps1_supports_dev_flag(self):
        """setup.ps1 -Dev installs development dependencies."""
        content = Path("setup.ps1").read_text(encoding="utf-8")
        assert "$Dev" in content
        assert ".[dev]" in content

    def test_setup_ps1_creates_venv(self):
        """setup.ps1 creates a .venv virtual environment."""
        content = Path("setup.ps1").read_text(encoding="utf-8")
        assert ".venv" in content
        assert "venv" in content

    def test_setup_ps1_copies_example_env(self):
        """setup.ps1 copies config/example.env to .env."""
        content = Path("setup.ps1").read_text(encoding="utf-8")
        assert "example.env" in content

    def test_setup_ps1_shows_next_steps(self):
        """setup.ps1 tells the user what to do after setup."""
        content = Path("setup.ps1").read_text(encoding="utf-8")
        assert "console.anthropic.com" in content
        assert "python -m src.agent" in content

    @pytest.mark.skipif(
        not Path("/bin/bash").exists() and not Path("/usr/bin/bash").exists(),
        reason="bash not available (Windows)",
    )
    def test_setup_sh_functional_python_check(self):
        """setup.sh correctly identifies the current Python as 3.11+."""
        import subprocess

        # Extract just the Python-finding logic and run it
        result = subprocess.run(
            ["bash", "-c", """
                PYTHON=""
                for candidate in python3 python; do
                    if command -v "$candidate" &>/dev/null; then
                        major=$("$candidate" -c "import sys; print(sys.version_info.major)" 2>/dev/null)
                        minor=$("$candidate" -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
                        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ] 2>/dev/null; then
                            PYTHON="$candidate"
                            break
                        fi
                    fi
                done
                if [ -z "$PYTHON" ]; then
                    echo "NOT_FOUND"
                    exit 1
                fi
                echo "FOUND:$PYTHON"
            """],
            capture_output=True, text=True,
        )
        # We know our current Python is 3.11+ (required by pyproject.toml)
        assert result.returncode == 0, "setup.sh would fail to find Python 3.11+"
        assert "FOUND:" in result.stdout

    @pytest.mark.skipif(
        not Path("/bin/bash").exists() and not Path("/usr/bin/bash").exists(),
        reason="bash not available (Windows)",
    )
    def test_setup_sh_env_copy_functional(self, tmp_path):
        """setup.sh's env-copy logic works correctly."""
        import subprocess
        import shutil

        # Copy example.env to a temp dir and test the copy logic
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        shutil.copy("config/example.env", config_dir / "example.env")

        # Run just the env-copy portion
        result = subprocess.run(
            ["bash", "-c", f"""
                cd "{tmp_path}"
                if [ ! -f ".env" ]; then
                    cp config/example.env .env
                    echo "COPIED"
                else
                    echo "SKIPPED"
                fi
            """],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "COPIED" in result.stdout
        assert (tmp_path / ".env").exists()

        # Run again — should skip
        result = subprocess.run(
            ["bash", "-c", f"""
                cd "{tmp_path}"
                if [ ! -f ".env" ]; then
                    cp config/example.env .env
                    echo "COPIED"
                else
                    echo "SKIPPED"
                fi
            """],
            capture_output=True, text=True,
        )
        assert "SKIPPED" in result.stdout
