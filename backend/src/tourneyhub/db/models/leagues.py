from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from tourneyhub.db.base import Base


class League(Base):
    __tablename__ = "leagues"

    id: Mapped[UUID] = mapped_column(primary_key=True)  # supplied by the client
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str]
    created_at: Mapped[datetime]  # the service's `now`, like updated_at
    updated_at: Mapped[datetime | None]
