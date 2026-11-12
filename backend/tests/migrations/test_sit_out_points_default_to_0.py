from datetime import UTC, date, datetime
from uuid import uuid7

import pytest
from pytest_alembic import MigrationContext
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

_REVISION = "c19e5a6d02f7"  # sit-out points default to 0, no "set by hand" flag
_AT = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)
_SWISS_ORDER = ["bh1", "bh2", "score_difference"]


def _insert_group_phase(
    alembic_runner: MigrationContext,
    *,
    format: str,  # noqa: A002
    sit_out_points: int | None,
    set_by_hand: bool,
    outcome: str | None = None,
) -> str:
    """A tournament whose one group phase has this format (BR-071)."""
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
    if outcome is not None or format != "round_robin":
        # A round with a match: played when it has an outcome (BR-096).
        round_id, match_id = uuid7(), uuid7()
        alembic_runner.insert_into(
            "rounds",
            {"id": round_id, "phase_id": phase_id, "round_no": 1, "created_at": _AT},
        )
        alembic_runner.insert_into(
            "matches",
            {
                "id": match_id,
                "round_id": round_id,
                "position": 1,
                "kind": "standard",
                "outcome": outcome,
                "result_entered_at": None if outcome is None else _AT,
                "created_at": _AT,
            },
        )
    return str(phase_id)


def _points(alembic_engine: Engine, phase_id: str) -> object:
    with alembic_engine.connect() as connection:
        return connection.execute(
            text("SELECT sit_out_points FROM tournament_phases WHERE id = :id"),
            {"id": phase_id},
        ).scalar_one()


def _flag(alembic_engine: Engine, phase_id: str) -> object:
    with alembic_engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT sit_out_points_set_by_hand FROM tournament_phases"
                " WHERE id = :id"
            ),
            {"id": phase_id},
        ).scalar_one()


def _columns(alembic_engine: Engine) -> set[str]:
    with alembic_engine.connect() as connection:
        return set(
            connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns"
                    " WHERE table_name = 'tournament_phases'"
                )
            ).scalars()
        )


@pytest.mark.parametrize("set_by_hand", [True, False])
def test_br071_the_migration_gives_a_round_robin_no_value(
    alembic_runner: MigrationContext, alembic_engine: Engine, set_by_hand: bool
) -> None:
    alembic_runner.migrate_up_before(_REVISION)
    round_robin = _insert_group_phase(
        alembic_runner,
        format="round_robin",
        sit_out_points=2,
        set_by_hand=set_by_hand,
        outcome="side_1",
    )

    alembic_runner.migrate_up_one()

    assert _points(alembic_engine, round_robin) is None


@pytest.mark.parametrize("set_by_hand", [True, False])
@pytest.mark.parametrize("format", ["swiss", "monster_dyp"])
def test_br075_the_migration_keeps_the_value_of_a_phase_with_a_result(
    alembic_runner: MigrationContext,
    alembic_engine: Engine,
    format: str,  # noqa: A002
    set_by_hand: bool,
) -> None:
    alembic_runner.migrate_up_before(_REVISION)
    played = _insert_group_phase(
        alembic_runner,
        format=format,
        sit_out_points=2,
        set_by_hand=set_by_hand,
        outcome="draw",
    )

    alembic_runner.migrate_up_one()

    assert _points(alembic_engine, played) == 2


@pytest.mark.parametrize("format", ["swiss", "monster_dyp"])
def test_br075_the_migration_keeps_a_picked_value_without_a_result(
    alembic_runner: MigrationContext,
    alembic_engine: Engine,
    format: str,  # noqa: A002
) -> None:
    alembic_runner.migrate_up_before(_REVISION)
    picked = _insert_group_phase(
        alembic_runner, format=format, sit_out_points=1, set_by_hand=True
    )

    alembic_runner.migrate_up_one()

    assert _points(alembic_engine, picked) == 1


@pytest.mark.parametrize("format", ["swiss", "monster_dyp"])
def test_fr039_the_migration_gives_a_default_without_a_result_0(
    alembic_runner: MigrationContext,
    alembic_engine: Engine,
    format: str,  # noqa: A002
) -> None:
    alembic_runner.migrate_up_before(_REVISION)
    default = _insert_group_phase(
        alembic_runner, format=format, sit_out_points=2, set_by_hand=False
    )

    alembic_runner.migrate_up_one()

    assert _points(alembic_engine, default) == 0


def test_fr039_the_migration_drops_the_set_by_hand_flag(
    alembic_runner: MigrationContext, alembic_engine: Engine
) -> None:
    alembic_runner.migrate_up_to(_REVISION)

    assert "sit_out_points_set_by_hand" not in _columns(alembic_engine)
    assert "sit_out_points" in _columns(alembic_engine)


@pytest.mark.parametrize(
    ("format", "assignment"),
    [
        pytest.param("round_robin", "sit_out_points = 0", id="round-robin-0"),
        pytest.param("swiss", "sit_out_points = NULL", id="swiss-null"),
        pytest.param("monster_dyp", "sit_out_points = NULL", id="monster-null"),
        pytest.param("swiss", "sit_out_points = 3", id="swiss-3"),
    ],
)
def test_br071_after_the_migration_the_check_holds_the_value_to_the_format(
    alembic_runner: MigrationContext,
    alembic_engine: Engine,
    format: str,  # noqa: A002
    assignment: str,
) -> None:
    alembic_runner.migrate_up_before(_REVISION)
    phase = _insert_group_phase(
        alembic_runner,
        format=format,
        sit_out_points=1,
        set_by_hand=True,
        outcome="side_2",
    )
    alembic_runner.migrate_up_one()
    before = _points(alembic_engine, phase)

    with pytest.raises(IntegrityError), alembic_engine.begin() as connection:
        connection.execute(
            text(f"UPDATE tournament_phases SET {assignment} WHERE id = :id"),  # noqa: S608
            {"id": phase},
        )

    assert _points(alembic_engine, phase) == before


def test_br071_the_downgrade_gives_a_round_robin_0_and_marks_every_value_picked(
    alembic_runner: MigrationContext, alembic_engine: Engine
) -> None:
    alembic_runner.migrate_up_before(_REVISION)
    round_robin = _insert_group_phase(
        alembic_runner, format="round_robin", sit_out_points=1, set_by_hand=False
    )
    swiss = _insert_group_phase(
        alembic_runner, format="swiss", sit_out_points=2, set_by_hand=False
    )
    alembic_runner.migrate_up_one()
    assert (_points(alembic_engine, round_robin), _points(alembic_engine, swiss)) == (
        None,
        0,
    )

    alembic_runner.migrate_down_one()

    assert (
        _points(alembic_engine, round_robin),
        _flag(alembic_engine, round_robin),
    ) == (
        0,
        True,
    )
    assert (_points(alembic_engine, swiss), _flag(alembic_engine, swiss)) == (0, True)
