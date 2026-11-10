"""Coming back from Stripe lands in the app, not in a browser tab.

Stripe Checkout only accepts http(s) in success_url, so it cannot be pointed at
"langup://" directly. It is pointed at a page of ours, and that URL is
registered as an Android App Link — so on a verified install the OS hands it to
the app and the page is never drawn. The page exists for every other case: an
older Android, a differently signed build, iOS, a desktop browser.
"""

from pathlib import Path

import pytest

from app.core import settings
from app.services.payments.return_page import assetlinks, is_known_outcome, render_return_page

WEBAPP = Path(__file__).resolve().parent.parent / "webapp" / "index.html"
needs_webapp = pytest.mark.skipif(not WEBAPP.is_file(), reason="no Flutter build to serve")


# --- where Stripe is told to send people -----------------------------------


def test_the_return_paths_are_ours_not_the_web_cabinet():
    """They used to end at /app/index.html, which is a browser page — the app
    user was simply left there."""
    assert settings.payments.SUCCESS_PATH == "/app/checkout/success"
    assert settings.payments.CANCEL_PATH == "/app/checkout/cancel"
    assert settings.payments.PORTAL_RETURN_PATH == "/app/checkout/portal"


async def test_the_portal_returns_the_same_way(monkeypatch):
    """Managing a subscription stranded app users in a browser just as badly as
    paying did; it was hard-coded rather than configured."""
    import inspect

    from app.services.payments import billing_service

    source = inspect.getsource(billing_service.BillingService.start_portal)
    assert "PORTAL_RETURN_PATH" in source
    assert "/app/index.html" not in source


# --- the bridge page -------------------------------------------------------


@pytest.mark.parametrize("outcome", ["success", "cancel", "portal"])
def test_every_outcome_offers_the_app(outcome):
    page = render_return_page(outcome)
    assert f"{settings.app.DEEP_LINK_SCHEME}:///app/checkout/{outcome}" in page


def test_the_scheme_link_has_the_same_path_as_the_app_link():
    """An empty host keeps the path identical to the https one, so the client
    needs a single route rather than two kept in step."""
    from urllib.parse import urlsplit

    target = urlsplit(f"{settings.app.DEEP_LINK_SCHEME}:///app/checkout/success")
    assert target.netloc == ""
    assert target.path == settings.payments.SUCCESS_PATH


def test_the_page_tries_once_and_still_shows_a_button():
    """A redirect the browser silently blocks is worse than a button somebody
    can press, so the button is not hidden behind a timer."""
    page = render_return_page("success")
    assert "location.replace" in page
    assert "Open LangUp" in page


def test_a_cancelled_checkout_says_nothing_was_charged():
    assert "Nothing was charged" in render_return_page("cancel")


@pytest.mark.parametrize("outcome", ["", "paid", "../etc", "success/x"])
def test_an_unknown_outcome_is_not_a_page(outcome):
    assert is_known_outcome(outcome) is False


@needs_webapp
async def test_the_route_serves_the_page(client):
    resp = await client.get("/app/checkout/success")

    assert resp.status_code == 200
    assert "checkout/success" in resp.text
    # Never cached: it carries a one-off outcome, not an asset.
    assert "no-cache" in resp.headers.get("cache-control", "")


@needs_webapp
async def test_an_unknown_outcome_is_a_404(client):
    assert (await client.get("/app/checkout/nonsense")).status_code == 404


# --- what Android reads to allow the jump ----------------------------------


def test_no_fingerprint_means_no_statement(monkeypatch):
    """A statement with no certificate is a verification that fails and then
    gets cached — worse than having none at all."""
    monkeypatch.setattr(settings.app, "ANDROID_SHA256_FINGERPRINTS", "")
    assert assetlinks() == []


def test_a_configured_fingerprint_produces_a_statement(monkeypatch):
    monkeypatch.setattr(settings.app, "ANDROID_SHA256_FINGERPRINTS", "AA:BB:CC")

    [statement] = assetlinks()
    assert statement["relation"] == ["delegate_permission/common.handle_all_urls"]
    assert statement["target"]["package_name"] == settings.app.ANDROID_PACKAGE_NAME
    assert statement["target"]["sha256_cert_fingerprints"] == ["AA:BB:CC"]


def test_several_fingerprints_are_all_listed(monkeypatch):
    """Debug, release and Play App Signing are three different certificates,
    and leaving one out silently stops verification for that build."""
    monkeypatch.setattr(settings.app, "ANDROID_SHA256_FINGERPRINTS", "aa:bb , cc:dd")

    assert assetlinks()[0]["target"]["sha256_cert_fingerprints"] == ["AA:BB", "CC:DD"]


async def test_the_well_known_route_404s_until_configured(client, monkeypatch):
    monkeypatch.setattr(settings.app, "ANDROID_SHA256_FINGERPRINTS", "")
    assert (await client.get("/.well-known/assetlinks.json")).status_code == 404


async def test_the_well_known_route_serves_the_statement(client, monkeypatch):
    monkeypatch.setattr(settings.app, "ANDROID_SHA256_FINGERPRINTS", "AA:BB:CC")

    resp = await client.get("/.well-known/assetlinks.json")

    assert resp.status_code == 200
    assert resp.json()[0]["target"]["package_name"] == settings.app.ANDROID_PACKAGE_NAME
