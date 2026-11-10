from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tourneyhub.db.models.leagues import League
from tourneyhub.engine.leagues import MAX_FIELD_COUNT, MAX_GOALS_PER_GAME


def _set(session: Session, league: League, column: str, value: int) -> None:
    session.execute(
        text(f"UPDATE leagues SET {column} = :value WHERE id = :id"),  # noqa: S608
        {"value": value, "id": league.id},
    )


@pytest.mark.parametrize(
    ("column", "value"),
    [
        pytest.param("default_field_count", 1, id="FR-011-1-field"),
        pytest.param("default_field_count", MAX_FIELD_COUNT, id="FR-011-32-fields"),
        pytest.param("default_goals_per_game", 1, id="FR-011-1-goal"),
        pytest.param(
            "default_goals_per_game", MAX_GOALS_PER_GAME, id="FR-011-99-goals"
        ),
    ],
)
def test_fr011_the_check_accepts_the_bounds(
    session: Session, make_league: Callable[..., League], column: str, value: int
) -> None:
    _set(session, make_league(), column, value)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        pytest.param("default_field_count", 0, id="FR-011-0-fields"),
        pytest.param("default_field_count", MAX_FIELD_COUNT + 1, id="FR-011-33-fields"),
        pytest.param("default_goals_per_game", 0, id="FR-011-0-goals"),
        pytest.param(
            "default_goals_per_game", MAX_GOALS_PER_GAME + 1, id="FR-011-100-goals"
        ),
    ],
)
def test_fr011_the_check_refuses_what_the_api_refuses_in_the_settings(
    session: Session, make_league: Callable[..., League], column: str, value: int
) -> None:
    league = make_league()

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        _set(session, league, column, value)

    assert f"ck_leagues_{column}" in str(raised.value)
