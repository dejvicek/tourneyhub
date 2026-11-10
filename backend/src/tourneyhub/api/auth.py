from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Cookie, Response
from fastapi.responses import JSONResponse

from tourneyhub.api.deps import (
    CustomHeaderDep,
    LoginThrottleDep,
    NowDep,
    SessionDep,
    SettingsDep,
)
from tourneyhub.api.errors import error_response
from tourneyhub.api.schemas import ErrorResponse, LoginRequest, ResponseModel
from tourneyhub.errors import ErrorCode
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
    "/login",
    responses={
        HTTPStatus.UNAUTHORIZED: {"model": ErrorResponse},
        HTTPStatus.TOO_MANY_REQUESTS: {
            "model": ErrorResponse,
            "headers": {
                "Retry-After": {
                    "description": "Seconds until the next attempt is checked.",
                    "schema": {"type": "integer"},
                }
            },
        },
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
