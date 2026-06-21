from pydantic import Field

from app.core.config.base import BaseConfig


class AuthConfig(BaseConfig):
    # Used to validate the audience of incoming Google ID tokens.
    GOOGLE_CLIENT_ID: str = Field("", alias="GOOGLE_CLIENT_ID")
