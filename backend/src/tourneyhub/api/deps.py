import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session, sessionmaker

from tourneyhub.api.schemas import LoginRequest
from tourneyhub.db.models.accounts import User
from tourneyhub.errors import ErrorCode, ForbiddenError, NotAuthenticatedError
from tourneyhub.services import accounts as account_service
from tourneyhub.services import auth as auth_service
from tourneyhub.settings import Settings


def get_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory.begin() as session:  # commits, or rolls back on an exception
        yield session


# scope="function" runs the commit before the response is sent.
SessionDep = Annotated[Session, Depends(get_session, scope="function")]


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_now() -> datetime:
    return datetime.now(UTC)


NowDep = Annotated[datetime, Depends(get_now)]


def get_current_user_id(x_user_id: Annotated[UUID | None, Header()] = None) -> UUID:
    """Placeholder for `CurrentUserDep` until authentication exists (ADR-006)."""
    if x_user_id is None:
        raise NotAuthenticatedError(ErrorCode.NOT_AUTHENTICATED)
    return x_user_id


CurrentUserIdDep = Annotated[UUID, Depends(get_current_user_id)]


def get_current_user(session: SessionDep, user_id: CurrentUserIdDep) -> User:
    return account_service.load_current_user(session, user_id=user_id)


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def get_admin(user: CurrentUserDep) -> User:
    """The admin flag is read from the user row, never from the token (ADR-007)."""
    if not user.is_admin:
        raise ForbiddenError(ErrorCode.FORBIDDEN)
    return user


AdminDep = Annotated[User, Depends(get_admin)]


def _client_ip(request: Request) -> str:
    # uvicorn sets request.client from X-Forwarded-For, trusted only from Caddy.
    return request.client.host if request.client else ""


def throttle_login(request: Request, body: LoginRequest, now: NowDep) -> None:
    """Delay a login after repeated failures (ADR-006), holding no connection."""
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory.begin() as session:  # a short transaction of its own
        delay = auth_service.login_delay(
            session, email=body.email, ip=_client_ip(request), now=now
        )
    time.sleep(delay.total_seconds())  # its connection is back in the pool


LoginThrottleDep = Annotated[None, Depends(throttle_login)]
