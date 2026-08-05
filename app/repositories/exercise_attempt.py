from app.models import ExerciseAttempt
from app.repositories.base import BaseRepository


class ExerciseAttemptRepository(BaseRepository[ExerciseAttempt]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=ExerciseAttempt)
