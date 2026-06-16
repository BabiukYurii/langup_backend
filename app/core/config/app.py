from pydantic import Field

from app.core.config.base import BaseConfig


class AppBaseConfig(BaseConfig):
    APP_NAME: str = Field("LangUp", alias="APP_NAME")
    ENV: str = Field("local", alias="ENV")
    DEBUG: bool = Field(True, alias="DEBUG")
    HOST: str = Field("0.0.0.0", alias="HOST")
    PORT: int = Field(8000, alias="PORT")
    WORKERS: int = Field(1, alias="WORKERS")
    API_PREFIX: str = Field("/api", alias="API_PREFIX")
    ALLOWED_ORIGINS: list[str] = Field(default_factory=lambda: ["*"], alias="ALLOWED_ORIGINS")
