"""The cabinet's static pages.

Cloudflare rewrites our `no-cache` into its own four-hour browser TTL, so a
deploy used to leave browsers running yesterday's scripts against today's
markup. Asset URLs therefore carry a version derived from the files themselves.

Which cabinet is served depends on whether a Flutter build has been dropped
into webapp/, so these pin the one they mean instead of taking whatever happens
to be on this machine's disk — otherwise a developer with a build in place gets
red tests that say nothing about their change.
"""

import re

import pytest
from httpx import ASGITransport, AsyncClient

import app.main as main_module


@pytest.fixture
async def legacy_client(monkeypatch):
    """A client for the original HTML cabinet, whatever else is on disk."""
    monkeypatch.setattr(main_module, "_WEBAPP_DIR", main_module._FRONTEND_DIR / "__absent__")
    transport = ASGITransport(app=main_module.create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_page_is_served_with_a_version_stamp(legacy_client):
    resp = await legacy_client.get("/app/practice.html")

    assert resp.status_code == 200
    versions = set(re.findall(r"\?v=([a-z0-9]+)", resp.text))
    assert versions, "asset URLs carry no version"
    assert "dev" not in versions, "the placeholder reached the browser"
    assert len(versions) == 1, "one deploy should produce one version"


async def test_pages_are_not_cached(legacy_client):
    resp = await legacy_client.get("/app/practice.html")
    assert "no-cache" in resp.headers["cache-control"]


async def test_assets_are_not_cached(legacy_client):
    resp = await legacy_client.get("/app/practice.js")
    assert resp.status_code == 200
    assert "no-cache" in resp.headers["cache-control"]


async def test_index_is_served_at_the_root(legacy_client):
    assert (await legacy_client.get("/app/")).status_code == 200


async def test_unknown_page_is_404(legacy_client):
    assert (await legacy_client.get("/app/nope.html")).status_code == 404


async def test_page_name_cannot_escape_the_frontend_directory(legacy_client):
    assert (await legacy_client.get("/app/..%2f..%2fetc%2fpasswd.html")).status_code == 404


# --- security headers --------------------------------------------------------


async def test_security_headers_are_present(client):
    resp = await client.get("/api/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "max-age" in resp.headers["strict-transport-security"]
    assert "referrer-policy" in resp.headers


# --- the Flutter cabinet -----------------------------------------------------


@pytest.fixture
async def flutter_client(tmp_path, monkeypatch):
    """A client for the Flutter build, from a minimal stand-in for one."""
    build = tmp_path / "webapp"
    build.mkdir()
    (build / "index.html").write_text('<base href="/app/">', encoding="utf-8")
    (build / "main.dart.js").write_text("// pretend bundle", encoding="utf-8")
    monkeypatch.setattr(main_module, "_WEBAPP_DIR", build)
    transport = ASGITransport(app=main_module.create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_a_build_replaces_the_legacy_cabinet(flutter_client):
    """Dropping a build in is the whole switch — no code change, no redeploy."""
    resp = await flutter_client.get("/app/")
    assert resp.status_code == 200
    assert "/app/v/" in resp.text


async def test_assets_move_onto_a_versioned_path(flutter_client):
    """Flutter names its bundle the same every build, so the URL has to carry
    the version instead — otherwise a cache is entitled to serve the old one."""
    index = (await flutter_client.get("/app/")).text
    stamp = re.search(r"/app/v/([a-f0-9]+)/", index).group(1)

    resp = await flutter_client.get(f"/app/v/{stamp}/main.dart.js")
    assert resp.status_code == 200
    assert "immutable" in resp.headers["cache-control"]


async def test_the_stamp_follows_the_build(flutter_client, tmp_path):
    before = (await flutter_client.get("/app/")).text
    (tmp_path / "webapp" / "main.dart.js").write_text("// a new build", encoding="utf-8")
    after = (await flutter_client.get("/app/")).text
    assert before != after, "a new build must produce a new asset URL"


async def test_the_index_itself_is_never_cached(flutter_client):
    """It is what carries the current stamp; caching it would pin the old one."""
    resp = await flutter_client.get("/app/")
    assert "no-cache" in resp.headers["cache-control"]


async def test_an_old_stamp_still_serves_the_app(flutter_client):
    """A browser holding a stale index must get a working app, not a blank page."""
    resp = await flutter_client.get("/app/v/000000000000/main.dart.js")
    assert resp.status_code == 200


async def test_an_asset_path_cannot_escape_the_build(flutter_client):
    for path in ("../../.env", "..%2f..%2f.env"):
        assert (await flutter_client.get(f"/app/v/abc/{path}")).status_code == 404
