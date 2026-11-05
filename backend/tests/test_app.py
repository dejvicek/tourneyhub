import pytest
from fastapi.testclient import TestClient

from tourneyhub.app import create_app
from tourneyhub.settings import Settings


def test_create_app_reads_settings_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TOURNEYHUB_ENV", "development")
    monkeypatch.setenv("TOURNEYHUB_DATABASE_URL", "postgresql+psycopg://h/d")
    monkeypatch.setenv("TOURNEYHUB_JWT_SECRET", "x" * 32)

    app = create_app()

    assert app.state.settings.env == "development"


def test_the_lifespan_disposes_the_engine(settings: Settings) -> None:
    app = create_app(settings)
    engine = app.state.engine
    pool_before = engine.pool

    with TestClient(app):
        pass

    assert engine.pool is not pool_before
