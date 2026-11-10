from collections.abc import Callable
from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tourneyhub.db.models.leagues import League, Season
from tourneyhub.engine.leagues import SeasonState


def _set_points(session: Session, season: Season, points: str) -> None:
    session.execute(
        text(
            "UPDATE seasons SET placement_points = CAST(:points AS integer[])"
            " WHERE id = :id"
        ),
        {"points": points, "id": season.id},
    )


@pytest.mark.parametrize(
    "points",
    [
        pytest.param("{10,8,6,4,2}", id="FR-011-default"),
        pytest.param("{3,3,0}", id="FR-011-equal-places"),
        pytest.param("[0:1]={5,4}", id="FR-011-other-lower-bound"),
    ],
)
def test_fr011_the_check_accepts_a_non_increasing_table(
    session: Session, make_league: Callable[..., League], points: str
) -> None:
    [season] = make_league().seasons

    _set_points(session, season, points)


@pytest.mark.parametrize(
    "points",
    [
        pytest.param("{}", id="FR-011-empty"),
        pytest.param("{10,-1}", id="FR-011-negative"),
        pytest.param("{10,8,9}", id="FR-011-increasing"),
        pytest.param("{10,NULL}", id="FR-011-null"),
        pytest.param("{{10},{8}}", id="FR-011-two-dimensional"),
    ],
)
def test_fr011_the_check_refuses_what_the_api_refuses(
    session: Session, make_league: Callable[..., League], points: str
) -> None:
    [season] = make_league().seasons

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        _set_points(session, season, points)

    assert "ck_seasons_placement_points" in str(raised.value)


def test_adr002_a_league_has_at_most_one_active_season(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        session.add(
            Season(
                league_id=league.id,
                number=2,
                state=SeasonState.ACTIVE,
                placement_points=[1],
                started_at=now,
                created_at=now,
            )
        )

    assert "uq_seasons_league_id_active" in str(raised.value)


def test_a_season_number_is_unique_in_its_league(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        session.add(
            Season(
                league_id=league.id,
                number=1,
                state=SeasonState.CLOSED,
                placement_points=[1],
                started_at=now,
                closed_at=now,
                created_at=now,
            )
        )

    assert "uq_seasons_league_id_number" in str(raised.value)


def test_fr013_deleting_a_league_cascades_to_its_seasons(
    session: Session, make_league: Callable[..., League]
) -> None:
    league = make_league()

    session.execute(text("DELETE FROM leagues WHERE id = :id"), {"id": league.id})

    remaining = session.execute(
        text("SELECT count(*) FROM seasons WHERE league_id = :id"), {"id": league.id}
    )
    assert remaining.scalar_one() == 0
