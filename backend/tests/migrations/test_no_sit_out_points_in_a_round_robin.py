from datetime import UTC, date, datetime
from uuid import uuid7

import pytest
from pytest_alembic import MigrationContext
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

_REVISION = "c19e5a6d02f7"  # no sit-out points in a round robin
_AT = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)
_SWISS_ORDER = ["bh1", "bh2", "score_difference"]


def _insert_group_phase(
    alembic_runner: MigrationContext,
    *,
    format: str,  # noqa: A002
    sit_out_points: int | None,
    set_by_hand: bool,
) -> str:
    """A tournament in setup whose one group phase has this format (BR-071)."""
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
            "type": "monster_dyp" if format == "monster_dyp" else "singles",
            "state": "setup",
            "seeding_method": "ranking",
            "halves_method": "ranking",
            "rng_seed": bytes(16),
            "draw_counter": 0,
            "goals_per_game": 10,
            "created_at": _AT,
        },
    )
    alembic_runner.insert_into(
        "tournament_phases",
        {
            "id": phase_id,
            "tournament_id": tournament_id,
            "position": 1,
            "kind": "group",
            "format": format,
            "round_robin_legs": 1 if format == "round_robin" else None,
            "sit_out_points": sit_out_points,
            "sit_out_points_set_by_hand": set_by_hand,
            "tiebreakers": None if format == "round_robin" else _SWISS_ORDER,
            "match_format": "bo1",
            "created_at": _AT,
        },
    )
    return str(phase_id)


def _read(alembic_engine: Engine, phase_id: str) -> tuple[object, object]:
    with alembic_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT sit_out_points, sit_out_points_set_by_hand"
                " FROM tournament_phases WHERE id = :id"
            ),
            {"id": phase_id},
        ).one()
    return row[0], row[1]


def test_br071_the_migration_clears_a_round_robins_value_and_keeps_the_others(
    alembic_runner: MigrationContext, alembic_engine: Engine
) -> None:
    alembic_runner.migrate_up_before(_REVISION)
    round_robin = _insert_group_phase(
        alembic_runner, format="round_robin", sit_out_points=1, set_by_hand=True
    )
    default_round_robin = _insert_group_phase(
        alembic_runner, format="round_robin", sit_out_points=2, set_by_hand=False
    )
    swiss = _insert_group_phase(
        alembic_runner, format="swiss", sit_out_points=0, set_by_hand=True
    )
    monster = _insert_group_phase(
        alembic_runner, format="monster_dyp", sit_out_points=2, set_by_hand=False
    )

    alembic_runner.migrate_up_one()

    assert _read(alembic_engine, round_robin) == (None, False)
    assert _read(alembic_engine, default_round_robin) == (None, False)
    assert _read(alembic_engine, swiss) == (0, True)
    assert _read(alembic_engine, monster) == (2, False)


@pytest.mark.parametrize(
    "assignments",
    [
        pytest.param("sit_out_points = 1", id="round-robin-with-a-value"),
        pytest.param("sit_out_points_set_by_hand = true", id="round-robin-picked"),
    ],
)
def test_br071_after_the_migration_a_round_robin_cannot_have_a_value(
    alembic_runner: MigrationContext, alembic_engine: Engine, assignments: str
) -> None:
    alembic_runner.migrate_up_before(_REVISION)
    round_robin = _insert_group_phase(
        alembic_runner, format="round_robin", sit_out_points=1, set_by_hand=True
    )
    alembic_runner.migrate_up_one()

    with pytest.raises(IntegrityError), alembic_engine.begin() as connection:
        connection.execute(
            text(f"UPDATE tournament_phases SET {assignments} WHERE id = :id"),  # noqa: S608
            {"id": round_robin},
        )

    assert _read(alembic_engine, round_robin) == (None, False)


def test_br071_after_the_migration_a_swiss_phase_needs_a_value(
    alembic_runner: MigrationContext, alembic_engine: Engine
) -> None:
    alembic_runner.migrate_up_before(_REVISION)
    swiss = _insert_group_phase(
        alembic_runner, format="swiss", sit_out_points=1, set_by_hand=False
    )
    alembic_runner.migrate_up_one()

    with pytest.raises(IntegrityError), alembic_engine.begin() as connection:
        connection.execute(
            text("UPDATE tournament_phases SET sit_out_points = NULL WHERE id = :id"),
            {"id": swiss},
        )

    assert _read(alembic_engine, swiss) == (1, False)


def test_br071_the_downgrade_gives_a_round_robin_0_points_as_a_pick(
    alembic_runner: MigrationContext, alembic_engine: Engine
) -> None:
    alembic_runner.migrate_up_to(_REVISION)
    round_robin = _insert_group_phase(
        alembic_runner, format="round_robin", sit_out_points=None, set_by_hand=False
    )
    swiss = _insert_group_phase(
        alembic_runner, format="swiss", sit_out_points=2, set_by_hand=False
    )

    alembic_runner.migrate_down_one()

    assert _read(alembic_engine, round_robin) == (0, True)
    assert _read(alembic_engine, swiss) == (2, False)
