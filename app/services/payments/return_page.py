"""The page Stripe sends a customer back to.

Stripe Checkout only accepts http(s) in `success_url`, so it cannot be pointed
at "langup://" directly. It is pointed here instead, and this URL is registered
as an Android App Link — so on a verified install Android hands it to the app
and this page is never drawn at all.

It is drawn when verification does not apply: an older Android, a build signed
with a different key, iOS, or a desktop browser. Then it tries the scheme once
and offers a button, because a redirect a browser silently blocks is worse than
a button somebody can press.

The copy is short and in English on purpose. The server has no idea which of
the eight interface languages the reader uses, and on the path that matters
nobody sees this page for longer than a blink.
"""

from app.core import settings

_OUTCOMES = {
    "success": ("Payment complete", "Returning you to LangUp…"),
    "cancel": ("Checkout cancelled", "Nothing was charged."),
    "portal": ("All set", "Returning you to LangUp…"),
}


def is_known_outcome(outcome: str) -> bool:
    return outcome in _OUTCOMES


def render_return_page(outcome: str) -> str:
    """The bridge page for one checkout outcome."""
    title, note = _OUTCOMES[outcome]
    # Three slashes, i.e. an empty host, so the PATH is identical to the App
    # Link's: "/app/checkout/success" either way. With a host ("scheme://
    # checkout/success") the router would be handed "/success" instead and the
    # two routes would have to be kept in sync for no reason.
    target = f"{settings.app.DEEP_LINK_SCHEME}:///app/checkout/{outcome}"
    web_fallback = "/app/"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · LangUp</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{
    margin: 0; min-height: 100vh; display: grid; place-items: center;
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    background: #f4f6fb; color: #1f2733; padding: 24px;
  }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #0f1420; color: #e8ecf3; }}
    .card {{ background: #171e2e !important; border-color: #242d40 !important; }}
  }}
  .card {{
    background: #fff; border: 1px solid #e6eaf1; border-radius: 16px;
    padding: 32px; max-width: 420px; width: 100%; text-align: center;
  }}
  h1 {{ font-size: 20px; margin: 0 0 8px; }}
  p {{ margin: 0 0 24px; opacity: .7; font-size: 15px; }}
  a.btn {{
    display: block; padding: 14px; border-radius: 12px; text-decoration: none;
    background: #3b5bdb; color: #fff; font-weight: 600;
  }}
  a.alt {{ display: block; margin-top: 16px; color: #3b5bdb; font-size: 14px; }}
</style>
</head>
<body>
  <div class="card">
    <h1>{title}</h1>
    <p>{note}</p>
    <a class="btn" href="{target}">Open LangUp</a>
    <a class="alt" href="{web_fallback}">Continue in the browser</a>
  </div>
<script>
  // One automatic attempt, straight away. A browser that blocks it leaves the
  // button above, which is why the button is not hidden behind a timer.
  location.replace({target!r});
</script>
</body>
</html>"""


def assetlinks() -> list[dict]:
    """Digital Asset Links, which is how Android verifies an App Link.

    Empty when no fingerprint is configured: serving a statement with no
    certificate in it would be a broken verification Android caches, which is
    worse than no statement at all.
    """
    fingerprints = settings.app.android_fingerprints
    if not fingerprints:
        return []
    return [
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": settings.app.ANDROID_PACKAGE_NAME,
                "sha256_cert_fingerprints": fingerprints,
            },
        }
    ]
