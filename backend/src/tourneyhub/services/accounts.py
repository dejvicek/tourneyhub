from uuid import UUID

from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import User
from tourneyhub.errors import ErrorCode, ForbiddenError, NotAuthenticatedError


def load_current_user(session: Session, *, user_id: UUID) -> User:
    """Load the caller's row, which authorization reads on every request (ADR-006).

    While `must_change_password` is set, only the auth routes and `GET /me` work.
    """
    user = session.get(User, user_id)
    if user is None:
        raise NotAuthenticatedError(ErrorCode.NOT_AUTHENTICATED)
    if user.must_change_password:
        raise ForbiddenError(ErrorCode.PASSWORD_CHANGE_REQUIRED)
    return user
