from datetime import datetime
from http import HTTPStatus
from uuid import UUID

from fastapi import APIRouter
from pydantic import StrictBool

from tourneyhub.api.deps import ClockDep, CurrentUserDep, SessionDep
from tourneyhub.api.schemas import (
    ErrorResponse,
    PlayerName,
    RequestModel,
    ResponseModel,
)
from tourneyhub.services import players as player_service

router = APIRouter(
    prefix="/leagues/{league_id}/players",
    tags=["players"],
    responses={
        HTTPStatus.UNAUTHORIZED: {"model": ErrorResponse},
        HTTPStatus.NOT_FOUND: {"model": ErrorResponse},
    },
)


class PlayerCreate(RequestModel):
    """A name to add to the league's player list (FR-012)."""

    name: PlayerName


class PlayerRename(RequestModel):
    """A player's new name, the target state (FR-012, ADR-008)."""

    name: PlayerName


class PlayerRemoval(RequestModel):
    """Whether the player is removed from the list, the target state (BR-002)."""

    removed: StrictBool


class PlayerRead(ResponseModel):
    """A player of a league; `removed_at` is null while they are on the list."""

    id: UUID
    name: str
    removed_at: datetime | None


@router.get("")
def list_players(
    league_id: UUID,
    session: SessionDep,
    user: CurrentUserDep,
    *,
    include_removed: bool = False,
) -> list[PlayerRead]:
    """List the league's players in the order they were added (FR-012).

    Removed players come only with `include_removed=true`. Players belong to the
    league, so closed seasons need nothing special.
    """
    players = player_service.list_players(
        session, league_id=league_id, user_id=user.id, include_removed=include_removed
    )
    return [PlayerRead.model_validate(player) for player in players]


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    responses={
        HTTPStatus.CONFLICT: {"model": ErrorResponse},
        HTTPStatus.UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    },
)
def add_player(
    league_id: UUID,
    body: PlayerCreate,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> PlayerRead:
    """Add a player to the league (FR-012).

    A name that another player has, in any case, is 422 `player_name_taken`
    with the holder's `player_id`, `name` and `removed` (BR-001). When the
    holder is removed, the UI asks whether it is the same person and restores
    them (ADR-002). A parallel add of the same name that wins the race to the
    unique index makes this one 409 `player_name_taken`: reload. A league holds at
    most 500 players, removed ones included: more is 422 `player_limit_reached`.
    """
    player = player_service.add_player(
        session, league_id=league_id, user_id=user.id, name=body.name, clock=clock
    )
    return PlayerRead.model_validate(player)


@router.put(
    "/{player_id}/name",
    responses={
        HTTPStatus.CONFLICT: {"model": ErrorResponse},
        HTTPStatus.UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    },
)
def rename_player(
    league_id: UUID,
    player_id: UUID,
    body: PlayerRename,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> PlayerRead:
    """Rename a player; the new name shows in past results too (FR-012).

    422 `player_name_taken` as for an add, 409 for the race. A removed player can
    be renamed too, and the new name must be free as well (BR-011).
    """
    player = player_service.rename_player(
        session,
        league_id=league_id,
        player_id=player_id,
        user_id=user.id,
        name=body.name,
        clock=clock,
    )
    return PlayerRead.model_validate(player)


@router.put("/{player_id}/removed")
def set_player_removed(
    league_id: UUID,
    player_id: UUID,
    body: PlayerRemoval,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> PlayerRead:
    """Remove a player from the list, or restore them (FR-012, BR-002).

    A removal keeps the player, their name and their history; a restored player
    is the same player. Both are target states, so repeating one changes nothing.
    """
    player = player_service.set_player_removed(
        session,
        league_id=league_id,
        player_id=player_id,
        user_id=user.id,
        removed=body.removed,
        clock=clock,
    )
    return PlayerRead.model_validate(player)
