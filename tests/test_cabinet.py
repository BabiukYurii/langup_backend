"""The cabinet's static pages.

Cloudflare rewrites our `no-cache` into its own four-hour browser TTL, so a
deploy used to leave browsers running yesterday's scripts against today's
markup. Asset URLs therefore carry a version derived from the files themselves.
"""

import re


async def test_page_is_served_with_a_version_stamp(client):
    resp = await client.get("/app/practice.html")

    assert resp.status_code == 200
    versions = set(re.findall(r"\?v=([a-z0-9]+)", resp.text))
    assert versions, "asset URLs carry no version"
    assert "dev" not in versions, "the placeholder reached the browser"
    assert len(versions) == 1, "one deploy should produce one version"


async def test_pages_are_not_cached(client):
    resp = await client.get("/app/practice.html")
    assert "no-cache" in resp.headers["cache-control"]


async def test_assets_are_not_cached(client):
    resp = await client.get("/app/practice.js")
    assert resp.status_code == 200
    assert "no-cache" in resp.headers["cache-control"]


async def test_index_is_served_at_the_root(client):
    assert (await client.get("/app/")).status_code == 200


async def test_unknown_page_is_404(client):
    assert (await client.get("/app/nope.html")).status_code == 404


async def test_page_name_cannot_escape_the_frontend_directory(client):
    assert (await client.get("/app/..%2f..%2fetc%2fpasswd.html")).status_code == 404
