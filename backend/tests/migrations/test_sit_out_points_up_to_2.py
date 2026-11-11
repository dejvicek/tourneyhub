from datetime import UTC, date, datetime
from uuid import uuid7

import pytest
from pytest_alembic import MigrationContext
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

_REVISION = "7b3d91c0a5e2"  # sit-out points up to 2
_AT = datetime(2026, 11, 11, 14, 0, tzinfo=UTC)


def _insert_tournament_with_phase(
    alembic_runner: MigrationContext, *, kind: str
) -> str:
    owner_id, league_id, season_id, tournament_id, phase_id = (
        uuid7() for _ in range(5)
    )
    alembic_runner.insert_into(
        "users",
        {
            "id": owner_id,
            "email": f"{owner_id}@example.test",
            "display_name": "old",
            "password_hash": "!",
            "language": "en",
            "created_at": _AT,
        },
    )
    alembic_runner.insert_into(
        "leagues",
        {
            "id": league_id,
            "owner_user_id": owner_id,
            "name": "Old",
            "created_at": _AT,
            "share_token": f"token-{league_id}",
        },
    )
    alembic_runner.insert_into(
        "seasons",
        {
            "id": season_id,
            "league_id": league_id,
            "number": 7,
            "state": "active",
            "placement_points": [3, 2, 1],
            "started_at": _AT,
            "created_at": _AT,
        },
    )
    alembic_runner.insert_into(
        "tournaments",
        {
            "id": tournament_id,
            "season_id": season_id,
            "name": "Thursday",
            "date": date(2026, 11, 12),
            "type": "singles",
            "state": "setup",
            "seeding_method": "ranking",
            "halves_method": "ranking",
            "rng_seed": bytes(16),
            "draw_counter": 0,
            "goals_per_game": 10,
            "created_at": _AT,
        },
    )
    group = kind == "group"
    alembic_runner.insert_into(
        "tournament_phases",
        {
            "id": phase_id,
            "tournament_id": tournament_id,
            "position": 1,
            "kind": kind,
            "format": "round_robin" if group else "single_elimination",
            "round_robin_legs": 1 if group else None,
            "sit_out_points": 1 if group else None,
            "third_place_match": None if group else False,
            "match_format": "bo1",
            "created_at": _AT,
        },
    )
    return str(phase_id)


def _read(alembic_engine: Engine, phase_id: str, column: str) -> object:
    with alembic_engine.connect() as connection:
        return connection.execute(
            text(f"SELECT {column} FROM tournament_phases WHERE id = :id"),  # noqa: S608
            {"id": phase_id},
        ).scalar_one()


def test_fr039_the_migration_keeps_the_value_of_a_group_phase_as_picked(
    alembic_runner: MigrationContext, alembic_engine: Engine
) -> None:
    alembic_runner.migrate_up_before(_REVISION)
    group = _insert_tournament_with_phase(alembic_runner, kind="group")
    knockout = _insert_tournament_with_phase(alembic_runner, kind="knockout")

    alembic_runner.migrate_up_one()

    assert _read(alembic_engine, group, "sit_out_points") == 1
    assert _read(alembic_engine, group, "sit_out_points_set_by_hand") is True
    assert _read(alembic_engine, knockout, "sit_out_points_set_by_hand") is False


def test_fr039_after_the_migration_a_sit_out_is_worth_up_to_2_points(
    alembic_runner: MigrationContext, alembic_engine: Engine
) -> None:
    alembic_runner.migrate_up_before(_REVISION)
    group = _insert_tournament_with_phase(alembic_runner, kind="group")
    alembic_runner.migrate_up_one()

    with alembic_engine.begin() as connection:
        connection.execute(
            text("UPDATE tournament_phases SET sit_out_points = 2 WHERE id = :id"),
            {"id": group},
        )
    with pytest.raises(IntegrityError), alembic_engine.begin() as connection:
        connection.execute(
            text("UPDATE tournament_phases SET sit_out_points = 3 WHERE id = :id"),
            {"id": group},
        )

    assert _read(alembic_engine, group, "sit_out_points") == 2


def test_fr039_the_downgrade_gives_2_points_back_as_1(
    alembic_runner: MigrationContext, alembic_engine: Engine
) -> None:
    alembic_runner.migrate_up_to(_REVISION)
    group = _insert_tournament_with_phase(alembic_runner, kind="group")
    with alembic_engine.begin() as connection:
        connection.execute(
            text("UPDATE tournament_phases SET sit_out_points = 2 WHERE id = :id"),
            {"id": group},
        )

    alembic_runner.migrate_down_one()

    assert _read(alembic_engine, group, "sit_out_points") == 1
