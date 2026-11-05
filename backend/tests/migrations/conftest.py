import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text


@pytest.fixture
def alembic_config() -> Config:
    return Config(toml_file=Path(__file__).parent.parent.parent / "pyproject.toml")


@pytest.fixture
def alembic_engine() -> Iterator[Engine]:
    """A database of their own, emptied first, so each test starts from base."""
    engine = create_engine(os.environ["TOURNEYHUB_TEST_MIGRATIONS_DATABASE_URL"])
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    yield engine
    engine.dispose()
