import re
from enum import StrEnum

from sqlalchemy import Engine, Enum, inspect, text

from tourneyhub.db.base import Base


def test_every_check_constraint_lists_exactly_the_values_of_its_enum(
    engine: Engine,
) -> None:
    inspector = inspect(engine)
    checked = 0

    for table in Base.metadata.tables.values():
        checks = {
            check["name"]: check["sqltext"]
            for check in inspector.get_check_constraints(table.name)
        }
        for column in table.columns:
            if not isinstance(column.type, Enum):
                continue
            enum_class = column.type.enum_class
            assert enum_class is not None
            assert issubclass(enum_class, StrEnum)
            sqltext = checks[f"ck_{table.name}_{column.type.name}"]
            assert set(re.findall(r"'([^']+)'", sqltext)) == {
                member.value for member in enum_class
            }
            checked += 1

    assert checked >= 1


def test_every_enum_column_is_a_varchar_without_a_length(engine: Engine) -> None:
    # str_enum() relies on Enum(length=None), which SQLAlchemy does not document,
    # and Alembic does not compare a length with no length.
    enum_columns = {
        (table.name, column.name)
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, Enum)
    }

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT table_name, column_name, data_type, character_maximum_length"
                " FROM information_schema.columns WHERE table_schema = 'public'"
            )
        ).all()

    found = {
        (row.table_name, row.column_name): (row.data_type, row.character_maximum_length)
        for row in rows
        if (row.table_name, row.column_name) in enum_columns
    }
    assert enum_columns
    assert found == dict.fromkeys(enum_columns, ("character varying", None))
