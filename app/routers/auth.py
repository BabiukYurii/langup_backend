from fastapi import APIRouter

from app.dependencies import AuthServiceDep, CurrentUserDep
from app.schemas.auth import GoogleLoginRequest, RefreshRequest, TokenPair
from app.schemas.user import UserOut

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/google", response_model=TokenPair)
async def google_login(data: GoogleLoginRequest, auth_service: AuthServiceDep) -> TokenPair:
    """Sign in or sign up with a Google ID token; returns our JWT pair."""
    return await auth_service.google_login(data.id_token)


@router.post("/refresh", response_model=TokenPair)
async def refresh_tokens(data: RefreshRequest, auth_service: AuthServiceDep) -> TokenPair:
    return await auth_service.refresh(data.refresh_token)


@router.get("/me", response_model=UserOut)
async def get_me(current_user: CurrentUserDep) -> UserOut:
    return current_user
