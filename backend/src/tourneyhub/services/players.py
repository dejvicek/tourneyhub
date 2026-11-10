from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tourneyhub.db.models.leagues import Player
from tourneyhub.engine.leagues import MAX_PLAYERS_PER_LEAGUE
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
    session: Session,
    *,
    league_id: UUID,
    user_id: UUID,
    name: str,
    clock: Callable[[], datetime],
) -> Player:
    """Add a player to the league's list (FR-012).

    A name that a player of the league has, in any case, is refused, and so is
    one that a removed player has: the organizer restores that player instead
    (BR-001, ADR-002). A league holds at most `MAX_PLAYERS_PER_LEAGUE` players,
    removed ones included, counted under the lock. `clock` is read after the
    lock is held, so "order added" is the commit order. Two adds of one name race at the unique index only when
    the league lock does not cover them, and the loser gets a 409 there
    (`api/errors.py`).
    """
    league = lock_league(session, league_id=league_id, user_id=user_id)
    _refuse_a_taken_name(session, league_id=league.id, name=name, except_player_id=None)
    count = session.scalar(
        select(func.count()).select_from(Player).where(Player.league_id == league.id)
    )
    if count is not None and count >= MAX_PLAYERS_PER_LEAGUE:
        raise RuleViolationError(
            ErrorCode.PLAYER_LIMIT_REACHED, limit=MAX_PLAYERS_PER_LEAGUE
        )
    player = Player(league_id=league.id, name=name, created_at=clock())
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
    clock: Callable[[], datetime],
) -> Player:
    """Give a player a new name; the new name shows in past results too (FR-012).

    The name is the target state, so a repeat changes nothing (ADR-008). A
    change of case only is the same player's name. A removed player can be renamed
    too: a rename always applies (BR-011), and the new name must be free like
    any other, removed holders included. `clock` is read after the lock.
    """
    player = _lock_player(
        session, league_id=league_id, player_id=player_id, user_id=user_id
    )
    if player.name == name:
        return player
    _refuse_a_taken_name(
        session, league_id=league_id, name=name, except_player_id=player.id
    )
    player.name = name
    player.updated_at = clock()
    session.flush()
    return player


def set_player_removed(
    session: Session,
    *,
    league_id: UUID,
    player_id: UUID,
    user_id: UUID,
    removed: bool,
    clock: Callable[[], datetime],
) -> Player:
    """Remove a player from the list, or put them back (FR-012, BR-002).

    A removal only sets `removed_at`: the row, its name and its history stay
    (DATA-MODEL D6). The flag is the target state, so repeating a removal keeps
    the first `removed_at`, and restoring a player on the list changes nothing
    (ADR-008). A restored player is the same player, with the same id. A restore
    needs no name check: the unique index includes removed players, so a name is
    never freed, and every add and rename checks against all players (BR-001).
    `clock` is read after the lock. BR-002, no removal from an unfinished
    tournament, joins these checks with the tournaments.
    """
    player = _lock_player(
        session, league_id=league_id, player_id=player_id, user_id=user_id
    )
    if removed and player.removed_at is None:
        player.removed_at = now = clock()
    elif not removed and player.removed_at is not None:
        player.removed_at = None
        now = clock()
    else:
        return player
    player.updated_at = now
    session.flush()
    return player
