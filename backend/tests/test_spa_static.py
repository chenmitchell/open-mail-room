"""ZEABUR-1: backend-serves-frontend SPA static mount + history fallback.

Covers: app/main.py's `_mount_spa` (SERVE_FRONTEND / FRONTEND_DIST) --
- GET / and GET on an unknown client-side route both serve index.html.
- Real static files (favicon.ico, assets/*) are served as themselves, not
  index.html.
- An unmatched /api/v1/* path still 404s through the normal JSON envelope
  error handler, not the SPA fallback (this is the one case where route
  registration order alone doesn't save you -- see _is_spa_excluded_path).
- /healthz, /readyz, /api/openapi.json are never shadowed by the catch-all.
- The app starts cleanly (no crash) when SERVE_FRONTEND=0, and when
  SERVE_FRONTEND=1 but FRONTEND_DIST doesn't exist / has no index.html.
"""

from __future__ import annotations

from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient


def _write_fake_dist(root: Path) -> Path:
    dist = root / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text(
        "<html><body>OpenMailroom SPA shell</body></html>", encoding="utf-8"
    )
    (dist / "favicon.ico").write_bytes(b"\x00\x01\x02")
    (assets / "index-abc123.js").write_text("console.log('hi');", encoding="utf-8")
    return dist


async def _make_client(app) -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver")


@pytest_asyncio.fixture
async def spa_app(db_engine, tmp_path, monkeypatch):
    dist = _write_fake_dist(tmp_path)
    monkeypatch.setenv("SERVE_FRONTEND", "1")
    monkeypatch.setenv("FRONTEND_DIST", str(dist))

    from app.config import reset_settings_cache

    reset_settings_cache()

    from app.main import create_app

    return create_app()


@pytest_asyncio.fixture
async def spa_client(spa_app):
    async with await _make_client(spa_app) as ac:
        yield ac


async def test_spa_root_serves_index_html(spa_client):
    resp = await spa_client.get("/")
    assert resp.status_code == 200
    assert "OpenMailroom SPA shell" in resp.text


async def test_spa_client_side_route_serves_index_html(spa_client):
    """A Vue-router deep link like /mail/123/detail has no matching backend
    route and no matching file on disk -- must still 200 with the SPA shell
    (history mode fallback), not 404."""
    resp = await spa_client.get("/mail/123/detail")
    assert resp.status_code == 200
    assert "OpenMailroom SPA shell" in resp.text


async def test_spa_serves_real_file_at_dist_root(spa_client):
    resp = await spa_client.get("/favicon.ico")
    assert resp.status_code == 200
    assert resp.content == b"\x00\x01\x02"


async def test_spa_serves_asset_via_static_mount(spa_client):
    resp = await spa_client.get("/assets/index-abc123.js")
    assert resp.status_code == 200
    assert "console.log" in resp.text


async def test_unmatched_api_path_still_json_404_not_index_html(spa_client):
    resp = await spa_client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["data"] is None
    assert body["error"]["code"]
    assert "spa shell" not in resp.text.lower()


async def test_healthz_not_intercepted_by_spa_fallback(spa_client):
    resp = await spa_client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_readyz_not_intercepted_by_spa_fallback(spa_client):
    resp = await spa_client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] is True


async def test_api_openapi_json_not_intercepted_by_spa_fallback(spa_client):
    resp = await spa_client.get("/api/openapi.json")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")


async def test_existing_api_endpoint_unaffected_by_spa_mount(spa_client):
    """A real, existing API route (list carriers) must still be routed to
    the real handler with the SPA mounted, not shadowed by the SPA
    fallback. Unauthenticated -> 401 with the normal JSON error envelope
    (per test_carriers.py::test_list_carriers_requires_auth) -- the
    important assertion is that this is *not* a 200 with the SPA shell."""
    resp = await spa_client.get("/api/v1/carriers")
    assert resp.status_code == 401
    body = resp.json()
    assert body["data"] is None
    assert body["error"]["code"]


@pytest_asyncio.fixture
async def missing_dist_app(db_engine, tmp_path, monkeypatch):
    monkeypatch.setenv("SERVE_FRONTEND", "1")
    monkeypatch.setenv("FRONTEND_DIST", str(tmp_path / "does-not-exist"))

    from app.config import reset_settings_cache

    reset_settings_cache()

    from app.main import create_app

    return create_app()


async def test_app_starts_when_serve_frontend_enabled_but_dist_missing(missing_dist_app):
    """SERVE_FRONTEND=1 with no built frontend (e.g. API-only dev checkout)
    must not crash app startup -- just skip the static mount."""
    async with await _make_client(missing_dist_app) as ac:
        resp = await ac.get("/healthz")
        assert resp.status_code == 200
        # No SPA mount at all -> unknown GET / falls through to a plain
        # (non-JSON-envelope) Starlette 404, not index.html.
        resp2 = await ac.get("/")
        assert resp2.status_code == 404


@pytest_asyncio.fixture
async def serve_frontend_disabled_app(db_engine, tmp_path, monkeypatch):
    dist = _write_fake_dist(tmp_path)
    monkeypatch.setenv("SERVE_FRONTEND", "0")
    monkeypatch.setenv("FRONTEND_DIST", str(dist))

    from app.config import reset_settings_cache

    reset_settings_cache()

    from app.main import create_app

    return create_app()


async def test_app_starts_with_serve_frontend_disabled(serve_frontend_disabled_app):
    """SERVE_FRONTEND=0 must not mount anything, even if a valid dist dir
    exists -- and the app must still start and serve the API normally."""
    async with await _make_client(serve_frontend_disabled_app) as ac:
        resp = await ac.get("/healthz")
        assert resp.status_code == 200
        resp2 = await ac.get("/")
        assert resp2.status_code == 404
        resp3 = await ac.get("/api/v1/carriers")
        assert resp3.status_code == 401
        assert resp3.json()["data"] is None
