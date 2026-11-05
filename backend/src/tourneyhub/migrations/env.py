from alembic import context
from sqlalchemy import Engine

from tourneyhub.db import models  # noqa: F401  (registers every model on Base.metadata)
from tourneyhub.db.base import Base
from tourneyhub.db.session import create_db_engine
from tourneyhub.settings import Settings


def _run_migrations(engine: Engine) -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,  # imported from tourneyhub.db.models
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


# Tests and pytest-alembic pass an Engine under "connection"; otherwise Settings decide.
_given: Engine | None = context.config.attributes.get("connection")
if _given is not None:
    _run_migrations(_given)
else:
    _engine = create_db_engine(Settings())
    try:
        _run_migrations(_engine)
    finally:
        _engine.dispose()
