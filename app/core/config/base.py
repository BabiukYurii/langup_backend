from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["BaseConfig"]


class BaseConfig(BaseSettings):
    # Shared pydantic-settings base: loads from .env, ignores unknown keys.
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")
