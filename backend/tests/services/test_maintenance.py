from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import uuid7

from sqlalchemy import select
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import AuthAttempt, RefreshToken, User
from tourneyhub.engine.auth import AuthAttemptKind
from tourneyhub.services import auth as auth_service
from tourneyhub.services import maintenance


def _token(
    session: Session,
    user: User,
    now: datetime,
    *,
    expires_in: timedelta = timedelta(days=90),
    rotated: bool = False,
    revoked: bool = False,
) -> RefreshToken:
    token = RefreshToken(
        user_id=user.id,
        family_id=uuid7(),
        token_hash=uuid7().bytes,
        expires_at=now + expires_in,
        rotated_at=now - timedelta(days=1) if rotated else None,
        revoked_at=now - timedelta(days=1) if revoked else None,
        created_at=now - timedelta(days=1),
    )
    session.add(token)
    session.flush()
    return token


def _attempt(session: Session, created_at: datetime) -> AuthAttempt:
    attempt = AuthAttempt(
        kind=AuthAttemptKind.LOGIN_IP,
        key="192.0.2.1",
        succeeded=False,
        created_at=created_at,
    )
    session.add(attempt)
    session.flush()
    return attempt


def test_adr006_cleanup_deletes_expired_and_revoked_refresh_tokens(
    session: Session, make_user: Callable[..., User], now: datetime
) -> None:
    user = make_user()
    expired = _token(session, user, now, expires_in=timedelta(seconds=-1))
    expiring_now = _token(session, user, now, expires_in=timedelta(0))
    revoked = _token(session, user, now, revoked=True)
    unrotated = _token(session, user, now)
    rotated = _token(session, user, now, rotated=True)
    expiring_soon = _token(session, user, now, expires_in=timedelta(seconds=1))

    result = maintenance.clean_up(session, now=now)

    assert result.refresh_tokens == 3
    session.expire_all()
    left = set(session.scalars(select(RefreshToken.id)))
    assert left == {unrotated.id, rotated.id, expiring_soon.id}
    assert {expired.id, expiring_now.id, revoked.id}.isdisjoint(left)


def test_adr006_cleanup_keeps_a_rotated_token_because_reuse_detection_needs_it(
    session: Session, make_user: Callable[..., User], now: datetime
) -> None:
    rotated = _token(session, make_user(), now, rotated=True)

    maintenance.clean_up(session, now=now)

    assert session.get(RefreshToken, rotated.id) is not None


def test_adr006_cleanup_deletes_attempts_older_than_the_longest_throttle_window(
    session: Session, now: datetime
) -> None:
    retention = auth_service.ATTEMPT_RETENTION
    old = _attempt(session, now - retention - timedelta(seconds=1))
    on_the_edge = _attempt(session, now - retention)
    recent = _attempt(session, now - timedelta(minutes=1))

    result = maintenance.clean_up(session, now=now)

    assert result.auth_attempts == 1
    session.expire_all()
    assert set(session.scalars(select(AuthAttempt.id))) == {on_the_edge.id, recent.id}
    assert old.id not in {on_the_edge.id, recent.id}


def test_adr006_the_retention_covers_the_longest_window_of_any_throttle() -> None:
    assert timedelta(hours=1) == auth_service.ATTEMPT_RETENTION


def test_adr006_cleanup_of_a_clean_database_deletes_nothing(
    session: Session, now: datetime
) -> None:
    result = maintenance.clean_up(session, now=now)

    assert (result.refresh_tokens, result.auth_attempts) == (0, 0)
