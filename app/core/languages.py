"""Languages the product supports.

The AI model handles these well and the cabinet's dropdowns offer exactly these
(Russian is intentionally excluded). Language detection is constrained to this
set so a stray guess can't create words under an unsupported language.
"""

SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"uk", "pl", "en", "de", "es", "fr", "it", "pt"})


def is_supported(code: str | None) -> bool:
    return bool(code) and code in SUPPORTED_LANGUAGES
