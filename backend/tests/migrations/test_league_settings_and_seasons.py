from datetime import UTC, datetime
from uuid import uuid7

from pytest_alembic import MigrationContext
from sqlalchemy import Engine, text

_REVISION = "f94c666342a1"  # add league settings and seasons


def test_fr010_an_existing_league_gets_its_settings_a_token_and_season_1(
    alembic_runner: MigrationContext, alembic_engine: Engine
) -> None:
    alembic_runner.migrate_up_before(_REVISION)
    created_at = datetime(2026, 11, 1, 18, 0, tzinfo=UTC)
    owner_id, league_ids = uuid7(), [uuid7(), uuid7()]
    alembic_runner.insert_into(
        "users",
        {
            "id": owner_id,
            "email": "old@example.test",
            "display_name": "old",
            "password_hash": "!",
            "language": "en",
            "created_at": created_at,
        },
    )
    for league_id in league_ids:
        alembic_runner.insert_into(
            "leagues",
            {
                "id": league_id,
                "owner_user_id": owner_id,
                "name": "Old",
                "created_at": created_at,
            },
        )

    alembic_runner.migrate_up_one()

    with alembic_engine.connect() as connection:
        leagues = connection.execute(
            text(
                "SELECT share_token, draws_allowed, default_field_count,"
                " default_match_format, default_goals_per_game FROM leagues"
            )
        ).all()
        seasons = connection.execute(
            text(
                "SELECT league_id, number, name, state, placement_points,"
                " started_at, closed_at, created_at FROM seasons ORDER BY league_id"
            )
        ).all()
    assert len({league.share_token for league in leagues}) == 2
    assert all(len(league.share_token) >= 22 for league in leagues)
    assert {tuple(league)[1:] for league in leagues} == {(False, 1, "bo1", 10)}
    assert [tuple(season) for season in seasons] == [
        (league_id, 1, None, "active", [10, 8, 6, 4, 2], created_at, None, created_at)
        for league_id in sorted(league_ids)
    ]
