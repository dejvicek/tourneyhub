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
from tourneyhub.api.public_headers import PUBLIC_PREFIX
from tourneyhub.api.schemas import ErrorResponse, ResponseModel
from tourneyhub.api.tournament_models import (
    EntryRead,
    FieldRead,
    PhaseRead,
    PlaceReasonKind,
    RoundRead,
    TournamentSummary,
)
from tourneyhub.engine.knockout import RoundName
from tourneyhub.engine.tournaments import PhaseFormat, TournamentState, TournamentType
from tourneyhub.services import public as public_service
from tourneyhub.services.tournaments import PlacesView

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

    A separate allowlist of fields, not a copy of the organizer's whole
    tournament: a field added to TournamentRead must not reach viewers until it
    is added here on purpose. `waiting` lists the matches waiting for a field,
    in the order they will get one.
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


class PublicStandingRow(ResponseModel):
    """One entry's line in the group-phase standings, for viewers (FR-060).

    A round robin's (BR-101), a Swiss's or a Monster DYP's (BR-072 to
    BR-074); a Monster DYP's row is a player's, by their main entry. `place`
    is shared by entries still level (BR-074), and the next place skips
    (BR-104). `points` come from the matches; in a Swiss and a Monster DYP
    they also include the points for sitting out, as soon as the round is
    drawn (BR-076, BR-077), and a round robin gives none (BR-071). `bh1` and
    `bh2` are the Swiss's and the Monster DYP's (BR-073), null in a round
    robin. `game_difference` ranks a round robin in
    every match format; the screen shows its column only in BO3 and BO5
    (BR-101). The organizer's extras, the form and what ranks one entry above
    the next, are not part of it.
    """

    place: int
    entry_id: UUID
    played: int
    won: int
    drawn: int
    lost: int
    sat_out: int
    points: int
    game_difference: int
    score_difference: int
    bh1: int | None
    bh2: int | None


class PublicSeasonStandingRow(ResponseModel):
    """One player's line in the season standings, for viewers (FR-061, BR-113).

    `place` is shared by players level on points and wins, and the next place
    skips (BR-104). Removed players stay, with their points (BR-002).
    """

    place: int
    player_id: UUID
    points: int
    tournaments_played: int
    tournament_wins: int


class PublicPlaceReasonRead(ResponseModel):
    """Why an entry has its place, for viewers (§7.13): the organizer's reason."""

    kind: PlaceReasonKind
    round: RoundName | None
    score: tuple[int, int] | None
    opponent_entry_id: UUID | None
    group_place: int | None
    group_format: PhaseFormat | None


class PublicPlaceRead(ResponseModel):
    """An entry's final place and the season points each of its players earns."""

    place: int
    entry_id: UUID
    points_per_player: int
    reason: PublicPlaceReasonRead


class PublicPlacesRead(ResponseModel):
    """The places of a tournament for viewers (FR-070), best place first.

    `complete` is true once the tournament is finished; before that `rows` is
    empty.
    """

    complete: bool
    rows: list[PublicPlaceRead]


def _public_places(places: PlacesView) -> PublicPlacesRead:
    return PublicPlacesRead(
        complete=places.complete,
        rows=[
            PublicPlaceRead(
                place=row.place,
                entry_id=row.entry_id,
                points_per_player=row.points_per_player,
                reason=PublicPlaceReasonRead(
                    kind=row.kind,
                    round=row.round,
                    score=row.score,
                    opponent_entry_id=row.opponent_entry_id,
                    group_place=row.group_place,
                    group_format=places.group_format,
                ),
            )
            for row in places.rows
        ],
    )


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


@router.get("/seasons/{season_id}/standings")
def read_public_season_standings(
    share_token: str, season_id: UUID, session: SessionDep
) -> list[PublicSeasonStandingRow]:
    """Return a season's standings from its finished tournaments (FR-070, FR-061).

    The same table as the organizer's, with removed players, whose points stay
    (BR-002). A season of another league is 404 `season_not_found`.
    """
    rows = public_service.read_shared_season_standings(
        session, share_token=share_token, season_id=season_id
    )
    return [PublicSeasonStandingRow.model_validate(row) for row in rows]


@router.get("/tournaments/{tournament_id}/standings")
def read_public_standings(
    share_token: str, tournament_id: UUID, session: SessionDep
) -> list[PublicStandingRow]:
    """Return the group phase's standings as they are now (FR-060, FR-070).

    A round robin's, a Swiss's or a Monster DYP's, one row per player in a
    Monster DYP; a tournament without a group phase has an empty list. A
    tournament in setup is 404
    `tournament_not_found`, like an unknown one or one of another league.
    """
    rows = public_service.read_shared_standings(
        session, share_token=share_token, tournament_id=tournament_id
    )
    return [PublicStandingRow.model_validate(row) for row in rows]


@router.get(
    "/tournaments/{tournament_id}/places",
    responses={HTTPStatus.UNPROCESSABLE_CONTENT: {"model": ErrorResponse}},
)
def read_public_places(
    share_token: str, tournament_id: UUID, session: SessionDep
) -> PublicPlacesRead:
    """Return the places and the season points of a finished tournament (FR-070).

    Before the tournament finishes, `complete` is false and there are no rows.
    With a knockout, its entries take the top places by BR-102, the others
    follow in their group-phase order (BR-103). A tournament in setup
    is 404 `tournament_not_found`.
    """
    places = public_service.read_shared_places(
        session, share_token=share_token, tournament_id=tournament_id
    )
    return _public_places(places)
