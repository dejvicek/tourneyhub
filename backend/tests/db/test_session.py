import logging

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from tourneyhub.db.session import create_db_engine
from tourneyhub.settings import Settings

SECRET = "share-token-that-must-not-leak"


def test_fr071_a_failing_statement_shows_no_parameter_value(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    # `hide_parameters=True`: the share token (FR-071) is a bound parameter of
    # the league's INSERT, and an error message or a log record would show it.
    caplog.set_level(logging.INFO, logger="sqlalchemy.engine")
    engine = create_db_engine(settings)

    with pytest.raises(ProgrammingError) as raised, engine.connect() as connection:
        connection.execute(
            text("SELECT CAST(:token AS text) FROM no_such_table"), {"token": SECRET}
        )
    engine.dispose()

    assert SECRET not in str(raised.value)
    assert SECRET not in repr(raised.value)
    assert SECRET not in caplog.text
    assert "SELECT CAST" in caplog.text  # the statement itself is still logged
