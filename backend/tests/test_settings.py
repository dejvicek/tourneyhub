import pytest
from pydantic import SecretStr, ValidationError

from tourneyhub.settings import Settings

_SECRET = "x" * 32


def test_settings_are_read_from_prefixed_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TOURNEYHUB_ENV", "production")
    monkeypatch.setenv("TOURNEYHUB_DATABASE_URL", "postgresql+psycopg://h/d")
    monkeypatch.setenv("TOURNEYHUB_JWT_SECRET", _SECRET)

    settings = Settings()

    assert settings.env == "production"
    assert settings.cookie_secure is True
    assert settings.jwt_secret.get_secret_value() == _SECRET


def test_cookie_secure_false_is_refused_in_production() -> None:
    with pytest.raises(ValidationError) as raised:
        Settings(
            env="production",
            database_url=SecretStr("postgresql+psycopg://h/d"),
            jwt_secret=SecretStr(_SECRET),
            cookie_secure=False,
        )

    assert raised.value.errors()[0]["type"] == "cookie_secure_required"


def test_cookie_secure_false_is_allowed_in_development() -> None:
    settings = Settings(
        env="development",
        database_url=SecretStr("postgresql+psycopg://h/d"),
        jwt_secret=SecretStr(_SECRET),
        cookie_secure=False,
    )

    assert settings.cookie_secure is False


def test_a_short_jwt_secret_stops_startup() -> None:
    with pytest.raises(ValidationError) as raised:
        Settings(
            env="development",
            database_url=SecretStr("postgresql+psycopg://h/d"),
            jwt_secret=SecretStr("short"),
        )

    assert raised.value.errors()[0]["loc"] == ("jwt_secret",)


def test_a_missing_variable_stops_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TOURNEYHUB_ENV", raising=False)

    with pytest.raises(ValidationError):
        Settings()
