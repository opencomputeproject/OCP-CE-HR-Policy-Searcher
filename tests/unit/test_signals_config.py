"""Tests for ConfigLoader.get_signals_config() (config/signals.yaml)."""

from src.core.config import ConfigLoader, DEFAULT_SIGNALS_CONFIG


class TestSignalsConfigLoading:
    """The real config/signals.yaml should load with the documented shape."""

    def test_loads_real_signals_yaml(self):
        config = ConfigLoader(config_dir="config")
        config.load()
        signals = config.get_signals_config()

        assert signals["enabled"] is True
        assert signals["max_leads_per_run"] == 50
        assert signals["auto_chase_top"] == 0
        assert signals["gdelt"]["enabled"] is True
        assert len(signals["gdelt"]["queries"]) >= 10
        assert signals["google_news"]["enabled"] is True
        assert len(signals["google_news"]["queries"]) >= 5
        assert any(f["name"] == "DataCenterDynamics" for f in signals["rss_feeds"])
        assert any(p["name"] == "Euroheat news" for p in signals["watch_pages"])

    def test_gdelt_queries_include_native_language_terms(self):
        config = ConfigLoader(config_dir="config")
        config.load()
        queries = [q["q"] for q in config.get_signals_config()["gdelt"]["queries"]]
        assert any("Abwärme" in q for q in queries)
        assert any("fjärrvärme" in q for q in queries)
        assert any("chaleur fatale" in q for q in queries)
        assert any("restwarmte" in q for q in queries)
        assert any("overskudsvarme" in q for q in queries)


class TestSignalsConfigMissingFile:
    """Missing config/signals.yaml must not raise — returns disabled default."""

    def test_missing_file_returns_disabled_default(self, tmp_path):
        config = ConfigLoader(config_dir=str(tmp_path))
        config._load_settings()
        config._load_domains = lambda: None  # avoid unrelated domain dir requirement
        config._domains_config = {"domains": [], "groups": {}}
        config._load_keywords = lambda: None
        config._keywords_config = {}
        config._load_url_filters()
        config._load_signals()

        assert config.get_signals_config() == DEFAULT_SIGNALS_CONFIG

    def test_load_signals_directly_tolerates_missing_file(self, tmp_path):
        config = ConfigLoader(config_dir=str(tmp_path))
        config._load_signals()
        assert config._signals_config == DEFAULT_SIGNALS_CONFIG

    def test_signals_config_property_lazy_loads(self, tmp_path):
        config = ConfigLoader(config_dir=str(tmp_path))
        config._load_signals()
        assert config.signals_config == DEFAULT_SIGNALS_CONFIG
