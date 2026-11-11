"""Season standings and a tournament's effect on them (FR-061, BR-110 to BR-113).

Computed on read from the finished tournaments (ADR-009); nothing is stored.
"""

from http import HTTPStatus
from uuid import UUID

from fastapi import APIRouter

from tourneyhub.api.deps import CurrentUserDep, SessionDep
from tourneyhub.api.schemas import ErrorResponse, ResponseModel
from tourneyhub.services import standings as standings_service

router = APIRouter(
    prefix="/leagues/{league_id}",
    tags=["standings"],
    responses={
        HTTPStatus.UNAUTHORIZED: {"model": ErrorResponse},
        HTTPStatus.NOT_FOUND: {"model": ErrorResponse},
    },
)


class SeasonStandingRead(ResponseModel):
    """One player's line in the season standings (FR-061, BR-113).

    `place` is shared by players level on points and wins, and the next place
    skips (BR-104). `tournament_wins` counts the finished tournaments in which
    the player's entry was 1st, a shared 1st included.
    """

    place: int
    player_id: UUID
    points: int
    tournaments_played: int
    tournament_wins: int


class SeasonEffectRead(ResponseModel):
    """One player's change in the season standings after a tournament (§7.13).

    `place` and `points` are those with the tournament; `earned` is what the
    player got from it (0 without playing in it); `previous_place` is the place
    in the standings of the season's other finished tournaments, null for a
    player who played in none of them.
    """

    player_id: UUID
    place: int
    points: int
    earned: int
    previous_place: int | None


@router.get("/seasons/{season_id}/standings")
def read_season_standings(
    league_id: UUID, season_id: UUID, session: SessionDep, user: CurrentUserDep
) -> list[SeasonStandingRead]:
    """Return the season's standings: every player of a finished tournament (FR-061).

    Total placement points, then tournament wins; players still level share
    the place (BR-113). Only finished tournaments count (BR-112), and removed
    players stay (BR-002). A closed season is read with the table it was
    played under. Another league's season is 404 `season_not_found`.
    """
    rows = standings_service.read_season_standings(
        session, league_id=league_id, season_id=season_id, user_id=user.id
    )
    return [SeasonStandingRead.model_validate(row) for row in rows]


@router.get("/tournaments/{tournament_id}/season-effect")
def read_season_effect(
    league_id: UUID, tournament_id: UUID, session: SessionDep, user: CurrentUserDep
) -> list[SeasonEffectRead]:
    """Return what a finished tournament changed in the season standings (screen 10).

    One row per player of the season standings, best first. A tournament that
    is not finished contributes nothing yet (BR-112): the list is empty, like
    its places. Another league's tournament is 404 `tournament_not_found`.
    """
    rows = standings_service.read_season_effect(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user.id
    )
    return [SeasonEffectRead.model_validate(row) for row in rows]
