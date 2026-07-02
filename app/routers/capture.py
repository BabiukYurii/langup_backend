from fastapi import APIRouter, status

from app.dependencies import CaptureServiceDep, CurrentUserDep
from app.schemas.capture import CaptureRequest, UserWordOut
from app.schemas.pagination import Page

router = APIRouter(prefix="/vocabulary", tags=["Vocabulary"])


@router.post("", response_model=UserWordOut, status_code=status.HTTP_201_CREATED)
async def capture_word(
    data: CaptureRequest,
    current_user: CurrentUserDep,
    capture_service: CaptureServiceDep,
) -> UserWordOut:
    """Save a captured word (with optional sentence/source) into MY vocabulary."""
    return await capture_service.capture(current_user.id, data)


@router.get("", response_model=Page[UserWordOut])
async def list_my_vocabulary(
    current_user: CurrentUserDep,
    capture_service: CaptureServiceDep,
    page: int = 1,
    limit: int = 20,
    query: str | None = None,
) -> Page[UserWordOut]:
    return await capture_service.list_vocabulary(current_user.id, page=page, limit=limit, query=query)
