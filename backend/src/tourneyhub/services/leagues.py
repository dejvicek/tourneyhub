import secrets
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from tourneyhub.db.models.leagues import League, Season
from tourneyhub.engine.leagues import (
    DEFAULT_PLACEMENT_POINTS,
    DefaultMatchFormat,
    SeasonState,
)
from tourneyhub.errors import ConflictError, ErrorCode, NotFoundError


def list_leagues(session: Session, *, user_id: UUID) -> list[League]:
    """Return the user's leagues, oldest first (FR-007)."""
    return list(
        session.scalars(
            select(League)
            .where(League.owner_user_id == user_id)
            .order_by(League.created_at, League.id)
        )
    )


def create_league(
    session: Session, *, league_id: UUID, owner_user_id: UUID, name: str, now: datetime
) -> League:
    """Add a league with a client-supplied id and its Season 1 (FR-010, ADR-008).

    Both rows are written in the request's transaction, so a league never exists
    without its first season. A repeated request gets its league back; an id of
    another organizer's league is a conflict. No league row exists yet to lock,
    so two requests racing on the same id meet at the primary key, which
    `api/errors.py` turns into a 409.
    """
    existing = session.get(
        League,
        league_id,
        options=[selectinload(League.seasons)],
        populate_existing=True,  # loads the seasons of a row already in the session
    )
    if existing is not None:
        if existing.owner_user_id != owner_user_id:
            raise ConflictError(ErrorCode.LEAGUE_ID_TAKEN)
        return existing
    league = League(
        id=league_id,
        owner_user_id=owner_user_id,
        name=name,
        share_token=secrets.token_urlsafe(16),  # 128 random bits (FR-071, ADR-008)
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


def get_league(session: Session, *, league_id: UUID, user_id: UUID) -> League:
    """Load one of the user's leagues with its seasons, without a lock.

    Another organizer's league is reported as not found (OWASP API1).
    """
    league = session.scalars(
        select(League)
        .where(League.id == league_id, League.owner_user_id == user_id)
        .options(selectinload(League.seasons))
    ).one_or_none()
    if league is None:
        raise NotFoundError(ErrorCode.LEAGUE_NOT_FOUND)
    return league


def lock_league(session: Session, *, league_id: UUID, user_id: UUID) -> League:
    """Load one of the user's leagues and its seasons under its row lock (ADR-008).

    Another organizer's league is reported as not found (OWASP API1).
    """
    league = session.scalars(
        select(League)
        .where(League.id == league_id, League.owner_user_id == user_id)
        .options(selectinload(League.seasons))
        .with_for_update(of=League)
        .execution_options(populate_existing=True)
    ).one_or_none()
    if league is None:
        raise NotFoundError(ErrorCode.LEAGUE_NOT_FOUND)
    return league


def update_league(
    session: Session,
    *,
    league_id: UUID,
    user_id: UUID,
    name: str | None = None,
    draws_allowed: bool | None = None,
    default_field_count: int | None = None,
    default_match_format: DefaultMatchFormat | None = None,
    default_goals_per_game: int | None = None,
    now: datetime,
) -> League:
    """Set the league settings that are given; None leaves one as it is (FR-011).

    Each value is a target state, so a repeated request changes nothing
    (ADR-008). Turning draws off affects only results entered afterwards
    (BR-012). A changed default never changes an existing tournament, which
    copied it (DATA-MODEL §4.2).
    """
    league = lock_league(session, league_id=league_id, user_id=user_id)
    changes = {
        "name": name,
        "draws_allowed": draws_allowed,
        "default_field_count": default_field_count,
        "default_match_format": default_match_format,
        "default_goals_per_game": default_goals_per_game,
    }
    changed = False
    for attribute, value in changes.items():
        if value is not None and getattr(league, attribute) != value:
            setattr(league, attribute, value)
            changed = True
    if changed:
        league.updated_at = now
    session.flush()
    return league


def delete_league(session: Session, *, league_id: UUID, user_id: UUID) -> None:
    """Delete a league and everything in it, closed seasons too (FR-013, BR-011).

    The seasons, and later everything under them, go through ON DELETE CASCADE
    (DATA-MODEL D6). A repeated delete finds no league: 404.
    """
    league = lock_league(session, league_id=league_id, user_id=user_id)
    session.delete(league)
    session.flush()


def _season_of(league: League, season_id: UUID) -> Season:
    """Find a season among the locked league's own (ADR-008)."""
    season = next((season for season in league.seasons if season.id == season_id), None)
    if season is None:
        raise NotFoundError(ErrorCode.SEASON_NOT_FOUND)
    return season


def _active_season(league: League) -> Season:
    # Every league has exactly one: Season 1 comes with it, and a new season
    # closes the active one in the same transaction.
    season = next(
        (season for season in league.seasons if season.state is SeasonState.ACTIVE),
        None,
    )
    if season is None:
        # Not a StopIteration, which would reach the client as an anonymous 500.
        msg = f"league {league.id} has no active season"
        raise RuntimeError(msg)
    return season


def rename_season(
    session: Session,
    *,
    league_id: UUID,
    season_id: UUID,
    user_id: UUID,
    name: str | None,
    now: datetime,
) -> Season:
    """Rename a season; None restores the default name (FR-020).

    A closed season can still be renamed (BR-011).
    """
    league = lock_league(session, league_id=league_id, user_id=user_id)
    season = _season_of(league, season_id)
    season.name = name
    season.updated_at = now
    session.flush()
    return season


def set_placement_points(
    session: Session,
    *,
    league_id: UUID,
    season_id: UUID,
    user_id: UUID,
    placement_points: Sequence[int],
    now: datetime,
) -> Season:
    """Set the placement points table of the league's active season (FR-011).

    The active season's standings follow on the next read (BR-012, ADR-009). A
    closed season keeps the table it was played under (BR-011, BR-012): the
    screen that sent the request is stale, so it is a conflict and the client
    reloads (ADR-008). The API checks the table with the database's rule
    (`placement_points_valid`).
    """
    league = lock_league(session, league_id=league_id, user_id=user_id)
    season = _season_of(league, season_id)
    if season.state is SeasonState.CLOSED:
        raise ConflictError(ErrorCode.SEASON_CLOSED)
    season.placement_points = list(placement_points)
    season.updated_at = now
    session.flush()
    return season


def start_season(
    session: Session,
    *,
    league_id: UUID,
    user_id: UUID,
    expected_current_number: int,
    now: datetime,
) -> Season:
    """Close the active season and start the next one (FR-021, ADR-008).

    The request carries the number of the season the client sees as active. A
    repeated or stale request finds a newer active season under the league lock
    and gets a conflict, so two starts with one number cannot both succeed. The
    new season starts with a copy of the closed season's table (DATA-MODEL
    §4.2). BR-010, no unfinished tournament, joins these checks together with
    the tournaments.
    """
    league = lock_league(session, league_id=league_id, user_id=user_id)
    current = _active_season(league)
    if current.number != expected_current_number:
        raise ConflictError(
            ErrorCode.SEASON_NUMBER_CHANGED, current_number=current.number
        )
    current.state = SeasonState.CLOSED
    current.closed_at = now
    current.updated_at = now
    session.flush()  # one active season per league: close before the insert
    season = Season(
        number=current.number + 1,
        state=SeasonState.ACTIVE,
        placement_points=list(current.placement_points),
        started_at=now,
        created_at=now,
    )
    league.seasons.append(season)
    session.flush()
    return season
