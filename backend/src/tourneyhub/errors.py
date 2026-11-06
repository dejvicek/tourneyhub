from enum import StrEnum

from pydantic import JsonValue


class ErrorCode(StrEnum):
    """Every stable error code of the API (ADR-008)."""

    # Framework errors
    VALIDATION_FAILED = "validation_failed"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    BAD_REQUEST = "bad_request"
    INTERNAL_ERROR = "internal_error"
    # Authentication
    TOKEN_EXPIRED = "token_expired"
    NOT_AUTHENTICATED = "not_authenticated"
    PASSWORD_CHANGE_REQUIRED = "password_change_required"
    FORBIDDEN = "forbidden"
    # Leagues
    LEAGUE_NOT_FOUND = "league_not_found"
    LEAGUE_ID_TAKEN = "league_id_taken"
    LEAGUE_NAME_CHANGED = "league_name_changed"
    LEAGUE_NOT_ACTIVE = "league_not_active"


class AppError(Exception):
    """An error the API reports as {"code": ..., "detail": ...} (ADR-008)."""

    def __init__(self, code: ErrorCode, **detail: JsonValue) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


class NotAuthenticatedError(AppError):
    """No valid access token (HTTP 401)."""


class ForbiddenError(AppError):
    """Not allowed (HTTP 403)."""


class NotFoundError(AppError):
    """Unknown id, or one from another organizer's league (HTTP 404)."""


class ConflictError(AppError):
    """The expected state did not match, or a client id is taken (HTTP 409)."""


class RuleViolationError(AppError):
    """A business rule refused the request (HTTP 422)."""
