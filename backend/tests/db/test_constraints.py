from collections.abc import Callable
from datetime import datetime
from uuid import uuid7

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tourneyhub.db.models.leagues import League
from tourneyhub.engine.leagues import LeagueStatus


def test_an_owner_cannot_have_two_leagues_with_one_name(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league(name="Taken")

    with pytest.raises(IntegrityError) as raised, session.begin_nested():
        session.add(
            League(
                id=uuid7(),
                owner_user_id=league.owner_user_id,
                name="Taken",
                status=LeagueStatus.ACTIVE,
                created_at=now,
            )
        )

    assert "uq_leagues_owner_user_id_name" in str(raised.value)
