from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import AuthAttempt, RefreshToken
from tourneyhub.services.auth import ATTEMPT_RETENTION


@dataclass(frozen=True, slots=True)
class CleanupResult:
    """How many rows `clean_up` deleted."""

    refresh_tokens: int
    auth_attempts: int


def clean_up(session: Session, *, now: datetime) -> CleanupResult:
    """Delete what can no longer matter (ADR-006, DATA-MODEL §4.1).

    Refresh tokens: an expired token gets 401, and so does a revoked one, as if
    it were unknown, so neither is needed for anything. Rotated tokens stay
    until they expire, because reuse detection needs them. A refresh that has
    read a deleted row finds it gone and answers 401.

    `auth_attempts`: rows older than the longest throttle window count for nothing.
    """
    tokens = session.scalars(
        delete(RefreshToken)
        .where(
            or_(RefreshToken.expires_at <= now, RefreshToken.revoked_at.is_not(None))
        )
        .returning(RefreshToken.id)
    ).all()
    attempts = session.scalars(
        delete(AuthAttempt)
        .where(AuthAttempt.created_at < now - ATTEMPT_RETENTION)
        .returning(AuthAttempt.id)
    ).all()
    return CleanupResult(refresh_tokens=len(tokens), auth_attempts=len(attempts))
