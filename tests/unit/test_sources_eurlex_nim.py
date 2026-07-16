"""Tests for the EUR-Lex national implementing measures structured source."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from src.core.models import PageStatus
from src.sources import SOURCE_REGISTRY
from src.sources.base import SourceError
from src.sources.eurlex_nim import EURLexNIMSource

NIM_HTML_TWO_MEASURES = """
<html><body>
<h2>Sweden</h2>
<ul><li><a href="/nat-law-se">Lag om energieffektivisering</a></li></ul>
<h2>Denmark</h2>
<ul><li><a href="/nat-law-dk">Bekendtgorelse om energieffektivitet</a></li></ul>
</body></html>
"""

NIM_HTML_THREE_MEASURES = """
<html><body>
<h2>Sweden</h2>
<ul><li><a href="/nat-law-se">Lag om energieffektivisering</a></li></ul>
<h2>Denmark</h2>
<ul><li><a href="/nat-law-dk">Bekendtgorelse om energieffektivitet</a></li></ul>
<h2>Germany</h2>
<ul><li><a href="/nat-law-de">Gesetz zur Energieeffizienz</a></li></ul>
</body></html>
"""

NIM_HTML_NO_STRUCTURE = "<html><body><p>No measures listed yet.</p></body></html>"


def _write_directives(tmp_path, directives):
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "directives.yaml").write_text(
        yaml.safe_dump({"directives": directives}), encoding="utf-8"
    )
    return str(config_dir)


def _mock_response(*, text="", status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.headers = {"content-type": "text/html"}
    resp.raise_for_status = MagicMock()
    return resp


def _mock_client(get_side_effect):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.get = AsyncMock(side_effect=get_side_effect)
    return client


class TestEURLexNIMSource:
    def test_registered(self):
        assert SOURCE_REGISTRY["eurlex_nim"] is EURLexNIMSource

    @pytest.mark.asyncio
    async def test_happy_path(self, tmp_path):
        config_dir = _write_directives(tmp_path, [{"celex": "32023L1791", "name": "EED"}])
        nim_resp = _mock_response(text=NIM_HTML_TWO_MEASURES)
        law_resp = _mock_response(text="<html><body>National law text.</body></html>")
        client = _mock_client([nim_resp, law_resp, law_resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = EURLexNIMSource()
            results = await source.fetch({
                "source_params": {
                    "config_dir": config_dir,
                    "data_dir": str(tmp_path / "data"),
                }
            })

        assert len(results) == 2
        assert all(r.status == PageStatus.SUCCESS for r in results)
        assert all(r.lifecycle_stage == "transposition_notified" for r in results)
        assert all(r.url.startswith("https://eur-lex.europa.eu/") for r in results)
        assert (tmp_path / "data" / "nim_seen.json").exists()

    @pytest.mark.asyncio
    async def test_unseen_only_diff_across_fetches(self, tmp_path):
        config_dir = _write_directives(tmp_path, [{"celex": "32023L1791", "name": "EED"}])
        data_dir = str(tmp_path / "data")
        law_resp = _mock_response(text="<html><body>National law text.</body></html>")

        # First fetch: two measures, both new.
        nim_resp_1 = _mock_response(text=NIM_HTML_TWO_MEASURES)
        client_1 = _mock_client([nim_resp_1, law_resp, law_resp])
        with patch("httpx.AsyncClient", return_value=client_1):
            source = EURLexNIMSource()
            first_results = await source.fetch({
                "source_params": {"config_dir": config_dir, "data_dir": data_dir}
            })
        assert len(first_results) == 2

        # Second fetch: same two measures plus one new (Germany) -> only the new one emitted.
        nim_resp_2 = _mock_response(text=NIM_HTML_THREE_MEASURES)
        client_2 = _mock_client([nim_resp_2, law_resp])
        with patch("httpx.AsyncClient", return_value=client_2):
            source = EURLexNIMSource()
            second_results = await source.fetch({
                "source_params": {"config_dir": config_dir, "data_dir": data_dir}
            })

        assert len(second_results) == 1
        assert "Germany" in second_results[0].title

        seen_data = json.loads((tmp_path / "data" / "nim_seen.json").read_text())
        assert len(seen_data["32023L1791"]) == 3

    @pytest.mark.asyncio
    async def test_directives_yaml_loading(self, tmp_path):
        config_dir = _write_directives(tmp_path, [
            {"celex": "32023L1791", "name": "EED"},
            {"celex": "32024L1275", "name": "EPBD"},
        ])
        nim_resp = _mock_response(text=NIM_HTML_NO_STRUCTURE)
        client = _mock_client([nim_resp, nim_resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = EURLexNIMSource()
            results = await source.fetch({
                "source_params": {
                    "config_dir": config_dir,
                    "data_dir": str(tmp_path / "data"),
                }
            })

        assert results == []
        called_urls = [call.args[0] for call in client.get.call_args_list]
        assert any("32023L1791" in u for u in called_urls)
        assert any("32024L1275" in u for u in called_urls)

    @pytest.mark.asyncio
    async def test_missing_directives_file_raises_source_error(self, tmp_path):
        source = EURLexNIMSource()
        with pytest.raises(SourceError):
            await source.fetch({
                "source_params": {
                    "config_dir": str(tmp_path / "does_not_exist"),
                    "data_dir": str(tmp_path / "data"),
                }
            })

    @pytest.mark.asyncio
    async def test_malformed_html_returns_empty_without_raising(self, tmp_path):
        config_dir = _write_directives(tmp_path, [{"celex": "32023L1791", "name": "EED"}])
        nim_resp = _mock_response(text=NIM_HTML_NO_STRUCTURE)
        client = _mock_client([nim_resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = EURLexNIMSource()
            results = await source.fetch({
                "source_params": {
                    "config_dir": config_dir,
                    "data_dir": str(tmp_path / "data"),
                }
            })

        assert results == []

    @pytest.mark.asyncio
    async def test_cap_respected(self, tmp_path):
        config_dir = _write_directives(tmp_path, [{"celex": "32023L1791", "name": "EED"}])
        many_measures_html = "<html><body>" + "".join(
            f'<h2>Country{i}</h2><ul><li><a href="/law-{i}">Law {i}</a></li></ul>'
            for i in range(10)
        ) + "</body></html>"
        nim_resp = _mock_response(text=many_measures_html)
        law_resp = _mock_response(text="<html><body>Text.</body></html>")
        client = _mock_client([nim_resp] + [law_resp] * 10)

        with patch("httpx.AsyncClient", return_value=client):
            source = EURLexNIMSource()
            results = await source.fetch({
                "source_params": {
                    "config_dir": config_dir,
                    "data_dir": str(tmp_path / "data"),
                    "max_documents": 4,
                }
            })

        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_dedupe_within_fetch(self, tmp_path):
        config_dir = _write_directives(tmp_path, [{"celex": "32023L1791", "name": "EED"}])
        duplicate_html = """
        <html><body>
        <h2>Sweden</h2>
        <ul>
          <li><a href="/nat-law-se">Lag om energieffektivisering</a></li>
          <li><a href="/nat-law-se">Lag om energieffektivisering</a></li>
        </ul>
        </body></html>
        """
        nim_resp = _mock_response(text=duplicate_html)
        law_resp = _mock_response(text="<html><body>Text.</body></html>")
        client = _mock_client([nim_resp, law_resp])

        with patch("httpx.AsyncClient", return_value=client):
            source = EURLexNIMSource()
            results = await source.fetch({
                "source_params": {
                    "config_dir": config_dir,
                    "data_dir": str(tmp_path / "data"),
                }
            })

        urls = [r.url for r in results]
        assert len(urls) == len(set(urls))
        assert len(results) == 1
