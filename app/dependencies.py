from typing import Annotated

from fastapi import Depends

from app.schemas.user import UserOut
from app.services.auth.auth import AuthService, get_auth_service
from app.services.auth.dependencies import get_current_user
from app.services.user import UserService, get_user_service
from app.services.vocabulary.word_service import WordService, get_word_service

UserServiceDep = Annotated[UserService, Depends(get_user_service)]
WordServiceDep = Annotated[WordService, Depends(get_word_service)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
CurrentUserDep = Annotated[UserOut, Depends(get_current_user)]
