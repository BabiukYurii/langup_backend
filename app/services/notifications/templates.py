"""Email bodies. Kept as small self-contained builders (no template files to
ship) — there is only one mail today and it needs no layout engine."""


def verification_email(verify_url: str, full_name: str | None = None) -> tuple[str, str, str]:
    """Return (subject, html, text) for the account-verification email."""
    greeting = f"Hi {full_name}," if full_name else "Hi,"
    subject = "Confirm your LangUp email"
    text = (
        f"{greeting}\n\n"
        "Welcome to LangUp! Please confirm your email address by opening the link below:\n\n"
        f"{verify_url}\n\n"
        "If you didn't create a LangUp account, you can ignore this message.\n"
    )
    html = f"""\
<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:480px;margin:0 auto;color:#1f2933;">
  <h2 style="color:#2563eb;">Welcome to LangUp</h2>
  <p>{greeting}</p>
  <p>Please confirm your email address to start saving and practising words.</p>
  <p style="text-align:center;margin:32px 0;">
    <a href="{verify_url}" style="background:#2563eb;color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;">Confirm my email</a>
  </p>
  <p style="font-size:13px;color:#616e7c;">Or paste this link into your browser:<br><a href="{verify_url}">{verify_url}</a></p>
  <p style="font-size:13px;color:#616e7c;">If you didn't create a LangUp account, you can ignore this message.</p>
</div>"""
    return subject, html, text
