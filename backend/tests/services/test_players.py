from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import User
from tourneyhub.db.models.leagues import League, Player
from tourneyhub.errors import (
    ErrorCode,
    NotFoundError,
    RuleViolationError,
)
from tourneyhub.services import players as player_service


def _add(session: Session, league: League, name: str, now: datetime) -> Player:
    return player_service.add_player(
        session, league_id=league.id, user_id=league.owner_user_id, name=name, now=now
    )


def _rename(
    session: Session, league: League, player: Player, name: str, now: datetime
) -> Player:
    return player_service.rename_player(
        session,
        league_id=league.id,
        player_id=player.id,
        user_id=league.owner_user_id,
        name=name,
        now=now,
    )


def _set_removed(
    session: Session, league: League, player: Player, now: datetime, *, removed: bool
) -> Player:
    return player_service.set_player_removed(
        session,
        league_id=league.id,
        player_id=player.id,
        user_id=league.owner_user_id,
        removed=removed,
        now=now,
    )


def _names(
    session: Session, league: League, *, include_removed: bool = False
) -> list[str]:
    return [
        player.name
        for player in player_service.list_players(
            session,
            league_id=league.id,
            user_id=league.owner_user_id,
            include_removed=include_removed,
        )
    ]


def test_fr012_add_player_puts_a_name_on_the_list(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()

    player = _add(session, league, "Ana", now)

    assert (player.league_id, player.name) == (league.id, "Ana")
    assert player.removed_at is None
    assert player.created_at == now
    assert _names(session, league) == ["Ana"]


def test_br001_add_player_refuses_a_name_in_another_case(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    ana = _add(session, league, "Ana", now)

    with pytest.raises(RuleViolationError) as raised:
        _add(session, league, "ANA", now)

    assert raised.value.code is ErrorCode.PLAYER_NAME_TAKEN
    assert raised.value.detail == {
        "player_id": str(ana.id),
        "name": "Ana",
        "removed": False,
    }


def test_br001_add_player_refuses_the_name_of_a_removed_player(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    ana = _add(session, league, "Ana", now)
    _set_removed(session, league, ana, now, removed=True)

    with pytest.raises(RuleViolationError) as raised:
        _add(session, league, "ana", now)

    assert raised.value.code is ErrorCode.PLAYER_NAME_TAKEN
    assert raised.value.detail == {
        "player_id": str(ana.id),
        "name": "Ana",
        "removed": True,
    }


def test_br001_two_leagues_can_have_a_player_of_the_same_name(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    first, second = make_league(), make_league()

    _add(session, first, "Ana", now)
    _add(session, second, "Ana", now)

    assert _names(session, first) == _names(session, second) == ["Ana"]


def test_fr012_list_players_leaves_out_removed_ones_unless_asked(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    ana = _add(session, league, "Ana", now)
    _add(session, league, "Bob", now + timedelta(minutes=1))
    _set_removed(session, league, ana, now, removed=True)

    assert _names(session, league) == ["Bob"]
    assert _names(session, league, include_removed=True) == ["Ana", "Bob"]


def test_fr012_list_players_is_in_the_order_they_were_added(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    for minutes, name in enumerate(["Zoe", "Ana", "Mia"]):
        _add(session, league, name, now + timedelta(minutes=minutes))

    assert _names(session, league) == ["Zoe", "Ana", "Mia"]


def test_fr012_rename_player_changes_the_name_and_the_update_time(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    player = _add(session, league, "Ana", now)
    later = now + timedelta(hours=1)

    renamed = player_service.rename_player(
        session,
        league_id=league.id,
        player_id=player.id,
        user_id=league.owner_user_id,
        name="Anna",
        now=later,
    )

    assert renamed.id == player.id
    assert (renamed.name, renamed.updated_at) == ("Anna", later)


def test_adr008_renaming_to_the_current_name_changes_nothing(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    player = _add(session, league, "Ana", now)

    renamed = player_service.rename_player(
        session,
        league_id=league.id,
        player_id=player.id,
        user_id=league.owner_user_id,
        name="Ana",
        now=now + timedelta(hours=1),
    )

    assert renamed.updated_at is None


def test_br001_a_player_can_change_the_case_of_their_own_name(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    player = _add(session, league, "ana", now)

    renamed = player_service.rename_player(
        session,
        league_id=league.id,
        player_id=player.id,
        user_id=league.owner_user_id,
        name="Ana",
        now=now,
    )

    assert renamed.name == "Ana"


@pytest.mark.parametrize("removed", [False, True])
def test_br001_rename_player_refuses_a_name_another_player_has(
    session: Session,
    make_league: Callable[..., League],
    now: datetime,
    removed: bool,
) -> None:
    league = make_league()
    bob = _add(session, league, "Bob", now)
    ana = _add(session, league, "Ana", now)
    if removed:
        _set_removed(session, league, bob, now, removed=True)

    with pytest.raises(RuleViolationError) as raised:
        player_service.rename_player(
            session,
            league_id=league.id,
            player_id=ana.id,
            user_id=league.owner_user_id,
            name="bOB",
            now=now,
        )

    assert raised.value.code is ErrorCode.PLAYER_NAME_TAKEN
    assert raised.value.detail["player_id"] == str(bob.id)
    assert raised.value.detail["removed"] is removed
    assert ana.name == "Ana"


def test_br002_a_removed_player_cannot_be_renamed_until_restored(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    player = _add(session, league, "Ana", now)
    _set_removed(session, league, player, now, removed=True)

    with pytest.raises(RuleViolationError) as raised:
        _rename(session, league, player, "Anna", now)
    assert raised.value.code is ErrorCode.PLAYER_REMOVED

    _set_removed(session, league, player, now, removed=False)
    assert _rename(session, league, player, "Anna", now).name == "Anna"


def test_br002_removing_keeps_the_player_and_repeating_keeps_the_first_time(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    player = _add(session, league, "Ana", now)
    first = now + timedelta(hours=1)

    removed = _set_removed(session, league, player, first, removed=True)
    again = _set_removed(
        session, league, player, now + timedelta(hours=2), removed=True
    )

    assert again.id == removed.id == player.id
    assert again.removed_at == first
    assert again.name == "Ana"


def test_br002_restoring_brings_back_the_same_player(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    player = _add(session, league, "Ana", now)
    _set_removed(session, league, player, now, removed=True)

    restored = _set_removed(session, league, player, now, removed=False)
    again = _set_removed(session, league, player, now, removed=False)

    assert restored.id == again.id == player.id
    assert restored.removed_at is None
    assert _names(session, league) == ["Ana"]


def test_br001_the_name_of_a_removed_player_cannot_be_taken_meanwhile(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    # "The name was taken while the player was removed" cannot happen: removed
    # players hold their names (BR-001) and nobody can rename them, so a restore
    # has nothing to collide with.
    league = make_league()
    ana = _add(session, league, "Ana", now)
    _set_removed(session, league, ana, now, removed=True)
    bob = _add(session, league, "Bob", now)

    with pytest.raises(RuleViolationError):
        _rename(session, league, bob, "ana", now)
    with pytest.raises(RuleViolationError):
        _add(session, league, "Ana", now)
    restored = _set_removed(session, league, ana, now, removed=False)

    assert (restored.name, restored.removed_at) == ("Ana", None)


def test_owasp_api1_another_organizers_league_is_not_found(
    session: Session,
    make_league: Callable[..., League],
    make_user: Callable[..., User],
    now: datetime,
) -> None:
    league = make_league()
    ana = _add(session, league, "Ana", now)
    stranger = make_user()
    mine = {"league_id": league.id, "user_id": stranger.id}

    with pytest.raises(NotFoundError) as raised:
        player_service.list_players(session, include_removed=True, **mine)
    assert raised.value.code is ErrorCode.LEAGUE_NOT_FOUND
    with pytest.raises(NotFoundError) as raised:
        player_service.add_player(session, name="Bob", now=now, **mine)
    assert raised.value.code is ErrorCode.LEAGUE_NOT_FOUND
    with pytest.raises(NotFoundError) as raised:
        player_service.rename_player(
            session, player_id=ana.id, name="Bob", now=now, **mine
        )
    assert raised.value.code is ErrorCode.LEAGUE_NOT_FOUND
    with pytest.raises(NotFoundError) as raised:
        player_service.set_player_removed(
            session, player_id=ana.id, removed=True, now=now, **mine
        )
    assert raised.value.code is ErrorCode.LEAGUE_NOT_FOUND


def test_owasp_api1_a_player_of_another_league_is_not_found(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league, other = make_league(), make_league()
    foreign = _add(session, other, "Ana", now)

    with pytest.raises(NotFoundError) as raised:
        player_service.rename_player(
            session,
            league_id=league.id,
            player_id=foreign.id,
            user_id=league.owner_user_id,
            name="Bob",
            now=now,
        )
    assert raised.value.code is ErrorCode.PLAYER_NOT_FOUND
    with pytest.raises(NotFoundError) as raised:
        _set_removed(session, league, foreign, now, removed=True)
    assert raised.value.code is ErrorCode.PLAYER_NOT_FOUND
    assert (foreign.name, foreign.removed_at) == ("Ana", None)
