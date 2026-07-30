from typing import Annotated

from fastapi import Depends

from app.core.exc import ForbiddenException
from app.schemas.user import UserOut
from app.services.auth.auth import AuthService, get_auth_service
from app.services.auth.dependencies import get_current_user
from app.services.auth.email_verification import EmailVerificationService, get_email_verification_service
from app.services.capture_service import CaptureService, get_capture_service
from app.services.learning.exercise_service import ExercisePoolService, get_exercise_pool_service
from app.services.learning.spaced_repetition import SpacedRepetitionService, get_review_service
from app.services.user import UserService, get_user_service
from app.services.vocabulary.word_service import WordService, get_word_service

UserServiceDep = Annotated[UserService, Depends(get_user_service)]
WordServiceDep = Annotated[WordService, Depends(get_word_service)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
CaptureServiceDep = Annotated[CaptureService, Depends(get_capture_service)]
ReviewServiceDep = Annotated[SpacedRepetitionService, Depends(get_review_service)]
ExercisePoolServiceDep = Annotated[ExercisePoolService, Depends(get_exercise_pool_service)]
EmailVerificationServiceDep = Annotated[EmailVerificationService, Depends(get_email_verification_service)]
CurrentUserDep = Annotated[UserOut, Depends(get_current_user)]

# Machine-readable marker the client matches to prompt for email verification.
EMAIL_NOT_VERIFIED = "email_not_verified"


def verified_user(current_user: CurrentUserDep) -> UserOut:
    """Gate features that need a real address behind a confirmed email.
    Google accounts arrive already verified, so this only stops unconfirmed
    email/password signups."""
    if not current_user.is_email_verified:
        raise ForbiddenException(EMAIL_NOT_VERIFIED)
    return current_user


VerifiedUserDep = Annotated[UserOut, Depends(verified_user)]
