from datetime import datetime
from uuid import UUID, uuid7

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    LargeBinary,
    SmallInteger,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from tourneyhub.db.base import Base, str_enum
from tourneyhub.engine.accounts import Language
from tourneyhub.engine.admin import AdminActionKind, AdminActionSource
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
    # Indexed for a password change, which revokes the user's other families.
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
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


class InstanceSettings(Base):
    """The instance's one row of settings (DATA-MODEL §4.1)."""

    __tablename__ = "instance_settings"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(
        SmallInteger, primary_key=True, autoincrement=False, default=1
    )
    # Plain text, so that the admin can see and share it; NULL: sign-up is closed.
    signup_code: Mapped[str | None]
    updated_at: Mapped[datetime | None]


class AdminAction(Base):
    """One admin action, from the web or the CLI (DATA-MODEL §4.1, ADR-007).

    The sign-up code itself is never stored here. The two CHECKs work in one
    direction only, because ON DELETE SET NULL has to clear a deleted account's
    reference.
    """

    __tablename__ = "admin_actions"
    __table_args__ = (
        CheckConstraint(
            "source = 'web' OR admin_user_id IS NULL", name="cli_action_has_no_admin"
        ),
        CheckConstraint(
            "action <> 'set_signup_code' OR target_user_id IS NULL",
            name="signup_code_has_no_target",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    source: Mapped[AdminActionSource] = mapped_column(
        str_enum(AdminActionSource, name="admin_action_source")
    )
    admin_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[AdminActionKind] = mapped_column(
        str_enum(AdminActionKind, name="admin_action_kind")
    )
    target_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime]
