from datetime import datetime
from uuid import UUID, uuid7

from sqlalchemy import Index, false
from sqlalchemy.orm import Mapped, mapped_column

from tourneyhub.db.base import Base, str_enum
from tourneyhub.engine.auth import AuthAttemptKind


class User(Base):
    """The `users` columns that `leagues` and authorization need (ADR-006)."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    email: Mapped[str] = mapped_column(unique=True)
    is_admin: Mapped[bool] = mapped_column(server_default=false())
    must_change_password: Mapped[bool] = mapped_column(server_default=false())


class AuthAttempt(Base):
    """One login or sign-up attempt, counted by the abuse limits (ADR-006)."""

    __tablename__ = "auth_attempts"
    __table_args__ = (
        Index("ix_auth_attempts_kind_key_created_at", "kind", "key", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    kind: Mapped[AuthAttemptKind] = mapped_column(
        str_enum(AuthAttemptKind, name="auth_attempt_kind")
    )
    key: Mapped[str]
    succeeded: Mapped[bool]
    created_at: Mapped[datetime]
