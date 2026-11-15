import pytest

from app.core.config import MigrationSettings, SettingsError, load_settings

REQUIRED = {
    "DATABASE_URL": "postgresql+psycopg://app:app-password@localhost:5432/sportlab_test",
    "DATABASE_MIGRATION_URL": "postgresql+psycopg://migrator:mig-password@localhost:5432/sportlab_test",
    "SECRET_KEY": "test-" + "x" * 32,  # obviously fake, long enough for the check
    "ENCRYPTION_KEY": "test-encryption-key",
}

OPTIONAL = [
    "ENVIRONMENT",
    "PUBLIC_URL",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "ADMIN_EMAIL",
    "ACCESS_TOKEN_MINUTES",
    "REFRESH_TOKEN_DAYS",
    "SESSION_MAX_DAYS",
]


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Only the required variables, nothing inherited from the shell or conftest."""
    for name in OPTIONAL:
        monkeypatch.delenv(name, raising=False)
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


def test_defaults(env: pytest.MonkeyPatch) -> None:
    settings = load_settings(env_file=None)

    assert settings.environment == "development"
    assert settings.access_token_minutes == 15
    assert settings.refresh_token_days == 30
    assert settings.session_max_days == 90
    assert settings.google_client_id is None
    assert settings.admin_email is None


def test_empty_value_means_not_set(env: pytest.MonkeyPatch) -> None:
    env.setenv("GOOGLE_CLIENT_ID", "")

    assert load_settings(env_file=None).google_client_id is None


def test_override(env: pytest.MonkeyPatch) -> None:
    env.setenv("ENVIRONMENT", "staging")
    env.setenv("PUBLIC_URL", "https://sportlab-staging.example.com")
    env.setenv("ACCESS_TOKEN_MINUTES", "5")

    settings = load_settings(env_file=None)

    assert settings.environment == "staging"
    assert settings.access_token_minutes == 5


@pytest.mark.parametrize("name", list(REQUIRED))
def test_missing_required_variable(env: pytest.MonkeyPatch, name: str) -> None:
    env.delenv(name)

    with pytest.raises(SettingsError, match=f"{name}: Field required"):
        load_settings(env_file=None)


def test_invalid_value_is_rejected(env: pytest.MonkeyPatch) -> None:
    env.setenv("ENVIRONMENT", "prod")

    with pytest.raises(SettingsError, match="ENVIRONMENT"):
        load_settings(env_file=None)


def test_error_message_does_not_leak_values(env: pytest.MonkeyPatch) -> None:
    env.setenv("DATABASE_URL", "mysql://app:leaked-password@localhost/db")
    env.setenv("ACCESS_TOKEN_MINUTES", "not-a-number-secret")

    with pytest.raises(SettingsError) as error:
        load_settings(env_file=None)

    message = str(error.value)
    assert "DATABASE_URL" in message
    assert "leaked-password" not in message
    assert "not-a-number-secret" not in message
    # `from None`: the original Pydantic error, which holds the values, is not chained
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__


def test_secrets_are_hidden_in_repr(env: pytest.MonkeyPatch) -> None:
    text = repr(load_settings(env_file=None))

    assert REQUIRED["SECRET_KEY"] not in text
    assert "app-password" not in text
    assert "mig-password" not in text


def test_migration_settings_need_only_the_migration_url(env: pytest.MonkeyPatch) -> None:
    """Alembic runs without the application's secrets (least privilege)."""
    for name in ("DATABASE_URL", "SECRET_KEY", "ENCRYPTION_KEY"):
        env.delenv(name)

    settings = load_settings(env_file=None, settings_class=MigrationSettings)

    assert settings.database_migration_url.unicode_string() == REQUIRED["DATABASE_MIGRATION_URL"]
    assert not hasattr(settings, "secret_key")


def test_migration_settings_require_the_migration_url(env: pytest.MonkeyPatch) -> None:
    env.delenv("DATABASE_MIGRATION_URL")

    with pytest.raises(SettingsError, match="DATABASE_MIGRATION_URL: Field required"):
        load_settings(env_file=None, settings_class=MigrationSettings)


@pytest.mark.parametrize("value", ["CHANGE_ME", "x" * 31])
def test_short_secret_key_is_refused(env: pytest.MonkeyPatch, value: str) -> None:
    env.setenv("SECRET_KEY", value)

    with pytest.raises(SettingsError, match="SECRET_KEY: Value error, must be at least 32"):
        load_settings(env_file=None)


def test_refresh_cannot_outlive_the_session(env: pytest.MonkeyPatch) -> None:
    env.setenv("REFRESH_TOKEN_DAYS", "100")

    with pytest.raises(SettingsError, match="cannot be longer than SESSION_MAX_DAYS"):
        load_settings(env_file=None)


def test_public_url_and_redirect_uri(env: pytest.MonkeyPatch) -> None:
    settings = load_settings(env_file=None)

    assert settings.google_redirect_uri == "http://localhost:8000/api/auth/google/callback"


def test_public_url_must_be_https_outside_development(env: pytest.MonkeyPatch) -> None:
    env.setenv("ENVIRONMENT", "staging")
    env.setenv("PUBLIC_URL", "http://sportlab-staging.example.com")

    with pytest.raises(SettingsError, match="PUBLIC_URL must use https"):
        load_settings(env_file=None)

    env.setenv("PUBLIC_URL", "https://sportlab-staging.example.com/")
    assert load_settings(env_file=None).google_redirect_uri == (
        "https://sportlab-staging.example.com/api/auth/google/callback"
    )


def test_admin_email_is_normalised(env: pytest.MonkeyPatch) -> None:
    env.setenv("ADMIN_EMAIL", "  Admin@Example.COM ")

    assert load_settings(env_file=None).admin_email_normalised == "admin@example.com"
