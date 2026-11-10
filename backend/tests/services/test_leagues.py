from collections.abc import Callable
from datetime import datetime
from uuid import uuid7

import pytest
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import User
from tourneyhub.db.models.leagues import League
from tourneyhub.engine.leagues import DefaultMatchFormat, SeasonState
from tourneyhub.errors import ConflictError, ErrorCode, NotFoundError
from tourneyhub.services import leagues as league_service


def test_fr010_create_league_starts_season_1_with_the_default_table(
    session: Session, make_user: Callable[..., User], now: datetime
) -> None:
    owner = make_user()
    league_id = uuid7()

    league = league_service.create_league(
        session,
        league_id=league_id,
        owner_user_id=owner.id,
        name="Thursday DYP",
        now=now,
    )

    assert league.id == league_id
    assert league.created_at == now
    [season] = league.seasons
    assert season.number == 1
    assert season.name is None
    assert season.state is SeasonState.ACTIVE
    assert season.placement_points == [10, 8, 6, 4, 2]
    assert season.started_at == now


def test_fr011_create_league_takes_the_default_settings(
    session: Session, make_user: Callable[..., User], now: datetime
) -> None:
    owner = make_user()

    league = league_service.create_league(
        session, league_id=uuid7(), owner_user_id=owner.id, name="L", now=now
    )

    assert league.draws_allowed is False
    assert league.default_field_count == 1
    assert league.default_match_format is DefaultMatchFormat.BO1
    assert league.default_goals_per_game == 10


def test_fr071_every_league_gets_its_own_unguessable_share_token(
    session: Session, make_user: Callable[..., User], now: datetime
) -> None:
    owner = make_user()

    tokens = {
        league_service.create_league(
            session, league_id=uuid7(), owner_user_id=owner.id, name="L", now=now
        ).share_token
        for _ in range(2)
    }

    assert len(tokens) == 2
    assert all(len(token) >= 22 for token in tokens)  # 16 bytes, base64url


def test_create_league_returns_the_league_of_a_repeated_request(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league(name="Thursday DYP")

    again = league_service.create_league(
        session,
        league_id=league.id,
        owner_user_id=league.owner_user_id,
        name="Thursday DYP",
        now=now,
    )

    assert again is league
    assert len(again.seasons) == 1


def test_create_league_with_another_organizers_id_is_a_conflict(
    session: Session,
    make_league: Callable[..., League],
    make_user: Callable[..., User],
    now: datetime,
) -> None:
    league = make_league()
    stranger = make_user()

    with pytest.raises(ConflictError) as raised:
        league_service.create_league(
            session,
            league_id=league.id,
            owner_user_id=stranger.id,
            name="Mine",
            now=now,
        )

    assert raised.value.code is ErrorCode.LEAGUE_ID_TAKEN


def test_lock_league_hides_another_organizers_league(
    session: Session, make_league: Callable[..., League], make_user: Callable[..., User]
) -> None:
    league = make_league()
    stranger = make_user()

    with pytest.raises(NotFoundError) as raised:
        league_service.lock_league(session, league_id=league.id, user_id=stranger.id)

    assert raised.value.code is ErrorCode.LEAGUE_NOT_FOUND


def test_rename_league_sets_name_and_updated_at(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league(name="Old")

    renamed = league_service.rename_league(
        session,
        league_id=league.id,
        user_id=league.owner_user_id,
        expected_name="Old",
        name="New",
        now=now,
    )

    assert renamed.name == "New"
    assert renamed.updated_at == now


def test_rename_league_refuses_a_stale_expected_name(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league(name="Current")

    with pytest.raises(ConflictError) as raised:
        league_service.rename_league(
            session,
            league_id=league.id,
            user_id=league.owner_user_id,
            expected_name="Stale",
            name="New",
            now=now,
        )

    assert raised.value.code is ErrorCode.LEAGUE_NAME_CHANGED
    assert raised.value.detail == {"current_name": "Current"}
