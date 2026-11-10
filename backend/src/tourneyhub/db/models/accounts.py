from datetime import datetime
from uuid import UUID, uuid7

from sqlalchemy import ForeignKey, Index, LargeBinary, false, func
from sqlalchemy.orm import Mapped, mapped_column

from tourneyhub.db.base import Base, str_enum
from tourneyhub.engine.accounts import Language
from tourneyhub.engine.auth import AuthAttemptKind


class User(Base):
    """An organizer or an admin (DATA-MODEL §4.1)."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    email: Mapped[str]
    display_name: Mapped[str]
    password_hash: Mapped[str]  # Argon2id (ADR-006)
    is_admin: Mapped[bool] = mapped_column(server_default=false())
    must_change_password: Mapped[bool] = mapped_column(server_default=false())
    language: Mapped[Language] = mapped_column(str_enum(Language, name="language"))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime | None]


# Unique on lower(email) (DATA-MODEL §4.1, FR-002). Named here, because the naming
# convention cannot name an expression index. A lookup by email compares
# func.lower(User.email) with func.lower() of the input, so that it uses this
# index and folds the case as the index does.
Index("uq_users_lower_email", func.lower(User.email), unique=True)


class RefreshToken(Base):
    """One rotating refresh token, stored only as its SHA-256 hash (ADR-006)."""

    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # All tokens of one login; the refresh endpoint locks them together.
    family_id: Mapped[UUID] = mapped_column(index=True)
    # The token this one was rotated from; a parent expires before its children.
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"), index=True
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    expires_at: Mapped[datetime]
    rotated_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[datetime]


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
