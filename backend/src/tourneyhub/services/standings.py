"""Season standings, computed on read from the finished tournaments (FR-061, BR-112).

Nothing derived is stored (DATA-MODEL D1): every read loads the season's
finished tournaments, places their entries with the season's table and adds
the points up with the engine. Removed players stay in the standings, since a
removed player keeps their past results, places and points (BR-002); the
league ranking leaves them out only because it orders who can still be picked
(BR-020).
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from tourneyhub.db.models.leagues import League, Season
from tourneyhub.db.models.tournaments import Tournament
from tourneyhub.engine.season_standings import (
    SeasonEffectRow,
    SeasonStandingRow,
    season_effect,
    season_standings,
)
from tourneyhub.engine.tournaments import TournamentState
from tourneyhub.errors import ErrorCode, NotFoundError
from tourneyhub.services import tournaments as tournament_service
from tourneyhub.services.leagues import get_league


def _season(league: League, season_id: UUID) -> Season:
    """One of the league's own seasons; another league's is 404 (ADR-008)."""
    season = next((s for s in league.seasons if s.id == season_id), None)
    if season is None:
        raise NotFoundError(ErrorCode.SEASON_NOT_FOUND)
    return season


def view_season_standings(
    session: Session, *, league: League, season_id: UUID
) -> tuple[SeasonStandingRow, ...]:
    """Return a season's standings: every player of a finished tournament (FR-061).

    Closed seasons too, with the table they were played under (BR-011).
    """
    season = _season(league, season_id)
    points = tournament_service.finished_season_points(session, season=season)
    return season_standings(points.values())


def read_season_standings(
    session: Session, *, league_id: UUID, season_id: UUID, user_id: UUID
) -> tuple[SeasonStandingRow, ...]:
    """Return the standings of one of the user's league's seasons (FR-061).

    Another organizer's league is 404 `league_not_found`, and a season of
    another league 404 `season_not_found`.
    """
    league = get_league(session, league_id=league_id, user_id=user_id)
    return view_season_standings(session, league=league, season_id=season_id)


def read_season_effect(
    session: Session, *, league_id: UUID, tournament_id: UUID, user_id: UUID
) -> tuple[SeasonEffectRow, ...]:
    """Return what a finished tournament changed in its season's standings.

    A tournament that is not finished contributes nothing yet (BR-112), so it
    has no rows, like its places. An unknown tournament or one of another
    league is 404 `tournament_not_found`.
    """
    league = get_league(session, league_id=league_id, user_id=user_id)
    found = session.execute(
        select(Tournament.season_id, Tournament.state)
        .join(Season, Tournament.season_id == Season.id)
        .where(Tournament.id == tournament_id, Season.league_id == league.id)
    ).one_or_none()
    if found is None:
        raise NotFoundError(ErrorCode.TOURNAMENT_NOT_FOUND)
    season_id, state = found
    if state is not TournamentState.FINISHED:
        return ()
    points = tournament_service.finished_season_points(
        session, season=_season(league, season_id)
    )
    this = points.pop(tournament_id, None)
    if this is None:  # a result was cleared between the two reads
        return ()
    return season_effect(this, points.values())
