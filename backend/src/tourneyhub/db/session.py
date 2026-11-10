from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from tourneyhub.settings import Settings


def create_db_engine(settings: Settings) -> Engine:
    """Create the engine; it connects on first use, not here."""
    # hide_parameters: a failed statement's error and the engine's log must not
    # show bound values such as a league's share token (FR-071, ADR-008).
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        hide_parameters=True,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine)
