from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import AuthAttempt, User
from tourneyhub.engine.auth import AuthAttemptKind
from tourneyhub.errors import ErrorCode, NotAuthenticatedError

_WINDOW = timedelta(minutes=15)
_FREE_FAILURES = 3
_MAX_DELAY = timedelta(seconds=8)


def login_delay(session: Session, *, email: str, ip: str, now: datetime) -> timedelta:
    """Return how long a login waits before it is checked (ADR-006).

    Failures in the window are counted per email and per client IP. Beyond the
    free ones, each failure doubles the delay up to a maximum; the account is
    never locked.
    """
    failures = max(
        _count_failures(
            session, kind=AuthAttemptKind.LOGIN_EMAIL, key=email.lower(), now=now
        ),
        _count_failures(session, kind=AuthAttemptKind.LOGIN_IP, key=ip, now=now),
    )
    if failures < _FREE_FAILURES:
        return timedelta(0)
    return min(timedelta(seconds=2 ** (failures - _FREE_FAILURES)), _MAX_DELAY)


def _count_failures(
    session: Session, *, kind: AuthAttemptKind, key: str, now: datetime
) -> int:
    count = session.scalar(
        select(func.count())
        .select_from(AuthAttempt)
        .where(
            AuthAttempt.kind == kind,
            AuthAttempt.key == key,
            AuthAttempt.succeeded.is_(False),
            AuthAttempt.created_at > now - _WINDOW,
        )
    )
    return count or 0


def record_login_attempt(
    session: Session, *, email: str, ip: str, succeeded: bool, now: datetime
) -> None:
    """Count one login attempt per email and per client IP (ADR-006)."""
    session.add_all(
        [
            AuthAttempt(
                kind=AuthAttemptKind.LOGIN_EMAIL,
                key=email.lower(),
                succeeded=succeeded,
                created_at=now,
            ),
            AuthAttempt(
                kind=AuthAttemptKind.LOGIN_IP,
                key=ip,
                succeeded=succeeded,
                created_at=now,
            ),
        ]
    )
    session.flush()


def log_in(session: Session, *, email: str) -> User:
    """Return the account for `email`.

    A placeholder: it checks only that the account exists. The password check and
    the tokens come with authentication (ADR-006).
    """
    user = session.scalars(
        select(User).where(func.lower(User.email) == email.lower())
    ).one_or_none()
    if user is None:
        raise NotAuthenticatedError(ErrorCode.NOT_AUTHENTICATED)
    return user
