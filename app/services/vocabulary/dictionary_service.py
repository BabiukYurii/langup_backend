"""Bulk import of a general dictionary into the shared `words` table.

The source is a table/txt of "word — translation" pairs (e.g. an EN-UK list),
so no model inference is needed: translations come from the file, and we just
lemmatize the word and upsert the sense. Runs in batches off the request path.
"""

import logging

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.models import Word
from app.repositories.word import WordRepository
from app.schemas.dictionary import DictionaryEntry, DictionaryImportRequest
from app.utils.lemmatize import to_lemma

logger = logging.getLogger(__name__)

# Tried in this order; the first one present in a line splits it (word, translation).
_DELIMITERS = ["\t", "|", ";", " — ", " – ", " - ", "=", ","]
_CHUNK = 500
# Lines per LLM normalization call — small enough to fit the model's context.
_LLM_CHUNK = 40


def content_lines(raw_text: str | None) -> list[str]:
    """Non-empty, non-comment lines of the raw input."""
    return [ln.strip() for ln in (raw_text or "").splitlines() if ln.strip() and not ln.strip().startswith("#")]


class DictionaryImportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.words = WordRepository(session)

    # --- parsing -----------------------------------------------------------

    @staticmethod
    def _split_line(line: str) -> tuple[str, str] | None:
        for d in _DELIMITERS:
            if d in line:
                word, _, translation = line.partition(d)
                word, translation = word.strip(), translation.strip()
                if word and translation:
                    return word, translation
                return None
        return None

    @classmethod
    def parse(cls, data: DictionaryImportRequest) -> list[DictionaryEntry]:
        """Turn the request into clean entries (structured or raw text)."""
        if data.entries:
            return data.entries
        entries: list[DictionaryEntry] = []
        for raw in (data.raw_text or "").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            pair = cls._split_line(line)
            if pair:
                entries.append(DictionaryEntry(word=pair[0], translation=pair[1]))
        return entries

    # --- LLM normalization -------------------------------------------------

    async def normalize_via_llm(
        self, source_language: str, target_language: str, raw_text: str, ai_client
    ) -> list[DictionaryEntry]:
        """Turn messy raw text into clean {word, translation} entries via the LLM.

        The model only reshapes the input into valid JSON — it does not invent
        translations. Sent in small chunks; unparseable chunks are skipped.
        """
        import json

        system = (
            f"You extract vocabulary pairs from a list. Each input line has a word in "
            f"'{source_language}' and its translation in '{target_language}', possibly in a "
            f"messy format. Return ONLY a JSON object: "
            f'{{"entries": [{{"word": "<{source_language} word, base form>", '
            f'"translation": "<{target_language} translation>"}}]}}. '
            f"Do not translate anything yourself; use only what each line already contains. "
            f"Skip lines that are not a word/translation pair."
        )
        lines = content_lines(raw_text)
        entries: list[DictionaryEntry] = []
        for i in range(0, len(lines), _LLM_CHUNK):
            chunk = "\n".join(lines[i : i + _LLM_CHUNK])
            try:
                reply = await ai_client.chat_json(system, chunk, temperature=0.0)
                parsed = json.loads(reply["content"])
                for item in parsed.get("entries", []):
                    word = str(item.get("word", "")).strip()
                    translation = str(item.get("translation", "")).strip()
                    if word and translation:
                        entries.append(DictionaryEntry(word=word[:128], translation=translation[:256]))
            except Exception:  # noqa: BLE001 — one bad chunk must not abort the whole import
                logger.exception("LLM normalization failed for a chunk; skipping it")
        logger.info("LLM normalized %d line(s) into %d entrie(s)", len(lines), len(entries))
        return entries

    # --- import ------------------------------------------------------------

    @staticmethod
    def _merge(definitions, lang: str, translation: str) -> list:
        senses = [d for d in (definitions or []) if d.get("lang") != lang]
        senses.append({"lang": lang, "translation": translation})
        return senses

    async def import_entries(self, source_language: str, target_language: str, entries: list[DictionaryEntry]) -> dict:
        """Upsert every entry into `words`, merging translations. Returns counts."""
        # Lemmatize + dedupe (a later line for the same lemma wins).
        by_lemma: dict[str, str] = {}
        for e in entries:
            by_lemma[to_lemma(e.word, source_language)] = e.translation.strip()

        created = updated = 0
        lemmas = list(by_lemma)
        for i in range(0, len(lemmas), _CHUNK):
            chunk = lemmas[i : i + _CHUNK]
            existing = {w.lemma: w for w in await self.words.get_by_lemmas(chunk, source_language)}
            new_rows = []
            for lemma in chunk:
                translation = by_lemma[lemma]
                word = existing.get(lemma)
                if word:
                    word.definitions = self._merge(word.definitions, target_language, translation)
                    updated += 1
                else:
                    new_rows.append(
                        Word(
                            lemma=lemma,
                            language=source_language,
                            definitions=[{"lang": target_language, "translation": translation}],
                        )
                    )
                    created += 1
            self.session.add_all(new_rows)
            await self.session.flush()
        await self.session.commit()
        logger.info(
            "Dictionary import (%s→%s): %d created, %d updated", source_language, target_language, created, updated
        )
        return {"created": created, "updated": updated}


# --- background dispatch ---------------------------------------------------


async def import_dictionary_in_background(source_language: str, target_language: str, pairs: list) -> None:
    """Fallback runner (FastAPI BackgroundTasks) — opens its own session."""
    from app.database.postgres import async_session

    try:
        async with async_session() as session:
            entries = [DictionaryEntry(word=w, translation=t) for w, t in pairs]
            await DictionaryImportService(session).import_entries(source_language, target_language, entries)
    except Exception:  # noqa: BLE001 — a background job must never crash the process
        logger.exception("Background dictionary import failed")


def schedule_dictionary_import(
    background: BackgroundTasks, source_language: str, target_language: str, entries: list[DictionaryEntry]
) -> None:
    """Queue the import on Celery (survives restarts); fall back to BackgroundTasks."""
    pairs = [[e.word, e.translation] for e in entries]
    if settings.celery.CELERY_ENABLED:
        try:
            from app.celery.tasks.dictionary_tasks import import_dictionary

            import_dictionary.delay(source_language, target_language, pairs)
            return
        except Exception:  # noqa: BLE001 — broker outage must not fail the request
            logger.exception("Could not enqueue dictionary import; running in-process")
    background.add_task(import_dictionary_in_background, source_language, target_language, pairs)


async def normalize_import_in_background(source_language: str, target_language: str, raw_text: str) -> None:
    """Fallback runner for the LLM path: normalize the raw text, then import."""
    from app.database.postgres import async_session
    from app.services.ai.client import AIClient

    try:
        async with async_session() as session:
            service = DictionaryImportService(session)
            entries = await service.normalize_via_llm(source_language, target_language, raw_text, AIClient())
            if entries:
                await service.import_entries(source_language, target_language, entries)
    except Exception:  # noqa: BLE001 — a background job must never crash the process
        logger.exception("Background dictionary normalize+import failed")


def schedule_normalize_import(
    background: BackgroundTasks, source_language: str, target_language: str, raw_text: str
) -> None:
    """Queue LLM normalization + import (Celery, else BackgroundTasks)."""
    if settings.celery.CELERY_ENABLED:
        try:
            from app.celery.tasks.dictionary_tasks import normalize_import_dictionary

            normalize_import_dictionary.delay(source_language, target_language, raw_text)
            return
        except Exception:  # noqa: BLE001 — broker outage must not fail the request
            logger.exception("Could not enqueue dictionary normalize+import; running in-process")
    background.add_task(normalize_import_in_background, source_language, target_language, raw_text)
