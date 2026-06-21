from uuid import UUID

from fastapi import APIRouter, status

from app.dependencies import WordServiceDep
from app.schemas.pagination import Page
from app.schemas.vocabulary import WordCreate, WordOut, WordUpdate

router = APIRouter(prefix="/words", tags=["Words"])


@router.post("", response_model=WordOut, status_code=status.HTTP_201_CREATED)
async def create_word(data: WordCreate, word_service: WordServiceDep) -> WordOut:
    return await word_service.create_word(data)


@router.get("", response_model=Page[WordOut])
async def list_words(
    word_service: WordServiceDep,
    page: int = 1,
    limit: int = 20,
    language: str | None = None,
    query: str | None = None,
) -> Page[WordOut]:
    return await word_service.list_words(page=page, limit=limit, language=language, query=query)


@router.get("/{word_uuid}", response_model=WordOut)
async def get_word(word_uuid: UUID, word_service: WordServiceDep) -> WordOut:
    return await word_service.get_word(word_uuid)


@router.patch("/{word_uuid}", response_model=WordOut)
async def update_word(word_uuid: UUID, data: WordUpdate, word_service: WordServiceDep) -> WordOut:
    return await word_service.update_word(word_uuid, data)


@router.delete("/{word_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_word(word_uuid: UUID, word_service: WordServiceDep) -> None:
    await word_service.delete_word(word_uuid)
