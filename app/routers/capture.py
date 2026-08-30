from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, status

from app.core import settings
from app.dependencies import CaptureServiceDep, CurrentUserDep
from app.schemas.capture import CaptureRequest, LanguageCountOut, UserWordDetailOut, UserWordOut
from app.schemas.pagination import Page
from app.services.audio.keys import VOICE_PREF_KEY
from app.services.learning.background import (
    schedule_audio_warmup,
    schedule_refill,
    schedule_translation,
)

router = APIRouter(prefix="/vocabulary", tags=["Vocabulary"])


@router.post("", response_model=UserWordOut, status_code=status.HTTP_201_CREATED)
async def capture_word(
    data: CaptureRequest,
    current_user: CurrentUserDep,
    capture_service: CaptureServiceDep,
    background_tasks: BackgroundTasks,
) -> UserWordOut:
    """Save a captured word (with optional sentence/source) into MY vocabulary."""
    result = await capture_service.capture(current_user.id, data)
    # Translate now, while the sentence this word came from is the freshest
    # context we have; exercises built later then need no inference.
    if settings.exercises.TRANSLATE_ON_CAPTURE:
        schedule_translation(background_tasks, current_user.id, result.word_uuid)
    # Pre-generate exercises so /exercises/next is instant despite slow CPU inference.
    if settings.exercises.EXERCISE_POOL_AUTOFILL:
        schedule_refill(background_tasks, current_user.id)
    # Warm the word AND the sentence it was met in: those are the two things a
    # learner taps 🔊 on, and only the first play of each is slow.
    if settings.audio.AUDIO_ENABLED:
        texts = [result.lemma]
        if data.sentence:
            texts.append(data.sentence)
        schedule_audio_warmup(
            background_tasks,
            texts,
            result.language,
            (current_user.preferences or {}).get(VOICE_PREF_KEY),
        )
    return result


@router.get("", response_model=Page[UserWordOut])
async def list_my_vocabulary(
    current_user: CurrentUserDep,
    capture_service: CaptureServiceDep,
    page: int = 1,
    limit: int = 20,
    query: str | None = None,
    language: str | None = None,
) -> Page[UserWordOut]:
    return await capture_service.list_vocabulary(
        current_user.id, page=page, limit=limit, query=query, language=language
    )


@router.get("/languages", response_model=list[LanguageCountOut])
async def my_languages(
    current_user: CurrentUserDep,
    capture_service: CaptureServiceDep,
) -> list[LanguageCountOut]:
    """The languages I'm learning (distinct word languages) with word counts —
    what the practice/dictionary language switcher is built from."""
    return await capture_service.list_languages(current_user.id)


@router.get("/{user_word_uuid}", response_model=UserWordDetailOut)
async def word_detail(
    user_word_uuid: UUID,
    current_user: CurrentUserDep,
    capture_service: CaptureServiceDep,
) -> UserWordDetailOut:
    """One of MY words with its translation and the sentences I saved it in."""
    return await capture_service.get_detail(current_user.id, user_word_uuid)


@router.delete("/{user_word_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_word(
    user_word_uuid: UUID,
    current_user: CurrentUserDep,
    capture_service: CaptureServiceDep,
) -> None:
    """Remove a word from MY dictionary (the shared entry stays for others)."""
    await capture_service.remove(current_user.id, user_word_uuid)
