from app.models import WordTranslation
from app.repositories.base import BaseRepository
from app.services.songs.translation_keys import context_hash, normalize_word


class WordTranslationRepository(BaseRepository[WordTranslation]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=WordTranslation)

    async def get_cached(self, word: str, source: str, target: str, line: str | None) -> str | None:
        """The stored gloss for this word in this context, or None."""
        row = await self.get_one(
            word=normalize_word(word),
            source_language=source.lower(),
            target_language=target.lower(),
            context_hash=context_hash(line),
        )
        return row.translation if row else None

    async def remember(self, word: str, source: str, target: str, line: str | None, translation: str) -> None:
        """Store a gloss, ignoring a row another worker wrote first.

        Two learners can tap the same word in the same second, and the warmer
        can be working on a song someone is reading right now. The unique key
        makes that harmless — whoever lands second simply keeps the existing
        row, because both answers are for the same question.
        """
        key = {
            "word": normalize_word(word),
            "source_language": source.lower(),
            "target_language": target.lower(),
            "context_hash": context_hash(line),
        }
        if await self.get_one(**key):
            return
        await self.create_one({**key, "translation": translation[:512]})
