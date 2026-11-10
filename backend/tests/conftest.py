import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid7

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, event, select, text
from sqlalchemy.orm import Session

from tourneyhub.api.deps import get_now, get_session
from tourneyhub.app import create_app
from tourneyhub.db.models.accounts import User
from tourneyhub.db.models.leagues import League
from tourneyhub.db.session import create_db_engine
from tourneyhub.engine.accounts import Language
from tourneyhub.settings import Settings


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(
        env="development",
        database_url=SecretStr(os.environ["TOURNEYHUB_TEST_DATABASE_URL"]),
        jwt_secret=SecretStr("x" * 32),
        cookie_secure=False,  # the test client talks to http://testserver
    )


@pytest.fixture(scope="session")
def engine(settings: Settings) -> Iterator[Engine]:
    engine = create_db_engine(settings)
    config = Config(toml_file=Path(__file__).parent.parent / "pyproject.toml")
    config.attributes["connection"] = engine
    command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        event.listen(session, "before_commit", _check_deferred_constraints)
        try:
            yield session
            if session.is_active:
                session.commit()  # runs the deferred checks on what the test left
            else:
                session.rollback()  # a flush failed; back to the last commit
            assert_invariants(session)  # the queries of DATA-MODEL §5
        finally:
            session.close()
            transaction.rollback()


def _check_deferred_constraints(session: Session) -> None:
    """Run the deferred checks that a real commit would run (DATA-MODEL §2)."""
    session.flush()
    session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    session.execute(text("SET CONSTRAINTS ALL DEFERRED"))


def assert_invariants(session: Session) -> None:
    """Check the committed data against the queries of DATA-MODEL §5."""
    blank_names = session.scalars(
        select(League.id).where(text("btrim(leagues.name) = ''"))
    ).all()
    assert blank_names == []


@pytest.fixture
def client(settings: Settings, session: Session, now: datetime) -> Iterator[TestClient]:
    app = create_app(settings)

    def test_session() -> Iterator[Session]:
        with session.begin_nested():  # a failing request undoes only its own changes
            yield session
        session.commit()  # releases the test's savepoint and runs the deferred checks

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[get_now] = lambda: now
    with TestClient(app) as client:  # the context manager runs the lifespan
        yield client


@pytest.fixture
def make_user(session: Session, now: datetime) -> Callable[..., User]:
    def make_user(
        *,
        email: str | None = None,
        is_admin: bool = False,
        must_change_password: bool = False,
    ) -> User:
        user = User(
            email=email or f"{uuid7()}@example.test",
            display_name="Ana",
            password_hash="!",
            is_admin=is_admin,
            must_change_password=must_change_password,
            language=Language.EN,
            created_at=now,
        )
        session.add(user)
        session.flush()
        return user

    return make_user


@pytest.fixture
def make_league(
    session: Session, make_user: Callable[..., User], now: datetime
) -> Callable[..., League]:
    def make_league(
        *, name: str | None = None, owner_user_id: UUID | None = None
    ) -> League:
        league = League(
            id=uuid7(),
            owner_user_id=owner_user_id or make_user().id,
            name=name or f"League {uuid7()}",
            created_at=now,
        )
        session.add(league)
        session.flush()
        return league

    return make_league
