from app.enums.base import BaseStrEnum


class OAuthProvider(BaseStrEnum):
    GOOGLE = "GOOGLE"


class TokenType(BaseStrEnum):
    ACCESS = "access"
    REFRESH = "refresh"
    EMAIL_VERIFY = "email_verify"
    RESET = "reset"
