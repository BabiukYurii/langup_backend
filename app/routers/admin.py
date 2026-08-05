from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.core.security.rbac import ADMIN_ROLES, require_roles
from app.schemas.admin import (
    AdminExerciseOut,
    AdminExerciseUpdate,
    AdminUserCreate,
    AdminUserUpdate,
    AdminVocabularyAdd,
    AdminWordOut,
    AdminWordUpdate,
)
from app.schemas.capture import UserWordOut
from app.schemas.dictionary import DictionaryImportRequest, DictionaryImportResult
from app.schemas.pagination import Page
from app.schemas.user import UserOut
from app.services.admin_service import AdminService, get_admin_service
from app.services.vocabulary.dictionary_service import (
    DictionaryImportService,
    content_lines,
    schedule_dictionary_import,
    schedule_normalize_import,
)

router = APIRouter(prefix="/admin", tags=["admin"])

AdminUserDep = Annotated[UserOut, Depends(require_roles(*ADMIN_ROLES))]
AdminServiceDep = Annotated[AdminService, Depends(get_admin_service)]


@router.get("/users", response_model=Page[UserOut])
async def list_users(
    admin: AdminUserDep,
    service: AdminServiceDep,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    query: str | None = Query(None, max_length=128),
) -> Page[UserOut]:
    """All users, newest first; `query` matches email or name."""
    return await service.list_users(page=page, limit=limit, query=query)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(data: AdminUserCreate, admin: AdminUserDep, service: AdminServiceDep) -> UserOut:
    """Create a user; only a SUPER_ADMIN may create a privileged one."""
    return await service.create_user(admin, data)


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: int, admin: AdminUserDep, service: AdminServiceDep) -> UserOut:
    return await service.get_user(user_id)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: int, data: AdminUserUpdate, admin: AdminUserDep, service: AdminServiceDep) -> UserOut:
    """Change a user's role, status or profile fields."""
    return await service.update_user(admin, user_id, data)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, admin: AdminUserDep, service: AdminServiceDep) -> None:
    """Delete a user and all their data (cascade)."""
    await service.delete_user(admin, user_id)


@router.get("/users/{user_id}/vocabulary", response_model=Page[UserWordOut])
async def user_vocabulary(
    user_id: int,
    admin: AdminUserDep,
    service: AdminServiceDep,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> Page[UserWordOut]:
    return await service.user_vocabulary(user_id, page=page, limit=limit)


@router.post("/users/{user_id}/vocabulary", response_model=UserWordOut, status_code=status.HTTP_201_CREATED)
async def add_vocabulary(
    user_id: int, data: AdminVocabularyAdd, admin: AdminUserDep, service: AdminServiceDep
) -> UserWordOut:
    """Add a word to a user's personal vocabulary."""
    return await service.add_vocabulary(user_id, data)


@router.delete("/users/{user_id}/vocabulary/{user_word_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_vocabulary(user_id: int, user_word_uuid: UUID, admin: AdminUserDep, service: AdminServiceDep) -> None:
    """Remove a word from a user's vocabulary (leaves the shared dictionary)."""
    await service.remove_vocabulary(user_id, user_word_uuid)


@router.patch("/words/{word_uuid}", response_model=AdminWordOut)
async def update_word(
    word_uuid: UUID, data: AdminWordUpdate, admin: AdminUserDep, service: AdminServiceDep
) -> AdminWordOut:
    """Edit the SHARED dictionary entry — affects every user who has this word."""
    return await service.update_word(word_uuid, data)


@router.get("/users/{user_id}/exercises", response_model=Page[AdminExerciseOut])
async def user_exercises(
    user_id: int,
    admin: AdminUserDep,
    service: AdminServiceDep,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> Page[AdminExerciseOut]:
    return await service.user_exercises(user_id, page=page, limit=limit)


@router.patch("/exercises/{exercise_uuid}", response_model=AdminExerciseOut)
async def update_exercise(
    exercise_uuid: UUID, data: AdminExerciseUpdate, admin: AdminUserDep, service: AdminServiceDep
) -> AdminExerciseOut:
    """Change an exercise's lifecycle status."""
    return await service.update_exercise(exercise_uuid, data)


@router.delete("/exercises/{exercise_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exercise(exercise_uuid: UUID, admin: AdminUserDep, service: AdminServiceDep) -> None:
    """Delete an exercise from a user's pool."""
    await service.delete_exercise(exercise_uuid)


@router.post("/dictionary/import", response_model=DictionaryImportResult, status_code=status.HTTP_202_ACCEPTED)
async def import_dictionary(
    data: DictionaryImportRequest, admin: AdminUserDep, background: BackgroundTasks
) -> DictionaryImportResult:
    """Bulk-import a general dictionary (word→translation table) into the shared
    words. Runs in the background (Celery, or in-process).

    `normalize` sends messy raw_text through the LLM to extract clean pairs;
    otherwise the pairs are split deterministically here.
    """
    if data.normalize and data.raw_text:
        lines = content_lines(data.raw_text)
        schedule_normalize_import(background, data.source_language, data.target_language, data.raw_text)
        return DictionaryImportResult(queued=len(lines))

    entries = DictionaryImportService.parse(data)
    if entries:
        schedule_dictionary_import(background, data.source_language, data.target_language, entries)
    return DictionaryImportResult(queued=len(entries))
