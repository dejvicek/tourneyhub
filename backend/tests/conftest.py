import functools
import os
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid7

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, event, func, make_url, select, text
from sqlalchemy.orm import Session, sessionmaker

from tourneyhub.api.deps import get_now, get_session, get_session_factory
from tourneyhub.app import create_app
from tourneyhub.db.models.accounts import InstanceSettings, User
from tourneyhub.db.models.leagues import League, Season
from tourneyhub.db.session import create_db_engine
from tourneyhub.engine.accounts import Language
from tourneyhub.engine.leagues import DEFAULT_PLACEMENT_POINTS, SeasonState
from tourneyhub.services import auth as auth_service
from tourneyhub.settings import Settings

PASSWORD = "correct horse battery staple"


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
    # Season 1 comes with its league, and a new season closes the active one in
    # the same transaction (FR-010, FR-021).
    active_seasons = (
        select(func.count())
        .where(Season.league_id == League.id, Season.state == SeasonState.ACTIVE)
        .scalar_subquery()
    )
    without_one_active = session.scalars(
        select(League.id).where(active_seasons != 1)
    ).all()
    assert without_one_active == []


@pytest.fixture
def client(settings: Settings, session: Session, now: datetime) -> Iterator[TestClient]:
    app = create_app(settings)

    def test_session() -> Iterator[Session]:
        with session.begin_nested():  # a failing request undoes only its own changes
            yield session
        session.commit()  # releases the test's savepoint and runs the deferred checks

    def test_session_factory() -> sessionmaker[Session]:
        # The auth dependencies' own transactions become savepoints of the test's.
        return sessionmaker(
            bind=session.get_bind(), join_transaction_mode="create_savepoint"
        )

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[get_session_factory] = test_session_factory
    app.dependency_overrides[get_now] = lambda: now
    with TestClient(app) as client:  # the context manager runs the lifespan
        yield client


@pytest.fixture
def travel(client: TestClient, now: datetime) -> Callable[[timedelta], datetime]:
    """Move the clock that the client's requests see to `now + offset`."""
    app = client.app
    assert isinstance(app, FastAPI)

    def travel(offset: timedelta) -> datetime:
        app.dependency_overrides[get_now] = lambda: now + offset
        return now + offset

    return travel


@pytest.fixture
def auth_header(settings: Settings, now: datetime) -> Callable[..., dict[str, str]]:
    """An `Authorization: Bearer` header for a user, issued at `now`."""

    def auth_header(
        user_id: UUID, *, issued_at: datetime | None = None
    ) -> dict[str, str]:
        token = auth_service.issue_access_token(
            user_id=user_id,
            family_id=uuid7(),
            key=settings.jwt_secret,
            now=issued_at or now,
        )
        return {"Authorization": f"Bearer {token}"}

    return auth_header


@pytest.fixture(autouse=True, scope="session")
def _real_dummy_hash() -> None:
    """Hash the login's dummy before any test replaces the Argon2 hasher.

    `_dummy_hash()` is cached for the process. Made first inside a test that
    patches `PasswordHasher.hash`, it would stay invalid for every later test.
    """
    auth_service._dummy_hash()


@functools.cache
def _password_hash(password: str) -> str:
    return auth_service.hash_password(password)  # 64 MiB and some time; once each


@pytest.fixture
def make_user(session: Session, now: datetime) -> Callable[..., User]:
    def make_user(
        *,
        email: str | None = None,
        password: str = PASSWORD,
        password_hash: str | None = None,
        is_admin: bool = False,
        must_change_password: bool = False,
    ) -> User:
        user = User(
            email=email or f"{uuid7()}@example.test",
            display_name="Ana",
            password_hash=password_hash or _password_hash(password),
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
def set_signup_code(session: Session) -> Callable[[str | None], None]:
    """Set the sign-up code of the one `instance_settings` row; None closes sign-up."""

    def set_signup_code(code: str | None) -> None:
        session.get_one(InstanceSettings, 1).signup_code = code
        session.flush()

    return set_signup_code


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
            share_token=f"token-{uuid7()}",
            created_at=now,
            seasons=[
                Season(
                    number=1,
                    state=SeasonState.ACTIVE,
                    placement_points=list(DEFAULT_PLACEMENT_POINTS),
                    started_at=now,
                    created_at=now,
                )
            ],
        )
        session.add(league)
        session.flush()
        return league

    return make_league


@pytest.fixture
def committing_engine(engine: Engine) -> Iterator[Engine]:
    """The test database for tests that commit; emptied afterwards (§9)."""
    yield engine
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE leagues, users, auth_attempts CASCADE"))


@pytest.fixture
def committing_settings(settings: Settings) -> Settings:
    """The test settings with a lock_timeout for apps that commit (§9).

    A lock that nobody will release then fails the test instead of hanging it.
    """
    url = make_url(settings.database_url.get_secret_value()).update_query_dict(
        {"options": "-c lock_timeout=5s"}
    )
    return settings.model_copy(
        update={"database_url": SecretStr(url.render_as_string(hide_password=False))}
    )


@pytest.fixture
def wait_for_a_lock_wait(committing_engine: Engine) -> Callable[[], None]:
    """Wait until another connection waits for a row lock (§9)."""
    query = text(
        "SELECT count(*) FROM pg_stat_activity"
        " WHERE datname = current_database() AND wait_event_type = 'Lock'"
    )

    def wait() -> None:
        for _ in range(500):
            with committing_engine.connect() as connection:  # a new snapshot
                if connection.scalar(query):
                    return
            time.sleep(0.01)
        pytest.fail("the second request never waited for the first")

    return wait
