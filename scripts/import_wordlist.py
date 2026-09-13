#!/usr/bin/env python3
"""Load a coursebook wordlist (xlsx) into one user's vocabulary.

Runs the REAL capture path rather than writing rows itself. It ships a small
program to the server and executes it inside the API container, where it calls
`CaptureService.capture()` and then queues exactly the jobs the router queues —
translation, audio warm-up, and that word's own full set of exercises. Bypassing
HTTP is only about authentication; nothing downstream of it is skipped, so an
imported word is indistinguishable from one saved by hand.

Budget it before starting: a word costs roughly a translation, two clips and
three or four generated exercises, so a unit of ~45 words keeps the model busy
for well over an hour. It all happens in the background — nothing here waits
for it — but the box is shared with whoever is practising.

Sheet layout (every "Unit N" tab in the Speakout wordlists):

    A Vocabulary | B Part of speech | C Pronunciation | D Definition | E Example

Column A is the word and column E the sentence it is saved with. The definition
is ignored on purpose: the capture API has nowhere to put an English gloss, and
the word gets a translation from the model instead.

Usage:
    python scripts/import_wordlist.py --sheet "Unit 1" --dry-run
    python scripts/import_wordlist.py --sheet "Unit 2"
    python scripts/import_wordlist.py --all

Needs openpyxl locally:  uv run --with openpyxl python scripts/import_wordlist.py ...
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_XLSX = Path.home() / "Downloads" / "SO3_B2_Wordlist.xlsx"
SERVER = "piatek@100.85.70.77"
CONTAINER = "langup-api"
USER_EMAIL = "yuriybabiyk@gmail.com"
LANGUAGE = "en"
SOURCE_TITLE = "Speakout 3rd Edition B2 Wordlist"

# Morphemes, not vocabulary: "dis-" and "re-" are not words anyone learns as
# words, and the model would refuse them anyway.
SKIP_PARTS_OF_SPEECH = {"prefix", "suffix"}


def read_sheet(xlsx: Path, sheet: str) -> list[dict]:
    """Column A + column E of one sheet, deduplicated, prefixes dropped."""
    import openpyxl

    workbook = openpyxl.load_workbook(xlsx, data_only=True, read_only=True)
    if sheet not in workbook.sheetnames:
        sys.exit(f"no sheet {sheet!r}; found: {', '.join(workbook.sheetnames)}")

    entries: list[dict] = []
    seen: set[str] = set()
    for row in workbook[sheet].iter_rows(min_row=2, values_only=True):
        word = (row[0] or "").strip() if isinstance(row[0], str) else ""
        if not word:
            continue
        part = (row[1] or "").strip().lower() if isinstance(row[1], str) else ""
        if part in SKIP_PARTS_OF_SPEECH:
            continue
        if word.lower() in seen:  # the same word can appear in two lessons
            continue
        seen.add(word.lower())
        sentence = (row[4] or "").strip() if isinstance(row[4], str) else ""
        entries.append({"word": word, "sentence": sentence})
    return entries


# The program that actually runs, inside the API container. Kept as a string so
# the whole import is one command and nothing has to be copied to the server.
REMOTE_PROGRAM = """
import asyncio, json, sys

ENTRIES = json.loads({entries!r})
USER_EMAIL = {email!r}
LANGUAGE = {language!r}
SOURCE_TITLE = {source_title!r}

async def main() -> int:
    from app.celery.tasks.ai_tasks import generate_word_exercises, translate_word
    from app.celery.tasks.audio_tasks import warm_word_audio
    from app.core import settings
    from app.database.postgres import async_session
    from app.repositories.user import UserRepository
    from app.routers.audio import chosen_voice
    from app.schemas.capture import CaptureRequest
    from app.services.capture_service import CaptureService

    added = skipped = 0
    async with async_session() as session:
        user = await UserRepository(session).get_by_email(USER_EMAIL)
        if not user:
            print("NO SUCH USER", USER_EMAIL)
            return 1
        voice = chosen_voice(user, LANGUAGE, None)
        service = CaptureService(session)

        for index, entry in enumerate(ENTRIES, 1):
            word, sentence = entry["word"], entry["sentence"]
            try:
                result = await service.capture(
                    user.id,
                    CaptureRequest(
                        word=word,
                        language=LANGUAGE,
                        sentence=sentence or None,
                        source_title=SOURCE_TITLE,
                    ),
                )
            except Exception as exc:
                skipped += 1
                print(f"{{index:3}}/{{len(ENTRIES)}} SKIP {{word!r}}: {{type(exc).__name__}}: {{exc}}", flush=True)
                continue

            added += 1
            print(f"{{index:3}}/{{len(ENTRIES)}} ok   {{word!r}} -> {{result.lemma!r}}", flush=True)

            # The same jobs the router queues after a capture, so an imported
            # word ends up with a translation, a spoken clip and its own cards.
            if settings.exercises.TRANSLATE_ON_CAPTURE:
                translate_word.delay(user.id, str(result.word_uuid))
            if settings.audio.AUDIO_ENABLED:
                texts = [result.lemma] + ([sentence] if sentence else [])
                warm_word_audio.delay(texts, LANGUAGE, voice)
            # Per word, not one pool refill at the end: the pool stops at a
            # global target, which is exactly how forty imported words ended up
            # sharing five exercises between them.
            if settings.exercises.EXERCISE_POOL_AUTOFILL:
                generate_word_exercises.delay(user.id, str(result.uuid))

    print(f"\\ndone: {{added}} added, {{skipped}} skipped")
    return 0

sys.exit(asyncio.run(main()))
"""


def run_remote(entries: list[dict]) -> int:
    program = REMOTE_PROGRAM.format(
        entries=json.dumps(entries, ensure_ascii=False),
        email=USER_EMAIL,
        language=LANGUAGE,
        source_title=SOURCE_TITLE,
    )
    completed = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", SERVER, f"docker exec -i {CONTAINER} python -"],
        input=program.encode("utf-8"),
    )
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet", help='e.g. "Unit 2"')
    parser.add_argument("--all", action="store_true", help="every Unit sheet, in order")
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    parser.add_argument("--dry-run", action="store_true", help="print what would be sent")
    args = parser.parse_args()

    if not args.sheet and not args.all:
        parser.error("pass --sheet or --all")
    if not args.xlsx.is_file():
        sys.exit(f"not found: {args.xlsx}")

    if args.all:
        import openpyxl

        names = [n for n in openpyxl.load_workbook(args.xlsx, read_only=True).sheetnames if n.startswith("Unit")]
    else:
        names = [args.sheet]

    for name in names:
        entries = read_sheet(args.xlsx, name)
        print(f"\n=== {name}: {len(entries)} entries ===")
        if args.dry_run:
            for entry in entries:
                print(f"   {entry['word']!r:<38} | {entry['sentence'][:70]}")
            continue
        code = run_remote(entries)
        if code != 0:
            return code
    return 0


if __name__ == "__main__":
    sys.exit(main())
