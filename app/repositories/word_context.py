from app.models import WordContext
from app.repositories.base import BaseRepository


class WordContextRepository(BaseRepository[WordContext]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=WordContext)
