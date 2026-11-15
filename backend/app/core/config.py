"""Application settings, read from environment variables and the optional `.env` file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import (
    Field,
    PostgresDsn,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repository root, where .env.example lives
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class EnvSettings(BaseSettings):
    """Where settings come from: the environment first, then the optional .env file."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        # The same .env can hold variables for other services (frontend, Compose)
        extra="ignore",
        # An empty value (GOOGLE_CLIENT_ID=) means "not set": the default applies
        env_ignore_empty=True,
    )


class MigrationSettings(EnvSettings):
    """What Alembic needs, and nothing more.

    A deploy runs the migrations as a separate job: it gets the migration role's
    URL but none of the application's secrets (least privilege).
    """

    # repr=False keeps the password inside the URL out of logs and tracebacks
    database_migration_url: PostgresDsn = Field(repr=False)


class Settings(MigrationSettings):
    """Everything the running application needs."""

    environment: Literal["development", "staging", "production"] = "development"

    database_url: PostgresDsn = Field(repr=False)

    secret_key: SecretStr
    encryption_key: SecretStr

    # Optional until the Google login step
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    admin_email: str | None = None

    access_token_minutes: int = Field(default=15, gt=0)
    refresh_token_days: int = Field(default=30, gt=0)
    # After this a session ends whatever the activity: sign in with Google again
    session_max_days: int = Field(default=90, gt=0)

    @field_validator("secret_key")
    @classmethod
    def secret_key_is_long_enough(cls, value: SecretStr) -> SecretStr:
        # It signs the access tokens: a short key can be brute-forced, and this
        # also refuses the CHANGE_ME placeholder of .env.example
        if len(value.get_secret_value()) < 32:
            raise ValueError("must be at least 32 characters")
        return value

    @model_validator(mode="after")
    def refresh_fits_in_session(self) -> "Settings":
        if self.refresh_token_days > self.session_max_days:
            raise ValueError("REFRESH_TOKEN_DAYS cannot be longer than SESSION_MAX_DAYS")
        return self


class SettingsError(RuntimeError):
    """Raised when the environment does not provide valid settings."""


def load_settings[T: EnvSettings](
    env_file: Path | None = ENV_FILE, settings_class: type[T] = Settings
) -> T:
    """Build the settings, turning validation errors into a message without values.

    Pydantic's own error text includes the rejected input, which could be a
    password or a key: here only the variable name and the reason are kept.
    `env_file=None` reads the process environment only (used by the tests).
    """
    try:
        return settings_class(_env_file=env_file)
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


@lru_cache
def get_migration_settings() -> MigrationSettings:
    """Settings for Alembic: only the migration role's URL is required."""
    return load_settings(settings_class=MigrationSettings)
