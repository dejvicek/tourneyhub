import functools
import os
import time
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid7

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, event, func, make_url, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from tourneyhub.api.deps import get_clock, get_now, get_session, get_session_factory
from tourneyhub.app import create_app
from tourneyhub.db.models.accounts import InstanceSettings, RefreshToken, User
from tourneyhub.db.models.leagues import League, Player, Season
from tourneyhub.db.models.tournaments import Field, Tournament, TournamentPhase
from tourneyhub.db.session import create_db_engine
from tourneyhub.engine.accounts import Language
from tourneyhub.engine.leagues import DEFAULT_PLACEMENT_POINTS, SeasonState
from tourneyhub.engine.tournaments import (
    DEFAULT_TIEBREAKERS,
    HalvesMethod,
    MatchFormat,
    PhaseFormat,
    PhaseKind,
    SeedingMethod,
    TournamentState,
    TournamentType,
)
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
    for name, query in _TOURNAMENT_INVARIANTS.items():
        assert session.execute(text(query)).all() == [], name


# DATA-MODEL §5: each query returns the rows that break one rule.
_TOURNAMENT_INVARIANTS = {
    "players of another league": """
        SELECT x.tournament_id, x.player_id FROM (
            SELECT tournament_id, player_id FROM tournament_players
            UNION ALL SELECT tournament_id, player_id FROM entry_members
            UNION ALL SELECT tournament_id, player_id FROM dyp_halves
        ) AS x
        JOIN tournaments t ON t.id = x.tournament_id
        JOIN seasons s ON s.id = t.season_id
        JOIN players p ON p.id = x.player_id
        WHERE p.league_id <> s.league_id
    """,
    "entries of the wrong size (BR-030)": """
        SELECT e.id FROM entries e
        WHERE (SELECT count(*) FROM entry_members m WHERE m.entry_id = e.id)
            <> CASE e.kind WHEN 'player' THEN 1 ELSE 2 END
    """,
    "a knockout at a position that does not fit the group phase (D9)": """
        SELECT k.id FROM tournament_phases k
        WHERE k.kind = 'knockout' AND (k.position = 2) <> EXISTS (
            SELECT FROM tournament_phases g
            WHERE g.tournament_id = k.tournament_id AND g.kind = 'group'
        )
    """,
    "Monster DYP without its own group phase, or another type with one (FR-031)": """
        SELECT t.id FROM tournaments t
        WHERE (t.type = 'monster_dyp') <> EXISTS (
            SELECT FROM tournament_phases p
            WHERE p.tournament_id = t.id AND p.format = 'monster_dyp'
        )
    """,
    "a tournament without a field (FR-090)": """
        SELECT t.id FROM tournaments t
        WHERE NOT EXISTS (SELECT FROM fields f WHERE f.tournament_id = t.id)
    """,
    "DYP halves outside a DYP tournament": """
        SELECT h.tournament_id FROM dyp_halves h
        JOIN tournaments t ON t.id = h.tournament_id
        WHERE t.type <> 'dyp'
    """,
    "participation or sides with an entry of another tournament or stage": """
        SELECT x.round_id, x.entry_id FROM (
            SELECT p.round_id, p.entry_id FROM round_participation p
            UNION ALL
            SELECT m.round_id, s.entry_id FROM match_sides s
            JOIN matches m ON m.id = s.match_id
            WHERE s.entry_id IS NOT NULL
        ) AS x
        JOIN rounds r ON r.id = x.round_id
        JOIN tournament_phases ph ON ph.id = r.phase_id
        JOIN entries e ON e.id = x.entry_id
        WHERE e.tournament_id <> ph.tournament_id
            OR e.stage <> CASE
                WHEN ph.kind = 'knockout' AND ph.position = 2 THEN 'knockout'
                ELSE 'main'
            END
    """,
    "side players of another league": """
        SELECT sp.match_id, sp.player_id FROM match_side_players sp
        JOIN matches m ON m.id = sp.match_id
        JOIN rounds r ON r.id = m.round_id
        JOIN tournament_phases ph ON ph.id = r.phase_id
        JOIN tournaments t ON t.id = ph.tournament_id
        JOIN seasons s ON s.id = t.season_id
        JOIN players p ON p.id = sp.player_id
        WHERE p.league_id <> s.league_id
    """,
    "side players that differ from the side's entry (D2)": """
        SELECT s.match_id, s.side FROM match_sides s
        WHERE s.entry_id IS NOT NULL AND ARRAY(
            SELECT sp.player_id FROM match_side_players sp
            WHERE sp.match_id = s.match_id AND sp.side = s.side
            ORDER BY sp.player_id
        ) <> ARRAY(
            SELECT em.player_id FROM entry_members em
            WHERE em.entry_id = s.entry_id ORDER BY em.player_id
        )
    """,
    "a bye side with players, or a match without two sides (BR-041)": """
        SELECT s.match_id FROM match_sides s
        WHERE s.is_bye AND EXISTS (
            SELECT FROM match_side_players sp
            WHERE sp.match_id = s.match_id AND sp.side = s.side
        )
        UNION ALL
        SELECT m.id FROM matches m
        JOIN rounds r ON r.id = m.round_id
        JOIN tournament_phases ph ON ph.id = r.phase_id
        WHERE (ph.kind = 'group' OR r.round_no = 1)
            AND (SELECT count(*) FROM match_sides s WHERE s.match_id = m.id) <> 2
        UNION ALL
        SELECT m.id FROM matches m
        JOIN rounds r ON r.id = m.round_id
        JOIN tournament_phases ph ON ph.id = r.phase_id
        WHERE ph.monster_knockout_mode = 'lord_have_mercy' AND r.round_no > 1
            AND (
                SELECT count(*) FROM match_sides s
                WHERE s.match_id = m.id AND s.entry_id IS NULL AND NOT s.is_bye
                    AND (
                        SELECT count(*) FROM match_side_players sp
                        WHERE sp.match_id = s.match_id AND sp.side = s.side
                    ) = 2
            ) <> 2
    """,
    "a group round without one participation row per main entry (D5)": """
        SELECT r.id FROM rounds r
        JOIN tournament_phases ph ON ph.id = r.phase_id
        WHERE ph.kind = 'group' AND (
            SELECT count(*) FROM round_participation p WHERE p.round_id = r.id
        ) <> (
            SELECT count(*) FROM entries e
            WHERE e.tournament_id = ph.tournament_id AND e.stage = 'main'
        )
    """,
    # A Monster DYP team is a side without an entry (D2): its entries are those
    # of its players.
    "a group round whose participation disagrees with its matches (D5)": """
        SELECT p.round_id, p.entry_id FROM round_participation p
        WHERE (p.status = 'played') <> EXISTS (
            SELECT FROM match_sides s JOIN matches m ON m.id = s.match_id
            WHERE m.round_id = p.round_id AND (
                s.entry_id = p.entry_id
                OR s.entry_id IS NULL AND EXISTS (
                    SELECT FROM match_side_players sp
                    JOIN entry_members em ON em.player_id = sp.player_id
                    WHERE sp.match_id = s.match_id AND sp.side = s.side
                        AND em.entry_id = p.entry_id
                )
            )
        )
    """,
    "games without a result, a result without games, or a gap (D11)": """
        SELECT g.match_id FROM match_games g
        JOIN matches m ON m.id = g.match_id
        WHERE m.outcome IS NULL OR m.is_walkover
        UNION ALL
        SELECT m.id FROM matches m
        WHERE m.outcome IS NOT NULL AND NOT m.is_walkover
            AND NOT EXISTS (SELECT FROM match_games g WHERE g.match_id = m.id)
        UNION ALL
        SELECT g.match_id FROM match_games g
        GROUP BY g.match_id HAVING max(g.game_no) <> count(*)
    """,
    "games that do not fit the match's format or its outcome (BR-121)": """
        WITH g AS (
            SELECT m.id, m.outcome::text AS outcome,
                CASE WHEN ph.kind = 'knockout' AND m.kind = 'standard'
                    AND ph.final_match_format IS NOT NULL
                    -- The final's round: the bit length of twice round 1's
                    -- standard matches, minus 1, drawn or not (BR-120, D4).
                    AND r.round_no = (
                        SELECT length(ltrim((2 * count(*))::int::bit(32)::text, '0'))
                            - 1
                        FROM rounds r1 JOIN matches m1 ON m1.round_id = r1.id
                        WHERE r1.phase_id = ph.id AND r1.round_no = 1
                            AND m1.kind = 'standard'
                    )
                THEN ph.final_match_format ELSE ph.match_format END AS fmt,
                count(*) AS games,
                count(*) FILTER (WHERE x.winner = 'side_1') AS w1,
                count(*) FILTER (WHERE x.winner = 'side_2') AS w2,
                count(*) FILTER (WHERE x.winner = 'draw') AS d,
                (array_agg(x.winner::text ORDER BY x.game_no DESC))[1] AS last
            FROM matches m
            JOIN match_games x ON x.match_id = m.id
            JOIN rounds r ON r.id = m.round_id
            JOIN tournament_phases ph ON ph.id = r.phase_id
            GROUP BY m.id, ph.id, r.round_no
        )
        SELECT id FROM g WHERE NOT CASE fmt
            WHEN 'bo1' THEN games = 1 AND outcome = last
            WHEN 'bo2' THEN games = 2 AND d = 0 AND outcome = CASE
                WHEN w1 = 2 THEN 'side_1' WHEN w2 = 2 THEN 'side_2' ELSE 'draw'
            END
            ELSE d = 0 AND outcome = last AND (
                CASE outcome WHEN 'side_1' THEN w1 ELSE w2 END
            ) = CASE fmt WHEN 'bo3' THEN 2 ELSE 3 END
        END
    """,
    "a draw outside a group phase, or a Swiss game without a score (BR-090, BR-092)": """
        SELECT m.id FROM matches m
        JOIN rounds r ON r.id = m.round_id
        JOIN tournament_phases ph ON ph.id = r.phase_id
        WHERE m.outcome = 'draw' AND ph.kind <> 'group'
        UNION ALL
        SELECT x.match_id FROM match_games x
        JOIN matches m ON m.id = x.match_id
        JOIN rounds r ON r.id = m.round_id
        JOIN tournament_phases ph ON ph.id = r.phase_id
        WHERE ph.format IN ('swiss', 'monster_dyp') AND x.score_1 IS NULL
    """,
    "a field with a match of another tournament, with a result or requeued": """
        SELECT f.id FROM fields f
        JOIN matches m ON m.id = f.match_id
        JOIN rounds r ON r.id = m.round_id
        JOIN tournament_phases ph ON ph.id = r.phase_id
        WHERE ph.tournament_id <> f.tournament_id
            OR m.outcome IS NOT NULL OR m.requeued_at IS NOT NULL
    """,
    "an entry in two matches of one round (BR-051)": """
        SELECT m.round_id, s.entry_id
        FROM match_sides s JOIN matches m ON m.id = s.match_id
        WHERE s.entry_id IS NOT NULL
        GROUP BY 1, 2 HAVING count(*) > 1
    """,
    "a player on two fields at once (BR-131)": """
        SELECT f.tournament_id, sp.player_id FROM fields f
        JOIN match_side_players sp ON sp.match_id = f.match_id
        GROUP BY f.tournament_id, sp.player_id HAVING count(*) > 1
    """,
}


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
    app.dependency_overrides[get_clock] = lambda: lambda: now
    with TestClient(app) as client:  # the context manager runs the lifespan
        yield client


@pytest.fixture
def travel(client: TestClient, now: datetime) -> Callable[[timedelta], datetime]:
    """Move the clock that the client's requests see to `now + offset`."""
    app = client.app
    assert isinstance(app, FastAPI)

    def travel(offset: timedelta) -> datetime:
        app.dependency_overrides[get_now] = lambda: now + offset
        app.dependency_overrides[get_clock] = lambda: lambda: now + offset
        return now + offset

    return travel


def _login_row(user_id: UUID, family_id: UUID, now: datetime) -> RefreshToken:
    """A refresh token that makes `family_id` a live login of the user (ADR-006)."""
    return RefreshToken(
        user_id=user_id,
        family_id=family_id,
        parent_id=None,
        token_hash=uuid7().bytes,
        expires_at=now + auth_service.REFRESH_TOKEN_LIFETIME,
        created_at=now,
    )


@pytest.fixture
def auth_header(
    settings: Settings, session: Session, now: datetime
) -> Callable[..., dict[str, str]]:
    """An `Authorization: Bearer` header for a user, issued at `now`.

    A user who exists gets a login of their own, a refresh-token family with one
    unrevoked row, because the API refuses a token whose family has none
    (ADR-006). A user who does not exist gets a token with a family of no rows.
    The row is not committed: for apps that commit, see `committed_auth_header`.
    """

    def auth_header(
        user_id: UUID, *, issued_at: datetime | None = None
    ) -> dict[str, str]:
        family_id = uuid7()
        try:
            with session.begin_nested():
                session.add(_login_row(user_id, family_id, now))
                session.flush()
        except IntegrityError:  # no such user
            pass
        token = auth_service.issue_access_token(
            user_id=user_id,
            family_id=family_id,
            key=settings.jwt_secret,
            now=issued_at or now,
        )
        return {"Authorization": f"Bearer {token}"}

    return auth_header


@pytest.fixture
def committed_auth_header(
    settings: Settings, committing_engine: Engine, now: datetime
) -> Callable[..., dict[str, str]]:
    """`auth_header` for tests that commit: the user is committed already, and so
    is the login (§9)."""

    def committed_auth_header(
        user_id: UUID, *, issued_at: datetime | None = None
    ) -> dict[str, str]:
        family_id = uuid7()
        with Session(committing_engine) as committing:
            committing.add(_login_row(user_id, family_id, now))
            committing.commit()
        token = auth_service.issue_access_token(
            user_id=user_id,
            family_id=family_id,
            key=settings.jwt_secret,
            now=issued_at or now,
        )
        return {"Authorization": f"Bearer {token}"}

    return committed_auth_header


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
def make_player(session: Session, now: datetime) -> Callable[..., Player]:
    def make_player(*, league: League, name: str | None = None) -> Player:
        player = Player(
            league_id=league.id, name=name or f"Player {uuid7()}", created_at=now
        )
        session.add(player)
        session.flush()
        return player

    return make_player


@pytest.fixture
def make_tournament(
    session: Session, make_league: Callable[..., League], now: datetime
) -> Callable[..., Tournament]:
    """A tournament in setup in the league's active season, with a round robin
    (Monster DYP: its own group phase) and one field; nothing picked."""

    def make_tournament(
        *,
        league: League | None = None,
        tournament_type: TournamentType = TournamentType.SINGLES,
        state: TournamentState = TournamentState.SETUP,
    ) -> Tournament:
        league = league or make_league()
        season = next(s for s in league.seasons if s.state is SeasonState.ACTIVE)
        monster = tournament_type is TournamentType.MONSTER_DYP
        tournament = Tournament(
            id=uuid7(),
            season_id=season.id,
            name="Thursday",
            date=date(2026, 11, 5),
            type=tournament_type,
            state=state,
            seeding_method=SeedingMethod.RANKING,
            halves_method=HalvesMethod.RANKING,
            rng_seed=bytes(range(16)),
            draw_counter=0,
            goals_per_game=10,
            created_at=now,
            phases=[
                TournamentPhase(
                    position=1,
                    kind=PhaseKind.GROUP,
                    format=PhaseFormat.MONSTER_DYP
                    if monster
                    else PhaseFormat.ROUND_ROBIN,
                    round_robin_legs=None if monster else 1,
                    sit_out_points=0 if monster else None,
                    tiebreakers=list(DEFAULT_TIEBREAKERS) if monster else None,
                    match_format=MatchFormat.BO1,
                    created_at=now,
                )
            ],
            fields=[Field(number=1, created_at=now)],
            players=[],
            halves=[],
            entries=[],
        )
        session.add(tournament)
        session.flush()
        return tournament

    return make_tournament


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
