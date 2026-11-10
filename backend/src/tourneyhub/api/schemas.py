from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    JsonValue,
    SecretStr,
    StringConstraints,
)

from tourneyhub.engine.accounts import Language
from tourneyhub.errors import ErrorCode
from tourneyhub.services.instance import SIGNUP_CODE_MAX_LENGTH


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)


type LeagueName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


# NIST SP 800-63B-4 asks 15 characters for a password used alone (ADR-006). FR-002
# says 12; the PRD team decides, and this is the only place that changes. The
# maximum bounds the Argon2 input; ADR-006's 64 is an open question.
MIN_PASSWORD_LENGTH = 15
MAX_PASSWORD_LENGTH = 1024

type NewPassword = Annotated[
    SecretStr,
    StringConstraints(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH),
]
type DisplayName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
# No email-validator dependency: one @, no spaces, a dot in the domain.
type Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$",
    ),
]


class LoginRequest(RequestModel):
    """An email and a password; `throttle_login` reads it too (ADR-006)."""

    email: Annotated[str, StringConstraints(max_length=320)]
    password: Annotated[SecretStr, StringConstraints(max_length=1024)]


class SignUpRequest(RequestModel):
    """A new account and the instance's sign-up code (FR-001); the throttle reads it."""

    signup_code: Annotated[
        SecretStr, StringConstraints(max_length=SIGNUP_CODE_MAX_LENGTH)
    ]
    email: Email
    display_name: DisplayName
    password: NewPassword
    language: Language = Language.EN


class ErrorResponse(ResponseModel):
    """The body of every error response (ADR-008)."""

    code: ErrorCode
    detail: dict[str, JsonValue]
