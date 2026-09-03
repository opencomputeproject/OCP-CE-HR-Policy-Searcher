"""Settings that exist in the model must also be read from settings.yaml and
handed to the code that uses them (lessons PL-007 and L003).

`data_center_required` was defined, defaulted, documented and tested at the
module level on 2026-08-28 and never passed from the YAML into
`AnalysisSettings`, so an administrator setting it to `adjacent` changed
nothing. These tests load a real config directory with the value changed
and follow it all the way to the scanner's constructor.
"""

import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from src.core.config import ConfigLoader
from src.core.models import (
    DEFAULT_SCREENER_REJECT_KINDS,
    DEFAULT_SCREENER_SOFT_REJECT_KINDS,
    DomainProgress,
    DomainScanStatus,
)

ROOT = Path(__file__).resolve().parents[2]


def _config_dir_with(tmp_path: Path, analysis_overrides: dict) -> Path:
    """A copy of the real config/ with keys changed in the analysis block."""
    target = tmp_path / "config"
    shutil.copytree(ROOT / "config", target, ignore=shutil.ignore_patterns("__pycache__"))
    settings_path = target / "settings.yaml"
    data = yaml.safe_load(settings_path.read_text(encoding="utf-8"))
    data.setdefault("analysis", {}).update(analysis_overrides)
    settings_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return target


@pytest.mark.medium
class TestAnalysisSettingsReachTheModel:
    def test_data_center_required_from_yaml_is_read(self, tmp_path):
        """FAILS ON OLD BEHAVIOUR: the loader never passed this key on, so
        the model default won regardless of the file."""
        config_dir = _config_dir_with(tmp_path, {"data_center_required": "adjacent"})
        assert ConfigLoader(str(config_dir)).settings.analysis.data_center_required == "adjacent"

    def test_the_default_is_still_required_when_the_key_is_absent(self, tmp_path):
        config_dir = _config_dir_with(tmp_path, {})
        data = yaml.safe_load((config_dir / "settings.yaml").read_text(encoding="utf-8"))
        data["analysis"].pop("data_center_required", None)
        (config_dir / "settings.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
        assert ConfigLoader(str(config_dir)).settings.analysis.data_center_required == "required"

    def test_both_screener_kind_lists_are_read(self, tmp_path):
        config_dir = _config_dir_with(
            tmp_path,
            {"screener_reject_kinds": ["speech"], "screener_soft_reject_kinds": ["report"]},
        )
        analysis = ConfigLoader(str(config_dir)).settings.analysis
        assert analysis.screener_reject_kinds == ["speech"]
        assert analysis.screener_soft_reject_kinds == ["report"]

    def test_the_kind_list_defaults_match_the_module_constants(self, tmp_path):
        analysis = ConfigLoader(str(_config_dir_with(tmp_path, {}))).settings.analysis
        assert analysis.screener_reject_kinds == list(DEFAULT_SCREENER_REJECT_KINDS)
        assert analysis.screener_soft_reject_kinds == list(DEFAULT_SCREENER_SOFT_REJECT_KINDS)


@pytest.mark.medium
class TestAnalysisSettingsReachTheScanner:
    @pytest.mark.asyncio
    async def test_scan_manager_hands_the_lists_and_the_scope_to_every_scanner(
        self, tmp_path, monkeypatch,
    ):
        from src.orchestration.scan_manager import ScanManager

        config_dir = _config_dir_with(
            tmp_path,
            {
                "data_center_required": "adjacent",
                "screener_reject_kinds": ["speech"],
                "screener_soft_reject_kinds": ["report", "article", "plan"],
            },
        )
        config = ConfigLoader(str(config_dir))
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        broadcaster = MagicMock()
        broadcaster.broadcast = AsyncMock()
        manager = ScanManager(config=config, broadcaster=broadcaster, data_dir=str(data_dir))

        seen: list[dict] = []

        def fake_scanner(**kwargs):
            seen.append(kwargs)
            scanner = MagicMock()
            scanner.scan = AsyncMock(return_value=[])
            scanner.duplicates = []
            scanner.progress = DomainProgress(
                domain_id=kwargs["domain"]["id"], domain_name=kwargs["domain"].get("name", ""),
                status=DomainScanStatus.COMPLETED,
            )
            return scanner

        monkeypatch.setattr("src.orchestration.scan_manager.DomainScanner", fake_scanner)
        monkeypatch.setattr(
            "src.orchestration.scan_manager.AsyncCrawler",
            lambda **kwargs: MagicMock(close=AsyncMock()),
        )

        job = await manager.start_scan(domains_group="quick", skip_llm=True)
        await manager._tasks[job.scan_id]

        assert seen, "no scanner was constructed for the quick group"
        for kwargs in seen:
            assert kwargs["scope_setting"] == "adjacent"
            assert kwargs["screener_reject_kinds"] == ["speech"]
            assert kwargs["screener_soft_reject_kinds"] == ["report", "article", "plan"]
