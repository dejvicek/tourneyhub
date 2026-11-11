"""The share link's routes: anonymous and read-only (FR-070 to FR-072, ADR-008).

Nothing here takes an access token or writes. The response models list only
what viewers may see: no league id, owner, email or share token, and no draw
counter or lot seed of a tournament.
"""

from datetime import date
from http import HTTPStatus
from uuid import UUID

from fastapi import APIRouter

from tourneyhub.api.deps import SessionDep
from tourneyhub.api.leagues import SeasonRead
from tourneyhub.api.schemas import ErrorResponse, ResponseModel
from tourneyhub.api.tournaments import (
    EntryRead,
    FieldRead,
    PhaseRead,
    RoundRead,
    TournamentSummary,
)
from tourneyhub.engine.tournaments import TournamentState, TournamentType
from tourneyhub.services import public as public_service

PUBLIC_PREFIX = "/public"

router = APIRouter(
    prefix=PUBLIC_PREFIX + "/{share_token}",
    tags=["public"],
    responses={HTTPStatus.NOT_FOUND: {"model": ErrorResponse}},
)


class PublicPlayerRead(ResponseModel):
    """A player's name for viewers; removed players too, for past results."""

    id: UUID
    name: str


class PublicLeagueRead(ResponseModel):
    """A league through its share link: name, seasons oldest first, players.

    Players come in the order they were added; names sort in the UI's language.
    """

    name: str
    seasons: list[SeasonRead]
    players: list[PublicPlayerRead]


class PublicTournamentRead(ResponseModel):
    """A tournament through the share link: entries, rounds and fields (FR-070).

    The same view as the organizer's whole tournament, without anything only the
    organizer uses. `waiting` lists the matches waiting for a field, in the
    order they will get one.
    """

    id: UUID
    season_id: UUID
    name: str
    date: date
    type: TournamentType
    state: TournamentState
    current_phase_id: UUID | None
    current_phase_done: bool
    goals_per_game: int
    phases: list[PhaseRead]
    entries: list[EntryRead]
    rounds: list[RoundRead]
    fields: list[FieldRead]
    waiting: list[UUID]


@router.get("")
def read_public_league(share_token: str, session: SessionDep) -> PublicLeagueRead:
    """Return the league of a share link (FR-070).

    An unknown token is 404 `share_link_not_found`, with an empty detail.
    """
    league = public_service.read_shared_league(session, share_token=share_token)
    return PublicLeagueRead.model_validate(league)


@router.get("/seasons/{season_id}/tournaments")
def list_public_tournaments(
    share_token: str, season_id: UUID, session: SessionDep
) -> list[TournamentSummary]:
    """List a season's tournaments, newest date first, without those in setup.

    A season of another league is 404 `season_not_found` (FR-070).
    """
    tournaments = public_service.list_shared_tournaments(
        session, share_token=share_token, season_id=season_id
    )
    return [TournamentSummary.model_validate(t) for t in tournaments]


@router.get("/tournaments/{tournament_id}")
def read_public_tournament(
    share_token: str, tournament_id: UUID, session: SessionDep
) -> PublicTournamentRead:
    """Return a tournament whole: its entries, rounds, results and fields.

    A tournament in setup is 404 `tournament_not_found`, like an unknown one or
    one of another league (FR-070).
    """
    tournament = public_service.read_shared_tournament(
        session, share_token=share_token, tournament_id=tournament_id
    )
    return PublicTournamentRead.model_validate(tournament)
