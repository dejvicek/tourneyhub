import secrets
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from tourneyhub.db.models.leagues import League, Season
from tourneyhub.engine.leagues import DEFAULT_PLACEMENT_POINTS, SeasonState
from tourneyhub.errors import ConflictError, ErrorCode, NotFoundError


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


def lock_league(session: Session, *, league_id: UUID, user_id: UUID) -> League:
    """Load one of the user's leagues under its row lock (ADR-008).

    Another organizer's league is reported as not found (OWASP API1).
    """
    league = session.scalars(
        select(League)
        .where(League.id == league_id, League.owner_user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if league is None:
        raise NotFoundError(ErrorCode.LEAGUE_NOT_FOUND)
    return league


def rename_league(
    session: Session,
    *,
    league_id: UUID,
    user_id: UUID,
    expected_name: str,
    name: str,
    now: datetime,
) -> League:
    """Rename a league if its name is still `expected_name` (ADR-008)."""
    league = lock_league(session, league_id=league_id, user_id=user_id)
    if league.name != expected_name:
        raise ConflictError(ErrorCode.LEAGUE_NAME_CHANGED, current_name=league.name)
    league.name = name
    league.updated_at = now
    session.flush()
    return league
