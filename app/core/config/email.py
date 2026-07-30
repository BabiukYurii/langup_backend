from pydantic import Field

from app.core.config.base import BaseConfig


class EmailConfig(BaseConfig):
    """SMTP / from-address for outgoing mail (verification, notifications).

    Leave SMTP_HOST empty in dev/CI: with no host configured the mailer logs
    the message instead of sending it, so the flow works end-to-end without a
    real provider.
    """

    SMTP_HOST: str = Field("", alias="SMTP_HOST")
    SMTP_PORT: int = Field(587, alias="SMTP_PORT")
    SMTP_USER: str = Field("", alias="SMTP_USER")
    SMTP_PASSWORD: str = Field("", alias="SMTP_PASSWORD")
    SMTP_STARTTLS: bool = Field(True, alias="SMTP_STARTTLS")
    EMAIL_FROM: str = Field("no-reply@langup.app", alias="EMAIL_FROM")
    EMAIL_FROM_NAME: str = Field("LangUp", alias="EMAIL_FROM_NAME")
    # How long an email-verification link stays valid.
    VERIFICATION_TTL_HOURS: int = Field(48, alias="EMAIL_VERIFICATION_TTL_HOURS")

    @property
    def enabled(self) -> bool:
        return bool(self.SMTP_HOST)
