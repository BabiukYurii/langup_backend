from fastapi import APIRouter, BackgroundTasks, status

from app.core import settings
from app.dependencies import CaptureServiceDep, CurrentUserDep
from app.schemas.capture import CaptureRequest, UserWordOut
from app.schemas.pagination import Page
from app.services.learning.exercise_service import refill_pool_in_background, translate_word_in_background

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
        background_tasks.add_task(translate_word_in_background, current_user.id, result.word_uuid)
    # Pre-generate exercises so /exercises/next is instant despite slow CPU inference.
    if settings.exercises.EXERCISE_POOL_AUTOFILL:
        background_tasks.add_task(refill_pool_in_background, current_user.id)
    return result


@router.get("", response_model=Page[UserWordOut])
async def list_my_vocabulary(
    current_user: CurrentUserDep,
    capture_service: CaptureServiceDep,
    page: int = 1,
    limit: int = 20,
    query: str | None = None,
) -> Page[UserWordOut]:
    return await capture_service.list_vocabulary(current_user.id, page=page, limit=limit, query=query)
