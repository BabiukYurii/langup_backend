"""The profile picker's demo phrase, per language.

Read from the cabinet's own i18n files — the same JSON the browser fetches — so
a warm-up hashes to exactly what the page will ask for. Reading them from
anywhere else would fill the cache under keys nobody looks up.

Shared by the warm-up script and the sweep: the warm-up renders these in every
voice, and the sweep has to know to spare them, since the picker legitimately
offers all ten voices to everyone regardless of what anybody has chosen.
"""

import json
from pathlib import Path

DEMO_KEY = "settings.voice_demo"
I18N_DIR = Path(__file__).resolve().parents[3] / "frontend" / "i18n"


def demo_phrases() -> dict[str, str]:
    """language -> the demo phrase the picker speaks."""
    phrases: dict[str, str] = {}
    if not I18N_DIR.is_dir():
        return phrases
    for path in sorted(I18N_DIR.glob("*.json")):
        try:
            text = json.loads(path.read_text(encoding="utf-8")).get(DEMO_KEY)
        except (OSError, ValueError):
            continue
        if text:
            phrases[path.stem] = text
    return phrases


def demo_texts() -> set[str]:
    """Just the phrases, for membership checks."""
    return set(demo_phrases().values())
