from pydantic import Field

from app.core.config.base import BaseConfig


class JwtConfig(BaseConfig):
    ACCESS_SECRET_KEY: str = Field("dev-access-secret-change-me", alias="JWT_ACCESS_SECRET_KEY")
    REFRESH_SECRET_KEY: str = Field("dev-refresh-secret-change-me", alias="JWT_REFRESH_SECRET_KEY")
    ALGORITHM: str = Field("HS256", alias="JWT_ALGORITHM")
    ACCESS_EXPIRE_MINUTES: int = Field(30, alias="JWT_ACCESS_EXPIRE_MINUTES")
    REFRESH_EXPIRE_DAYS: int = Field(30, alias="JWT_REFRESH_EXPIRE_DAYS")
