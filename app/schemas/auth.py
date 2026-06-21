from pydantic import BaseModel


class GoogleLoginRequest(BaseModel):
    # Google ID token (JWT) obtained on the client via Google Sign-In.
    id_token: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
