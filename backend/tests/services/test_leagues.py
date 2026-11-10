from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import uuid7

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import User
from tourneyhub.db.models.leagues import League, Season
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


def test_fr007_list_leagues_returns_only_the_users_own(
    session: Session, make_league: Callable[..., League], make_user: Callable[..., User]
) -> None:
    owner = make_user()
    first = make_league(owner_user_id=owner.id)
    second = make_league(owner_user_id=owner.id)
    make_league()

    leagues = league_service.list_leagues(session, user_id=owner.id)

    assert {league.id for league in leagues} == {first.id, second.id}


def test_lock_league_hides_another_organizers_league(
    session: Session, make_league: Callable[..., League], make_user: Callable[..., User]
) -> None:
    league = make_league()
    stranger = make_user()

    with pytest.raises(NotFoundError) as raised:
        league_service.lock_league(session, league_id=league.id, user_id=stranger.id)

    assert raised.value.code is ErrorCode.LEAGUE_NOT_FOUND


def test_get_league_hides_another_organizers_league(
    session: Session, make_league: Callable[..., League], make_user: Callable[..., User]
) -> None:
    league = make_league()
    stranger = make_user()

    with pytest.raises(NotFoundError) as raised:
        league_service.get_league(session, league_id=league.id, user_id=stranger.id)

    assert raised.value.code is ErrorCode.LEAGUE_NOT_FOUND


def test_fr011_update_league_sets_the_given_settings_and_updated_at(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league(name="Old")

    updated = league_service.update_league(
        session,
        league_id=league.id,
        user_id=league.owner_user_id,
        draws_allowed=True,
        default_match_format=DefaultMatchFormat.BO3,
        now=now,
    )

    assert updated.name == "Old"
    assert updated.draws_allowed is True
    assert updated.default_match_format is DefaultMatchFormat.BO3
    assert updated.default_field_count == 1
    assert updated.updated_at == now


def test_adr008_update_league_repeated_changes_nothing(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league(name="Same")

    updated = league_service.update_league(
        session,
        league_id=league.id,
        user_id=league.owner_user_id,
        name="Same",
        now=now,
    )

    assert updated.updated_at is None


def test_fr021_start_season_closes_the_active_one_and_copies_its_table(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    [first] = league.seasons
    later = now + timedelta(days=30)

    second = league_service.start_season(
        session,
        league_id=league.id,
        user_id=league.owner_user_id,
        expected_current_number=1,
        now=later,
    )

    assert second.number == 2
    assert second.state is SeasonState.ACTIVE
    assert second.placement_points == first.placement_points
    assert second.started_at == later
    assert first.state is SeasonState.CLOSED
    assert first.closed_at == later


def test_adr008_start_season_with_a_stale_number_is_a_conflict(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    league_service.start_season(
        session,
        league_id=league.id,
        user_id=league.owner_user_id,
        expected_current_number=1,
        now=now,
    )

    with pytest.raises(ConflictError) as raised:
        league_service.start_season(
            session,
            league_id=league.id,
            user_id=league.owner_user_id,
            expected_current_number=1,
            now=now,
        )

    assert raised.value.code is ErrorCode.SEASON_NUMBER_CHANGED
    assert raised.value.detail == {"current_number": 2}


def test_fr020_rename_season_and_restore_the_default_name(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    [season] = league.seasons

    renamed = league_service.rename_season(
        session,
        league_id=league.id,
        season_id=season.id,
        user_id=league.owner_user_id,
        name="Autumn",
        now=now,
    )
    assert renamed.name == "Autumn"
    restored = league_service.rename_season(
        session,
        league_id=league.id,
        season_id=season.id,
        user_id=league.owner_user_id,
        name=None,
        now=now,
    )

    assert restored.name is None
    assert restored.updated_at == now


def test_rename_season_of_another_league_is_not_found(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    other = make_league(owner_user_id=league.owner_user_id)

    with pytest.raises(NotFoundError) as raised:
        league_service.rename_season(
            session,
            league_id=league.id,
            season_id=other.seasons[0].id,
            user_id=league.owner_user_id,
            name="Mixed",
            now=now,
        )

    assert raised.value.code is ErrorCode.SEASON_NOT_FOUND


def test_br012_set_placement_points_replaces_the_active_seasons_table(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    [season] = league.seasons

    updated = league_service.set_placement_points(
        session,
        league_id=league.id,
        season_id=season.id,
        user_id=league.owner_user_id,
        placement_points=[12, 9, 9, 0],
        now=now,
    )

    assert updated.placement_points == [12, 9, 9, 0]
    assert updated.updated_at == now


def test_br011_a_closed_season_keeps_its_table(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    [first] = league.seasons
    league_service.start_season(
        session,
        league_id=league.id,
        user_id=league.owner_user_id,
        expected_current_number=1,
        now=now,
    )

    with pytest.raises(ConflictError) as raised:
        league_service.set_placement_points(
            session,
            league_id=league.id,
            season_id=first.id,
            user_id=league.owner_user_id,
            placement_points=[1],
            now=now,
        )

    assert raised.value.code is ErrorCode.SEASON_CLOSED
    assert first.placement_points == [10, 8, 6, 4, 2]


def test_fr013_delete_league_removes_its_seasons(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    league_service.start_season(
        session,
        league_id=league.id,
        user_id=league.owner_user_id,
        expected_current_number=1,
        now=now,
    )

    league_service.delete_league(
        session, league_id=league.id, user_id=league.owner_user_id
    )

    assert session.get(League, league.id) is None
    seasons = session.scalars(select(Season).where(Season.league_id == league.id))
    assert seasons.all() == []


def test_adr002_a_league_without_an_active_season_is_an_internal_error(
    session: Session, make_league: Callable[..., League], now: datetime
) -> None:
    league = make_league()
    [season] = league.seasons
    # The invariant check after the test needs the broken state rolled back.
    broken = session.begin_nested()
    season.state = SeasonState.CLOSED
    season.closed_at = now
    session.flush()

    with pytest.raises(RuntimeError, match="has no active season"):
        league_service.start_season(
            session,
            league_id=league.id,
            user_id=league.owner_user_id,
            expected_current_number=1,
            now=now,
        )

    broken.rollback()
