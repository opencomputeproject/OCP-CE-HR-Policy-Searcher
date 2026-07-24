"""Tests for serving the built React app from the FastAPI process.

Production runs one process on one port: FastAPI serves /api/* as always,
and — when a built frontend exists on disk — also serves the SPA's static
assets and falls back to index.html for client-side routes. Every
dev/test setup today has no build directory, so that path must stay a
complete no-op: byte-identical to current behavior.

Two layers are tested:
  - ``mount_frontend()`` in isolation, against a bare FastAPI() app, for
    the mounting logic itself (fast, no reload gymnastics).
  - the real ``src.api.app`` module, reloaded with ``OCP_STATIC_DIR`` set
    to a tmp fake build dir, proving the wiring in app.py actually serves
    /, a nested SPA route, and a static asset while /api/* and /health
    keep working.
"""

import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_fake_build(tmp_path):
    build_dir = tmp_path / "build"
    js_dir = build_dir / "static" / "js"
    js_dir.mkdir(parents=True)
    (build_dir / "index.html").write_text(
        "<html><body>SPA shell</body></html>", encoding="utf-8"
    )
    (js_dir / "main.abc123.js").write_text("console.log('hi');", encoding="utf-8")
    return build_dir


# ---------------------------------------------------------------------------
# mount_frontend() in isolation
# ---------------------------------------------------------------------------

class TestMountFrontendUnit:
    def test_returns_false_when_dir_missing(self, tmp_path):
        from src.api.static_site import mount_frontend

        app = FastAPI()

        @app.get("/")
        def root():
            return {"service": "test"}

        routes_before = list(app.router.routes)
        mounted = mount_frontend(app, tmp_path / "does-not-exist")

        assert mounted is False
        assert list(app.router.routes) == routes_before

    def test_returns_true_and_serves_index_when_dir_exists(self, tmp_path):
        from src.api.static_site import mount_frontend

        build_dir = _make_fake_build(tmp_path)
        app = FastAPI()

        @app.get("/health")
        def health():
            return {"status": "ok"}

        mounted = mount_frontend(app, build_dir)
        assert mounted is True

        client = TestClient(app)
        assert client.get("/").text == "<html><body>SPA shell</body></html>"
        assert client.get("/health").json() == {"status": "ok"}

    def test_spa_fallback_and_asset_serving(self, tmp_path):
        from src.api.static_site import mount_frontend

        build_dir = _make_fake_build(tmp_path)
        app = FastAPI()
        mount_frontend(app, build_dir)
        client = TestClient(app)

        # Unknown client-side route falls back to index.html (SPA routing).
        spa_response = client.get("/some/spa/route")
        assert spa_response.status_code == 200
        assert spa_response.text == "<html><body>SPA shell</body></html>"

        # A real asset under static/ is served as itself, not index.html.
        asset_response = client.get("/static/js/main.abc123.js")
        assert asset_response.status_code == 200
        assert "console.log" in asset_response.text

    def test_unknown_api_path_stays_404_not_index_html(self, tmp_path):
        """A genuine 404 under /api/* must not be masked by the SPA fallback."""
        from src.api.static_site import mount_frontend

        build_dir = _make_fake_build(tmp_path)
        app = FastAPI()

        @app.get("/api/domains")
        def domains():
            return []

        mount_frontend(app, build_dir)
        client = TestClient(app)

        response = client.get("/api/no-such-route")
        assert response.status_code == 404
        assert "SPA shell" not in response.text

        # The real /api route still resolves normally.
        assert client.get("/api/domains").json() == []


# ---------------------------------------------------------------------------
# The real app, reloaded with OCP_STATIC_DIR set to a fake build dir
# ---------------------------------------------------------------------------

@pytest.fixture
def app_module():
    import src.api.app as module
    yield module


class TestAppServesStaticFrontendWhenPresent:
    def test_without_build_dir_root_returns_pinned_json(self, tmp_path, monkeypatch, app_module):
        """Pin today's behavior: no build dir -> / returns the JSON info route."""
        monkeypatch.delenv("OCP_STATIC_DIR", raising=False)
        importlib.reload(app_module)
        try:
            client = TestClient(app_module.app)
            response = client.get("/")
            assert response.status_code == 200
            data = response.json()
            assert data["service"] == "OCP CE HR Policy Searcher"
            assert "endpoints" in data
        finally:
            importlib.reload(app_module)

    def test_with_build_dir_serves_frontend_and_keeps_api(
        self, tmp_path, monkeypatch, app_module
    ):
        build_dir = _make_fake_build(tmp_path)
        monkeypatch.setenv("OCP_STATIC_DIR", str(build_dir))
        importlib.reload(app_module)
        try:
            client = TestClient(app_module.app)

            # / and unknown SPA routes serve the built index.html.
            assert client.get("/").text == "<html><body>SPA shell</body></html>"
            spa = client.get("/some/spa/route")
            assert spa.status_code == 200
            assert spa.text == "<html><body>SPA shell</body></html>"

            # The nested static asset serves as itself.
            asset = client.get("/static/js/main.abc123.js")
            assert asset.status_code == 200
            assert "console.log" in asset.text

            # /api/* and /health are untouched.
            health = client.get("/health")
            assert health.status_code == 200
            assert health.json()["status"] == "ok"
        finally:
            monkeypatch.delenv("OCP_STATIC_DIR", raising=False)
            importlib.reload(app_module)


class TestPathTraversal:
    def test_dot_segments_cannot_escape_build_dir(self, tmp_path):
        """A traversal path must never serve files outside the build dir."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api.static_site import mount_frontend

        build = tmp_path / "build"
        build.mkdir()
        (build / "index.html").write_text("<html>app</html>", encoding="utf-8")
        secret = tmp_path / "secret.txt"
        secret.write_text("ANTHROPIC_API_KEY=sk-oops", encoding="utf-8")

        app = FastAPI()
        assert mount_frontend(app, build)
        client = TestClient(app)

        for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/a/../../secret.txt"):
            r = client.get(path)
            assert "sk-oops" not in r.text, f"traversal served secret via {path}"
