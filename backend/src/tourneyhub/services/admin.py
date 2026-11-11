import secrets
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import AdminAction, InstanceSettings, User
from tourneyhub.engine.accounts import Language
from tourneyhub.engine.admin import AdminActionKind, AdminActionSource
from tourneyhub.errors import ErrorCode, NotFoundError, RuleViolationError
from tourneyhub.services import auth as auth_service
from tourneyhub.services import instance as instance_service

# 24 URL-safe characters, 144 bits; the password rule asks for 15 (ADR-006).
_GENERATED_PASSWORD_BYTES = 18


def record_action(
    session: Session,
    *,
    source: AdminActionSource,
    action: AdminActionKind,
    admin_user_id: UUID | None,
    target_user_id: UUID | None,
    now: datetime,
) -> None:
    """Record an admin action in the request's transaction (ADR-007).

    The row commits or rolls back with the action itself. It never holds the
    sign-up code or a password.
    """
    session.add(
        AdminAction(
            source=source,
            action=action,
            admin_user_id=admin_user_id,
            target_user_id=target_user_id,
            created_at=now,
        )
    )


def get_signup_settings(session: Session) -> InstanceSettings:
    """The sign-up code and when it last changed; the admin may see it (ADR-007)."""
    return instance_service.read_signup_code(session)


def set_signup_code(
    session: Session,
    *,
    source: AdminActionSource,
    admin_user_id: UUID | None,
    code: str | None,
    now: datetime,
) -> bool:
    """Set, change or clear the sign-up code, and record it (FR-005, ADR-007).

    Setting and clearing are one action, `set_signup_code`, without a target; the
    code itself is not recorded. A call that leaves the code as it was, such as
    closing sign-up that is closed, changes nothing and records nothing; the
    result says whether the code changed.
    """
    if not instance_service.set_signup_code(session, code=code, now=now):
        return False
    record_action(
        session,
        source=source,
        action=AdminActionKind.SET_SIGNUP_CODE,
        admin_user_id=admin_user_id,
        target_user_id=None,
        now=now,
    )
    return True


def generate_signup_code(
    session: Session, *, admin_user_id: UUID, now: datetime
) -> str:
    """Store a random sign-up code made here and return it (ADR-007)."""
    code = instance_service.generate_signup_code()
    set_signup_code(
        session,
        source=AdminActionSource.WEB,
        admin_user_id=admin_user_id,
        code=code,
        now=now,
    )
    return code


def list_organizers(session: Session) -> Sequence[User]:
    """Every account by email, admins too: an admin can be an organizer (ADR-007)."""
    return session.scalars(select(User).order_by(func.lower(User.email), User.id)).all()


def reset_password(
    session: Session,
    *,
    admin: User,
    user_id: UUID,
    temporary_password: str | None,
    now: datetime,
) -> str | None:
    """Give an account a temporary password and end its logins (FR-006, ADR-006).

    Every refresh family of the account is revoked and `must_change_password`
    is set, so its next login must choose a new password before anything else.
    With no `temporary_password` a random one is made and returned, to be shown
    once; a password the admin typed is not returned. The admin's own account is
    refused (`own_account`): it would revoke the admin's own login. Another
    admin's account is refused too (`admin_target`): a stolen admin session could
    otherwise take over every other admin, so admins are handled with the CLI.
    """
    if user_id == admin.id:
        raise RuleViolationError(ErrorCode.OWN_ACCOUNT)
    # NO KEY UPDATE, as in `change_password`: it waits for a change under way, and
    # a login that verified the old hash meanwhile is refused (see `log_in`).
    target = session.scalars(
        select(User)
        .where(User.id == user_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    ).one_or_none()
    if target is None:
        raise NotFoundError(ErrorCode.USER_NOT_FOUND)
    if target.is_admin:
        raise RuleViolationError(ErrorCode.ADMIN_TARGET)
    if temporary_password is None:
        password = generated = secrets.token_urlsafe(_GENERATED_PASSWORD_BYTES)
    else:
        password, generated = temporary_password, None
    target.password_hash = auth_service.hash_password(password)
    target.must_change_password = True
    target.updated_at = now
    auth_service.revoke_all_families(session, user_id=target.id, now=now)
    record_action(
        session,
        source=AdminActionSource.WEB,
        action=AdminActionKind.RESET_PASSWORD,
        admin_user_id=admin.id,
        target_user_id=target.id,
        now=now,
    )
    return generated


def create_admin(
    session: Session,
    *,
    email: str,
    display_name: str,
    password: str,
    language: Language,
    now: datetime,
) -> User | None:
    """Create an account with the admin flag, from the CLI only (ADR-007).

    Returns None when the email already has an account (any letter case): the
    caller points to `grant-admin`.
    """
    taken = session.scalar(
        select(User.id).where(func.lower(User.email) == func.lower(email))
    )
    if taken is not None:
        return None
    user = User(
        email=email,
        display_name=display_name,
        password_hash=auth_service.hash_password(password),
        is_admin=True,
        language=language,
        created_at=now,
    )
    session.add(user)
    session.flush()
    record_action(
        session,
        source=AdminActionSource.CLI,
        action=AdminActionKind.CREATE_ADMIN,
        admin_user_id=None,
        target_user_id=user.id,
        now=now,
    )
    return user


def set_admin_flag(
    session: Session, *, email: str, is_admin: bool, now: datetime
) -> bool | None:
    """Grant or revoke the admin flag, from the CLI only (ADR-007).

    Returns None for an unknown email, False when the flag already had that value
    (nothing changed, so nothing is recorded), True when it was changed and
    recorded. The flag is read from the row on every request, so it takes effect
    at once (ADR-006).
    """
    user = session.scalars(
        select(User)
        .where(func.lower(User.email) == func.lower(email))
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    ).one_or_none()
    if user is None:
        return None
    if user.is_admin == is_admin:
        return False
    user.is_admin = is_admin
    user.updated_at = now
    record_action(
        session,
        source=AdminActionSource.CLI,
        action=AdminActionKind.GRANT_ADMIN
        if is_admin
        else AdminActionKind.REVOKE_ADMIN,
        admin_user_id=None,
        target_user_id=user.id,
        now=now,
    )
    return True
