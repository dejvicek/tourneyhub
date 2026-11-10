from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Cookie, Response
from fastapi.responses import JSONResponse
from pydantic import SecretStr, StringConstraints

from tourneyhub.api.deps import (
    AccessClaimsDep,
    AccountDep,
    CustomHeaderDep,
    LoginThrottleDep,
    NowDep,
    PasswordChangeThrottleDep,
    SessionDep,
    SettingsDep,
    SignUpThrottleDep,
)
from tourneyhub.api.errors import error_response
from tourneyhub.api.schemas import (
    ErrorResponse,
    LoginRequest,
    NewPassword,
    RequestModel,
    ResponseModel,
    SignUpRequest,
)
from tourneyhub.errors import ErrorCode
from tourneyhub.services import accounts as account_service
from tourneyhub.services import auth as auth_service
from tourneyhub.settings import Settings

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
# The routes of this router, under the app's /api/v1 (ADR-006).
_REFRESH_COOKIE_PATH = "/api/v1/auth"

# The browser sends the cookie; the SPA never reads it (HttpOnly).
RefreshCookie = Annotated[str | None, Cookie(max_length=128)]


class AccessTokenRead(ResponseModel):
    """An access token for `Authorization: Bearer`, valid 15 minutes (ADR-006).

    The SPA keeps it in memory only; the refresh token comes as a cookie.
    """

    access_token: str


class PasswordChange(RequestModel):
    """The current password and the new one (FR-004)."""

    current_password: Annotated[SecretStr, StringConstraints(max_length=1024)]
    new_password: NewPassword


_TOO_MANY_ATTEMPTS = {
    "model": ErrorResponse,
    "headers": {
        "Retry-After": {
            "description": "Seconds until the next attempt is checked.",
            "schema": {"type": "integer"},
        }
    },
}


def _set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=int(auth_service.REFRESH_TOKEN_LIFETIME.total_seconds()),
        path=_REFRESH_COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )


@router.post(
    "/signup",
    status_code=HTTPStatus.CREATED,
    responses={
        HTTPStatus.CONFLICT: {"model": ErrorResponse},
        HTTPStatus.TOO_MANY_REQUESTS: _TOO_MANY_ATTEMPTS,
    },
)
def sign_up(
    attempt: SignUpThrottleDep,
    body: SignUpRequest,
    session: SessionDep,
    settings: SettingsDep,
    now: NowDep,
    response: Response,
) -> AccessTokenRead:
    """Create an organizer's account with the instance's sign-up code, logged in.

    422 `invalid_signup_code` means a wrong code or closed sign-up; 422
    `email_taken` an email that has an account, in any letter case. After
    repeated failures an attempt within a growing waiting period gets 429 with
    `Retry-After`. The tokens are those of a login.
    """
    tokens = account_service.sign_up(
        session,
        attempt=attempt,
        signup_code=body.signup_code.get_secret_value(),
        email=body.email,
        display_name=body.display_name,
        password=body.password.get_secret_value(),
        language=body.language,
        key=settings.jwt_secret,
        now=now,
    )
    _set_refresh_cookie(response, tokens.refresh_token, settings)
    return AccessTokenRead(access_token=tokens.access_token)


@router.post(
    "/login",
    responses={
        HTTPStatus.UNAUTHORIZED: {"model": ErrorResponse},
        HTTPStatus.TOO_MANY_REQUESTS: _TOO_MANY_ATTEMPTS,
    },
)
def log_in(
    attempt: LoginThrottleDep,
    body: LoginRequest,
    session: SessionDep,
    settings: SettingsDep,
    now: NowDep,
    response: Response,
) -> AccessTokenRead:
    """Log in with email and password and start a login on this device.

    A wrong password and an unknown email get the same 401. After repeated
    failures, an attempt within a growing waiting period gets 429 with
    `Retry-After`; nothing is locked.
    """
    tokens = auth_service.log_in(
        session,
        attempt=attempt,
        email=body.email,
        password=body.password.get_secret_value(),
        key=settings.jwt_secret,
        now=now,
    )
    _set_refresh_cookie(response, tokens.refresh_token, settings)
    return AccessTokenRead(access_token=tokens.access_token)


@router.post(
    "/refresh",
    response_model=AccessTokenRead,
    responses={HTTPStatus.UNAUTHORIZED: {"model": ErrorResponse}},
)
def refresh(
    _custom_header: CustomHeaderDep,
    session: SessionDep,
    settings: SettingsDep,
    now: NowDep,
    response: Response,
    refresh_token: RefreshCookie = None,
) -> AccessTokenRead | JSONResponse:
    """Exchange the refresh cookie for a new access token and a new cookie.

    A 401 means: log in again.
    """
    tokens = auth_service.refresh_session(
        session, refresh_token=refresh_token, key=settings.jwt_secret, now=now
    )
    if tokens is None:
        # Reuse: the family was revoked. Returned, not raised, so that the
        # transaction commits the revocation (ADR-001, ADR-006).
        return error_response(HTTPStatus.UNAUTHORIZED, ErrorCode.NOT_AUTHENTICATED)
    _set_refresh_cookie(response, tokens.refresh_token, settings)
    return AccessTokenRead(access_token=tokens.access_token)


@router.post("/logout", status_code=HTTPStatus.NO_CONTENT)
def log_out(
    _custom_header: CustomHeaderDep,
    session: SessionDep,
    settings: SettingsDep,
    now: NowDep,
    response: Response,
    refresh_token: RefreshCookie = None,
) -> None:
    """End this device's login and remove the cookie; repeating it is harmless."""
    auth_service.log_out(session, refresh_token=refresh_token, now=now)
    response.delete_cookie(
        REFRESH_COOKIE,
        path=_REFRESH_COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )


@router.post(
    "/password",
    status_code=HTTPStatus.NO_CONTENT,
    responses={
        HTTPStatus.UNAUTHORIZED: {"model": ErrorResponse},
        HTTPStatus.TOO_MANY_REQUESTS: _TOO_MANY_ATTEMPTS,
    },
)
def change_password(
    attempt: PasswordChangeThrottleDep,
    claims: AccessClaimsDep,
    user: AccountDep,
    body: PasswordChange,
    session: SessionDep,
    now: NowDep,
) -> None:
    """Change the password and log out every other device (FR-004, ADR-006).

    Works while an admin reset requires a new password, and then ends that
    requirement. The login this call came from stays. 422 `wrong_password` is a
    wrong current password; 422 `password_unchanged` a new one equal to it. The
    current password is checked on the login's budget: after repeated failures,
    here or at login, an attempt within a growing waiting period gets 429 with
    `Retry-After`.
    """
    account_service.change_password(
        session,
        attempt=attempt,
        user=user,
        keep_family_id=claims.family_id,
        current_password=body.current_password.get_secret_value(),
        new_password=body.new_password.get_secret_value(),
        now=now,
    )
