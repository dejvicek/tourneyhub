from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    JsonValue,
    SecretStr,
    StringConstraints,
)

from tourneyhub.errors import ErrorCode


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)


type LeagueName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class LoginRequest(RequestModel):
    """An email and a password; `throttle_login` reads it too (ADR-006)."""

    email: Annotated[str, StringConstraints(max_length=320)]
    password: Annotated[SecretStr, StringConstraints(max_length=1024)]


class ErrorResponse(ResponseModel):
    """The body of every error response (ADR-008)."""

    code: ErrorCode
    detail: dict[str, JsonValue]
