"""Application settings, read from environment variables and the optional `.env` file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repository root, where .env.example lives
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        # The same .env can hold variables for other services (frontend, Compose)
        extra="ignore",
        # An empty value (GOOGLE_CLIENT_ID=) means "not set": the default applies
        env_ignore_empty=True,
    )

    environment: Literal["development", "staging", "production"] = "development"

    # repr=False keeps the passwords inside the URLs out of logs and tracebacks
    database_url: PostgresDsn = Field(repr=False)
    database_migration_url: PostgresDsn = Field(repr=False)

    secret_key: SecretStr
    encryption_key: SecretStr

    # Optional until the Google login step
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    admin_email: str | None = None

    access_token_minutes: int = Field(default=15, gt=0)
    refresh_token_days: int = Field(default=30, gt=0)


class SettingsError(RuntimeError):
    """Raised when the environment does not provide valid settings."""


def load_settings(env_file: Path | None = ENV_FILE) -> Settings:
    """Build the settings, turning validation errors into a message without values.

    Pydantic's own error text includes the rejected input, which could be a
    password or a key: here only the variable name and the reason are kept.
    `env_file=None` reads the process environment only (used by the tests).
    """
    try:
        return Settings(_env_file=env_file)
    except ValidationError as exc:
        problems = [
            f"  {'.'.join(str(part) for part in error['loc']).upper()}: {error['msg']}"
            for error in exc.errors()
        ]
        message = "Invalid or missing environment variables:\n" + "\n".join(problems)
        raise SettingsError(message) from None


@lru_cache
def get_settings() -> Settings:
    """Settings for the running application, read once and then reused."""
    return load_settings()
