from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TOURNEYHUB_", frozen=True)

    env: Literal["development", "production"]
    database_url: SecretStr
    jwt_secret: Annotated[SecretStr, Field(min_length=32)]  # HS256 needs 32 bytes
    cookie_secure: bool = True

    @model_validator(mode="after")
    def _require_secure_cookie_outside_development(self) -> Self:
        """Refuse `cookie_secure=False` unless `env` is `development` (ADR-004)."""
        if not self.cookie_secure and self.env != "development":
            raise PydanticCustomError(
                "cookie_secure_required",
                "cookie_secure may only be False when env is development",
            )
        return self
