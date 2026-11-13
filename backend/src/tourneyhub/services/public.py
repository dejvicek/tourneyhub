"""The share link's read-only views, without an account (FR-070 to FR-072).

Every view first finds the league by its share token; the ids in the path are
then loaded through that league, like the organizer's ids through theirs
(ADR-008). Tournaments in setup are visible only to the organizer, so here
they are not found at all.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from tourneyhub.db.models.leagues import League, Player, Season
from tourneyhub.engine.season_standings import SeasonStandingRow
from tourneyhub.errors import ErrorCode, NotFoundError
from tourneyhub.services import standings as standings_service
from tourneyhub.services import tournaments as tournament_service
from tourneyhub.services.tournaments import (
    PlacesView,
    TournamentSummary,
    TournamentView,
)

MAX_SHARE_TOKEN_LENGTH = 128
"""Longer than any token the app issues (22 characters for 128 bits)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SharedLeague:
    """A league as viewers see it: its name, seasons and every player's name.

    Removed players are included, since their names stay in past results.
    """

    name: str
    seasons: tuple[Season, ...]
    players: tuple[Player, ...]


def _shared_league(session: Session, *, share_token: str) -> League:
    """The league with this share token and its seasons (FR-071).

    One equality lookup on the unique index of `share_token`, with no other
    query before it. An unknown token, a malformed one and the token of a
    deleted league are all 404 `share_link_not_found` with an empty detail, so
    the answer tells nothing about which leagues exist. The token is never
    logged, and the error does not repeat it.
    """
    if not 0 < len(share_token) <= MAX_SHARE_TOKEN_LENGTH:
        raise NotFoundError(ErrorCode.SHARE_LINK_NOT_FOUND)
    league = session.scalars(
        select(League)
        .where(League.share_token == share_token)
        .options(selectinload(League.seasons))
    ).one_or_none()
    if league is None:
        raise NotFoundError(ErrorCode.SHARE_LINK_NOT_FOUND)
    return league


def read_shared_league(session: Session, *, share_token: str) -> SharedLeague:
    """Return the league's name, its seasons oldest first and its players."""
    league = _shared_league(session, share_token=share_token)
    players = session.scalars(
        select(Player)
        .where(Player.league_id == league.id)
        .order_by(Player.created_at, Player.id)
    ).all()
    return SharedLeague(
        name=league.name, seasons=tuple(league.seasons), players=tuple(players)
    )


def list_shared_tournaments(
    session: Session, *, share_token: str, season_id: UUID
) -> list[TournamentSummary]:
    """Return a season's tournaments past setup, newest date first (FR-070).

    A season of another league is 404 `season_not_found`.
    """
    league = _shared_league(session, share_token=share_token)
    return tournament_service.list_season_tournaments(
        session, league=league, season_id=season_id, past_setup=True
    )


def read_shared_tournament(
    session: Session, *, share_token: str, tournament_id: UUID
) -> TournamentView:
    """Return a tournament past setup whole: entries, rounds and fields (FR-070).

    A tournament in setup, of another league or unknown is 404
    `tournament_not_found`, the same answer for all three.
    """
    league = _shared_league(session, share_token=share_token)
    return tournament_service.view_tournament(
        session, league=league, tournament_id=tournament_id, past_setup=True
    )


def read_shared_season_standings(
    session: Session, *, share_token: str, season_id: UUID
) -> tuple[SeasonStandingRow, ...]:
    """Return a season's standings, from its finished tournaments (FR-070, FR-061).

    A season of another league is 404 `season_not_found`.
    """
    league = _shared_league(session, share_token=share_token)
    return standings_service.view_season_standings(
        session, league=league, season_id=season_id
    )


def read_shared_standings(
    session: Session, *, share_token: str, tournament_id: UUID
) -> tuple[tournament_service.GroupStandingRow, ...]:
    """Return the group phase's standings now, a round robin's or a Swiss's (FR-060).

    A tournament in setup, of another league or unknown is 404
    `tournament_not_found`, the same answer for all three.
    """
    league = _shared_league(session, share_token=share_token)
    return tournament_service.view_group_standings(
        session, league=league, tournament_id=tournament_id, past_setup=True
    )


def read_shared_places(
    session: Session, *, share_token: str, tournament_id: UUID
) -> PlacesView:
    """Return the places and season points of a tournament past setup (FR-070).

    Before the tournament finishes there are none. A tournament in setup, of
    another league or unknown is 404 `tournament_not_found`.
    """
    league = _shared_league(session, share_token=share_token)
    return tournament_service.view_places(
        session, league=league, tournament_id=tournament_id, past_setup=True
    )
