from typing import Annotated

from fastapi import Depends

from app.services.user import UserService, get_user_service
from app.services.vocabulary.word_service import WordService, get_word_service

UserServiceDep = Annotated[UserService, Depends(get_user_service)]
WordServiceDep = Annotated[WordService, Depends(get_word_service)]
