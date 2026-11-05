from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from tourneyhub.settings import Settings


def create_db_engine(settings: Settings) -> Engine:
    """Create the engine; it connects on first use, not here."""
    return create_engine(settings.database_url.get_secret_value(), pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine)
