from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from tourneyhub.db.base import Base, str_enum
from tourneyhub.engine.leagues import LeagueStatus


class League(Base):
    __tablename__ = "leagues"
    __table_args__ = (UniqueConstraint("owner_user_id", "name"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)  # supplied by the client
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str]
    status: Mapped[LeagueStatus] = mapped_column(
        str_enum(LeagueStatus, name="league_status")
    )
    created_at: Mapped[datetime]  # the service's `now`, like updated_at
    updated_at: Mapped[datetime | None]
