import io
import json
from contextlib import redirect_stderr

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text

from tourneyhub.cli import main


@pytest.fixture
def migrations_database(
    monkeypatch: pytest.MonkeyPatch, alembic_engine: Engine
) -> Engine:
    """Point Settings at the migration tests' database, which starts empty."""
    monkeypatch.setenv("TOURNEYHUB_ENV", "development")
    monkeypatch.setenv(
        "TOURNEYHUB_DATABASE_URL",
        alembic_engine.url.render_as_string(hide_password=False),
    )
    monkeypatch.setenv("TOURNEYHUB_JWT_SECRET", "x" * 32)
    assert inspect(alembic_engine).get_table_names() == []
    return alembic_engine


def test_migrate_upgrades_an_empty_database_to_the_head_of_tool_alembic(
    migrations_database: Engine, alembic_config: Config
) -> None:
    assert main(["migrate"]) == 0

    head = ScriptDirectory.from_config(alembic_config).get_current_head()
    with migrations_database.connect() as connection:
        current = connection.scalar(text("SELECT version_num FROM alembic_version"))
    assert current == head


@pytest.mark.usefixtures("migrations_database")
def test_migrate_logs_every_upgrade_step_as_a_json_line(alembic_config: Config) -> None:
    with redirect_stderr(io.StringIO()) as stderr:  # main() applies §4.6 first
        main(["migrate"])

    messages = [json.loads(line)["message"] for line in stderr.getvalue().splitlines()]
    upgraded = {
        message.split(" -> ")[1].split(",")[0]
        for message in messages
        if message.startswith("Running upgrade")
    }
    revisions = ScriptDirectory.from_config(alembic_config).walk_revisions()
    assert upgraded == {script.revision for script in revisions}
