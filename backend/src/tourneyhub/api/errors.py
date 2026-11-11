import logging
from http import HTTPStatus
from typing import cast

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import JsonValue
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from tourneyhub.errors import (
    AppError,
    ConflictError,
    ErrorCode,
    ForbiddenError,
    NotAuthenticatedError,
    NotFoundError,
    RuleViolationError,
    TooManyAttemptsError,
)

logger = logging.getLogger(__name__)

_STATUS_BY_ERROR: dict[type[AppError], HTTPStatus] = {
    NotAuthenticatedError: HTTPStatus.UNAUTHORIZED,
    ForbiddenError: HTTPStatus.FORBIDDEN,
    NotFoundError: HTTPStatus.NOT_FOUND,
    ConflictError: HTTPStatus.CONFLICT,
    RuleViolationError: HTTPStatus.UNPROCESSABLE_CONTENT,
    TooManyAttemptsError: HTTPStatus.TOO_MANY_REQUESTS,
}

# Constraint name -> the 409 code of a violation (DATA-MODEL §2). Only constraints
# that a race can reach belong here: creating a league locks nothing, and the league
# locks of two leagues do not exclude each other (§4.4).
_CONFLICT_BY_CONSTRAINT: dict[str, ErrorCode] = {
    "pk_leagues": ErrorCode.LEAGUE_ID_TAKEN,
    # One client id sent to two leagues of one organizer: each holds its own league
    # lock, and the lookup of the id before the insert saw neither row.
    "pk_tournaments": ErrorCode.TOURNAMENT_ID_TAKEN,
    # Two parallel sign-ups with one email: the check before the insert saw neither.
    "uq_users_lower_email": ErrorCode.EMAIL_TAKEN,
    # Adding or renaming to a name that another request is inserting at the same time.
    "uq_players_league_id_lower_name": ErrorCode.PLAYER_NAME_TAKEN,
}


def error_response(
    status: HTTPStatus,
    code: ErrorCode,
    detail: dict[str, JsonValue] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code.value, "detail": detail or {}},
        headers=headers,
    )


async def handle_app_error(_request: Request, exc: Exception) -> JSONResponse:
    # cast: Starlette types every handler as taking Exception; it passes the
    # class this handler was registered for.
    error = cast("AppError", exc)
    status = next(
        (
            status
            for error_type, status in _STATUS_BY_ERROR.items()
            if isinstance(error, error_type)
        ),
        HTTPStatus.INTERNAL_SERVER_ERROR,
    )
    headers = None
    if isinstance(error, TooManyAttemptsError):
        headers = {"Retry-After": str(error.retry_after)}
    return error_response(status, error.code, error.detail, headers)


async def handle_validation_error(_request: Request, exc: Exception) -> JSONResponse:
    # cast: see handle_app_error.
    error = cast("RequestValidationError", exc)
    problems: list[JsonValue] = []
    for item in error.errors():
        numeric_ctx: dict[str, JsonValue] = {
            key: value
            for key, value in item.get("ctx", {}).items()
            if isinstance(value, int | float) and not isinstance(value, bool)
        }
        problem: JsonValue = {
            "loc": list(item["loc"]),
            "type": item["type"],
        } | numeric_ctx
        # A body that a dependency reads too, such as a throttle's, is reported
        # once by each.
        if problem not in problems:
            problems.append(problem)
    return error_response(
        HTTPStatus.UNPROCESSABLE_CONTENT,
        ErrorCode.VALIDATION_FAILED,
        {"errors": problems},
    )


async def handle_http_exception(_request: Request, exc: Exception) -> JSONResponse:
    # cast: see handle_app_error.
    error = cast("StarletteHTTPException", exc)
    codes: dict[int, ErrorCode] = {
        HTTPStatus.NOT_FOUND: ErrorCode.NOT_FOUND,
        HTTPStatus.METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
    }
    code = codes.get(error.status_code, ErrorCode.BAD_REQUEST)
    return error_response(
        HTTPStatus(error.status_code), code, headers=dict(error.headers or {})
    )


async def handle_integrity_error(_request: Request, exc: Exception) -> JSONResponse:
    # cast: see handle_app_error.
    error = cast("IntegrityError", exc)
    constraint = None
    if isinstance(error.orig, psycopg.Error):
        constraint = error.orig.diag.constraint_name
    code = _CONFLICT_BY_CONSTRAINT.get(constraint or "")
    if code is None:
        logger.error(
            "unexpected constraint violation",
            extra={"constraint": constraint},
            exc_info=error,
        )
        return error_response(
            HTTPStatus.INTERNAL_SERVER_ERROR, ErrorCode.INTERNAL_ERROR
        )
    return error_response(HTTPStatus.CONFLICT, code)


async def handle_unexpected_error(_request: Request, _exc: Exception) -> JSONResponse:
    # Not logged here: Starlette re-raises the exception after this response, and
    # uvicorn logs it with its traceback (§4.4).
    return error_response(HTTPStatus.INTERNAL_SERVER_ERROR, ErrorCode.INTERNAL_ERROR)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(IntegrityError, handle_integrity_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
