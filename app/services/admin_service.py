from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exc import (
    BadRequestException,
    ForbiddenException,
    ObjectAlreadyExistsException,
    ObjectNotFoundException,
)
from app.core.languages import is_supported
from app.core.security.password import hash_password
from app.database.postgres import get_session
from app.enums.user import RoleEnum
from app.models import Exercise
from app.repositories.exercise import ExerciseRepository
from app.repositories.user import UserRepository
from app.repositories.user_word import UserWordRepository
from app.repositories.word import WordRepository
from app.schemas.admin import (
    AdminExerciseOut,
    AdminExerciseUpdate,
    AdminUserCreate,
    AdminUserUpdate,
    AdminVocabularyAdd,
    AdminWordCreate,
    AdminWordOut,
    AdminWordUpdate,
)
from app.schemas.capture import LanguageCountOut, UserWordOut
from app.schemas.pagination import Page
from app.schemas.user import UserOut
from app.utils.lemmatize import to_lemma


class AdminService:
    """Full moderation over users and their learning data.

    Writes are guarded: an admin can't touch their own account here, and only
    a SUPER_ADMIN may create, edit or delete another privileged user. Shared
    dictionary edits are deliberate — they change the word for every user.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.users = UserRepository(session)
        self.user_words = UserWordRepository(session)
        self.exercises = ExerciseRepository(session)
        self.words = WordRepository(session)

    # --- users -------------------------------------------------------------

    async def list_users(self, page: int = 1, limit: int = 20, query: str | None = None) -> Page[UserOut]:
        rows, total = await self.users.search(page=page, limit=limit, query=query)
        return Page[UserOut](items=[UserOut.model_validate(u) for u in rows], total=total, page=page, limit=limit)

    async def get_user(self, user_id: int) -> UserOut:
        return UserOut.model_validate(await self._get_user_or_404(user_id))

    async def create_user(self, acting: UserOut, data: AdminUserCreate) -> UserOut:
        if data.role != RoleEnum.USER and acting.role != RoleEnum.SUPER_ADMIN:
            raise ForbiddenException("Only a SUPER_ADMIN can create a privileged user")
        if await self.users.get_by_email(data.email):
            raise ObjectAlreadyExistsException(data.email, "User")
        user = await self.users.create_one(
            {
                "email": data.email,
                "hashed_password": hash_password(data.password),
                "full_name": data.full_name,
                "role": data.role.value,
                "status": data.status.value,
            }
        )
        return UserOut.model_validate(user)

    async def update_user(self, acting: UserOut, user_id: int, data: AdminUserUpdate) -> UserOut:
        user = await self._get_manageable_user(acting, user_id)
        if data.role == RoleEnum.SUPER_ADMIN and acting.role != RoleEnum.SUPER_ADMIN:
            raise ForbiddenException("Only a SUPER_ADMIN can grant SUPER_ADMIN")
        # mode="json" serializes the enum fields (role/status) to their string
        # values while leaving the plain string fields untouched.
        changes = data.model_dump(exclude_none=True, mode="json")
        if changes:
            user = await self.users.update_one(user, changes)
        return UserOut.model_validate(user)

    async def delete_user(self, acting: UserOut, user_id: int) -> None:
        await self._get_manageable_user(acting, user_id)
        # Child rows (words, exercises, tokens…) go via ON DELETE CASCADE.
        await self.users.delete_by(id=user_id)

    # --- a user's vocabulary ----------------------------------------------

    async def user_vocabulary(self, user_id: int, page: int = 1, limit: int = 20) -> Page[UserWordOut]:
        await self._get_user_or_404(user_id)
        rows, total = await self.user_words.list_for_user(user_id, page=page, limit=limit)
        return Page[UserWordOut](
            items=[UserWordOut.from_user_word(uw) for uw in rows], total=total, page=page, limit=limit
        )

    async def add_vocabulary(self, user_id: int, data: AdminVocabularyAdd) -> UserWordOut:
        await self._get_user_or_404(user_id)
        lemma = to_lemma(data.word, data.language)
        word = await self.words.get_by_lemma_language(lemma, data.language)
        if not word:
            word = await self.words.create_one({"lemma": lemma, "language": data.language})
        existing = await self.user_words.get_by_user_word(user_id, word.uuid)
        if existing:
            raise ObjectAlreadyExistsException(lemma, "UserWord")
        created = await self.user_words.create_one({"user_id": user_id, "word_uuid": word.uuid})
        return UserWordOut.from_user_word(await self.user_words.get_with_word(created.uuid))

    async def remove_vocabulary(self, user_id: int, user_word_uuid: UUID) -> None:
        uw = await self.user_words.get_for_user(user_id, user_word_uuid)
        if not uw:
            raise ObjectNotFoundException(user_word_uuid, "UserWord")
        await self.user_words.delete_one(uw)

    # --- shared dictionary -------------------------------------------------

    async def list_words(
        self, page: int = 1, limit: int = 20, language: str | None = None, query: str | None = None
    ) -> Page[AdminWordOut]:
        rows, total = await self.words.search(page=page, limit=limit, language=language, query=query)
        return Page[AdminWordOut](
            items=[AdminWordOut.model_validate(w) for w in rows], total=total, page=page, limit=limit
        )

    async def word_languages(self) -> list[LanguageCountOut]:
        return [
            LanguageCountOut(language=lang, count=count) for lang, count in await self.words.languages_with_counts()
        ]

    async def create_word(self, data: AdminWordCreate) -> AdminWordOut:
        if not is_supported(data.language):
            raise BadRequestException(f"Unsupported language: {data.language}")
        lemma = to_lemma(data.lemma, data.language)
        if await self.words.get_by_lemma_language(lemma, data.language):
            raise ObjectAlreadyExistsException(f"{lemma} ({data.language})", "Word")
        definitions = None
        if data.translation:
            definitions = [{"lang": data.translation_lang, "translation": data.translation}]
        word = await self.words.create_one({"lemma": lemma, "language": data.language, "definitions": definitions})
        return AdminWordOut.model_validate(word)

    async def delete_word(self, word_uuid: UUID) -> None:
        # Removes the shared entry; it also disappears from every user's
        # vocabulary via ON DELETE CASCADE on user_words.
        word = await self.words.get_one(uuid=word_uuid)
        if not word:
            raise ObjectNotFoundException(word_uuid, "Word")
        await self.words.delete_one(word)

    async def update_word(self, word_uuid: UUID, data: AdminWordUpdate) -> AdminWordOut:
        word = await self.words.get_one(uuid=word_uuid)
        if not word:
            raise ObjectNotFoundException(word_uuid, "Word")
        changes: dict = {}
        if data.lemma and data.lemma != word.lemma:
            clash = await self.words.get_by_lemma_language(data.lemma, word.language)
            if clash:
                raise ObjectAlreadyExistsException(f"{data.lemma} ({word.language})", "Word")
            changes["lemma"] = data.lemma
        if data.translation is not None:
            changes["definitions"] = self._merge_translation(word.definitions, data.translation_lang, data.translation)
        if changes:
            word = await self.words.update_one(word, changes)
        return AdminWordOut.model_validate(word)

    @staticmethod
    def _merge_translation(definitions, lang: str, translation: str) -> list:
        # Keep senses in other languages, replace the one for `lang`.
        senses = [d for d in (definitions or []) if d.get("lang") != lang]
        senses.append({"lang": lang, "translation": translation})
        return senses

    # --- exercises ---------------------------------------------------------

    async def user_exercises(self, user_id: int, page: int = 1, limit: int = 20) -> Page[AdminExerciseOut]:
        await self._get_user_or_404(user_id)
        rows, total = await self.exercises.get_many(
            page=page, limit=limit, order_by=[Exercise.created_at.desc()], user_id=user_id
        )
        return Page[AdminExerciseOut](
            items=[AdminExerciseOut.model_validate(e) for e in rows], total=total, page=page, limit=limit
        )

    async def update_exercise(self, exercise_uuid: UUID, data: AdminExerciseUpdate) -> AdminExerciseOut:
        ex = await self.exercises.get_one(uuid=exercise_uuid)
        if not ex:
            raise ObjectNotFoundException(exercise_uuid, "Exercise")
        ex = await self.exercises.update_one(ex, {"status": data.status.value})
        return AdminExerciseOut.model_validate(ex)

    async def delete_exercise(self, exercise_uuid: UUID) -> None:
        ex = await self.exercises.get_one(uuid=exercise_uuid)
        if not ex:
            raise ObjectNotFoundException(exercise_uuid, "Exercise")
        await self.exercises.delete_one(ex)

    # --- helpers -----------------------------------------------------------

    async def _get_user_or_404(self, user_id: int):
        user = await self.users.get_by_id(user_id)
        if not user:
            raise ObjectNotFoundException(user_id, "User")
        return user

    async def _get_manageable_user(self, acting: UserOut, user_id: int):
        """The target user, or raise if `acting` isn't allowed to manage it."""
        user = await self._get_user_or_404(user_id)
        if user.id == acting.id:
            raise BadRequestException("Use your own profile settings, not the admin panel")
        if user.role != RoleEnum.USER.value and acting.role != RoleEnum.SUPER_ADMIN:
            raise ForbiddenException("Only a SUPER_ADMIN can manage privileged users")
        return user


async def get_admin_service(session: AsyncSession = Depends(get_session)) -> AdminService:
    return AdminService(session)
