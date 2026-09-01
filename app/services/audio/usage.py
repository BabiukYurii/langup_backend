"""Which (language, voice) pairs anyone can still be served.

The clip cache is shared: a row is keyed by what was said and how, never by who
asked. That is what makes it cheap — but it also means one learner switching
voice does not make their old clips disposable, because another learner may be
listening to that same voice.

So "can this be deleted" is not a per-user question. It is: is there anybody
left who would be served this pair? This module answers that, and it lives
apart from AudioService for the same reason the voice preference does — the
service caches by voice and has no business knowing about users.
"""

from sqlalchemy import select

from app.core import settings
from app.models import User
from app.services.audio.keys import LEGACY_VOICE_PREF_KEY, VOICES_PREF_KEY


async def voices_in_use(session) -> set[tuple[str, str]]:
    """Every (language, voice) a request could still resolve to today.

    Three sources, and all three matter:
      * what each learner explicitly chose,
      * the single voice the first cut stored account-wide, still honoured,
      * the configured default for every language — what a learner who has
        chosen nothing hears, which is most of them.
    """
    available = set(settings.audio.available_voices)
    in_use = {(language, voice) for language, voice in settings.audio.voice_map.items()}

    result = await session.execute(select(User.preferences))
    for prefs in result.scalars().all():
        if not prefs:
            continue

        chosen = prefs.get(VOICES_PREF_KEY)
        if isinstance(chosen, dict):
            for language, voice in chosen.items():
                if voice in available:
                    in_use.add((str(language).lower()[:2], voice))
            continue

        legacy = prefs.get(LEGACY_VOICE_PREF_KEY)
        if legacy in available:
            # Applied to every language, exactly as the router resolves it.
            in_use.update((language, legacy) for language in settings.audio.voice_map)

    return in_use
