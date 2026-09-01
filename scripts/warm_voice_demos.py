"""One-off: pre-render the profile picker's demo phrase in every voice.

The picker lets a learner audition ten voices in whichever languages they
study. Each first play costs about a second of synthesis, so without this the
very first person to open the picker pays that cost ten times over while
deciding. Rendering all of them once fills the shared cache, and every learner
after that hears each voice instantly.

The phrases are read from the cabinet's own i18n files — the same JSON the
browser fetches — so the text hashes identically to what the page will send.
Reading them from anywhere else would warm clips under keys nobody looks up.

Run inside the api container:

    docker exec -w /app -e PYTHONPATH=/app langup-api python scripts/warm_voice_demos.py

Safe to re-run: anything already cached is skipped without touching the gateway.
"""

import asyncio
import sys
import time

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import settings
from app.repositories.audio_clip import AudioClipRepository
from app.services.ai.client import AIClient
from app.services.audio.demos import demo_phrases
from app.services.audio.service import AudioService
from app.services.audio.storage import get_audio_storage


async def main() -> int:
    phrases = demo_phrases()
    voices = settings.audio.available_voices
    if not phrases or not voices:
        print("nothing to warm: no demo phrases or no voices configured")
        return 1

    total = len(phrases) * len(voices)
    print(f"warming {len(phrases)} language(s) x {len(voices)} voice(s) = {total} clips\n")

    engine = create_async_engine(settings.db.url, connect_args=settings.db.connect_args, pool_pre_ping=True)
    made = hit = failed = 0
    started = time.perf_counter()

    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        service = AudioService(AudioClipRepository(session), get_audio_storage(), AIClient())
        for language, phrase in phrases.items():
            for voice in voices:
                label = f"{language} {voice}"
                try:
                    t0 = time.perf_counter()
                    clip, cached = await service.get_or_create(phrase, language, voice)
                    took = time.perf_counter() - t0
                except Exception as e:  # noqa: BLE001 — one bad clip must not stop the run
                    failed += 1
                    print(f"  {label:8} FAILED  {e}")
                    continue
                if cached:
                    hit += 1
                    print(f"  {label:8} cached")
                else:
                    made += 1
                    print(f"  {label:8} {clip.size_bytes / 1024:5.1f} KB  {clip.duration_ms:5} ms  {took:4.1f}s")

    await engine.dispose()
    elapsed = time.perf_counter() - started
    print(f"\nsynthesized {made}, already cached {hit}, failed {failed} in {elapsed / 60:.1f} min")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
