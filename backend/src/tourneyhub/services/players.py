from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tourneyhub.db.models.leagues import Player
from tourneyhub.errors import ErrorCode, NotFoundError, RuleViolationError
from tourneyhub.services.leagues import get_league, lock_league


def list_players(
    session: Session, *, league_id: UUID, user_id: UUID, include_removed: bool
) -> list[Player]:
    """Return a league's players in the order they were added (FR-012).

    Removed players are left out unless asked for. The order is stable and
    carries no language: names sort in the UI's language (DATA-MODEL §2).
    Players belong to the league, so every season shows the same list.
    """
    league = get_league(session, league_id=league_id, user_id=user_id)
    query = select(Player).where(Player.league_id == league.id)
    if not include_removed:
        query = query.where(Player.removed_at.is_(None))
    return list(session.scalars(query.order_by(Player.created_at, Player.id)))


def _lock_player(
    session: Session, *, league_id: UUID, player_id: UUID, user_id: UUID
) -> Player:
    """Lock the league, then load one of its players (ADR-008).

    The id is loaded through the organizer's league, so another league's player
    is not found, nor is one of another organizer.
    """
    league = lock_league(session, league_id=league_id, user_id=user_id)
    player = session.scalars(
        select(Player)
        .where(Player.league_id == league.id, Player.id == player_id)
        .execution_options(populate_existing=True)
    ).one_or_none()
    if player is None:
        raise NotFoundError(ErrorCode.PLAYER_NOT_FOUND)
    return player


def _refuse_a_taken_name(
    session: Session, *, league_id: UUID, name: str, except_player_id: UUID | None
) -> None:
    """Refuse a name that another player of the league has, removed or not (BR-001).

    Compares as the unique index does, with lower() on both sides. The detail
    names the holder, so that the client can offer to restore a removed one
    (ADR-002).
    """
    query = select(Player).where(
        Player.league_id == league_id, func.lower(Player.name) == func.lower(name)
    )
    if except_player_id is not None:
        query = query.where(Player.id != except_player_id)
    holder = session.scalars(query.execution_options(populate_existing=True)).first()
    if holder is not None:
        raise RuleViolationError(
            ErrorCode.PLAYER_NAME_TAKEN,
            player_id=str(holder.id),
            name=holder.name,
            removed=holder.removed_at is not None,
        )


def add_player(
    session: Session, *, league_id: UUID, user_id: UUID, name: str, now: datetime
) -> Player:
    """Add a player to the league's list (FR-012).

    A name that a player of the league has, in any case, is refused, and so is
    one that a removed player has: the organizer restores that player instead
    (BR-001, ADR-002). Two adds of one name race at the unique index only when
    the league lock does not cover them, and the loser gets a 409 there
    (`api/errors.py`).
    """
    league = lock_league(session, league_id=league_id, user_id=user_id)
    _refuse_a_taken_name(session, league_id=league.id, name=name, except_player_id=None)
    player = Player(league_id=league.id, name=name, created_at=now)
    session.add(player)
    session.flush()
    return player


def rename_player(
    session: Session,
    *,
    league_id: UUID,
    player_id: UUID,
    user_id: UUID,
    name: str,
    now: datetime,
) -> Player:
    """Give a player a new name; the new name shows in past results too (FR-012).

    The name is the target state, so a repeat changes nothing (ADR-008). A
    change of case only is the same player's name. A removed player stays as
    they are until restored. Renaming is allowed in any season (BR-011).
    """
    player = _lock_player(
        session, league_id=league_id, player_id=player_id, user_id=user_id
    )
    if player.removed_at is not None:
        raise RuleViolationError(ErrorCode.PLAYER_REMOVED)
    if player.name == name:
        return player
    _refuse_a_taken_name(
        session, league_id=league_id, name=name, except_player_id=player.id
    )
    player.name = name
    player.updated_at = now
    session.flush()
    return player


def set_player_removed(
    session: Session,
    *,
    league_id: UUID,
    player_id: UUID,
    user_id: UUID,
    removed: bool,
    now: datetime,
) -> Player:
    """Remove a player from the list, or put them back (FR-012, BR-002).

    A removal only sets `removed_at`: the row, its name and its history stay
    (DATA-MODEL D6). The flag is the target state, so repeating a removal keeps
    the first `removed_at`, and restoring a player on the list changes nothing
    (ADR-008). A restored player is the same player, with the same id. The
    name cannot have been taken meanwhile: removed players hold their names
    (BR-001) and cannot be renamed. BR-002, no removal from an unfinished
    tournament, joins these checks with the tournaments.
    """
    player = _lock_player(
        session, league_id=league_id, player_id=player_id, user_id=user_id
    )
    if removed and player.removed_at is None:
        player.removed_at = now
    elif not removed and player.removed_at is not None:
        player.removed_at = None
    else:
        return player
    player.updated_at = now
    session.flush()
    return player
