from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, sessionmaker

from tourneyhub.api.schemas import LoginRequest, SignUpRequest
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


def get_session_factory(request: Request) -> sessionmaker[Session]:
    """For the short transactions of their own that the auth dependencies open."""
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    return session_factory


SessionFactoryDep = Annotated[sessionmaker[Session], Depends(get_session_factory)]


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_now() -> datetime:
    return datetime.now(UTC)


NowDep = Annotated[datetime, Depends(get_now)]

type Clock = Callable[[], datetime]


def get_clock() -> Clock:
    """The clock to read after a lock is held, so that stamps follow commit order."""
    return lambda: datetime.now(UTC)


# NowDep is read before the request waits for a lock; ClockDep is read after it.
ClockDep = Annotated[Clock, Depends(get_clock)]


# auto_error=False: a missing token gets our own 401 code, not FastAPI's English.
_bearer = HTTPBearer(auto_error=False)
BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def get_access_claims(
    credentials: BearerDep, settings: SettingsDep, now: NowDep
) -> auth_service.AccessClaims:
    """Check the access token: signature and expiry, no query (ADR-006)."""
    if credentials is None:
        raise NotAuthenticatedError(ErrorCode.NOT_AUTHENTICATED)
    return auth_service.read_access_token(
        credentials.credentials, key=settings.jwt_secret, now=now
    )


AccessClaimsDep = Annotated[auth_service.AccessClaims, Depends(get_access_claims)]


def get_account(claims: AccessClaimsDep, session: SessionDep) -> User:
    """Load the caller's row from the user id in the access token (ADR-006).

    The token's refresh-token family must still be live: after a reset, a logout
    or a password change elsewhere the token is refused at once, with the answer
    for an expired token, so the SPA refreshes once and then logs out.

    For the routes that work while `must_change_password` is set: the password
    change and `GET /me`. The other routes use `CurrentUserDep`.
    """
    user = account_service.load_user(session, user_id=claims.user_id)
    auth_service.require_live_family(session, claims=claims)
    return user


AccountDep = Annotated[User, Depends(get_account)]


def get_current_user(user: AccountDep) -> User:
    """The caller's row, unless an admin reset still requires a new password."""
    if user.must_change_password:
        raise ForbiddenError(ErrorCode.PASSWORD_CHANGE_REQUIRED)
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def get_admin(user: CurrentUserDep) -> User:
    """The admin flag is read from the user row, never from the token (ADR-007)."""
    if not user.is_admin:
        raise ForbiddenError(ErrorCode.FORBIDDEN)
    return user


AdminDep = Annotated[User, Depends(get_admin)]


def get_client_ip(request: Request) -> str:
    # uvicorn sets request.client from X-Forwarded-For, trusted only from Caddy.
    return request.client.host if request.client else ""


ClientIpDep = Annotated[str, Depends(get_client_ip)]


def throttle_login(
    session_factory: SessionFactoryDep,
    body: LoginRequest,
    client_ip: ClientIpDep,
    now: NowDep,
) -> auth_service.Attempt:
    """Count a login before its password is checked, or refuse it (ADR-006).

    A short transaction of its own commits the attempt at once: parallel
    attempts see it, and it stays counted as a failure when the login's own
    transaction rolls back with its 401. An attempt inside the waiting period
    gets 429 `too_many_attempts`; nothing sleeps.
    """
    with session_factory.begin() as session:
        return auth_service.start_login_attempt(
            session, email=body.email, ip=client_ip, now=now
        )


LoginThrottleDep = Annotated[auth_service.Attempt, Depends(throttle_login)]


def throttle_signup(
    session_factory: SessionFactoryDep,
    # Unused: a body that fails validation is refused before it is counted.
    body: SignUpRequest,  # noqa: ARG001
    client_ip: ClientIpDep,
    now: NowDep,
) -> auth_service.Attempt:
    """Count a sign-up before its code is checked, or refuse it (ADR-006).

    As `throttle_login`: a short transaction of its own, 429 inside the waiting
    period, nothing sleeps.
    """
    with session_factory.begin() as session:
        return auth_service.start_signup_attempt(session, ip=client_ip, now=now)


SignUpThrottleDep = Annotated[auth_service.Attempt, Depends(throttle_signup)]


def throttle_password_change(
    session_factory: SessionFactoryDep,
    claims: AccessClaimsDep,
    client_ip: ClientIpDep,
    now: NowDep,
) -> auth_service.Attempt:
    """Count a password change before its current password is checked (ADR-006).

    On the login's budget, per email and per client IP, as `throttle_login`: a
    short transaction of its own, 429 inside the waiting period, nothing sleeps.
    """
    with session_factory.begin() as session:
        return account_service.start_password_change_attempt(
            session, user_id=claims.user_id, ip=client_ip, now=now
        )


PasswordChangeThrottleDep = Annotated[
    auth_service.Attempt, Depends(throttle_password_change)
]


def require_custom_header(
    _x_requested_with: Annotated[str, Header(alias="X-Requested-With", max_length=64)],
) -> None:
    """Refuse a cookie-authenticated call that a cross-site form could send.

    Browsers never add a custom header to a cross-site form, and without CORS a
    cross-site script cannot send one (ADR-005, ADR-006). Its value is not read.
    """


CustomHeaderDep = Annotated[None, Depends(require_custom_header)]
