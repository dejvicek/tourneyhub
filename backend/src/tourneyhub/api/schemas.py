import unicodedata
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SecretStr,
    StringConstraints,
)
from pydantic_core import PydanticCustomError

from tourneyhub.engine.accounts import Language
from tourneyhub.engine.leagues import first_increase
from tourneyhub.errors import ErrorCode
from tourneyhub.services.instance import SIGNUP_CODE_MAX_LENGTH

# The largest value of a PostgreSQL int column (DATA-MODEL §2: scores and points).
INT_MAX = 2_147_483_647


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)


type LeagueName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]

type SeasonName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


def _check_non_increasing(points: list[int]) -> list[int]:
    index = first_increase(points)
    if index is not None:
        raise PydanticCustomError(
            "placement_points_increase",
            "place {place} is worth more than the place above it",
            {"place": index + 1},
        )
    return points


# FR-011, the rule of the database's placement_points_valid(): not empty, whole
# numbers, none negative, none worth more than the place above. At most 256
# places: the most entries a tournament is sized for (ADR-009).
type PlacementPoints = Annotated[
    list[Annotated[int, Field(ge=0, le=INT_MAX)]],
    Field(min_length=1, max_length=256),
    AfterValidator(_check_non_increasing),
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


def _reject_invisible_characters(name: str) -> str:
    """Refuse control, zero-width and other format characters (Unicode Cc, Cf).

    A name made of them looks empty, and one that contains them can look like
    another person's.
    """
    if any(unicodedata.category(char) in {"Cc", "Cf"} for char in name):
        raise PydanticCustomError(
            "invisible_characters", "the name contains invisible characters"
        )
    return name


type DisplayName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    AfterValidator(_reject_invisible_characters),
]
# A player's name looks like a person's: the same limits, and the same refusal of
# invisible characters, so that no two names look alike (BR-001).
type PlayerName = DisplayName
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
