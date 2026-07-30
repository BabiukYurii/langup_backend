from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import RedirectResponse

from app.core import settings
from app.core.security.rate_limit import auth_rate_limit
from app.dependencies import AuthServiceDep, CurrentUserDep, EmailVerificationServiceDep
from app.schemas.auth import GoogleLoginRequest, LoginRequest, RefreshRequest, RegisterRequest, TokenPair
from app.schemas.user import UserOut

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=TokenPair, status_code=201, dependencies=[Depends(auth_rate_limit)])
async def register(
    data: RegisterRequest,
    auth_service: AuthServiceDep,
    email_service: EmailVerificationServiceDep,
    background: BackgroundTasks,
) -> TokenPair:
    """Create an account with email + password; returns our JWT pair and emails
    a verification link (the account starts unverified)."""
    tokens, user = await auth_service.register(data)
    await email_service.send_verification(user, background)
    return tokens


@router.get("/verify-email")
async def verify_email(token: str, email_service: EmailVerificationServiceDep) -> RedirectResponse:
    """Confirm an email from the link we mailed. Redirects back to the cabinet
    with ?verified=1 on success, ?verified=0 for a stale or bad link."""
    ok = await email_service.verify(token)
    base = settings.app.BASE_URL.rstrip("/")
    return RedirectResponse(url=f"{base}/app/index.html?verified={1 if ok else 0}", status_code=303)


@router.post("/verify-email/resend", status_code=202, dependencies=[Depends(auth_rate_limit)])
async def resend_verification(
    current_user: CurrentUserDep,
    email_service: EmailVerificationServiceDep,
    background: BackgroundTasks,
) -> dict:
    """Re-send the verification email to the signed-in user. Idempotent: does
    nothing if the address is already confirmed."""
    from app.repositories.user import UserRepository

    user = await UserRepository(email_service.session).get_by_id(current_user.id)
    sent = await email_service.send_verification(user, background) if user else False
    return {"status": "sent" if sent else "already_verified"}


@router.post("/login", response_model=TokenPair, dependencies=[Depends(auth_rate_limit)])
async def login(data: LoginRequest, auth_service: AuthServiceDep) -> TokenPair:
    """Sign in with email + password."""
    return await auth_service.login(data)


@router.post("/google", response_model=TokenPair, dependencies=[Depends(auth_rate_limit)])
async def google_login(data: GoogleLoginRequest, auth_service: AuthServiceDep) -> TokenPair:
    """Sign in or sign up with a Google ID token; returns our JWT pair."""
    return await auth_service.google_login(data.id_token)


@router.post("/refresh", response_model=TokenPair, dependencies=[Depends(auth_rate_limit)])
async def refresh_tokens(data: RefreshRequest, auth_service: AuthServiceDep) -> TokenPair:
    return await auth_service.refresh(data.refresh_token)


@router.post("/logout", status_code=204)
async def logout(data: RefreshRequest, auth_service: AuthServiceDep) -> None:
    """End this session by retiring its refresh token."""
    await auth_service.logout(data.refresh_token)


@router.post("/logout-all", status_code=204)
async def logout_everywhere(current_user: CurrentUserDep, auth_service: AuthServiceDep) -> None:
    """End every session of the signed-in user — the button you want after a
    device is lost."""
    await auth_service.logout_everywhere(current_user.id)


@router.get("/me", response_model=UserOut)
async def get_me(current_user: CurrentUserDep) -> UserOut:
    return current_user
