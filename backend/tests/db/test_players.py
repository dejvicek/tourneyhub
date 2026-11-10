from collections.abc import Callable
from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tourneyhub.db.models.leagues import League, Player


def _add(session: Session, league: League, name: str, now: datetime) -> Player:
    player = Player(league_id=league.id, name=name, created_at=now)
    session.add(player)
    session.flush()
    return player


@pytest.mark.parametrize(
    ("first", "second"),
    [
        pytest.param("Ana", "ana", id="BR-001-ascii"),
        pytest.param("Čeněk", "čENĚK", id="BR-001-czech-letters"),
    ],
)
def test_br001_a_name_is_unique_in_a_league_ignoring_case(
    session: Session,
    make_league: Callable[..., League],
    now: datetime,
    first: str,
    second: str,
) -> None:
    league = make_league()
    _add(session, league, first, now)

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        _add(session, league, second, now)

    assert "uq_players_league_id_lower_name" in str(raised.value)


def test_br001_a_removed_player_still_holds_the_name(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    _add(session, league, "Ana", now).removed_at = now
    session.flush()

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        _add(session, league, "ANA", now)

    assert "uq_players_league_id_lower_name" in str(raised.value)


def test_br001_two_leagues_can_have_the_same_name(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    _add(session, make_league(), "Ana", now)
    _add(session, make_league(), "Ana", now)


def test_d6_deleting_a_league_deletes_its_players(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    _add(session, league, "Ana", now)

    session.delete(league)
    session.flush()

    assert session.scalars(select(Player)).all() == []
