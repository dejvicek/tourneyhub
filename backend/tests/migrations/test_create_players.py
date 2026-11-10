from datetime import UTC, datetime
from uuid import uuid7

import pytest
from pytest_alembic import MigrationContext
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

_REVISION = "f85d43721969"  # create players
_AT = datetime(2026, 11, 1, 18, 0, tzinfo=UTC)


def _insert_league(alembic_runner: MigrationContext) -> str:
    owner_id, league_id = uuid7(), uuid7()
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
    return str(league_id)


def _insert_player(
    alembic_engine: Engine, league_id: str, name: str, removed_at: datetime | None
) -> None:
    with alembic_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO players (id, league_id, name, removed_at, created_at)"
                " VALUES (:id, :league_id, :name, :removed_at, :created_at)"
            ),
            {
                "id": uuid7(),
                "league_id": league_id,
                "name": name,
                "removed_at": removed_at,
                "created_at": _AT,
            },
        )


def test_fr012_the_migration_starts_every_league_with_an_empty_player_list(
    alembic_runner: MigrationContext, alembic_engine: Engine
) -> None:
    alembic_runner.migrate_up_before(_REVISION)
    league_id = _insert_league(alembic_runner)

    alembic_runner.migrate_up_one()

    with alembic_engine.connect() as connection:
        players = connection.execute(
            text("SELECT count(*) FROM players WHERE league_id = :id"),
            {"id": league_id},
        ).scalar_one()
    assert players == 0


def test_br001_the_index_refuses_a_name_in_another_case_even_if_removed(
    alembic_runner: MigrationContext, alembic_engine: Engine
) -> None:
    alembic_runner.migrate_up_to(_REVISION)
    league_id, other_league_id = (
        _insert_league(alembic_runner),
        _insert_league(alembic_runner),
    )
    _insert_player(alembic_engine, league_id, "Čeněk", removed_at=_AT)

    with pytest.raises(IntegrityError) as raised:
        _insert_player(alembic_engine, league_id, "čENĚK", removed_at=None)

    assert "uq_players_league_id_lower_name" in str(raised.value)
    # Another league may have the same name.
    _insert_player(alembic_engine, other_league_id, "Čeněk", removed_at=None)


def test_d6_a_players_row_goes_with_its_league(
    alembic_runner: MigrationContext, alembic_engine: Engine
) -> None:
    alembic_runner.migrate_up_to(_REVISION)
    league_id = _insert_league(alembic_runner)
    _insert_player(alembic_engine, league_id, "Ana", removed_at=None)

    with alembic_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM leagues WHERE id = :id"), {"id": league_id}
        )

    with alembic_engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM players")).scalar() == 0


def test_the_downgrade_drops_the_players_table_and_keeps_the_leagues(
    alembic_runner: MigrationContext, alembic_engine: Engine
) -> None:
    alembic_runner.migrate_up_to(_REVISION)
    league_id = _insert_league(alembic_runner)

    alembic_runner.migrate_down_one()

    with alembic_engine.connect() as connection:
        tables = (
            connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables"
                    " WHERE table_schema = 'public'"
                )
            )
            .scalars()
            .all()
        )
        leagues = connection.execute(text("SELECT id FROM leagues")).scalars().all()
    assert "players" not in tables
    assert [str(league) for league in leagues] == [league_id]
